# chat/urls.py (atualizado)
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views


urlpatterns = [
    # Autenticação
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),

    # Password reset (opcional)
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='chat/password_reset.html',
             email_template_name='chat/password_reset_email.html',
             subject_template_name='chat/password_reset_subject.txt',
             success_url='/login/'
         ),
         name='password_reset'),

    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='chat/password_reset_done.html'
         ),
         name='password_reset_done'),

    path('password-reset-confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='chat/password_reset_confirm.html',
             success_url='/login/'
         ),
         name='password_reset_confirm'),

    path('password-reset-complete/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='chat/password_reset_complete.html'
         ),
         name='password_reset_complete'),

    path('', views.chat_home, name='chat_home'),
    path('create/', views.create_room, name='create_room'),
    path('edit/<str:room_name>/', views.edit_room, name='edit_room'),
    path('<str:room_name>/', views.chat_room, name='chat_room'),
    path('<str:room_name>/add-member/<str:username>/', views.add_member_to_room, name='add_member'),
    path('<str:room_name>/remove-member/<str:username>/', views.remove_member_from_room, name='remove_member'),
    path('<str:room_name>/unread-count/', views.get_unread_count, name='unread_count'),
    path('unread-count/', views.get_unread_count, name='total_unread_count'),
    path('<str:room_name>/mark-read/', views.mark_all_as_read, name='mark_all_read'),
    path('<str:room_name>/members/', views.get_room_members, name='room_members'),
    path('search-users/', views.search_users, name='search_users'),
    path('activity/', views.user_activity, name='user_activity'),
    path('<str:room_name>/delete/', views.delete_room, name='delete_room'),
    path('<str:room_name>/leave/', views.leave_room, name='leave_room'),
    path('api/available-users/', views.get_available_users, name='available_users'),
    path('<str:room_name>/mark-read/', views.mark_room_as_read, name='mark_room_read'),
    path('<str:room_name>/stats/', views.room_stats, name='room_stats'),
    path('<str:room_name>/messages/', views.get_message_history, name='get_message_history'),
    path('upload_attachment/', views.upload_attachment, name='upload_attachment'),
]
