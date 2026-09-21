from django.contrib import admin


admin.site.site_header = 'Administración TotalCounts'
admin.site.site_title = 'TotalCounts'
admin.site.index_title = 'Panel de administración'

from .models import Empresa, UsuarioEmpresa


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ('ruc', 'razon_social', 'nombre_comercial', 'activo')
    search_fields = ('ruc', 'razon_social', 'nombre_comercial')
    list_filter = ('activo',)


@admin.register(UsuarioEmpresa)
class UsuarioEmpresaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'empresa', 'rol', 'activo', 'creado_en')
    search_fields = ('usuario__username', 'empresa__ruc', 'empresa__razon_social')
    list_filter = ('rol', 'activo')
