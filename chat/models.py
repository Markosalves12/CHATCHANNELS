# chat/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    last_activity = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username