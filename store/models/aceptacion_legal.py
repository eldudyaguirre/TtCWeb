from django.conf import settings
from django.db import models


class AceptacionLegal(models.Model):
    class Tipo(models.TextChoices):
        POLITICA_DATOS = 'POLITICA_DATOS', 'Política de Protección de Datos'
        TERMINOS_USO = 'TERMINOS_USO', 'Términos y Condiciones de Uso'

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='aceptaciones_legales',
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    version = models.CharField(max_length=20)
    aceptado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'aceptaciones_legales'
        ordering = ['-aceptado_en']
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'tipo', 'version'],
                name='uq_aceptacion_legal_usuario_tipo_version',
            ),
        ]

    def __str__(self):
        return f'{self.usuario.username} - {self.get_tipo_display()} v{self.version}'
