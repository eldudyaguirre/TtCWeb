import uuid

from django.conf import settings
from django.db import models


class Archivo(models.Model):
    class Tipo(models.TextChoices):
        CERTIFICADO_P12 = 'CERTIFICADO_P12', 'Certificado P12'
        XML = 'XML', 'XML'
        PDF = 'PDF', 'PDF'
        DOCUMENTO = 'DOCUMENTO', 'Documento'
        REPORTE = 'REPORTE', 'Reporte'
        OTRO = 'OTRO', 'Otro'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cliente = models.ForeignKey(
        'store.Cliente',
        on_delete=models.PROTECT,
        related_name='archivos',
        db_column='ruccedcli',
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    nombre_original = models.CharField(max_length=255)
    nombre_fisico = models.CharField(max_length=255)
    ruta_relativa = models.CharField(max_length=1000, unique=True)
    extension = models.CharField(max_length=20, blank=True)
    mime_type = models.CharField(max_length=150, blank=True)
    tamano = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='archivos_creados',
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'archivos'
        ordering = ['-creado_en']
        indexes = [
            models.Index(fields=['cliente', 'tipo'], name='idx_archivos_cliente_tipo'),
            models.Index(fields=['sha256'], name='idx_archivos_sha256'),
        ]

    def __str__(self):
        return f'{self.cliente.ruccedcli} - {self.nombre_original}'
