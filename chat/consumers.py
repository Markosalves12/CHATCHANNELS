# # chat/consumers.py
# import json
# from channels.generic.websocket import AsyncWebsocketConsumer
# from asgiref.sync import sync_to_async
# from django.contrib.auth.models import User
# from django.utils import timezone
# from .models import ChatRoom, Message, UserProfile, RoomMembership
#
# class ChatConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
#         self.room_group_name = f"chat_{self.room_name}"
#         self.user = self.scope["user"]
#
#         if not self.user.is_authenticated:
#             await self.close()
#             return
#
#         # Verificar acesso à sala
#         has_access = await self.check_room_access()
#         if not has_access:
#             await self.close()
#             return
#
#         # Garantir que usuário seja membro em salas privadas
#         room = await sync_to_async(ChatRoom.objects.get)(name=self.room_name)
#         if room.is_private:
#             await self.ensure_user_membership(room)
#
#         # Atualizar última atividade
#         await self.update_user_activity()
#
#         # Entrar no grupo da sala
#         await self.channel_layer.group_add(self.room_group_name, self.channel_name)
#         await self.accept()
#
#         # Enviar histórico de mensagens
#         await self.send_message_history()
#
#     # ------------------------
#     # Utils
#     # ------------------------
#
#     @sync_to_async
#     def update_user_activity(self):
#         """Atualiza a última atividade do usuário"""
#         profile, _ = UserProfile.objects.get_or_create(user=self.user)
#         profile.last_activity = timezone.now()
#         profile.save()
#
#     @sync_to_async
#     def check_room_access(self):
#         """Verifica se usuário tem acesso à sala"""
#         try:
#             room = ChatRoom.objects.get(name=self.room_name)
#             return room.can_user_access(self.user)
#         except ChatRoom.DoesNotExist:
#             # Cria sala pública se não existir
#             ChatRoom.objects.create(
#                 name=self.room_name,
#                 created_by=self.user,
#                 is_private=False
#             )
#             return True
#
#     @sync_to_async
#     def ensure_user_membership(self, room):
#         """Garante que usuário é membro da sala privada"""
#         if room.is_private and not room.members.filter(id=self.user.id).exists():
#             room.add_member(self.user, added_by=room.created_by)
#
#     # ------------------------
#     # Histórico de mensagens
#     # ------------------------
#
#     async def send_message_history(self):
#         """Envia histórico de mensagens visíveis para o usuário"""
#         messages_data = await self.get_messages_history_data()
#         for message_data in messages_data:
#             await self.send(text_data=json.dumps({
#                 "type": "chat_message",
#                 "message": message_data["content"],
#                 "author": message_data["author_username"],
#                 "author_id": message_data["author_id"],
#                 "message_id": message_data["id"],
#                 "timestamp": message_data["timestamp"].isoformat(),
#                 "is_history": True
#             }))
#
#     @sync_to_async
#     def get_messages_history_data(self):
#         """Obtém histórico de mensagens"""
#         try:
#             room = ChatRoom.objects.get(name=self.room_name)
#             messages = Message.objects.filter(room=room).select_related("author").order_by("timestamp")[:50]
#
#             return [
#                 {
#                     "id": msg.id,
#                     "content": msg.content,
#                     "author_username": msg.author.username,
#                     "author_id": msg.author.id,
#                     "timestamp": msg.timestamp,
#                 }
#                 for msg in messages
#             ]
#         except ChatRoom.DoesNotExist:
#             return []
#
#     # ------------------------
#     # Receber mensagens
#     # ------------------------
#
#     async def receive(self, text_data):
#         try:
#             data = json.loads(text_data)
#             message_type = data.get("type", "chat_message")
#
#             # Checar acesso
#             has_access = await self.check_room_access()
#             if not has_access:
#                 await self.send(text_data=json.dumps({
#                     "type": "error",
#                     "message": "Acesso negado"
#                 }))
#                 return
#
#             if message_type == "mark_as_read":
#                 await self.mark_messages_as_read()
#
#             elif message_type == "typing":
#                 await self.update_user_activity()
#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         "type": "user.activity",
#                         "user_id": self.user.id,
#                         "username": self.user.username,
#                         "is_typing": data.get("is_typing", False),
#                     }
#                 )
#
#             else:
#                 # Enviar mensagem
#                 message_content = data.get("message", "")
#                 if message_content:
#                     await self.update_user_activity()
#                     message = await self.save_message(message_content)
#
#                     if message:
#                         await self.channel_layer.group_send(
#                             self.room_group_name,
#                             {
#                                 "type": "chat.message",
#                                 "message": message_content,
#                                 "author": self.user.username,
#                                 "author_id": self.user.id,
#                                 "message_id": message.id,
#                                 "timestamp": message.timestamp.isoformat(),
#                             }
#                         )
#         except json.JSONDecodeError:
#             print("Erro ao decodificar JSON")
#
#     @sync_to_async
#     def save_message(self, message_content):
#         """Salva mensagem no banco"""
#         try:
#             room, _ = ChatRoom.objects.get_or_create(name=self.room_name)
#             return Message.objects.create(
#                 room=room,
#                 author=self.user,
#                 content=message_content
#             )
#         except Exception as e:
#             print(f"Erro ao salvar mensagem: {e}")
#             return None
#
#     # ------------------------
#     # Leitura de mensagens (simplificado)
#     # ------------------------
#
#     async def mark_messages_as_read(self):
#         """Marca mensagens como lidas"""
#         try:
#             await self.update_user_activity()
#             await sync_to_async(self._mark_messages_as_read_sync)()
#         except Exception as e:
#             print(f"Erro ao marcar como lido: {e}")
#
#     def _mark_messages_as_read_sync(self):
#         try:
#             room = ChatRoom.objects.get(name=self.room_name)
#             unread_messages = Message.objects.filter(room=room).exclude(read_by=self.user)
#
#             for msg in unread_messages:
#                 msg.mark_as_read(self.user)
#
#             return unread_messages.count()
#         except ChatRoom.DoesNotExist:
#             return 0
#
#     # ------------------------
#     # Eventos do grupo
#     # ------------------------
#
#     async def chat_message(self, event):
#         await self.send(text_data=json.dumps({
#             "type": "chat_message",
#             "message": event["message"],
#             "author": event["author"],
#             "author_id": event["author_id"],
#             "message_id": event["message_id"],
#             "timestamp": event["timestamp"],
#         }))
#
#     async def user_activity(self, event):
#         await self.send(text_data=json.dumps({
#             "type": "user_activity",
#             "user_id": event["user_id"],
#             "username": event["username"],
#             "is_typing": event["is_typing"],
#         }))


# import json
# from channels.generic.websocket import AsyncWebsocketConsumer
# from asgiref.sync import sync_to_async
# from django.utils import timezone
# from .models import ChatRoom, Message, UserProfile
# from .utils import get_user_chat_rooms_data  # Importa a função refatorada
#
#
# class ChatConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
#         self.room_group_name = f"chat_{self.room_name}"
#         self.user = self.scope["user"]
#
#         if not self.user.is_authenticated:
#             await self.close()
#             return
#
#         # Cria um grupo pessoal para o usuário
#         self.user_group_name = f"user_{self.user.id}"
#
#         # Verificar acesso à sala
#         has_access = await self.check_room_access()
#         if not has_access:
#             await self.close()
#             return
#
#         # Garantir que usuário seja membro em salas privadas
#         room = await sync_to_async(ChatRoom.objects.get)(name=self.room_name)
#         if room.is_private:
#             await self.ensure_user_membership(room)
#
#         # Atualizar última atividade
#         await self.update_user_activity()
#
#         # Entrar no grupo pessoal e no grupo da sala
#         await self.channel_layer.group_add(self.user_group_name, self.channel_name)
#         await self.channel_layer.group_add(self.room_group_name, self.channel_name)
#         await self.accept()
#
#         # Enviar histórico de mensagens
#         await self.send_message_history()
#
#     async def disconnect(self, close_code):
#         # Sair dos grupos ao desconectar
#         await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
#         await self.channel_layer.group_discard(self.user_group_name, self.channel_name)
#
#     # ------------------------
#     # Utils
#     # ------------------------
#
#     @sync_to_async
#     def update_user_activity(self):
#         """Atualiza a última atividade do usuário"""
#         profile, _ = UserProfile.objects.get_or_create(user=self.user)
#         profile.last_activity = timezone.now()
#         profile.save()
#
#     @sync_to_async
#     def check_room_access(self):
#         """Verifica se usuário tem acesso à sala"""
#         try:
#             room = ChatRoom.objects.get(name=self.room_name)
#             return room.can_user_access(self.user)
#         except ChatRoom.DoesNotExist:
#             # Cria sala pública se não existir
#             ChatRoom.objects.create(
#                 name=self.room_name,
#                 created_by=self.user,
#                 is_private=False
#             )
#             return True
#
#     @sync_to_async
#     def ensure_user_membership(self, room):
#         """Garante que usuário é membro da sala privada"""
#         if room.is_private and not room.members.filter(id=self.user.id).exists():
#             room.add_member(self.user, added_by=room.created_by)
#
#     # ------------------------
#     # Histórico de mensagens
#     # ------------------------
#
#     async def send_message_history(self):
#         """Envia histórico de mensagens visíveis para o usuário"""
#         messages_data = await self.get_messages_history_data()
#         for message_data in messages_data:
#             await self.send(text_data=json.dumps({
#                 "type": "chat_message",
#                 "message": message_data["content"],
#                 "author": message_data["author_username"],
#                 "author_id": message_data["author_id"],
#                 "message_id": message_data["id"],
#                 "timestamp": message_data["timestamp"].isoformat(),
#                 "is_history": True
#             }))
#
#     @sync_to_async
#     def get_messages_history_data(self):
#         """Obtém histórico de mensagens"""
#         try:
#             room = ChatRoom.objects.get(name=self.room_name)
#             messages = Message.objects.filter(room=room).select_related("author").order_by("timestamp")[:50]
#             return [
#                 {
#                     "id": msg.id,
#                     "content": msg.content,
#                     "author_username": msg.author.username,
#                     "author_id": msg.author.id,
#                     "timestamp": msg.timestamp,
#                 }
#                 for msg in messages
#             ]
#         except ChatRoom.DoesNotExist:
#             return []
#
#     # ------------------------
#     # Receber mensagens
#     # ------------------------
#
#     async def receive(self, text_data):
#         try:
#             data = json.loads(text_data)
#             message_type = data.get("type", "chat_message")
#
#             # Checar acesso
#             has_access = await self.check_room_access()
#             if not has_access:
#                 await self.send(text_data=json.dumps({
#                     "type": "error",
#                     "message": "Acesso negado"
#                 }))
#                 return
#
#             if message_type == "mark_as_read":
#                 await self.mark_messages_as_read()
#
#             elif message_type == "typing":
#                 await self.update_user_activity()
#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         "type": "user.activity",
#                         "user_id": self.user.id,
#                         "username": self.user.username,
#                         "is_typing": data.get("is_typing", False),
#                     }
#                 )
#
#             else:
#                 # Enviar mensagem
#                 message_content = data.get("message", "")
#                 if message_content:
#                     await self.update_user_activity()
#                     message, room_members = await self.save_message(message_content)
#
#                     if message:
#                         await self.channel_layer.group_send(
#                             self.room_group_name,
#                             {
#                                 "type": "chat.message",
#                                 "message": message_content,
#                                 "author": self.user.username,
#                                 "author_id": self.user.id,
#                                 "message_id": message.id,
#                                 "timestamp": message.timestamp.isoformat(),
#                             }
#                         )
#                         # Notificar outros usuários na sala sobre a nova mensagem
#                         await self.notify_users_of_new_message(room_members)
#
#         except json.JSONDecodeError:
#             print("Erro ao decodificar JSON")
#
#     @sync_to_async
#     def save_message(self, message_content):
#         """Salva mensagem no banco e retorna a sala e seus membros."""
#         try:
#             room, _ = ChatRoom.objects.get_or_create(name=self.room_name)
#             message = Message.objects.create(
#                 room=room,
#                 author=self.user,
#                 content=message_content
#             )
#             # Retorna a mensagem salva e os membros da sala para notificação posterior
#             return message, list(room.members.all())
#         except Exception as e:
#             print(f"Erro ao salvar mensagem: {e}")
#             return None, []
#
#     # ------------------------
#     # Notificação de Nova Mensagem
#     # ------------------------
#
#     async def notify_users_of_new_message(self, room_members):
#         """Notifica cada membro da sala (exceto o autor) sobre a nova mensagem."""
#         for member in room_members:
#             # Não notifica o autor da mensagem, pois ele a verá imediatamente
#             if member.id != self.user.id:
#                 user_group_name = f"user_{member.id}"
#                 # Obtém os dados de salas para o usuário e envia a atualização
#                 updated_room_data = await sync_to_async(get_user_chat_rooms_data)(member)
#
#                 await self.channel_layer.group_send(
#                     user_group_name,
#                     {
#                         "type": "unread.count.update",
#                         "room_data": updated_room_data,
#                     }
#                 )
#
#     # ------------------------
#     # Leitura de mensagens (simplificado)
#     # ------------------------
#
#     async def mark_messages_as_read(self):
#         """Marca mensagens como lidas e notifica o usuário"""
#         try:
#             await self.update_user_activity()
#             unread_count_change = await sync_to_async(self._mark_messages_as_read_sync)()
#
#             if unread_count_change > 0:
#                 # Envia uma atualização para o usuário individualmente
#                 await self.send_unread_count_update()
#
#         except Exception as e:
#             print(f"Erro ao marcar como lido: {e}")
#
#     def _mark_messages_as_read_sync(self):
#         try:
#             room = ChatRoom.objects.get(name=self.room_name)
#             unread_messages = Message.objects.filter(room=room).exclude(read_by=self.user)
#
#             for msg in unread_messages:
#                 msg.mark_as_read(self.user)
#
#             return unread_messages.count()
#         except ChatRoom.DoesNotExist:
#             return 0
#
#     # ------------------------
#     # Atualização de Contagem de Não Lidas
#     # ------------------------
#
#     async def send_unread_count_update(self):
#         """Obtém os dados atualizados e envia para o grupo pessoal do usuário."""
#         try:
#             updated_room_data = await sync_to_async(get_user_chat_rooms_data)(self.user)
#
#             await self.channel_layer.group_send(
#                 self.user_group_name,
#                 {
#                     "type": "unread.count.update",
#                     "room_data": updated_room_data,
#                 }
#             )
#         except Exception as e:
#             print(f"Erro ao enviar atualização de não lidas: {e}")
#
#     # ------------------------
#     # Eventos do grupo
#     # ------------------------
#
#     async def chat_message(self, event):
#         await self.send(text_data=json.dumps({
#             "type": "chat_message",
#             "message": event["message"],
#             "author": event["author"],
#             "author_id": event["author_id"],
#             "message_id": event["message_id"],
#             "timestamp": event["timestamp"],
#         }))
#
#     async def user_activity(self, event):
#         await self.send(text_data=json.dumps({
#             "type": "user_activity",
#             "user_id": event["user_id"],
#             "username": event["username"],
#             "is_typing": event["is_typing"],
#         }))
#
#     async def unread_count_update(self, event):
#         """Manipula o evento de atualização de contagem de não lidas."""
#         await self.send(text_data=json.dumps({
#             "type": "unread_count_update",
#             "room_data": event["room_data"],
#         }))


import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils import timezone
from .models import ChatRoom, Message, UserProfile
from .utils import get_user_chat_rooms_data


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        # Cria um grupo pessoal para o usuário
        self.user_group_name = f"user_{self.user.id}"

        # Verificar acesso à sala
        has_access = await self.check_room_access()
        if not has_access:
            await self.close()
            return

        # Garantir que usuário seja membro em salas privadas
        room = await sync_to_async(ChatRoom.objects.get)(name=self.room_name)
        if room.is_private:
            await self.ensure_user_membership(room)

        # Atualizar última atividade
        await self.update_user_activity()

        # Entrar no grupo pessoal e no grupo da sala
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Enviar histórico de mensagens
        await self.send_message_history()

    async def disconnect(self, close_code):
        # Sair dos grupos ao desconectar
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        await self.channel_layer.group_discard(self.user_group_name, self.channel_name)

    # ------------------------
    # Utils
    # ------------------------

    @sync_to_async
    def update_user_activity(self):
        """Atualiza a última atividade do usuário"""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.last_activity = timezone.now()
        profile.save()

    @sync_to_async
    def check_room_access(self):
        """Verifica se usuário tem acesso à sala"""
        try:
            room = ChatRoom.objects.get(name=self.room_name)
            return room.can_user_access(self.user)
        except ChatRoom.DoesNotExist:
            # Cria sala pública se não existir
            ChatRoom.objects.create(
                name=self.room_name,
                created_by=self.user,
                is_private=False
            )
            return True

    @sync_to_async
    def ensure_user_membership(self, room):
        """Garante que usuário é membro da sala privada"""
        if room.is_private and not room.members.filter(id=self.user.id).exists():
            room.add_member(self.user, added_by=room.created_by)

    # ------------------------
    # Histórico de mensagens
    # ------------------------

    async def send_message_history(self):
        """Envia histórico de mensagens visíveis para o usuário"""
        messages_data = await self.get_messages_history_data()
        for message_data in messages_data:
            await self.send(text_data=json.dumps({
                "type": "chat_message",
                "message": message_data["content"],
                "author": message_data["author_username"],
                "author_id": message_data["author_id"],
                "message_id": message_data["id"],
                "timestamp": message_data["timestamp"].isoformat(),
                "is_history": True
            }))

    @sync_to_async
    def get_messages_history_data(self):
        """Obtém histórico de mensagens"""
        try:
            room = ChatRoom.objects.get(name=self.room_name)
            messages = Message.objects.filter(room=room).select_related("author").order_by("timestamp")[:50]
            return [
                {
                    "id": msg.id,
                    "content": msg.content,
                    "author_username": msg.author.username,
                    "author_id": msg.author.id,
                    "timestamp": msg.timestamp,
                }
                for msg in messages
            ]
        except ChatRoom.DoesNotExist:
            return []

    # ------------------------
    # Receber mensagens
    # ------------------------

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get("type", "chat_message")

            # Checar acesso
            has_access = await self.check_room_access()
            if not has_access:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "Acesso negado"
                }))
                return

            if message_type == "mark_as_read":
                await self.mark_messages_as_read()

            elif message_type == "typing":
                await self.update_user_activity()
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "user.activity",
                        "user_id": self.user.id,
                        "username": self.user.username,
                        "is_typing": data.get("is_typing", False),
                    }
                )

            else:
                # Enviar mensagem
                message_content = data.get("message", "")
                if message_content:
                    await self.update_user_activity()
                    message, room_members = await self.save_message(message_content)

                    if message:
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                "type": "chat.message",
                                "message": message_content,
                                "author": self.user.username,
                                "author_id": self.user.id,
                                "message_id": message.id,
                                "timestamp": message.timestamp.isoformat(),
                            }
                        )
                        # Notificar o autor da mensagem para reordenar sua barra lateral
                        await self.send_unread_count_update()

                        # Notificar outros usuários na sala sobre a nova mensagem
                        await self.notify_users_of_new_message(room_members)

        except json.JSONDecodeError:
            print("Erro ao decodificar JSON")

    @sync_to_async
    def save_message(self, message_content):
        """Salva mensagem no banco e retorna a sala e seus membros."""
        try:
            room, _ = ChatRoom.objects.get_or_create(name=self.room_name)
            message = Message.objects.create(
                room=room,
                author=self.user,
                content=message_content
            )
            # Retorna a mensagem salva e os membros da sala para notificação posterior
            return message, list(room.members.all())
        except Exception as e:
            print(f"Erro ao salvar mensagem: {e}")
            return None, []

    # ------------------------
    # Notificação de Nova Mensagem
    # ------------------------

    async def notify_users_of_new_message(self, room_members):
        """Notifica cada membro da sala (exceto o autor) sobre a nova mensagem."""
        for member in room_members:
            # Não notifica o autor da mensagem, pois ele a verá imediatamente
            if member.id != self.user.id:
                user_group_name = f"user_{member.id}"
                # Obtém os dados de salas para o usuário e envia a atualização
                updated_room_data = await sync_to_async(get_user_chat_rooms_data)(member)

                await self.channel_layer.group_send(
                    user_group_name,
                    {
                        "type": "unread.count.update",
                        "room_data": updated_room_data,
                    }
                )

    # ------------------------
    # Leitura de mensagens (simplificado)
    # ------------------------

    async def mark_messages_as_read(self):
        """Marca mensagens como lidas e notifica o usuário"""
        try:
            await self.update_user_activity()
            unread_count_change = await sync_to_async(self._mark_messages_as_read_sync)()

            if unread_count_change > 0:
                # Envia uma atualização para o usuário individualmente
                await self.send_unread_count_update()

        except Exception as e:
            print(f"Erro ao marcar como lido: {e}")

    def _mark_messages_as_read_sync(self):
        try:
            room = ChatRoom.objects.get(name=self.room_name)
            unread_messages = Message.objects.filter(room=room).exclude(read_by=self.user)

            for msg in unread_messages:
                msg.mark_as_read(self.user)

            return unread_messages.count()
        except ChatRoom.DoesNotExist:
            return 0

    # ------------------------
    # Atualização de Contagem de Não Lidas
    # ------------------------

    async def send_unread_count_update(self):
        """Obtém os dados atualizados e envia para o grupo pessoal do usuário."""
        try:
            updated_room_data = await sync_to_async(get_user_chat_rooms_data)(self.user)

            await self.channel_layer.group_send(
                self.user_group_name,
                {
                    "type": "unread.count.update",
                    "room_data": updated_room_data,
                }
            )
        except Exception as e:
            print(f"Erro ao enviar atualização de não lidas: {e}")

    # ------------------------
    # Eventos do grupo
    # ------------------------

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "message": event["message"],
            "author": event["author"],
            "author_id": event["author_id"],
            "message_id": event["message_id"],
            "timestamp": event["timestamp"],
        }))

    async def user_activity(self, event):
        await self.send(text_data=json.dumps({
            "type": "user_activity",
            "user_id": event["user_id"],
            "username": event["username"],
            "is_typing": event["is_typing"],
        }))

    async def unread_count_update(self, event):
        """Manipula o evento de atualização de contagem de não lidas."""
        await self.send(text_data=json.dumps({
            "type": "unread_count_update",
            "room_data": event["room_data"],
        }))


import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils import timezone
from .models import ChatRoom, Message, UserProfile
from .utils import get_user_chat_rooms_data


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        # Cria um grupo pessoal para o usuário
        self.user_group_name = f"user_{self.user.id}"

        # Verificar acesso à sala
        has_access = await self.check_room_access()
        if not has_access:
            await self.close()
            return

        # Garantir que usuário seja membro em salas privadas
        room = await sync_to_async(ChatRoom.objects.get)(name=self.room_name)
        if room.is_private:
            await self.ensure_user_membership(room)

        # Atualizar última atividade
        await self.update_user_activity()

        # Entrar no grupo pessoal e no grupo da sala
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Enviar histórico de mensagens
        await self.send_message_history()

    async def disconnect(self, close_code):
        # Sair dos grupos ao desconectar
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        await self.channel_layer.group_discard(self.user_group_name, self.channel_name)

    # ------------------------
    # Utils
    # ------------------------

    @sync_to_async
    def update_user_activity(self):
        """Atualiza a última atividade do usuário"""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.last_activity = timezone.now()
        profile.save()

    @sync_to_async
    def check_room_access(self):
        """Verifica se usuário tem acesso à sala"""
        try:
            room = ChatRoom.objects.get(name=self.room_name)
            return room.can_user_access(self.user)
        except ChatRoom.DoesNotExist:
            # Cria sala pública se não existir
            ChatRoom.objects.create(
                name=self.room_name,
                created_by=self.user,
                is_private=False
            )
            return True

    @sync_to_async
    def ensure_user_membership(self, room):
        """Garante que usuário é membro da sala privada"""
        if room.is_private and not room.members.filter(id=self.user.id).exists():
            room.add_member(self.user, added_by=room.created_by)

    # ------------------------
    # Histórico de mensagens
    # ------------------------

    async def send_message_history(self):
        """Envia histórico de mensagens visíveis para o usuário"""
        messages_data = await self.get_messages_history_data()
        for message_data in messages_data:
            await self.send(text_data=json.dumps({
                "type": "chat_message",
                "message": message_data["content"],
                "author": message_data["author_username"],
                "author_id": message_data["author_id"],
                "message_id": message_data["id"],
                "timestamp": message_data["timestamp"].isoformat(),
                "is_history": True
            }))

    @sync_to_async
    def get_messages_history_data(self):
        """Obtém histórico de mensagens"""
        try:
            room = ChatRoom.objects.get(name=self.room_name)
            messages = Message.objects.filter(room=room).select_related("author").order_by("timestamp")[:50]
            return [
                {
                    "id": msg.id,
                    "content": msg.content,
                    "author_username": msg.author.username,
                    "author_id": msg.author.id,
                    "timestamp": msg.timestamp,
                }
                for msg in messages
            ]
        except ChatRoom.DoesNotExist:
            return []

    # ------------------------
    # Receber mensagens
    # ------------------------

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get("type", "chat_message")

            # Checar acesso
            has_access = await self.check_room_access()
            if not has_access:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "Acesso negado"
                }))
                return

            if message_type == "mark_as_read":
                await self.mark_messages_as_read()

            elif message_type == "typing":
                await self.update_user_activity()
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "user.activity",
                        "user_id": self.user.id,
                        "username": self.user.username,
                        "is_typing": data.get("is_typing", False),
                    }
                )

            else:
                # Enviar mensagem
                message_content = data.get("message", "")
                if message_content:
                    await self.update_user_activity()
                    message, room_members = await self.save_message(message_content)

                    if message:
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                "type": "chat.message",
                                "message": message_content,
                                "author": self.user.username,
                                "author_id": self.user.id,
                                "message_id": message.id,
                                "timestamp": message.timestamp.isoformat(),
                            }
                        )
                        # Notificar o autor da mensagem para reordenar sua barra lateral
                        await self.send_unread_count_update()

                        # Notificar outros usuários na sala sobre a nova mensagem
                        await self.notify_users_of_new_message(room_members)

        except json.JSONDecodeError:
            print("Erro ao decodificar JSON")

    @sync_to_async
    def save_message(self, message_content):
        """Salva mensagem no banco e retorna a sala e seus membros."""
        try:
            room, _ = ChatRoom.objects.get_or_create(name=self.room_name)
            message = Message.objects.create(
                room=room,
                author=self.user,
                content=message_content
            )
            # Retorna a mensagem salva e os membros da sala para notificação posterior
            return message, list(room.members.all())
        except Exception as e:
            print(f"Erro ao salvar mensagem: {e}")
            return None, []

    # ------------------------
    # Notificação de Nova Mensagem
    # ------------------------

    async def notify_users_of_new_message(self, room_members):
        """Notifica cada membro da sala (exceto o autor) sobre a nova mensagem."""
        for member in room_members:
            # Não notifica o autor da mensagem, pois ele a verá imediatamente
            if member.id != self.user.id:
                user_group_name = f"user_{member.id}"
                # Obtém os dados de salas para o usuário e envia a atualização
                updated_room_data = await sync_to_async(get_user_chat_rooms_data)(member)

                await self.channel_layer.group_send(
                    user_group_name,
                    {
                        "type": "unread.count.update",
                        "room_data": updated_room_data,
                    }
                )

    # ------------------------
    # Leitura de mensagens (simplificado)
    # ------------------------

    async def mark_messages_as_read(self):
        """Marca mensagens como lidas e notifica o usuário"""
        try:
            await self.update_user_activity()
            unread_count_change = await sync_to_async(self._mark_messages_as_read_sync)()

            if unread_count_change > 0:
                # Envia uma atualização para o usuário individualmente
                await self.send_unread_count_update()

        except Exception as e:
            print(f"Erro ao marcar como lido: {e}")

    def _mark_messages_as_read_sync(self):
        try:
            room = ChatRoom.objects.get(name=self.room_name)
            unread_messages = Message.objects.filter(room=room).exclude(read_by=self.user)

            for msg in unread_messages:
                msg.mark_as_read(self.user)

            return unread_messages.count()
        except ChatRoom.DoesNotExist:
            return 0

    # ------------------------
    # Atualização de Contagem de Não Lidas
    # ------------------------

    async def send_unread_count_update(self):
        """Obtém os dados atualizados e envia para o grupo pessoal do usuário."""
        try:
            updated_room_data = await sync_to_async(get_user_chat_rooms_data)(self.user)

            await self.channel_layer.group_send(
                self.user_group_name,
                {
                    "type": "unread.count.update",
                    "room_data": updated_room_data,
                }
            )
        except Exception as e:
            print(f"Erro ao enviar atualização de não lidas: {e}")

    # ------------------------
    # Eventos do grupo
    # ------------------------

    async def user_added_to_room(self, event):
        """Manipula o evento quando o usuário é adicionado a uma sala."""
        # Obtém os dados de salas atualizados para o usuário
        updated_room_data = await sync_to_async(get_user_chat_rooms_data)(self.user)

        await self.send(text_data=json.dumps({
            "type": "notification",
            "message": f"Você foi adicionado à sala {event['room_name']} por {event['adder_name']}.",
            "room_data": updated_room_data,  # Inclui os dados para reordenar a barra lateral
        }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "message": event["message"],
            "author": event["author"],
            "author_id": event["author_id"],
            "message_id": event["message_id"],
            "timestamp": event["timestamp"],
        }))

    async def user_activity(self, event):
        await self.send(text_data=json.dumps({
            "type": "user_activity",
            "user_id": event["user_id"],
            "username": event["username"],
            "is_typing": event["is_typing"],
        }))

    async def unread_count_update(self, event):
        """Manipula o evento de atualização de contagem de não lidas."""
        await self.send(text_data=json.dumps({
            "type": "unread_count_update",
            "room_data": event["room_data"],
        }))


# import json
# from channels.generic.websocket import AsyncWebsocketConsumer
# from asgiref.sync import sync_to_async
# from django.utils import timezone
# from .models import ChatRoom, Message, UserProfile
# from .utils import get_user_chat_rooms_data
#
#
# class ChatConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
#         self.room_group_name = f"chat_{self.room_name}"
#         self.user = self.scope["user"]
#
#         if not self.user.is_authenticated:
#             await self.close()
#             return
#
#         # Cria um grupo pessoal para o usuário
#         self.user_group_name = f"user_{self.user.id}"
#
#         # Verificar acesso à sala
#         has_access = await self.check_room_access()
#         if not has_access:
#             await self.close()
#             return
#
#         # Garantir que usuário seja membro em salas privadas
#         room = await sync_to_async(ChatRoom.objects.get)(name=self.room_name)
#         if room.is_private:
#             await self.ensure_user_membership(room)
#
#         # Atualizar última atividade
#         await self.update_user_activity()
#
#         # Entrar no grupo pessoal e no grupo da sala
#         await self.channel_layer.group_add(self.user_group_name, self.channel_name)
#         await self.channel_layer.group_add(self.room_group_name, self.channel_name)
#         await self.accept()
#
#         # Enviar histórico de mensagens
#         await self.send_message_history()
#
#     async def disconnect(self, close_code):
#         # Sair dos grupos ao desconectar
#         await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
#         await self.channel_layer.group_discard(self.user_group_name, self.channel_name)
#
#     # ------------------------
#     # Utils
#     # ------------------------
#
#     @sync_to_async
#     def update_user_activity(self):
#         """Atualiza a última atividade do usuário"""
#         profile, _ = UserProfile.objects.get_or_create(user=self.user)
#         profile.last_activity = timezone.now()
#         profile.save()
#
#     @sync_to_async
#     def check_room_access(self):
#         """Verifica se usuário tem acesso à sala"""
#         try:
#             room = ChatRoom.objects.get(name=self.room_name)
#             return room.can_user_access(self.user)
#         except ChatRoom.DoesNotExist:
#             # Cria sala pública se não existir
#             ChatRoom.objects.create(
#                 name=self.room_name,
#                 created_by=self.user,
#                 is_private=False
#             )
#             return True
#
#     @sync_to_async
#     def ensure_user_membership(self, room):
#         """Garante que usuário é membro da sala privada"""
#         if room.is_private and not room.members.filter(id=self.user.id).exists():
#             room.add_member(self.user, added_by=room.created_by)
#
#     # ------------------------
#     # Histórico de mensagens
#     # ------------------------
#
#     async def send_message_history(self):
#         """Envia histórico de mensagens visíveis para o usuário"""
#         messages_data = await self.get_messages_history_data()
#         for message_data in messages_data:
#             await self.send(text_data=json.dumps({
#                 "type": "chat_message",
#                 "message": message_data["content"],
#                 "author": message_data["author_username"],
#                 "author_id": message_data["author_id"],
#                 "message_id": message_data["id"],
#                 "timestamp": message_data["timestamp"].isoformat(),
#                 "is_history": True,
#                 "is_system_message": message_data["author_username"] == 'System'  # Adiciona essa flag
#             }))
#
#     @sync_to_async
#     def get_messages_history_data(self):
#         """Obtém histórico de mensagens"""
#         try:
#             room = ChatRoom.objects.get(name=self.room_name)
#             messages = Message.objects.filter(room=room).select_related("author").order_by("timestamp")[:50]
#             return [
#                 {
#                     "id": msg.id,
#                     "content": msg.content,
#                     "author_username": msg.author.username,
#                     "author_id": msg.author.id,
#                     "timestamp": msg.timestamp,
#                 }
#                 for msg in messages
#             ]
#         except ChatRoom.DoesNotExist:
#             return []
#
#     # ------------------------
#     # Receber mensagens
#     # ------------------------
#
#     async def receive(self, text_data):
#         try:
#             data = json.loads(text_data)
#             message_type = data.get("type", "chat_message")
#
#             # Checar acesso
#             has_access = await self.check_room_access()
#             if not has_access:
#                 await self.send(text_data=json.dumps({
#                     "type": "error",
#                     "message": "Acesso negado"
#                 }))
#                 return
#
#             if message_type == "mark_as_read":
#                 await self.mark_messages_as_read()
#
#             elif message_type == "typing":
#                 await self.update_user_activity()
#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         "type": "user.activity",
#                         "user_id": self.user.id,
#                         "username": self.user.username,
#                         "is_typing": data.get("is_typing", False),
#                     }
#                 )
#
#             else:
#                 # Enviar mensagem
#                 message_content = data.get("message", "")
#                 if message_content:
#                     await self.update_user_activity()
#                     message, room_members = await self.save_message(message_content)
#
#                     if message:
#                         await self.channel_layer.group_send(
#                             self.room_group_name,
#                             {
#                                 "type": "chat.message",
#                                 "message": message_content,
#                                 "author": self.user.username,
#                                 "author_id": self.user.id,
#                                 "message_id": message.id,
#                                 "timestamp": message.timestamp.isoformat(),
#                             }
#                         )
#                         # Notificar o autor da mensagem para reordenar sua barra lateral
#                         await self.send_unread_count_update()
#
#                         # Notificar outros usuários na sala sobre a nova mensagem
#                         await self.notify_users_of_new_message(room_members)
#
#         except json.JSONDecodeError:
#             print("Erro ao decodificar JSON")
#
#     @sync_to_async
#     def save_message(self, message_content):
#         """Salva mensagem no banco e retorna a sala e seus membros."""
#         try:
#             room, _ = ChatRoom.objects.get_or_create(name=self.room_name)
#             message = Message.objects.create(
#                 room=room,
#                 author=self.user,
#                 content=message_content
#             )
#             # Retorna a mensagem salva e os membros da sala para notificação posterior
#             return message, list(room.members.all())
#         except Exception as e:
#             print(f"Erro ao salvar mensagem: {e}")
#             return None, []
#
#     # ------------------------
#     # Notificação de Nova Mensagem
#     # ------------------------
#
#     async def notify_users_of_new_message(self, room_members):
#         """Notifica cada membro da sala (exceto o autor) sobre a nova mensagem."""
#         for member in room_members:
#             # Não notifica o autor da mensagem, pois ele a verá imediatamente
#             if member.id != self.user.id:
#                 user_group_name = f"user_{member.id}"
#                 # Obtém os dados de salas para o usuário e envia a atualização
#                 updated_room_data = await sync_to_async(get_user_chat_rooms_data)(member)
#
#                 await self.channel_layer.group_send(
#                     user_group_name,
#                     {
#                         "type": "unread.count.update",
#                         "room_data": updated_room_data,
#                     }
#                 )
#
#     # ------------------------
#     # Leitura de mensagens (simplificado)
#     # ------------------------
#
#     async def mark_messages_as_read(self):
#         """Marca mensagens como lidas e notifica o usuário"""
#         try:
#             await self.update_user_activity()
#             unread_count_change = await sync_to_async(self._mark_messages_as_read_sync)()
#
#             if unread_count_change > 0:
#                 # Envia uma atualização para o usuário individualmente
#                 await self.send_unread_count_update()
#
#         except Exception as e:
#             print(f"Erro ao marcar como lido: {e}")
#
#     def _mark_messages_as_read_sync(self):
#         try:
#             room = ChatRoom.objects.get(name=self.room_name)
#             unread_messages = Message.objects.filter(room=room).exclude(read_by=self.user)
#
#             for msg in unread_messages:
#                 msg.mark_as_read(self.user)
#
#             return unread_messages.count()
#         except ChatRoom.DoesNotExist:
#             return 0
#
#     # ------------------------
#     # Atualização de Contagem de Não Lidas
#     # ------------------------
#
#     async def send_unread_count_update(self):
#         """Obtém os dados atualizados e envia para o grupo pessoal do usuário."""
#         try:
#             updated_room_data = await sync_to_async(get_user_chat_rooms_data)(self.user)
#
#             await self.channel_layer.group_send(
#                 self.user_group_name,
#                 {
#                     "type": "unread.count.update",
#                     "room_data": updated_room_data,
#                 }
#             )
#         except Exception as e:
#             print(f"Erro ao enviar atualização de não lidas: {e}")
#
#     # ------------------------
#     # Eventos do grupo
#     # ------------------------
#
#     async def chat_message(self, event):
#         is_system_message = event["author"] == 'System'
#
#         await self.send(text_data=json.dumps({
#             "type": "chat_message",
#             "message": event["message"],
#             "author": event["author"],
#             "author_id": event["author_id"],
#             "message_id": event["message_id"],
#             "timestamp": event["timestamp"],
#             "is_system_message": is_system_message
#         }))
#
#     async def user_activity(self, event):
#         await self.send(text_data=json.dumps({
#             "type": "user_activity",
#             "user_id": event["user_id"],
#             "username": event["username"],
#             "is_typing": event["is_typing"],
#         }))
#
#     async def unread_count_update(self, event):
#         """Manipula o evento de atualização de contagem de não lidas."""
#         await self.send(text_data=json.dumps({
#             "type": "unread_count_update",
#             "room_data": event["room_data"],
#         }))