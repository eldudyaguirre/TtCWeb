from django.contrib import admin

from .models import Cliente, UsuarioCliente


admin.site.site_header = 'Administración TotalCounts'
admin.site.site_title = 'TotalCounts'
admin.site.index_title = 'Panel de administración'


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('ruccedcli', 'nomclient', 'acceso_ttcweb')
    search_fields = ('ruccedcli', 'nomclient')
    list_filter = ('acceso_ttcweb',)
    readonly_fields = ('ruccedcli', 'nomclient')


@admin.register(UsuarioCliente)
class UsuarioClienteAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'cliente', 'rol', 'activo', 'creado_en')
    search_fields = ('usuario__username', 'cliente__ruccedcli', 'cliente__nomclient')
    list_filter = ('rol', 'activo')
