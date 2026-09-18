from django.db import models
from store.models import Pedido, Producto

class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, related_name='items', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.PositiveSmallIntegerField(default=1)
    
    def __str__(self) -> str:
        return f'{self.id}'
    
    class Meta:
        db_table = 'st_items_pedido'
        verbose_name = 'Item Pedido'
        verbose_name_plural = 'Items Pedido'
        