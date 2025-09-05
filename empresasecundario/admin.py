from django.contrib import admin
from empresasecundario.models import EmpresaSecundaria

# Register your models here.
class EmpresaSecundariaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nome', 'status', 'empresaprimaria', )
    list_display_links = ('id', 'nome', 'status', 'empresaprimaria', )
    search_fields = ('nome', )
    list_filter = ('nome', )

    list_per_page = 20

admin.site.register(EmpresaSecundaria, EmpresaSecundariaAdmin)