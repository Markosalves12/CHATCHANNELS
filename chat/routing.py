# routing.py - Versão atualizada para usar id_random

from django.urls import re_path
from . import consumers

# Versão original (usando room_name)
# websocket_urlpatterns = [
#     re_path(r"ws/chat/(?P<room_name>\w+)/$", consumers.ChatConsumer.as_asgi()),
# ]

# Versão atualizada (usando id_random)
websocket_urlpatterns = [
    re_path(r"ws/chat/(?P<id_random>\w+)/$", consumers.ChatConsumer.as_asgi()),
]

# Alternativa mais flexível para IDs únicos (UUID, hash, etc.)
# websocket_urlpatterns = [
#     re_path(r"ws/chat/(?P<room_id>[\w\-]+)/$", consumers.ChatConsumer.as_asgi()),
# ]

# Alternativa ainda mais flexível (aceita mais caracteres especiais)
# websocket_urlpatterns = [
#     re_path(r"ws/chat/(?P<room_id>[^/]+)/$", consumers.ChatConsumer.as_asgi()),
# ]

