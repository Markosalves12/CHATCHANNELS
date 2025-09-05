from django.contrib import admin
from zeladorx.models import TypeZeladoria

# Register your models here.
class TypeZeladoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'setor', )
    list_display_links = ('id', 'setor', )
    search_fields = ('setor', )
    list_filter = ('setor', )

    list_per_page = 20

admin.site.register(TypeZeladoria, TypeZeladoriaAdmin)