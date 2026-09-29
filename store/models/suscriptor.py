from django.db import models


class Suscriptor(models.Model):
    """Persona que autoriza recibir noticias, novedades y comunicaciones de TotalCounts."""

    email = models.EmailField(unique=True, max_length=254)
    nombre = models.CharField(max_length=150, blank=True)
    activo = models.BooleanField(default=True)
    consentimiento_marketing = models.BooleanField(default=True)
    consentimiento_en = models.DateTimeField(auto_now_add=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    origen = models.CharField(max_length=30, default='WEB')

    class Meta:
        db_table = 'suscriptores'
        ordering = ['-creado_en']
        verbose_name = 'Suscriptor'
        verbose_name_plural = 'Suscriptores'

    def __str__(self):
        return f'{self.nombre} <{self.email}>' if self.nombre else self.email
