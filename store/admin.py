from django.contrib import admin
from store.models import Categoria, Producto, Pedido, ItemPedido

admin.site.site_header = 'Administrador de TotalCountsWeb'

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'slug', 'fecha_registro', 'fecha_ult_act')
    
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'descripcion', 'precio', 'activo', 'fecha_registro', 'fecha_ult_act')

class ItemPedidoTabInline(admin.TabularInline):
    list_display = ('id', 'producto', 'cantidad')
    model = ItemPedido
    extra = 0
    
    @admin.display(description='Subtotal')
    def get_subtotal(self, obj):
        return obj.cantidad * obj.producto.precio
    
    readonly_fields = ('get_subtotal',)
    

@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'codigo', 'usuario', 'total', 'fecha_registro', 'fecha_ult_act')
    inlines = (ItemPedidoTabInline,)