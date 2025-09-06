from django.urls import path
from . import views

urlpatterns = [
    path('chat_home/', views.chat_home, name='chat_home'),
    path('create/', views.create_room, name='create_room'),
    path('edit/<str:id_random>/', views.edit_room, name='edit_room'),  # Alterado para uuid
    path('<str:id_random>/', views.chat_room, name='chat_room'),  # Alterado para uuid
    path('<str:id_random>/add-member/<str:username>/', views.add_member_to_room, name='add_member'),  # Alterado
    path('<str:id_random>/remove-member/<str:username>/', views.remove_member_from_room, name='remove_member'),  # Alterado
    path('<str:id_random>/members/', views.get_room_members, name='room_members'),  # Alterado
    path('search-users/', views.search_users, name='search_users'),
    path('activity/', views.user_activity, name='user_activity'),
    path('<str:id_random>/delete/', views.delete_room, name='delete_room'),  # Alterado
    path('<str:id_random>/leave/', views.leave_room, name='leave_room'),  # Alterado
    path('api/available-users/', views.get_available_users, name='available_users'),
    path('<str:id_random>/stats/', views.room_stats, name='room_stats'),  # Alterado
]