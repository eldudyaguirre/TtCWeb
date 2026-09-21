from django.conf import settings
from django.db import models


class UsuarioEmpresa(models.Model):
    class Rol(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrador'
        OPERADOR = 'OPERADOR', 'Operador'
        CONSULTA = 'CONSULTA', 'Consulta'

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='empresas_asignadas',
    )
    empresa = models.ForeignKey(
        'store.Empresa',
        on_delete=models.CASCADE,
        related_name='usuarios_asignados',
    )
    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.OPERADOR)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usuarios_empresas'
        ordering = ['empresa__razon_social', 'usuario__username']
        verbose_name = 'Usuario por empresa'
        verbose_name_plural = 'Usuarios por empresa'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'empresa'],
                name='uq_usuario_empresa',
            ),
        ]

    def __str__(self):
        return f'{self.usuario.username} - {self.empresa.razon_social} ({self.rol})'
