from django.urls import path
from . import views


urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('enviar-token', views.reset_password, name='reset_password'),
    path('atualizar-senha/<str:token>', views.update_password, name='update_password'),
]
