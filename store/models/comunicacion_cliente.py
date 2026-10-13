from django.db import models


class ComunicacionCliente(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        PENDIENTE = "PENDIENTE", "Pendiente"
        ENVIANDO = "ENVIANDO", "Enviando"
        ENVIADO = "ENVIADO", "Enviado"
        ERROR = "ERROR", "Con errores"

    asunto = models.CharField(max_length=220)
    titulo = models.CharField(max_length=220, blank=True)
    mensaje = models.TextField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR, db_index=True)
    destinatarios = models.PositiveIntegerField(default=0)
    enviados = models.PositiveIntegerField(default=0)
    fallidos = models.PositiveIntegerField(default=0)
    correos_pendientes = models.TextField(blank=True)
    creado_por = models.CharField(max_length=150, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    enviado_en = models.DateTimeField(null=True, blank=True)
    error_detalle = models.TextField(blank=True)

    class Meta:
        db_table = "comunicaciones_clientes"
        ordering = ["-creado_en"]
        verbose_name = "Comunicación a clientes"
        verbose_name_plural = "Comunicaciones a clientes"

    def __str__(self):
        return self.asunto
