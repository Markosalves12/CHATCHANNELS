# chat/admin.py
from django.contrib import admin
from chat.models import Message


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
            members = room.members.all()
            for user in members:
                if room.can_user_access(user) and not message.is_read_by(user):
                    message.mark_as_read(user)
        self.message_user(request, "Mensagens marcadas como lidas para todos os membros.")
    mark_as_read_by_all.short_description = "Marcar como lido por todos os membros"