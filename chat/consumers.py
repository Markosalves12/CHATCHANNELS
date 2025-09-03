from asgiref.sync import sync_to_async
from django.utils import timezone
from .models import Message, UserProfile
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatRoom, Attachment
from .utils import get_user_chat_rooms_data
from django.core.files.base import ContentFile
import base64
import os
import uuid

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

            # Check access
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

            elif message_type == "chat_message":
                message_content = data.get("message", "").strip()
                attachments = data.get("attachments", [])

                # Validate attachment count
                if len(attachments) > 5:  # Configurable limit
                    await self.send(text_data=json.dumps({
                        "type": "error",
                        "message": "Máximo de 5 anexos por mensagem"
                    }))
                    return

                await self.update_user_activity()
                message, room_members = await self.save_message_with_attachments(message_content, attachments)

                if message:
                    attachments_data = []
                    # Ensure attachments are committed before accessing URLs
                    related_attachments = await database_sync_to_async(list)(message.attachments.all())

                    # try:
                    #     attachments_data = await sync_to_async(message.get_attachments_data)()
                    # except Exception as e:
                    #     print(f"Erro ao obter dados de anexos: {e}")
                    #     attachments_data = []  # Fallback to empty list to avoid breaking the broadcast

                    for attachment in related_attachments:
                        attachments_data.append({
                            'file_url': attachment.file.url,
                            'original_filename': attachment.original_filename,
                            'attachment_type': attachment.attachment_type,
                            # Supondo que seu modelo Attachment tenha este campo
                        })

                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "chat_message",
                            "message": message.content,
                            "author": self.user.username,
                            "author_id": self.user.id,
                            "message_id": message.id,
                            "timestamp": message.timestamp.isoformat(),
                            "is_system_message": False,
                            "attachments": attachments_data
                        }
                    )
                    await self.send_unread_count_update()
                    await self.notify_users_of_new_message(room_members)
                else:
                    await self.send(text_data=json.dumps({
                        "type": "error",
                        "message": "Erro ao salvar mensagem ou anexos"
                    }))

        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar JSON: {e}")
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": "Formato de dados inválido"
            }))
        except Exception as e:
            print(f"Erro inesperado no receive: {e}")
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": f"Erro interno: {str(e)}"
            }))


    @sync_to_async
    def save_message_with_attachments(self, message_content, attachments):
        """
        Salva mensagem + anexos no banco de forma síncrona, mas chamada do asyncio.
        Suporta arquivos base64 com ou sem header (data:...;base64,...).
        """
        try:
            room, _ = ChatRoom.objects.get_or_create(name=self.room_name)
            message = Message.objects.create(
                room=room,
                author=self.user,
                content=message_content or ""
            )

            for att in attachments:
                try:
                    file_data = att.get("data")
                    filename = att.get("filename", "file")

                    if file_data:
                        # Decodifica como antes
                        if isinstance(file_data, str) and ";base64," in file_data:
                            _, imgstr = file_data.split(";base64,", 1)
                            decoded_file = base64.b64decode(imgstr)
                        elif isinstance(file_data, str):
                            decoded_file = base64.b64decode(file_data)
                        elif isinstance(file_data, bytes):
                            decoded_file = file_data
                        else:
                            print(f"Aviso: formato de arquivo desconhecido: {filename}")
                            continue

                        # CORREÇÃO: Preservar a extensão original corretamente
                        name, ext = os.path.splitext(filename)

                        # Se não tiver extensão, tentar detectar pelo tipo MIME
                        if not ext:
                            # Gerar um nome único com extensão baseada no tipo
                            final_filename = f"{uuid.uuid4().hex}_file"
                        else:
                            # Usar nome único mas preservar a extensão original
                            final_filename = f"{uuid.uuid4().hex}{ext}"

                        file = ContentFile(decoded_file, name=final_filename)

                        Attachment.objects.create(
                            message=message,
                            file=file,
                            original_filename=filename  # Manter o nome original para exibição
                        )

                    else:
                        print(f"Aviso: arquivo sem dados: {filename}")

                except Exception as e:
                    print(f"Erro ao salvar anexo '{filename}': {e}")


            return message, list(room.members.all())

        except Exception as e:
            print(f"Erro ao salvar mensagem com anexos: {e}")
            return None, []


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
            "attachments": event.get("attachments", []),
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

    async def user_left(self, event):
        # Envie como tipo 'user_left' em vez de 'user_activity'
        await self.send(text_data=json.dumps({
            "type": "user_left",  # Alterado para corresponder ao esperado no JS
            "username": event["username"],
        }))

    async def room_deleted(self, event):
        # Envia evento para todos os usuários conectados na sala
        await self.send(text_data=json.dumps({
            "type": "room_deleted",
            "room_name": event["room_name"],
        }))



class ChatHomeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close()
            return

        self.user_group_name = f"user_{user.id}"

        # Adiciona o usuário ao grupo pessoal
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        await self.accept()

        # Envia estado inicial (contagem de mensagens não lidas)
        await self.send_unread_counts(user)

    async def disconnect(self, close_code):
        user = self.scope["user"]
        await self.channel_layer.group_discard(
            f"user_{user.id}",
            self.channel_name
        )

    # ------------------------
    # Eventos
    # ------------------------

    async def unread_count_update(self, event):
        """Atualiza contadores de não lidas na home."""
        await self.send(text_data=json.dumps({
            "type": "unread_count_update",
            "room_data": event["room_data"]
        }))

    async def room_deleted(self, event):
        """Notifica que a sala foi excluída."""
        await self.send(text_data=json.dumps({
            "type": "room_deleted",
            "room_name": event["room_name"],
        }))

    # ------------------------
    # Utils
    # ------------------------
    @database_sync_to_async
    def send_unread_counts(self, user):
        """Envia os contadores iniciais quando o usuário se conecta."""
        room_data = get_user_chat_rooms_data(user)
        return self.send(text_data=json.dumps({
            "type": "unread_count_update",
            "room_data": room_data
        }))

    @database_sync_to_async
    def get_message_attachments(self, message_id):
        # Retorna uma lista de objetos Attachment para serem serializados
        return list(Attachment.objects.filter(message_id=message_id))