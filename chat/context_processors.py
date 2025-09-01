from .utils import get_user_chat_rooms_data
from .utils import get_room_members_context
from django.contrib.auth import get_user_model


def user_chat_rooms(request):
    """
    Context processor para salas do usuário com contagem de não lidas.
    Agora chama a função auxiliar.
    """
    return {'chat_rooms': get_user_chat_rooms_data(request.user)}



def room_context_processor(request):
    """Context processor para injetar dados da sala e membros no template."""
    return get_room_members_context(request)



def available_users(request):
    User = get_user_model()
    if request.user.is_authenticated:
        # Exclui o próprio usuário e talvez já participantes da sala
        users = User.objects.exclude(id=request.user.id)
    else:
        users = User.objects.none()

    return {"available_users": users}