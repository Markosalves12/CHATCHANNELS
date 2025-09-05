from django.contrib import admin
from empresaprimaria.models import EmpresaPrimaria

# Register your models here.
class EmpresaPrimariaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nome', 'N_unidades', 'status', )
    list_display_links = ('id', 'nome', 'N_unidades', 'status', )
    search_fields = ('nome', )
    list_filter = ('nome', )

    list_per_page = 20

admin.site.register(EmpresaPrimaria, EmpresaPrimariaAdmin)