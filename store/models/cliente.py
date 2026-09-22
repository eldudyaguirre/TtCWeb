from django.db import models


class Cliente(models.Model):
    """Representación de la tabla existente public.clientes.

    Django no crea ni modifica esta tabla.
    """

    ruccedcli = models.CharField(max_length=255, primary_key=True, db_column='ruccedcli')
    nomclient = models.CharField(max_length=255, blank=True, db_column='nomclient')
    acceso_ttcweb = models.BooleanField(default=False, db_column='acceso_ttcweb')

    class Meta:
        managed = False
        db_table = 'clientes'
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        return f'{self.nomclient} ({self.ruccedcli})'
