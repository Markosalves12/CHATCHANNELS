from django.utils import timezone
from django.utils import timezone
from .utils import get_user_chat_rooms_data
import json
import base64
from django.core.files.base import ContentFile
import os
import uuid
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import ChatRoom, Message, UserProfile
from attachments.models import Attachment
import mimetypes


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

        # Garantir que usuário seja membro em salas privadas
        room = await sync_to_async(ChatRoom.objects.get)(id_random=self.room_id_random)
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
            room = ChatRoom.objects.get(id_random=self.room_id_random)
            return room.can_user_access(self.user)
        except ChatRoom.DoesNotExist:
            return False  # Sala não existe, não criamos automaticamente

    @sync_to_async
    def ensure_user_membership(self, room):
        """Garante que usuário é membro da sala privada"""
        if room.is_private and not room.members.filter(id=self.user.id).exists():
            room.add_member(self.user, added_by=room.created_by)

    ### NOVO: Função util para obter dados de anexos (usada em updates)
    @sync_to_async
    def get_attachments_data(self, message):
        """Obtém dados de anexos para broadcast"""
        attachments_data = []
        related_attachments = list(message.attachments.all())
        for att in related_attachments:
            # Se attachment_type não existir no model, calcule aqui
            if not hasattr(att, 'attachment_type') or not att.attachment_type:
                mime, _ = mimetypes.guess_type(att.file.name)
                att_type = mime.split("/")[0] if mime else "document"
                if mime == "application/pdf":
                    att_type = "pdf"
            else:
                att_type = att.attachment_type

            attachments_data.append({
                'id': att.id,  # NOVO: Inclui ID para frontend deletar/editar
                'file_url': att.file.url,
                'original_filename': att.original_filename,
                'attachment_type': att_type,
            })
        return attachments_data

    # ------------------------
    # Histórico de mensagens
    # ------------------------

    async def send_message_history(self):
        """Envia histórico de mensagens visíveis para o usuário"""
        messages_data = await self.get_messages_history_data()
        for message_data in messages_data:
            # NOVO: Adicione attachments no histórico
            attachments_data = await self.get_attachments_data(message_data['message_obj'])  # Assuma que get_messages_history_data retorna obj também
            await self.send(text_data=json.dumps({
                "type": "chat_message",
                "message": message_data["content"],
                "author": message_data["author_username"],
                "author_id": message_data["author_id"],
                "message_id": message_data["id"],
                "timestamp": message_data["timestamp"].isoformat(),
                "is_history": True,
                "attachments": attachments_data  # NOVO
            }))

    @sync_to_async
    def get_messages_history_data(self):
        """Obtém histórico de mensagens"""
        try:
            room = ChatRoom.objects.get(id_random=self.room_id_random)
            # NOVO: Filtra is_deleted=False e inclui attachments
            messages = Message.objects.filter(
                room=room,
                is_deleted=False  # NOVO: Não envia deletadas
            ).select_related("author").order_by("timestamp")[:50]
            return [
                {
                    "id": msg.id,
                    "content": msg.content,
                    "author_username": msg.author.username,
                    "author_id": msg.author.id,
                    "timestamp": msg.timestamp,
                    "message_obj": msg  # NOVO: Para acessar attachments no send
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

            ### NOVO: Deletar mensagem
            elif message_type == "delete_message":
                message_id = data.get("message_id")
                if not message_id:
                    await self.send(text_data=json.dumps({"type": "error", "message": "ID da mensagem obrigatório"}))
                    return
                try:
                    message = await sync_to_async(Message.objects.get)(id=message_id, author=self.user, room__id_random=self.room_id_random)
                    if message.is_deleted:
                        return  # Já deletada
                    await sync_to_async(lambda: message.delete_message() or setattr(message, 'is_deleted', True) or message.save())()  # Assuma método delete_message se tiver, senão set is_deleted=True
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "chat.message.deleted",
                            "message_id": message_id,
                            "room_id_random": self.room_id_random
                        }
                    )
                    await self.send_unread_count_update()  # Opcional: update counts se afetar
                except Message.DoesNotExist:
                    await self.send(text_data=json.dumps({"type": "error", "message": "Mensagem não encontrada ou não autorizada"}))

            ### NOVO: Editar mensagem (texto + remover anexos)
            elif message_type == "edit_message":
                message_id = data.get("message_id")
                new_content = data.get("content", "").strip()
                attachments_to_delete = data.get("attachments_to_delete", [])  # Lista de IDs
                if not message_id:
                    await self.send(text_data=json.dumps({"type": "error", "message": "ID da mensagem obrigatório"}))
                    return
                try:
                    message = await sync_to_async(Message.objects.get)(id=message_id, author=self.user, room__id_random=self.room_id_random)
                    if message.is_deleted:
                        await self.send(text_data=json.dumps({"type": "error", "message": "Mensagem já deletada"}))
                        return
                    # Atualiza content se fornecido
                    if new_content:
                        await sync_to_async(lambda: setattr(message, 'content', new_content) or message.save())()
                    # Remove anexos
                    if attachments_to_delete:
                        await sync_to_async(Attachment.objects.filter(id__in=attachments_to_delete, message=message).delete)()
                    # Obtém attachments atualizados
                    attachments_data = await self.get_attachments_data(message)
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "chat.message.updated",
                            "message_id": message_id,
                            "content": message.content,
                            "attachments": attachments_data,
                            "timestamp": message.timestamp.isoformat(),
                            "author": self.user.username,
                            "author_id": self.user.id
                        }
                    )
                    await self.send_unread_count_update()
                except Message.DoesNotExist:
                    await self.send(text_data=json.dumps({"type": "error", "message": "Mensagem não encontrada ou não autorizada"}))

            ### NOVO: Deletar anexo individual
            elif message_type == "delete_attachment":
                attachment_id = data.get("attachment_id")
                if not attachment_id:
                    await self.send(text_data=json.dumps({"type": "error", "message": "ID do anexo obrigatório"}))
                    return
                try:
                    attachment = await sync_to_async(Attachment.objects.get)(id=attachment_id, message__author=self.user, message__room__id_random=self.room_id_random)
                    message = attachment.message
                    await sync_to_async(attachment.delete)()
                    # Broadcast update da mensagem
                    attachments_data = await self.get_attachments_data(message)
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "chat.message.updated",
                            "message_id": message.id,
                            "content": message.content,
                            "attachments": attachments_data,
                            "timestamp": message.timestamp.isoformat(),
                            "author": self.user.username,
                            "author_id": self.user.id
                        }
                    )
                    await self.send_unread_count_update()
                except Attachment.DoesNotExist:
                    await self.send(text_data=json.dumps({"type": "error", "message": "Anexo não encontrado ou não autorizado"}))

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
                    attachments_data = await self.get_attachments_data(message)  # NOVO: Usa a função util

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
                            "attachments": attachments_data  # NOVO: Já inclui IDs
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

                        new_attachment = Attachment.objects.create(
                            message=message,
                            file=file,
                            original_filename=filename  # Manter o nome original para exibição
                            # Se attachment_type no model, defina aqui baseado em mimetypes
                        )
                        # Exemplo: new_attachment.attachment_type = ... ; new_attachment.save()

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
            # NOVO: Filtra is_deleted=False
            unread_messages = Message.objects.filter(
                room=room,
                is_deleted=False
            ).exclude(read_by=self.user)

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

    ### NOVO: Handler para mensagem deletada
    async def chat_message_deleted(self, event):
        """Broadcast para deletar mensagem no frontend"""
        await self.send(text_data=json.dumps({
            "type": "message_deleted",
            "message_id": event["message_id"],
        }))

    ### NOVO: Handler para mensagem atualizada
    async def chat_message_updated(self, event):
        """Broadcast para atualizar mensagem no frontend"""
        await self.send(text_data=json.dumps({
            "type": "message_updated",
            "message_id": event["message_id"],
            "content": event["content"],
            "attachments": event["attachments"],
            "timestamp": event["timestamp"],
        }))



# class ChatHomeConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         user = self.scope["user"]
#         if not user.is_authenticated:
#             await self.close()
#             return
#
#         self.user_group_name = f"user_{user.id}"
#
#         # Adiciona o usuário ao grupo pessoal
#         await self.channel_layer.group_add(
#             self.user_group_name,
#             self.channel_name
#         )
#         await self.accept()
#
#         # Envia estado inicial (contagem de mensagens não lidas)
#         await self.send_unread_counts(user)
#
#     async def disconnect(self, close_code):
#         user = self.scope["user"]
#         await self.channel_layer.group_discard(
#             f"user_{user.id}",
#             self.channel_name
#         )
#
#     # ------------------------
#     # Eventos
#     # ------------------------
#
#     async def unread_count_update(self, event):
#         """Atualiza contadores de não lidas na home."""
#         await self.send(text_data=json.dumps({
#             "type": "unread_count_update",
#             "room_data": event["room_data"]
#         }))
#
#     async def room_deleted(self, event):
#         """Notifica que a sala foi excluída."""
#         await self.send(text_data=json.dumps({
#             "type": "room_deleted",
#             "room_name": event["room_name"],
#         }))
#
#     # ------------------------
#     # Utils
#     # ------------------------
#     @database_sync_to_async
#     def send_unread_counts(self, user):
#         """Envia os contadores iniciais quando o usuário se conecta."""
#         room_data = get_user_chat_rooms_data(user)
#         return self.send(text_data=json.dumps({
#             "type": "unread_count_update",
#             "room_data": room_data
#         }))
#
#     @database_sync_to_async
#     def get_message_attachments(self, message_id):
#         # Retorna uma lista de objetos Attachment para serem serializados
#         return list(Attachment.objects.filter(message_id=message_id))