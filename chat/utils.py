# from django.db.models import Q
# from .models import ChatRoom, Message
#
# def get_user_chat_rooms_data(user):
#     """
#     Obtém a lista de salas do usuário com a contagem de mensagens não lidas.
#     Esta função é agnóstica ao contexto (não depende do objeto 'request').
#     """
#     if not user.is_authenticated:
#         return []
#
#     rooms = ChatRoom.objects.filter(
#         Q(members=user) | Q(created_by=user)
#     ).distinct()
#
#     room_data = []
#     for room in rooms:
#         unread_count = Message.objects.filter(
#             room=room
#         ).exclude(author=user).exclude(read_by=user).count()
#
#         room_data.append({
#             'name': room.name,
#             'is_private': room.is_private,
#             'unread_count': unread_count,
#         })
#
#     return room_data


from django.db.models import Q
from .models import ChatRoom, Message
from django.shortcuts import get_object_or_404
from django.http import Http404


def get_user_chat_rooms_data(user):
    """
    Obtém a lista de salas do usuário com a contagem de mensagens não lidas
    e a ordem baseada na última mensagem, convertendo a data para string.
    """
    if not user.is_authenticated:
        return []

    # Filtra salas em que o usuário participa ou criou
    rooms = ChatRoom.objects.filter(
        Q(members=user) | Q(created_by=user)
    ).distinct()

    room_data = []
    for room in rooms:
        # Contagem de mensagens não lidas (apenas mensagens de outros usuários)
        unread_count = Message.objects.filter(
            room=room
        ).exclude(author=user).exclude(read_by=user).count()

        # Obtém a última mensagem da sala para ordenação
        last_message = Message.objects.filter(room=room).order_by('-timestamp').first()
        last_message_timestamp = last_message.timestamp if last_message else room.created_at

        room_data.append({
            'name': room.name,
            'is_private': room.is_private,
            'unread_count': unread_count,
            'last_message_timestamp': last_message_timestamp.isoformat()  # Convertido para string
        })

    # Ordena a lista de salas do mais recente para o mais antigo
    sorted_room_data = sorted(
        room_data,
        key=lambda x: x['last_message_timestamp'],
        reverse=True
    )

    return sorted_room_data



def get_room_members_context(request):
    """
    Retorna um dicionário com informações da sala e seus membros,
    ou um dicionário vazio se não estiver em uma página de chat.
    """
    context = {}
    room_name = request.resolver_match.kwargs.get('room_name')

    if room_name:
        try:
            room = get_object_or_404(ChatRoom, name=room_name)

            if room.can_user_access(request.user):
                members_info = room.get_members_info()
                context = {
                    'current_room_members': {
                        'room_name': room.name,
                        'is_private': room.is_private,
                        'created_by': room.created_by.username,
                        'members': members_info,
                        'total_members': len(members_info)
                    }
                }
        except Http404:
            # Não faz nada, o contexto permanecerá vazio
            pass

    return context