from django.test import TestCase
from django.urls import reverse

from gerente.models import Gerente

from .models import ChatRoom, Message


class ChatHistoryPermissionTests(TestCase):
    def setUp(self):
        self.user = Gerente.objects.create_user(
            email='criador@example.com',
            username='Criador',
            password='senha-segura',
        )
        self.room = ChatRoom.objects.create(
            name='Operações',
            created_by=self.user,
        )
        Message.objects.create(
            room=self.room,
            author=self.user,
            content='Mensagem anterior',
        )
        self.client.force_login(self.user)

    def test_history_is_hidden_by_default(self):
        response = self.client.get(
            reverse('get_message_history', args=[self.room.id_random])
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, [])

    def test_history_returns_recent_messages_when_enabled(self):
        self.room.history_enabled = True
        self.room.save(update_fields=['history_enabled'])

        response = self.client.get(
            reverse('get_message_history', args=[self.room.id_random])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['message'], 'Mensagem anterior')

    def test_user_without_access_cannot_read_private_room_history(self):
        outsider = Gerente.objects.create_user(
            email='externo@example.com',
            username='Externo',
            password='senha-segura',
        )
        self.room.is_private = True
        self.room.history_enabled = True
        self.room.save(update_fields=['is_private', 'history_enabled'])
        self.client.force_login(outsider)

        response = self.client.get(
            reverse('get_message_history', args=[self.room.id_random])
        )

        self.assertEqual(response.status_code, 403)


class DeleteRoomTests(TestCase):
    def setUp(self):
        self.creator = Gerente.objects.create_user(
            email='dono@example.com',
            username='Dono',
            password='senha-segura',
        )
        self.outsider = Gerente.objects.create_user(
            email='externo-delete@example.com',
            username='ExternoDelete',
            password='senha-segura',
        )
        self.room = ChatRoom.objects.create(
            name='Sala para excluir',
            created_by=self.creator,
        )

    def test_delete_requires_post(self):
        self.client.force_login(self.creator)
        response = self.client.get(reverse('delete_room', args=[self.room.id_random]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(ChatRoom.objects.filter(pk=self.room.pk).exists())

    def test_creator_can_delete_room_by_id_random(self):
        self.client.force_login(self.creator)
        response = self.client.post(reverse('delete_room', args=[self.room.id_random]))

        self.assertRedirects(response, reverse('chat_home'))
        self.assertFalse(ChatRoom.objects.filter(pk=self.room.pk).exists())

    def test_other_user_cannot_delete_room(self):
        self.client.force_login(self.outsider)
        response = self.client.post(reverse('delete_room', args=[self.room.id_random]))

        self.assertRedirects(response, reverse('chat_room', args=[self.room.id_random]))
        self.assertTrue(ChatRoom.objects.filter(pk=self.room.pk).exists())
