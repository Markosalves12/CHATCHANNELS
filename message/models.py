# chat/models.py
from django.db import models
from django.contrib.auth.models import User
from chat.models import ChatRoom



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