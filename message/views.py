# chat/views.py
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.http import JsonResponse
from chat.models import Message
from attachments.models import Attachment
from django.db.models import Q
from chat.models import ChatRoom
import mimetypes
from django.views.decorators.http import require_POST

def get_unread_count(request, id_random=None):
    if not request.user.is_authenticated:
        return redirect('login')

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
    View de API para retornar o histórico de mensagens de uma sala em JSON.
    """
    try:
        room = ChatRoom.objects.get(id_random=id_random)
        messages = (
            Message.objects.filter(room=room)
            .order_by("timestamp")
            .select_related("author")
        )

        history = []
        for msg in messages:
            attachments_data = []
            for att in msg.attachments.all():
                # Detecta tipo do anexo
                mime, _ = mimetypes.guess_type(att.file.name)
                if mime:
                    attachment_type = mime.split("/")[0]  # "image", "video", "audio", "application"
                    # tratar pdf como "pdf"
                    if mime == "application/pdf":
                        attachment_type = "pdf"
                else:
                    attachment_type = "document"

                attachments_data.append({
                    "id": att.id,
                    "file_url": att.file.url,
                    "original_filename": att.original_filename,
                    "attachment_type": attachment_type,
                })

            history.append({
                "message_id": msg.id,
                "author": msg.author.username,
                "message": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                # "is_system_message": msg.is_system_message,
                "attachments": attachments_data,
            })

        return JsonResponse(history, safe=False)

    except ChatRoom.DoesNotExist:
        return JsonResponse({"error": "Sala não encontrada"}, status=404)




@require_POST
def delete_message(request, message_id):
    if not request.user.is_authenticated:
        return redirect('login')

    try:
        message = Message.objects.get(id=message_id, author=request.user)
        message.is_deleted = True
        message.save()
        # Broadcast via WS (chame o consumer ou use channel layer)
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{message.room.id_random}",
            {
                "type": "chat.message.deleted",
                "message_id": message.id,
            }
        )
        return JsonResponse({"success": True})
    except Message.DoesNotExist:
        return JsonResponse({"error": "Mensagem não encontrada ou não é sua"}, status=403)

@require_POST
def edit_message(request, message_id):
    if not request.user.is_authenticated:
        return redirect('login')

    try:
        data = json.loads(request.body)
        message = Message.objects.get(id=message_id, author=request.user)
        if not message.is_deleted:
            message.content = data.get('content', message.content)
            message.save()
            # Remover anexos específicos se enviados IDs pra delete
            attachments_to_delete = data.get('attachments_to_delete', [])
            Attachment.objects.filter(id__in=attachments_to_delete, message=message).delete()
            # Adicionar novos anexos? (Se quiser, handle files aqui, mas pra simplicidade, assuma que edição só texto + remove anexos; novos via resend)
            # Broadcast
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"chat_{message.room.id_random}",
                {
                    "type": "chat.message.updated",
                    "message_id": message.id,
                    "content": message.content,
                    "attachments": [  # Envie lista atualizada
                        {
                            "file_url": att.file.url,
                            "original_filename": att.original_filename,
                            "attachment_type": mimetypes.guess_type(att.file.name)[0].split("/")[0] if mimetypes.guess_type(att.file.name)[0] else "document",
                        } for att in message.attachments.all()
                    ],
                    "timestamp": message.timestamp.isoformat(),
                }
            )
            return JsonResponse({"success": True})
    except Message.DoesNotExist:
        return JsonResponse({"error": "Mensagem não encontrada ou não é sua"}, status=403)


@require_POST
def delete_attachment(request, attachment_id):
    if not request.user.is_authenticated:
        return redirect('login')

    try:
        attachment = Attachment.objects.get(id=attachment_id)
        if attachment.message.author != request.user:
            return JsonResponse({"error": "Não autorizado"}, status=403)
        attachment.delete()
        # Broadcast update da mensagem
        message = attachment.message
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{message.room.id_random}",
            {
                "type": "chat.message.updated",
                "message_id": message.id,
                "content": message.content,
                "attachments": [  # Lista atualizada
                    {
                        "file_url": att.file.url,
                        "original_filename": att.original_filename,
                        "attachment_type": mimetypes.guess_type(att.file.name)[0].split("/")[0] if mimetypes.guess_type(att.file.name)[0] else "document",
                    } for att in message.attachments.all()
                ],
                "timestamp": message.timestamp.isoformat(),
            }
        )
        return JsonResponse({"success": True})
    except Attachment.DoesNotExist:
        return JsonResponse({"error": "Anexo não encontrado"}, status=404)