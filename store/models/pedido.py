from django.db import models
from django.contrib.auth.models import User

class Pedido(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    codigo = models.CharField(max_length=25)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_ult_act = models.DateTimeField(auto_now=True)
    
    @property
    def contar_items(self):
        items = self.items.all()
        cantidad = sum([item.cantidad for item in items])
        return cantidad
    
    def __str__(self) -> str:
        return f'{self.codigo}'
    
    class Meta:
        db_table = 'st_pedidos'
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'