from .utils import get_user_chat_rooms_data
from .utils import get_room_members_context

def user_chat_rooms(request):
    """
    Context processor para salas do usuário com contagem de não lidas.
    Agora chama a função auxiliar.
    """
    return {'chat_rooms': get_user_chat_rooms_data(request.user)}



def room_context_processor(request):
    """Context processor para injetar dados da sala e membros no template."""
    return get_room_members_context(request)