from django.db import models


class Cliente(models.Model):
    """Representación de la tabla existente public.clientes.

    Django no crea ni modifica esta tabla.
    """

    ruccedcli = models.CharField(max_length=255, primary_key=True, db_column='ruccedcli')
    nomclient = models.CharField(max_length=255, blank=True, db_column='nomclient')
    dirclient = models.CharField(max_length=255, blank=True, db_column='dirclient')
    ocuclient = models.CharField(max_length=255, blank=True, db_column='ocuclient')
    corelectr = models.CharField(max_length=255, blank=True, db_column='corelectr')
    teldomcli = models.CharField(max_length=100, blank=True, db_column='teldomcli')
    teloficli = models.CharField(max_length=100, blank=True, db_column='teloficli')
    telcelcli = models.CharField(max_length=100, blank=True, db_column='telcelcli')
    estcivcli = models.CharField(max_length=100, blank=True, db_column='estcivcli')
    fecnacimi = models.CharField(max_length=100, blank=True, db_column='fecnacimi')
    edaclient = models.CharField(max_length=100, blank=True, db_column='edaclient')
    clavesri = models.CharField(max_length=255, blank=True, db_column='clavesri')
    cediess = models.CharField(max_length=255, blank=True, db_column='cediess')
    claveiess = models.CharField(max_length=255, blank=True, db_column='claveiess')
    mrlcon = models.CharField(max_length=255, blank=True, db_column='mrlcon')
    mrlsal = models.CharField(max_length=255, blank=True, db_column='mrlsal')
    clavesuper = models.CharField(max_length=255, blank=True, db_column='clavesuper')
    iessdomestica = models.CharField(max_length=255, blank=True, db_column='iessdomestica')
    datiess = models.CharField(max_length=255, blank=True, db_column='datiess')
    acceso_ttcweb = models.BooleanField(default=False, db_column='acceso_ttcweb')
    activo = models.BooleanField(default=False, db_column='activo')
    salcuenta = models.FloatField(default=0, db_column='salcuenta')

    class Meta:
        managed = False
        db_table = 'clientes'
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        return f'{self.nomclient} ({self.ruccedcli})'
