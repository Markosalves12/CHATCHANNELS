# chat/models.py
from django.db import models
from django.utils import timezone
import mimetypes
import os
from django.core.exceptions import ValidationError
from chat.models import Message

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