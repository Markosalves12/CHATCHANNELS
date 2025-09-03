# chat/admin.py
from django.contrib import admin
from .models import ChatRoom, RoomMembership, Message, UserProfile, Attachment
from django.utils import timezone
from django.contrib.auth.models import User

@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_private', 'created_by', 'created_at', 'member_count')
    list_filter = ('is_private', 'created_at')
    search_fields = ('name', 'created_by__username')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    # Exibir contagem de membros
    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Número de Membros'

    # Ação para tornar uma sala pública ou privada
    actions = ['make_public', 'make_private']

    def make_public(self, request, queryset):
        queryset.update(is_private=False)
        self.message_user(request, "As salas selecionadas foram tornadas públicas.")
    make_public.short_description = "Tornar salas públicas"

    def make_private(self, request, queryset):
        queryset.update(is_private=True)
        self.message_user(request, "As salas selecionadas foram tornadas privadas.")
    make_private.short_description = "Tornar salas privadas"


@admin.register(RoomMembership)
class RoomMembershipAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'added_by', 'joined_at')
    list_filter = ('room__name', 'joined_at')
    search_fields = ('room__name', 'user__username', 'added_by__username')
    date_hierarchy = 'joined_at'
    ordering = ('-joined_at',)
    readonly_fields = ('joined_at',)

    # Ação para remover membros
    actions = ['remove_members']

    def remove_members(self, request, queryset):
        for membership in queryset:
            membership.room.remove_member(membership.user)
        self.message_user(request, "Os membros selecionados foram removidos das salas.")
    remove_members.short_description = "Remover membros das salas"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'author', 'content_preview', 'timestamp', 'read_by_count')
    list_filter = ('room__name', 'timestamp')
    search_fields = ('room__name', 'author__username', 'content')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp',)

    # Exibir trecho do conteúdo
    def content_preview(self, obj):
        return obj.content[:50] + ('...' if len(obj.content) > 50 else '')
    content_preview.short_description = 'Conteúdo'

    # Exibir contagem de leitores
    def read_by_count(self, obj):
        return obj.read_by.count()
    read_by_count.short_description = 'Lido por'

    # Ação para marcar mensagens como lidas por todos os membros da sala
    actions = ['mark_as_read_by_all']

    def mark_as_read_by_all(self, request, queryset):
        for message in queryset:
            room = message.room
            members = room.members.all() if room.is_private else User.objects.all()
            for user in members:
                if room.can_user_access(user) and not message.is_read_by(user):
                    message.mark_as_read(user)
        self.message_user(request, "Mensagens marcadas como lidas para todos os membros.")
    mark_as_read_by_all.short_description = "Marcar como lido por todos os membros"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'last_activity')
    search_fields = ('user__username',)
    date_hierarchy = 'last_activity'
    ordering = ('-last_activity',)
    readonly_fields = ('last_activity',)

    # Ação para atualizar última atividade (útil para debugging)
    actions = ['update_last_activity']

    def update_last_activity(self, request, queryset):
        for profile in queryset:
            profile.last_activity = timezone.now()
            profile.save()
        self.message_user(request, "Última atividade atualizada para os perfis selecionados.")
    update_last_activity.short_description = "Atualizar última atividade"

@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('message', 'file', 'attachment_type', 'uploaded_at', 'original_filename',)
    search_fields = ('message', 'file', 'attachment_type', 'uploaded_at', 'original_filename',)