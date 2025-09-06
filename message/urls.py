# chat/urls.py (atualizado)
from django.urls import path
from message import views

urlpatterns = [
    path('<str:room_name>/unread-count/', views.get_unread_count, name='unread_count'),
    path('unread-count/', views.get_unread_count, name='total_unread_count'),
    path('<str:id_random>/mark-read/', views.mark_all_as_read, name='mark_all_read'),
    path('<str:id_random>/messages/', views.get_message_history, name='get_message_history'),
]