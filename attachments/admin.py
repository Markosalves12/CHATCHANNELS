# chat/admin.py
from django.contrib import admin
from attachments.models import Attachment

@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('message', 'file', 'attachment_type', 'uploaded_at', 'original_filename',)
    search_fields = ('message', 'file', 'attachment_type', 'uploaded_at', 'original_filename',)