# chat/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import mimetypes
import os
from django.core.exceptions import ValidationError


class ChatRoom(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_private = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_rooms')
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(
        User,
        through='RoomMembership',
        through_fields=('room', 'user'),
        related_name='chat_rooms'
    )

    def __str__(self):
        return self.name

    def add_member(self, user, added_by=None):
        """Adiciona um membro à sala com verificação de duplicidade"""
        if added_by is None:
            added_by = user

        # Verificar se o usuário já é membro
        if self.members.filter(id=user.id).exists():
            return None

        membership, created = RoomMembership.objects.get_or_create(
            room=self,
            user=user,
            defaults={'added_by': added_by}
        )
        return membership

    def add_members(self, users, added_by=None):
        """Adiciona múltiplos membros de uma vez"""
        if added_by is None:
            added_by = self.created_by

        added_members = []
        for user in users:
            membership = self.add_member(user, added_by)
            if membership:
                added_members.append(membership)

        return added_members

    def remove_member(self, user):
        """Remove um membro da sala"""
        RoomMembership.objects.filter(room=self, user=user).delete()

    def get_member_joined_time(self, user):
        """Retorna quando o usuário foi adicionado à sala"""
        try:
            membership = RoomMembership.objects.get(room=self, user=user)
            return membership.joined_at
        except RoomMembership.DoesNotExist:
            return None

    def can_user_access(self, user):
        """Verifica se usuário tem acesso à sala"""
        if not self.is_private:
            return True
        return self.members.filter(id=user.id).exists() or self.created_by == user

    def get_members_info(self):
        """Retorna informações dos membros"""
        memberships = RoomMembership.objects.filter(room=self).select_related('user', 'added_by')
        return [
            {
                'user': membership.user.username,
                'added_by': membership.added_by.username,
                'joined_at': membership.joined_at,
                'is_creator': membership.user == self.created_by
            }
            for membership in memberships
        ]

    def get_unread_count_for_user(self, user):
        """Retorna número básico de mensagens não lidas"""
        try:
            return Message.objects.filter(
                room=self
            ).exclude(author=user).exclude(read_by=user).count()
        except:
            return 0

    class Meta:
        ordering = ['-created_at']


class RoomMembership(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='added_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['room', 'user']
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user.username} in {self.room.name} (added by {self.added_by.username})"

    def can_remove(self, requesting_user):
        """Verifica se um usuário pode remover este membro"""
        return (requesting_user == self.added_by or
                requesting_user == self.room.created_by or
                requesting_user == self.user)


class Message(models.Model):
    room = models.ForeignKey(ChatRoom, related_name='messages', on_delete=models.CASCADE)
    author = models.ForeignKey(User, related_name='messages', on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    read_by = models.ManyToManyField(User, related_name='read_messages', blank=True)

    def __str__(self):
        return f'{self.author.username}: {self.content[:50]}'

    def is_read_by(self, user):
        return self.read_by.filter(id=user.id).exists()

    def mark_as_read(self, user):
        if not self.is_read_by(user):
            self.read_by.add(user)

    def get_read_status_for_user(self, user):
        return self.read_by.filter(id=user.id).exists()

    def get_attachments_data(self):
        """Retorna informações resumidas dos anexos para o frontend"""
        return [
            {
                'id': a.id,
                'url': a.file.url,
                'filename': a.filename,
                'type': a.attachment_type,
                'original_filename': a.original_filename,
            }
            for a in self.attachments.all()
        ]



class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    last_activity = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username


def message_attachment_path(instance, filename):
    """Define o caminho de upload para anexos"""
    ext = filename.split('.')[-1]
    filename = f"{timezone.now().strftime('%Y%m%d%H%M%S')}_{instance.message.id}.{ext}"
    return os.path.join('chat_attachments', str(instance.message.room.id), filename)


def validate_file_size(file):
    max_size_mb = 10
    if file.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f"Tamanho máximo permitido é {max_size_mb} MB")


class Attachment(models.Model):
    ATTACHMENT_TYPES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('pdf', 'PDF'),
        ('other', 'Other'),
    ]

    message = models.ForeignKey(to=Message, related_name='attachments', on_delete=models.CASCADE, null=True, blank=True)
    file = models.FileField(upload_to=message_attachment_path, validators=[validate_file_size])
    attachment_type = models.CharField(max_length=10, choices=ATTACHMENT_TYPES, default='other')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    original_filename = models.CharField(max_length=255)

    @property
    def filename(self):
        return os.path.basename(self.file.name)

    def save(self, *args, **kwargs):
        if not self.original_filename:
            self.original_filename = self.file.name

        # Detectar tipo com mais precisão
        if not self.attachment_type or self.attachment_type == 'other':
            self.detect_attachment_type()

        super().save(*args, **kwargs)

    def detect_attachment_type(self):
        """Detecta o tipo de anexo com mais precisão"""
        filename = self.original_filename.lower()

        # Mapeamento de extensões para tipos
        extension_mapping = {
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'],
            'video': ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv'],
            'audio': ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'],
            'pdf': ['.pdf'],
            'document': ['.doc', '.docx', '.txt', '.rtf'],
            'spreadsheet': ['.xls', '.xlsx', '.csv'],
            'presentation': ['.ppt', '.pptx'],
            'archive': ['.zip', '.rar', '.7z', '.tar', '.gz']
        }

        # Verificar por extensão primeiro
        for att_type, extensions in extension_mapping.items():
            if any(filename.endswith(ext) for ext in extensions):
                self.attachment_type = att_type
                return

        # Se não encontrou por extensão, tentar por mimetype
        mime, _ = mimetypes.guess_type(self.original_filename)
        if mime:
            if mime.startswith('image'):
                self.attachment_type = 'image'
            elif mime.startswith('video'):
                self.attachment_type = 'video'
            elif mime.startswith('audio'):
                self.attachment_type = 'audio'
            elif mime == 'application/pdf':
                self.attachment_type = 'pdf'
            elif mime.startswith('text') or 'document' in mime:
                self.attachment_type = 'document'
            elif 'spreadsheet' in mime:
                self.attachment_type = 'spreadsheet'
            elif 'presentation' in mime:
                self.attachment_type = 'presentation'
            elif 'archive' in mime or 'compressed' in mime:
                self.attachment_type = 'archive'

    def __str__(self):
        return f"{self.attachment_type} - {self.original_filename}"