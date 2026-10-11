from django.conf import settings
from django.db import models


class RequerimientoContacto(models.Model):
    TIPOS = [
        ('Consulta Tributaria', 'Consulta Tributaria'),
        ('Consulta Contable', 'Consulta Contable'),
        ('Consulta Laboral', 'Consulta Laboral'),
        ('Consulta Seguridad Laboral', 'Consulta Seguridad Laboral'),
        ('Consulta Legal', 'Consulta Legal'),
        ('Tramites y Requerimientos', 'Trámites y Requerimientos'),
        ('Otros', 'Otros'),
    ]
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('CONTACTADO', 'Contactado'),
        ('EN_SEGUIMIENTO', 'En seguimiento'),
        ('RESUELTO', 'Resuelto'),
        ('NO_CONCRETADO', 'No concretado'),
    ]

    nombre = models.CharField(max_length=120)
    email = models.EmailField(max_length=254)
    celular = models.CharField(max_length=30, blank=True)
    tema = models.CharField(max_length=60, choices=TIPOS)
    mensaje = models.TextField(max_length=5000)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE', db_index=True)
    correo_enviado = models.BooleanField(default=False)
    notas_internas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    gestionado_por = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'requerimientos_contacto'
        ordering = ['-creado_en']
        verbose_name = 'Requerimiento de contacto'
        verbose_name_plural = 'Requerimientos de contacto'

    def __str__(self):
        return f'{self.nombre} - {self.tema} ({self.get_estado_display()})'


class HistorialRequerimientoContacto(models.Model):
    requerimiento = models.ForeignKey(
        RequerimientoContacto,
        on_delete=models.CASCADE,
        related_name='historial',
    )
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20)
    nota = models.TextField(blank=True)
    usuario = models.CharField(max_length=150, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'historial_requerimientos_contacto'
        ordering = ['-creado_en']
        verbose_name = 'Historial de requerimiento'
        verbose_name_plural = 'Historial de requerimientos'
