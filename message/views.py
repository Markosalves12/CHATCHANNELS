# chat/views.py
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from chat.models import Message
from attachments.models import Attachment
from django.db.models import Q
from django.shortcuts import redirect
from chat.models import ChatRoom
from django.contrib.auth.decorators import login_required


@login_required
def get_unread_count(request, id_random=None):
    """Retorna a contagem de mensagens não lidas"""
    if id_random:
        # Contagem para uma sala específica
        room = get_object_or_404(ChatRoom, id_random=id_random)
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
def mark_all_as_read(request, id_random):
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
    """
    View de API para retornar o histórico de mensagens de uma sala em JSON.
    """
    try:
        room = ChatRoom.objects.get(id_random=id_random)
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
