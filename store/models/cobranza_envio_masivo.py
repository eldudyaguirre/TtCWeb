from django.db import models


class CobranzaEnvioMasivo(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "En cola"
        ENVIANDO = "ENVIANDO", "Enviando"
        ENVIADO = "ENVIADO", "Enviado"
        ERROR = "ERROR", "Con errores"

    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        db_index=True,
    )
    destinatarios = models.PositiveIntegerField(default=0)
    enviados = models.PositiveIntegerField(default=0)
    fallidos = models.PositiveIntegerField(default=0)
    omitidos_sin_cliente = models.PositiveIntegerField(default=0)
    omitidos_sin_correo = models.PositiveIntegerField(default=0)
    omitidos_correo_invalido = models.PositiveIntegerField(default=0)
    pendientes_json = models.TextField(blank=True)
    fallidos_json = models.TextField(blank=True)
    creado_por = models.CharField(max_length=150, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    enviado_en = models.DateTimeField(null=True, blank=True)
    error_detalle = models.TextField(blank=True)

    class Meta:
        db_table = "cobranza_envios_masivos"
        ordering = ["-creado_en"]
        verbose_name = "Envío masivo de cobranza"
        verbose_name_plural = "Envíos masivos de cobranza"

    def __str__(self):
        return f"Envío de cobranza #{self.pk} · {self.get_estado_display()}"
