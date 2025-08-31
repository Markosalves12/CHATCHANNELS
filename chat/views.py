# chat/views.py
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from .models import  Message, UserProfile
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.db.models import Count, Q, Prefetch
from .utils import get_user_chat_rooms_data
from asgiref.sync import sync_to_async

@login_required
def chat_home(request):
    """Página inicial do chat - lista todas as salas disponíveis"""
    # Obter todas as salas públicas + salas privadas onde o usuário é membro
    chat_rooms = ChatRoom.objects.filter(
        Q(is_private=False) |
        Q(members=request.user) |
        Q(created_by=request.user)
    ).distinct()

    # Adicionar contagem de mensagens não lidas para cada sala
    rooms_with_unread = []
    for room in chat_rooms:
        unread_count = room.get_unread_count_for_user(request.user)
        rooms_with_unread.append({
            'room': room,
            'unread_count': unread_count
        })

    # Formulário para criar nova sala
    # form = CreateRoomForm()

    if request.method == 'POST':
        form = CreateRoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.created_by = request.user
            room.save()

            # Se for sala privada, adiciona o criador como membro
            if room.is_private:
                room.add_member(request.user, added_by=request.user)

            return redirect('chat_room', room_name=room.name)

    context = {
        'rooms_with_unread': rooms_with_unread,
        # 'form': form,
    }
    return render(request, 'chat/home.html', context)


@login_required
def chat_room(request, room_name):
    """Página da sala de chat específica com otimizações"""
    # Obter ou criar a sala com select_related para created_by
    room = get_object_or_404(
        ChatRoom.objects.select_related('created_by'),
        name=room_name
    )

    # Verificar acesso à sala
    if not room.can_user_access(request.user):
        messages.error(request, "Você não tem acesso a esta sala.")
        return redirect('chat_home')

    # Garantir que usuário seja membro em salas privadas
    if room.is_private and not room.members.filter(id=request.user.id).exists():
        room.add_member(request.user, added_by=room.created_by)
        messages.info(request, f"Você foi adicionado à sala {room_name}")

    # Pré-carregar relações para melhor performance
    messages_prefetch = Prefetch(
        'messages',
        queryset=Message.objects.select_related('author')
                 .prefetch_related('read_by')
                 .order_by('-timestamp')[:100],
        to_attr='recent_messages'
    )

    # Obter sala com mensagens recentes
    room_with_messages = ChatRoom.objects.filter(id=room.id) \
        .prefetch_related(messages_prefetch) \
        .first()

    # Processar mensagens com status de leitura
    messages_with_status = []
    unread_count = 0

    for message in getattr(room_with_messages, 'recent_messages', []):
        is_read_by_user = message.get_read_status_for_user(request.user)

        # Contar mensagens não lidas (apenas de outros usuários)
        if not is_read_by_user and message.author != request.user:
            unread_count += 1

        messages_with_status.append({
            'id': message.id,
            'content': message.content,
            'author': message.author,
            'timestamp': message.timestamp,
            'is_read_by_user': is_read_by_user,
            'read_count': message.read_by.count(),
        })

    # Reverter a ordem para mostrar as mais antigas primeiro
    messages_with_status.reverse()

    # Obter informações dos membros (apenas para salas privadas)
    room_members = []
    if room.is_private:
        room_members = room.members.select_related('userprofile').all()

    # Atualizar última atividade do usuário
    UserProfile.objects.update_or_create(
        user=request.user,
        defaults={'last_activity': timezone.now()}
    )

    # Estatísticas da sala (opcional)
    room_stats = {
        'total_messages': Message.objects.filter(room=room).count(),
        'active_today': Message.objects.filter(
            room=room,
            timestamp__date=timezone.now().date()
        ).count(),
        'members_count': room.members.count() + 1,  # +1 para o criador
    }

    context = {
        'room_name': room_name,
        'room': room,
        'messages': messages_with_status,
        'unread_count': unread_count,
        'room_members': room_members,
        'room_stats': room_stats,
        'is_room_creator': room.created_by == request.user,
        'user_is_member': room.members.filter(id=request.user.id).exists(),
        'now': timezone.now(),
    }

    return render(request, 'chat/room.html', context)


# Context Processor otimizado
def user_chat_rooms(request):
    """
    Context processor otimizado para salas do usuário
    """
    if not request.user.is_authenticated:
        return {'chat_rooms': []}

    # Obter salas com contagem de mensagens não lidas em uma única query
    rooms = ChatRoom.objects.filter(
        Q(members=request.user) | Q(created_by=request.user)
    ).distinct().annotate(
        unread_count=Count(
            'messages',
            filter=Q(
                messages__read_by__id__isnull=True,
                messages__author__id__ne=request.user.id
            ),
            distinct=True
        )
    ).values('name', 'is_private', 'unread_count')

    return {
        'chat_rooms': list(rooms)
    }


# View para marcar mensagens como lidas via AJAX
@login_required
def mark_room_as_read(request, room_name):
    """Marca todas as mensagens de uma sala como lidas"""
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        room = get_object_or_404(ChatRoom, name=room_name)

        if not room.can_user_access(request.user):
            return JsonResponse({'success': False, 'error': 'Acesso negado'}, status=403)

        # Marcar mensagens não lidas como lidas
        unread_messages = Message.objects.filter(
            room=room
        ).exclude(read_by=request.user).exclude(author=request.user)

        count = 0
        for message in unread_messages:
            message.mark_as_read(request.user)
            count += 1

        return JsonResponse({
            'success': True,
            'message': f'{count} mensagens marcadas como lidas',
            'count': count
        })

    return JsonResponse({'success': False, 'error': 'Método não permitido'}, status=405)


# View para obter estatísticas da sala via AJAX
@login_required
def room_stats(request, room_name):
    """Retorna estatísticas da sala em tempo real"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        room = get_object_or_404(ChatRoom, name=room_name)

        if not room.can_user_access(request.user):
            return JsonResponse({'error': 'Acesso negado'}, status=403)

        # Contagem de mensagens não lidas
        unread_count = Message.objects.filter(
            room=room
        ).exclude(read_by=request.user).exclude(author=request.user).count()

        # Última atividade
        last_activity = Message.objects.filter(room=room) \
            .order_by('-timestamp') \
            .values('timestamp', 'author__username') \
            .first()

        # Membros online (últimos 5 minutos)
        five_minutes_ago = timezone.now() - timezone.timedelta(minutes=5)
        online_members = UserProfile.objects.filter(
            last_activity__gte=five_minutes_ago,
            user__in=room.members.all()
        ).values('user__username', 'last_activity')

        return JsonResponse({
            'unread_count': unread_count,
            'last_activity': last_activity,
            'online_members': list(online_members),
            'total_members': room.members.count() + 1,  # +1 para o criador
        })

    return JsonResponse({'error': 'Requisição inválida'}, status=400)


# chat/views.py (atualizar a view create_room)
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from .forms import CreateRoomForm
from .models import ChatRoom
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


@login_required
def create_room(request):
    """Cria uma nova sala de chat com participantes"""
    if request.method == 'POST':
        form = CreateRoomForm(request.POST, request=request)
        if form.is_valid():
            try:
                room = form.save(commit=False)
                room.created_by = request.user
                room.save()

                # Obter participantes selecionados
                participants = form.cleaned_data.get('participants', [])
                added_count = 0

                # Obtém o usuário "System" para ser o autor da mensagem de notificação
                try:
                    system_user = User.objects.get(username='System')
                except User.DoesNotExist:
                    # Se não existir, podemos criar ou usar um fallback
                    system_user = request.user  # Fallback para o criador

                # Adicionar participantes (apenas para salas privadas)
                if room.is_private:
                    # Adicionar o criador primeiro
                    room.add_member(request.user, added_by=request.user)

                    # Adicionar participantes selecionados
                    for user in participants:
                        if not room.members.filter(id=user.id).exists():
                            room.add_member(user, added_by=request.user)
                            added_count += 1

                            # Cria uma mensagem de sistema para notificar na sala
                            notification_message = f"{request.user.username} adicionou {user.username} à sala."
                            Message.objects.create(
                                room=room,
                                author=system_user,
                                content=notification_message
                            )
                else:
                    # Mensagem de sistema para salas públicas
                    notification_message = f"{request.user.username} criou a sala."
                    Message.objects.create(
                        room=room,
                        author=system_user,
                        content=notification_message
                    )

                # Notifica todos os participantes (incluindo o criador)
                # para que eles atualizem sua barra lateral
                room_members = room.members.all()
                for member in room_members:
                    channel_layer = get_channel_layer()
                    user_group_name = f"user_{member.id}"

                    updated_room_data = get_user_chat_rooms_data(member)

                    async_to_sync(channel_layer.group_send)(
                        user_group_name,
                        {
                            "type": "unread.count.update",
                            "room_data": updated_room_data,
                        }
                    )

                # Mensagem de sucesso
                if room.is_private:
                    messages.success(
                        request,
                        f'Sala "{room.name}" criada com sucesso! {added_count} participante(s) adicionado(s).'
                    )
                else:
                    messages.success(request, f'Sala pública "{room.name}" criada com sucesso!')

                return redirect('chat_room', room_name=room.name)

            except Exception as e:
                messages.error(request, f'Erro ao criar sala: {str(e)}')
        else:
            messages.error(request, 'Por favor, corrija os erros no formulário.')
    else:
        form = CreateRoomForm(request=request)

    # Contar usuários disponíveis para adicionar
    total_users = User.objects.exclude(id=request.user.id).count()

    return render(request, 'chat/create_room.html', {
        'form': form,
        'total_users': total_users,
        'available_users': User.objects.exclude(id=request.user.id).order_by('username')[:50]
    })


@login_required
def room_members(request, room_name):
    """Retorna informações dos membros da sala"""
    room = get_object_or_404(ChatRoom, name=room_name)

    if not room.can_user_access(request.user):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    members_info = room.get_members_info()

    return JsonResponse({
        'room_name': room.name,
        'is_private': room.is_private,
        'created_by': room.created_by.username,
        'members': members_info,
        'total_members': len(members_info)
    })


@login_required
def get_available_users(request):
    """Retorna usuários disponíveis para adicionar à sala (API)"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        search_term = request.GET.get('q', '')

        users = User.objects.exclude(id=request.user.id).order_by('username')

        if search_term:
            users = users.filter(
                Q(username__icontains=search_term) |
                Q(email__icontains=search_term) |
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term)
            )

        users_data = [{
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': user.get_full_name() or user.username
        } for user in users[:20]]

        return JsonResponse({'users': users_data})

    return JsonResponse({'error': 'Requisição inválida'}, status=400)


@login_required
def add_member_to_room(request, room_name, username):
    """Adiciona um membro à sala privada"""
    room = get_object_or_404(ChatRoom, name=room_name)

    # Apenas o criador da sala pode adicionar membros
    if room.created_by != request.user:
        return HttpResponseForbidden("Apenas o criador da sala pode adicionar membros")

    user_to_add = get_object_or_404(User, username=username)

    # Verificar se usuário já é membro
    if room.members.filter(id=user_to_add.id).exists():
        return JsonResponse({
            'success': False,
            'message': 'Usuário já é membro desta sala'
        })

    # Adicionar membro
    room.add_member(user_to_add, added_by=request.user)

    return JsonResponse({
        'success': True,
        'message': f'Usuário {username} adicionado à sala'
    })


@login_required
def remove_member_from_room(request, room_name, username):
    """Remove um membro da sala privada"""
    room = get_object_or_404(ChatRoom, name=room_name)

    # Apenas o criador da sala pode remover membros
    if room.created_by != request.user:
        return HttpResponseForbidden("Apenas o criador da sala pode remover membros")

    user_to_remove = get_object_or_404(User, username=username)

    # Não permitir remover o criador
    if user_to_remove == room.created_by:
        return JsonResponse({
            'success': False,
            'message': 'Não é possível remover o criador da sala'
        })

    # Remover membro
    room.remove_member(user_to_remove)

    return JsonResponse({
        'success': True,
        'message': f'Usuário {username} removido da sala'
    })


@login_required
def get_unread_count(request, room_name=None):
    """Retorna a contagem de mensagens não lidas"""
    if room_name:
        # Contagem para uma sala específica
        room = get_object_or_404(ChatRoom, name=room_name)
        if not room.can_user_access(request.user):
            return JsonResponse({'error': 'Acesso negado'}, status=403)

        unread_count = room.get_unread_count_for_user(request.user)
        return JsonResponse({'unread_count': unread_count})
    else:
        # Contagem total para todas as salas
        rooms = ChatRoom.objects.filter(
            Q(is_private=False) |
            Q(members=request.user) |
            Q(created_by=request.user)
        ).distinct()

        total_unread = 0
        for room in rooms:
            total_unread += room.get_unread_count_for_user(request.user)

        return JsonResponse({'total_unread': total_unread})


@login_required
def mark_all_as_read(request, room_name):
    """Marca todas as mensagens não lidas como lidas"""
    room = get_object_or_404(ChatRoom, name=room_name)

    if not room.can_user_access(request.user):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    # Obter mensagens não lidas
    unread_messages = Message.objects.filter(room=room).exclude(read_by=request.user).exclude(author=request.user)

    if room.is_private:
        user_joined_time = room.get_member_joined_time(request.user)
        if user_joined_time:
            unread_messages = unread_messages.filter(timestamp__gte=user_joined_time)

    # Marcar como lidas
    count = 0
    for message in unread_messages:
        if not message.get_read_status_for_user(request.user):
            message.mark_as_read(request.user)
            count += 1

    return JsonResponse({
        'success': True,
        'message': f'{count} mensagens marcadas como lidas'
    })


@login_required
def get_room_members(request, room_name):
    """Retorna os membros de uma sala privada"""
    room = get_object_or_404(ChatRoom, name=room_name)

    if not room.can_user_access(request.user):
        return JsonResponse({'error': 'Acesso negado'}, status=403)

    if not room.is_private:
        return JsonResponse({'error': 'Esta não é uma sala privada'}, status=400)

    members = room.members.all().values('id', 'username', 'email')
    creator = {
        'id': room.created_by.id,
        'username': room.created_by.username,
        'email': room.created_by.email,
        'is_creator': True
    }

    # Garantir que o criador esteja na lista
    members_list = list(members)
    if not any(member['id'] == room.created_by.id for member in members_list):
        members_list.append(creator)

    return JsonResponse({'members': members_list})


@login_required
def search_users(request):
    """Busca usuários para adicionar à sala"""
    query = request.GET.get('q', '')

    if not query:
        return JsonResponse({'users': []})

    # Buscar usuários (excluindo o próprio usuário)
    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(email__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).exclude(id=request.user.id).values('id', 'username', 'email', 'first_name', 'last_name')[:10]

    return JsonResponse({'users': list(users)})


@login_required
def user_activity(request):
    """Retorna a atividade recente dos usuários"""
    # Últimos usuários ativos (últimos 5 minutos)
    five_minutes_ago = timezone.now() - timezone.timedelta(minutes=5)
    active_users = UserProfile.objects.filter(
        last_activity__gte=five_minutes_ago
    ).select_related('user').values('user__username', 'last_activity')

    return JsonResponse({'active_users': list(active_users)})


@login_required
def delete_room(request, room_name):
    """Exclui uma sala de chat"""
    room = get_object_or_404(ChatRoom, name=room_name)

    # Apenas o criador pode excluir a sala
    if room.created_by != request.user:
        return HttpResponseForbidden("Apenas o criador pode excluir a sala")

    room.delete()
    return redirect('chat_home')


@login_required
def leave_room(request, room_name):
    """Sai de uma sala privada"""
    room = get_object_or_404(ChatRoom, name=room_name)

    if not room.is_private:
        return JsonResponse({
            'success': False,
            'message': 'Você não pode sair de uma sala pública'
        })

    # Não permitir que o criador saia da própria sala
    if room.created_by == request.user:
        return JsonResponse({
            'success': False,
            'message': 'O criador não pode sair da sala. Transfira a propriedade primeiro.'
        })

    # Remover usuário da sala
    room.remove_member(request.user)

    return JsonResponse({
        'success': True,
        'message': 'Você saiu da sala'
    })


@csrf_protect
def login_view(request):
    """View de login personalizada"""
    if request.user.is_authenticated:
        return redirect('chat_home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)

            if user is not None:
                login(request, user)
                messages.success(request, f'Bem-vindo de volta, {username}!')

                # Redirecionar para a próxima página ou home
                next_page = request.GET.get('next', 'chat_home')
                return redirect(next_page)
            else:
                messages.error(request, 'Credenciais inválidas.')
        else:
            messages.error(request, 'Por favor, corrija os erros abaixo.')
    else:
        form = AuthenticationForm()

    return render(request, 'chat/login.html', {'form': form})


def logout_view(request):
    """View de logout"""
    logout(request)
    messages.success(request, 'Você foi desconectado com sucesso.')
    return redirect('login')


def register_view(request):
    """View de registro de novos usuários"""
    if request.user.is_authenticated:
        return redirect('chat_home')

    if request.method == 'POST':
        # Formulário simples de registro
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        email = request.POST.get('email', '')

        # Validações básicas
        if not username or not password:
            messages.error(request, 'Username e senha são obrigatórios.')
        elif password != confirm_password:
            messages.error(request, 'As senhas não coincidem.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Este username já está em uso.')
        else:
            # Criar novo usuário
            try:
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    email=email
                )
                login(request, user)
                messages.success(request, f'Conta criada com sucesso! Bem-vindo, {username}!')
                return redirect('chat_home')
            except Exception as e:
                messages.error(request, f'Erro ao criar conta: {str(e)}')

    return render(request, 'chat/register.html')