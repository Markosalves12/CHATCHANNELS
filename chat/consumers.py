from asgiref.sync import sync_to_async
from django.utils import timezone
from .models import UserProfile
from chat.models import Message
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatRoom
from attachments.models import Attachment
from .utils import get_user_chat_rooms_data
from django.core.files.base import ContentFile
import base64
import os
import uuid

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Agora usamos id_random em vez de room_name
        self.room_id_random = self.scope["url_route"]["kwargs"]["id_random"]
        self.room_group_name = f"chat_{self.room_id_random}"
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


        # Atualizar última atividade
        await self.update_user_activity()

        # Entrar no grupo pessoal e no grupo da sala
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # O histórico é carregado exclusivamente pelo endpoint HTTP.
        # Assim evitamos mensagens duplicadas entre a API e o WebSocket.

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
            room = ChatRoom.objects.get(id_random=self.room_id_random)
            return room.can_user_access(self.user)
        except ChatRoom.DoesNotExist:
            return False  # Sala não existe, não criamos automaticamente

    @sync_to_async
    def ensure_user_membership(self, room):
        """Garante que usuário é membro da sala privada"""
        if not room.members.filter(id=self.user.id).exists():
            room.add_member(self.user, added_by=room.created_by)

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

                temp_id = data.get("temp_id")  # <-- pega o temp_id do front

                # Validação básica

                if len(attachments) > 5:
                    await self.send(text_data=json.dumps({

                        "type": "error",

                        "message": "Máximo de 5 anexos por mensagem"

                    }))

                    return

                await self.update_user_activity()

                message, room_members = await self.save_message_with_attachments(message_content, attachments)

                if message:

                    attachments_data = []

                    related_attachments = await database_sync_to_async(list)(message.attachments.all())

                    for attachment in related_attachments:
                        attachments_data.append({

                            'id': attachment.id,
                            'file_url': attachment.file.url,

                            'original_filename': attachment.original_filename,

                            'attachment_type': attachment.attachment_type,

                        })

                    # Envia para todos no grupo (incluindo o autor)

                    await self.channel_layer.group_send(

                        self.room_group_name,

                        {

                            "type": "chat_message",

                            "message": message.content,

                            "author": self.user.username,

                            "author_id": self.user.id,

                            "message_id": message.id,

                            "temp_id": temp_id,  # <-- passa para front substituir placeholder

                            "timestamp": message.timestamp.isoformat(),

                            "is_system_message": False,

                            "attachments": attachments_data

                        }

                    )

                    await self.send_unread_count_update()

                    await self.notify_users_of_new_message(room_members)


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
            room = ChatRoom.objects.get(id_random=self.room_id_random)
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

                        # Preservar a extensão original corretamente
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
    # Leitura de mensagens
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
            room = ChatRoom.objects.get(id_random=self.room_id_random)
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
            "temp_id": event["temp_id"],
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
        await self.send(text_data=json.dumps({
            "type": "user_left",
            "username": event["username"],
        }))

    async def room_deleted(self, event):
        await self.send(text_data=json.dumps({
            "type": "room_deleted",
            "room_id_random": event["room_id_random"],
        }))