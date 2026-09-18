from django.db import models
from store.models import Categoria

class Campaña(models.Model):
    categorias = models.ManyToManyField(Categoria, related_name='campaña')
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)
    precio = models.DecimalField(max_digits=9, decimal_places=2)
    imagen = models.ImageField(upload_to='imagenes/')
    activo = models.BooleanField()
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_ult_act = models.DateTimeField(auto_now=True)
    
    def __str__(self) -> str:
        return f'{self.nombre} ({self.id})'
    
    class Meta:
        db_table = 'st_campana'
        verbose_name = 'Campaña'
        verbose_name_plural = 'Campañas'