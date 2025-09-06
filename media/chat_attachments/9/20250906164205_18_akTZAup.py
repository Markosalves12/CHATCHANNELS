from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from .models import UserProfile
from chat.models import Message
from django.db.models import Count, Q
from .utils import get_user_chat_rooms_data
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib import messages
from .forms import CreateRoomForm
from .models import ChatRoom
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from attachments.models import Attachment
from django.conf import settings
from gerente.models import Gerente


def chat_home(request):
    if not request.user.is_authenticated:
        return redirect('login')

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

    context = {
        'rooms_with_unread': rooms_with_unread,
    }
    return render(request, 'home.html', context)


def chat_room(request, id_random):
    if not request.user.is_authenticated:
        return redirect('login')

    try:
        room = ChatRoom.objects.select_related('created_by').get(id_random=id_random)
    except ChatRoom.DoesNotExist:
        messages.error(request, "A sala de chat que você tentou acessar não existe.")
        return redirect('chat_home')

    if not room.can_user_access(request.user):
        messages.error(request, "Você não tem acesso a esta sala privada.")
        return redirect('chat_home')

    UserProfile.objects.update_or_create(
        user=request.user,
        defaults={'last_activity': timezone.now()}
    )

    context = {
        'room_id_random': room.id_random,
        'room': room,
        'user_username': request.user.username,
        'user_id': request.user.id,
    }
    return render(request, 'room.html', context)


def create_room(request):
    if not request.user.is_authenticated:
        return redirect('login')

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

                return redirect('chat_room', id_random=room.id_random)  # Alterado para id_random

            except Exception as e:
                messages.error(request, f'Erro ao criar sala: {str(e)}')
        else:
            messages.error(request, 'Por favor, corrija os erros no formulário.')
    else:
        form = CreateRoomForm(request=request)

    # Contar usuários disponíveis para adicionar
    total_users = Gerente.objects.exclude(id=request.user.id).count()

    return render(request, 'create_room.html', {
        'form': form,
        'total_users': total_users,
        'available_users': Gerente.objects.exclude(id=request.user.id).order_by('username')[:50]
    })


def edit_room(request, id_random):
    if not request.user.is_authenticated:
        return redirect('login')

    """Edita uma sala de chat."""
    room = get_object_or_404(ChatRoom, id_random=id_random)

    if room.created_by != request.user:
        messages.error(request, 'Você não tem permissão para editar esta sala.')
        return redirect('chat_room', id_random=room.id_random)  # Alterado para id_random

    if request.method == 'POST':
        form = CreateRoomForm(request.POST, instance=room, request=request)
        if form.is_valid():

            # Obter a lista atual de membros antes de salvar o formulário
            current_members = set(room.members.all())

            # Salva o formulário (altera nome e is_private)
            form.save()

            # Obter a nova lista de membros após o salvamento
            updated_room = ChatRoom.objects.get(id_random=id_random)
            new_members = set(updated_room.members.all())

            # Identificar quem foi adicionado e quem foi removido
            added_users = new_members - current_members
            removed_users = current_members - new_members

            try:
                system_user = Gerente.objects.get(username='System')
            except Gerente.DoesNotExist:
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
            return redirect('chat_room', id_random=updated_room.id_random)  # Alterado para id_random
    else:
        form = CreateRoomForm(instance=room, request=request)

    return render(request, 'edit_room.html', {'form': form, 'room': room})


def room_members(request, id_random):
    if not request.user.is_authenticated:
        return redirect('login')

    """Retorna informações dos membros da sala"""
    room = get_object_or_404(ChatRoom, id_random=id_random)

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


def add_member_to_room(request, id_random, username):
    if not request.user.is_authenticated:
        return redirect('login')

    """Adiciona um membro à sala privada"""
    room = get_object_or_404(ChatRoom, id_random=id_random)

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


def remove_member_from_room(request, id_random, username):
    if not request.user.is_authenticated:
        return redirect('login')

    """Remove um membro da sala privada"""
    room = get_object_or_404(ChatRoom, id_random=id_random)

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


def get_room_members(request, id_random):
    if not request.user.is_authenticated:
        return redirect('login')

    """Retorna os membros de uma sala privada"""
    room = get_object_or_404(ChatRoom, id_random=id_random)

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


def delete_room(request, id_random):
    if not request.user.is_authenticated:
        return redirect('login')

    """Deleta uma sala e redireciona todos os usuários para a home do chat."""
    room = get_object_or_404(ChatRoom, id_random=id_random)

    # Só o criador pode excluir
    if room.created_by != request.user:
        messages.error(request, 'Apenas o criador pode excluir esta sala.')
        return redirect('chat_room', id_random=room.id_random)  # Alterado para id_random

    channel_layer = get_channel_layer()

    # Notificar todos os usuários da sala que ela foi excluída
    async_to_sync(channel_layer.group_send)(
        f"chat_{room.id_random}",  # Alterado para usar id_random
        {
            "type": "room_deleted",
            "room_id_random": str(room.id_random),  # Enviar id_random em vez de name
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


def leave_room(request, id_random):
    if not request.user.is_authenticated:
        return redirect('login')

    """Usuário sai de uma sala privada."""
    room = get_object_or_404(ChatRoom, id_random=id_random)

    # Só faz sentido sair de salas privadas
    if not room.is_private:
        messages.error(request, 'Você não pode sair de uma sala pública.')
        return redirect('chat_room', id_random=room.id_random)  # Alterado para id_random

    # Criador não pode sair sem transferir
    if room.created_by == request.user:
        messages.error(request, 'O criador não pode sair da sala. Transfira a propriedade primeiro.')
        return redirect('chat_room', id_random=room.id_random)  # Alterado para id_random

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
            f"chat_{room.id_random}",  # Alterado para usar id_random
            {
                "type": "user_left",
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


def mark_all_as_read(request, id_random):
    if not request.user.is_authenticated:
        return redirect('login')

    """Marca todas as mensagens não lidas como lidas"""
    room = get_object_or_404(ChatRoom, id_random=id_random)

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


def get_message_history(request, id_random):
    if not request.user.is_authenticated:
        return redirect('login')

    """
    View de API para retornar o histórico de mensagens de uma sala em JSON,
    baseada na lógica da view original e otimizada para serialização.
    """
    # 1. Obter a sala e verificar o acesso do usuário
    try:
        room = ChatRoom.objects.get(id_random=id_random)
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
            'is_system_message': False,
            'attachments': message_attachments,
        })

    return JsonResponse(history, safe=False)


def room_stats(request, id_random):
    if not request.user.is_authenticated:
        return redirect('login')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        room = get_object_or_404(ChatRoom, id_random=id_random)

        if not room.can_user_access(request.user):
            return JsonResponse({'error': 'Acesso negado'}, status=403)

        unread_count = Message.objects.filter(room=room).exclude(read_by=request.user).exclude(author=request.user).count()
        last_activity = Message.objects.filter(room=room).order_by('-timestamp').values('timestamp', 'author__username').first()

        five_minutes_ago = timezone.now() - timezone.timedelta(minutes=5)
        online_members = UserProfile.objects.filter(
            last_activity__gte=five_minutes_ago,
            user__in=room.members.all()
        ).values('user__username', 'last_activity')

        return JsonResponse({
            'unread_count': unread_count,
            'last_activity': last_activity,
            'online_members': list(online_members),
            'total_members': room.members.count() + 1,
        })

    return JsonResponse({'error': 'Requisição inválida'}, status=400)