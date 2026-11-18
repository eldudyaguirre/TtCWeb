from django.db import models


class IessRdepJob(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        PROCESANDO = "PROCESANDO", "Procesando"
        COMPLETADO = "COMPLETADO", "Completado"
        ERROR = "ERROR", "Error"

    cliente = models.ForeignKey(
        "store.Cliente",
        on_delete=models.PROTECT,
        db_column="cliente_ruc",
        to_field="ruccedcli",
        related_name="iess_rdep_jobs",
    )
    anio = models.PositiveSmallIntegerField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    mensaje = models.CharField(max_length=500, blank=True)
    archivo_relativo = models.CharField(max_length=500, blank=True)
    worker_id = models.CharField(max_length=150, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    iniciado_en = models.DateTimeField(null=True, blank=True)
    heartbeat_en = models.DateTimeField(null=True, blank=True)
    terminado_en = models.DateTimeField(null=True, blank=True)
    error_detalle = models.TextField(blank=True)

    class Meta:
        db_table = "iess_rdep_jobs"
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "anio"],
                condition=models.Q(estado__in=["PENDIENTE", "PROCESANDO"]),
                name="uq_iess_rdep_job_activo_cliente_anio",
            )
        ]

    def __str__(self):
        return f"IESS RDEP {self.cliente_id} - {self.anio} ({self.estado})"
