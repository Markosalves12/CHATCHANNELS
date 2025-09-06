# chat/urls.py (atualizado)
from django.urls import path
from . import views


urlpatterns = [
    # Autenticação
    path('upload_attachment/', views.upload_attachment, name='upload_attachment'),
]
