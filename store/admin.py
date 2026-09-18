from django.contrib import admin
from store.models import Categoria, Producto

admin.site.site_header = 'Administrador de TotalCountsWeb'

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'slug', 'fecha_registro', 'fecha_ult_act')
    
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'descripcion', 'precio', 'activo', 'fecha_registro', 'fecha_ult_act')
