from django.conf import settings
from django.db import models


class UsuarioCliente(models.Model):
    class Rol(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrador'
        OPERADOR = 'OPERADOR', 'Operador'
        CONSULTA = 'CONSULTA', 'Consulta'

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='clientes_asignados',
    )
    cliente = models.ForeignKey(
        'store.Cliente',
        on_delete=models.PROTECT,
        related_name='usuarios_asignados',
        db_column='ruccedcli',
        db_constraint=True,
    )
    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.OPERADOR)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usuarios_clientes'
        ordering = ['cliente__nomclient', 'usuario__username']
        verbose_name = 'Usuario por cliente'
        verbose_name_plural = 'Usuarios por cliente'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'cliente'],
                name='uq_usuario_cliente',
            ),
        ]

    def __str__(self):
        return f'{self.usuario.username} - {self.cliente.nomclient} ({self.rol})'
