from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.utils.crypto import get_random_string
from empresasecundario.models import EmpresaSecundaria
from notifications.utils import enviar_notificacao
from utils.utils import generate_id_random


class GerenteManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError('O campo email deve ser preenchido')
        if not username:
            raise ValueError('O campo nome deve ser preenchido')

        email = self.normalize_email(email)
        user = self.model(
            email=email,
            username=username,
            **extra_fields
        )

        # Gera senha aleatória se não for fornecida
        if password:
            user.set_password(password)
        else:
            password = get_random_string(length=12)
            user.set_password(password)
            # Marca para enviar o email após salvar
            user._send_welcome_email = True
            user._temp_password = password  # Armazena a senha temporariamente

        user.save(using=self._db)

        # Envia o email após o usuário ser salvo com sucesso
        if hasattr(user, '_send_welcome_email'):
            enviar_notificacao(
                destinatario=[email],
                assunto="Novo gerente",
                contexto={
                    'username': username,
                    'email': email,
                    'cargo': 'gerente',
                    'senha': user._temp_password
                },
                template='notifications/adicao_gestor.html'
            )
            # Limpa os atributos temporários
            del user._send_welcome_email
            del user._temp_password

        return user

    def create_superuser(self, email, username, password, **extra_fields):
        extra_fields.setdefault('is_admin', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        return self.create_user(
            email=email,
            password=password,
            username=username,
            **extra_fields
        )


class Gerente(AbstractBaseUser):
    id_random = models.CharField(
        unique=True,
        default=generate_id_random,
        max_length=20
    )
    email = models.EmailField(verbose_name="email", max_length=100, unique=True)
    username = models.CharField(max_length=100, unique=False)
    STATUS_OPCOES = [
        ('Mobilizado', 'Mobilizado'),
        ('Desmobilizado', 'Desmobilizado'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_OPCOES, default='Mobilizado')
    date_joined = models.DateTimeField(verbose_name='date joined', auto_now_add=True)
    last_login = models.DateTimeField(verbose_name='last login', auto_now=True)
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    empresasecundaria = models.ManyToManyField(
        to=EmpresaSecundaria,
        blank=False,
        related_name='REmpresaSecundariagerente'
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = GerenteManager()

    def __str__(self):
        return self.username + " | " + self.email

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def has_module_perms(self, app_label):
        return True

    def save(self, *args, **kwargs):
        if not self.pk and not self.password:
            senha_gerada = get_random_string(length=12)
            self.set_password(senha_gerada)
            enviar_notificacao(
                destinatario=[self.email],
                assunto="Novo gerente",
                contexto={
                    'username': self.username,
                    'email': self.email,
                    'cargo': 'gerente',
                    'senha': senha_gerada
                },
                template='notifications/adicao_gestor.html'
            )

        super().save(*args, **kwargs)