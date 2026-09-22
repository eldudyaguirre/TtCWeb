from django.contrib import admin

from .models import (
    Cliente,
    Establecimiento,
    ParametrosCliente,
    PuntoEmision,
    SecuencialDocumento,
    UsuarioCliente,
)


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



@admin.register(ParametrosCliente)
class ParametrosClienteAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'ambiente', 'certificado_nombre', 'activo', 'actualizado_en')
    search_fields = ('cliente__ruccedcli', 'cliente__nomclient')
    list_filter = ('ambiente', 'activo')


@admin.register(Establecimiento)
class EstablecimientoAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'codigo', 'nombre', 'direccion', 'activo')
    search_fields = ('cliente__ruccedcli', 'cliente__nomclient', 'codigo', 'nombre')
    list_filter = ('activo',)


@admin.register(PuntoEmision)
class PuntoEmisionAdmin(admin.ModelAdmin):
    list_display = ('establecimiento', 'codigo', 'nombre', 'activo')
    search_fields = ('establecimiento__cliente__ruccedcli', 'establecimiento__cliente__nomclient', 'codigo', 'nombre')
    list_filter = ('activo',)


@admin.register(SecuencialDocumento)
class SecuencialDocumentoAdmin(admin.ModelAdmin):
    list_display = ('punto_emision', 'tipo_documento', 'secuencial_actual', 'activo')
    list_filter = ('tipo_documento', 'activo')
