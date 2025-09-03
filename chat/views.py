# chat/views.py
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from .models import  Message, UserProfile, Attachment
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.csrf import csrf_protect
from django.db.models import Count, Q, Prefetch
from .utils import get_user_chat_rooms_data
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from .forms import CreateRoomForm
from .models import ChatRoom
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.views.decorators.http import require_POST
import os

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
    """
    Renderiza a página de uma sala de chat.
    A view foi simplificada para apenas verificar o acesso e renderizar o template base.
    Todo o histórico de mensagens é carregado de forma assíncrona via API.
    """
    # 1. Obter a sala e verificar se ela existe
    try:
        # Usamos select_related para otimizar o acesso ao 'created_by' se necessário no template
        room = ChatRoom.objects.select_related('created_by').get(name=room_name)
    except ChatRoom.DoesNotExist:
        messages.error(request, "A sala de chat que você tentou acessar não existe.")
        return redirect('chat_home') # Redireciona para uma página inicial de chat

    # 2. Verificar se o usuário tem permissão para acessar a sala
    if not room.can_user_access(request.user):
        messages.error(request, "Você não tem acesso a esta sala privada.")
        return redirect('chat_home')

    # 3. (Opcional, mas recomendado) Atualizar a última atividade do usuário
    # Isso é útil para saber quem está online.
    UserProfile.objects.update_or_create(
        user=request.user,
        defaults={'last_activity': timezone.now()}
    )

    # 4. Preparar o contexto mínimo para o template
    # O template agora só precisa de informações básicas sobre a sala e o usuário.
    # O JavaScript cuidará do resto.
    context = {
        'room_name': room.name,
        'room': room,  # Passamos o objeto para acessar dados como room.is_private no template
        'user_username': request.user.username, # Passa o nome de usuário de forma explícita
        'user_id': request.user.id, # Passa o ID do usuário
    }

    # 5. Renderizar o template "esqueleto"
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
def edit_room(request, room_name):
    """Edita uma sala de chat."""
    room = get_object_or_404(ChatRoom, name=room_name)

    if room.created_by != request.user:
        messages.error(request, 'Você não tem permissão para editar esta sala.')
        return redirect('chat_room', room_name=room.name)

    if request.method == 'POST':
        form = CreateRoomForm(request.POST, instance=room, request=request)
        if form.is_valid():

            # Obter a lista atual de membros antes de salvar o formulário
            current_members = set(room.members.all())

            # Salva o formulário (altera nome e is_private)
            form.save()

            # Obter a nova lista de membros após o salvamento
            updated_room = ChatRoom.objects.get(name=room.name)
            new_members = set(updated_room.members.all())

            # Identificar quem foi adicionado e quem foi removido
            added_users = new_members - current_members
            removed_users = current_members - new_members

            try:
                system_user = User.objects.get(username='System')
            except User.DoesNotExist:
                system_user = request.user

            # Notificar os usuários sobre as mudanças
            channel_layer = get_channel_layer()

            # Notifica adições
            for user in added_users:
                notification_message = f"{request.user.username} adicionou {user.username} à sala."
                Message.objects.create(room=updated_room, author=system_user, content=notification_message)

                # Dispara a atualização para o usuário adicionado
                user_group_name = f"user_{user.id}"
                updated_room_data = get_user_chat_rooms_data(user)
                async_to_sync(channel_layer.group_send)(
                    user_group_name,
                    {
                        "type": "unread.count.update",
                        "room_data": updated_room_data,
                    }
                )

            # Notifica remoções
            for user in removed_users:
                # O criador não pode ser removido
                if user != room.created_by:
                    notification_message = f"{request.user.username} removeu {user.username} da sala."
                    Message.objects.create(room=updated_room, author=system_user, content=notification_message)

                    # Dispara a atualização para o usuário removido
                    user_group_name = f"user_{user.id}"
                    updated_room_data = get_user_chat_rooms_data(user)
                    async_to_sync(channel_layer.group_send)(
                        user_group_name,
                        {
                            "type": "unread.count.update",
                            "room_data": updated_room_data,
                        }
                    )

            # O próprio editor também precisa ter sua lista de salas atualizada
            editor_group_name = f"user_{request.user.id}"
            updated_room_data = get_user_chat_rooms_data(request.user)
            async_to_sync(channel_layer.group_send)(
                editor_group_name,
                {
                    "type": "unread.count.update",
                    "room_data": updated_room_data,
                }
            )

            messages.success(request, f'Sala "{updated_room.name}" atualizada com sucesso!')
            return redirect('chat_room', room_name=updated_room.name)
    else:
        form = CreateRoomForm(instance=room, request=request)

    return render(request, 'chat/edit_room.html', {'form': form, 'room': room})


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
    """Deleta uma sala e redireciona todos os usuários para a home do chat."""
    room = get_object_or_404(ChatRoom, name=room_name)

    # Só o criador pode excluir
    if room.created_by != request.user:
        messages.error(request, 'Apenas o criador pode excluir esta sala.')
        return redirect('chat_room', room_name=room.name)

    channel_layer = get_channel_layer()

    # Notificar todos os usuários da sala que ela foi excluída
    async_to_sync(channel_layer.group_send)(
        f"chat_{room.name}",
        {
            "type": "room_deleted",  # vai chamar room_deleted no consumer
            "room_name": room.name,
        }
    )

    # Atualizar a sidebar de todos os membros
    for member in room.members.all():
        user_group_name = f"user_{member.id}"
        updated_room_data = get_user_chat_rooms_data(member)
        async_to_sync(channel_layer.group_send)(
            user_group_name,
            {
                "type": "unread_count_update",
                "room_data": updated_room_data,
            }
        )

    room.delete()
    messages.success(request, f'A sala "{room.name}" foi excluída.')
    return redirect('chat_home')


@login_required
def leave_room(request, room_name):
    """Usuário sai de uma sala privada."""
    room = get_object_or_404(ChatRoom, name=room_name)

    # Só faz sentido sair de salas privadas
    if not room.is_private:
        messages.error(request, 'Você não pode sair de uma sala pública.')
        return redirect('chat_room', room_name=room.name)

    # Criador não pode sair sem transferir
    if room.created_by == request.user:
        messages.error(request, 'O criador não pode sair da sala. Transfira a propriedade primeiro.')
        return redirect('chat_room', room_name=room.name)

    # Remover usuário da sala
    if request.user in room.members.all():
        room.members.remove(request.user)

        # Criar mensagem de sistema
        try:
            system_user = User.objects.get(username="System")
        except User.DoesNotExist:
            system_user = request.user

        Message.objects.create(
            room=room,
            author=system_user,
            content=f"{request.user.username} saiu da sala."
        )

        # Notificar os outros membros via WebSocket
        channel_layer = get_channel_layer()

        # Notificar a sala que o usuário saiu
        async_to_sync(channel_layer.group_send)(
            f"chat_{room.name}",
            {
                "type": "user_left",  # Isso chama o método user_left no consumer
                "username": request.user.username,
            }
        )

        # Atualizar a sidebar de todos os usuários
        for member in room.members.all():
            user_group_name = f"user_{member.id}"
            updated_room_data = get_user_chat_rooms_data(member)

            async_to_sync(channel_layer.group_send)(
                user_group_name,
                {
                    "type": "unread_count_update",
                    "room_data": updated_room_data,
                }
            )

        # Atualizar a sidebar do usuário que saiu também
        user_group_name = f"user_{request.user.id}"
        updated_room_data = get_user_chat_rooms_data(request.user)
        async_to_sync(channel_layer.group_send)(
            user_group_name,
            {
                "type": "unread_count_update",
                "room_data": updated_room_data,
            }
        )

        messages.success(request, f'Você saiu da sala "{room.name}".')
        return redirect('chat_home')

    messages.error(request, 'Você não faz parte desta sala.')
    return redirect('chat_home')


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


def get_message_history(request, room_name):
    """
    View de API para retornar o histórico de mensagens de uma sala em JSON.
    """
    try:
        room = ChatRoom.objects.get(name=room_name)
        messages = Message.objects.filter(room=room).order_by('timestamp').select_related('author')

        history = []
        for msg in messages:
            attachments_data = []
            # Supondo que você tenha um related_name 'attachments' no seu modelo Message
            for att in msg.attachments.all():
                attachments_data.append({
                    'file': att.file.url,
                    'original_filename': att.original_filename,
                })

            history.append({
                'message_id': msg.id,
                'author': msg.author.username,
                'message': msg.content,
                'timestamp': msg.timestamp.isoformat(),
                'is_system_message': msg.is_system_message,
                'attachments': attachments_data,
            })

        return JsonResponse(history, safe=False)

    except ChatRoom.DoesNotExist:
        return JsonResponse({'error': 'Sala não encontrada'}, status=404)


@login_required
def get_message_history(request, room_name):
    """
    View de API para retornar o histórico de mensagens de uma sala em JSON,
    baseada na lógica da view original e otimizada para serialização.
    """
    # 1. Obter a sala e verificar o acesso do usuário
    try:
        room = ChatRoom.objects.get(name=room_name)
        if not room.can_user_access(request.user):
            return JsonResponse({'error': 'Acesso negado'}, status=403)
    except ChatRoom.DoesNotExist:
        return JsonResponse({'error': 'Sala não encontrada'}, status=404)

    # 2. Buscar as últimas 100 mensagens com autores pré-carregados
    messages_query = Message.objects.filter(room=room).select_related('author').order_by('-timestamp').distinct()[:100]

    # Inverter a ordem para do mais antigo para o mais novo
    messages = list(messages_query)[::-1]

    # 3. Otimização: Buscar todos os anexos de uma vez
    message_ids = [msg.id for msg in messages]
    attachments_by_message_id = {}

    # Usamos prefetch_related para buscar todos os anexos de todas as mensagens em uma única query
    attachments_query = Attachment.objects.filter(message_id__in=message_ids)
    for attachment in attachments_query:
        if attachment.message_id not in attachments_by_message_id:
            attachments_by_message_id[attachment.message_id] = []

        # Estrutura do anexo para o JSON
        attachments_by_message_id[attachment.message_id].append({
            'file_url': attachment.file.url,
            'original_filename': attachment.original_filename,
            'attachment_type': attachment.attachment_type,
        })

    # 4. Montar a lista final de mensagens para o JSON
    history = []
    for msg in messages:
        # Usamos o dicionário de anexos pré-buscados
        message_attachments = attachments_by_message_id.get(msg.id, [])

        history.append({
            'message_id': msg.id,
            'author': msg.author.username,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat(),
            'is_system_message': False,  # Seu modelo Message não parece ter esse campo, então definimos como False.
            'attachments': message_attachments,
        })

    return JsonResponse(history, safe=False)


@require_POST  # Restricts to POST only for security
def upload_attachment(request):
    attachment_ids = []
    try:
        files = request.FILES.getlist('files')  # Matches the FormData key 'files'
        if not files:
            return JsonResponse({'error': 'Nenhum arquivo enviado'}, status=400)

        for file in files:
            # Determine attachment type based on content_type
            content_type = file.content_type.lower()
            attachment_type = 'other'
            if 'image' in content_type:
                attachment_type = 'image'
            elif 'video' in content_type:
                attachment_type = 'video'
            elif 'audio' in content_type:
                attachment_type = 'audio'
            elif 'application/pdf' in content_type:
                attachment_type = 'pdf'

            # Create the attachment (message=None initially)
            attachment = Attachment.objects.create(
                file=file,
                original_filename=file.name,
                attachment_type=attachment_type,
                # Add other fields if needed, e.g., uploaded_by=request.user
            )
            attachment_ids.append(attachment.id)

        return JsonResponse({'attachment_ids': attachment_ids})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
