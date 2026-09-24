from django.db import models


class VisitaWeb(models.Model):
    """
    Registro de visitas a las páginas públicas de TotalCounts.
    No almacena la IP en claro; se guarda un hash para estadísticas técnicas.
    """

    fecha_hora = models.DateTimeField(auto_now_add=True, db_index=True)
    pagina = models.CharField(max_length=500, db_index=True)
    visitor_id = models.CharField(max_length=64, db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)
    referencia = models.CharField(max_length=1000, blank=True)

    class Meta:
        db_table = 'visitas_web'
        ordering = ['-fecha_hora']
        indexes = [
            models.Index(fields=['fecha_hora', 'pagina'], name='idx_visitas_fecha_pagina'),
            models.Index(fields=['fecha_hora', 'visitor_id'], name='idx_visitas_fecha_visitor'),
        ]

    def __str__(self):
        return f'{self.fecha_hora:%Y-%m-%d %H:%M} - {self.pagina}'
