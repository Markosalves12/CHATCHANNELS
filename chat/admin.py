# chat/admin.py
from django.contrib import admin
from .models import ChatRoom, RoomMembership, UserProfile
from django.utils import timezone
from django.contrib.auth.models import User

@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_private', 'history_enabled', 'created_by', 'created_at', 'member_count')
    list_filter = ('is_private', 'history_enabled', 'created_at')
    search_fields = ('name', 'created_by__username')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    # Exibir contagem de membros
    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Número de Membros'

    # Ação para tornar uma sala pública ou privada
    actions = ['make_public', 'make_private', 'enable_history', 'disable_history']

    def make_public(self, request, queryset):
        queryset.update(is_private=False)
        self.message_user(request, "As salas selecionadas foram tornadas públicas.")
    make_public.short_description = "Tornar salas públicas"

    def make_private(self, request, queryset):
        queryset.update(is_private=True)
        self.message_user(request, "As salas selecionadas foram tornadas privadas.")
    make_private.short_description = "Tornar salas privadas"

    def enable_history(self, request, queryset):
        queryset.update(history_enabled=True)
        self.message_user(request, "O histórico foi habilitado nas salas selecionadas.")
    enable_history.short_description = "Habilitar histórico"

    def disable_history(self, request, queryset):
        queryset.update(history_enabled=False)
        self.message_user(request, "O histórico foi desabilitado nas salas selecionadas.")
    disable_history.short_description = "Desabilitar histórico"


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
