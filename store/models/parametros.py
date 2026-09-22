from django.core.validators import MinValueValidator
from django.db import models


class ParametrosCliente(models.Model):
    class Ambiente(models.TextChoices):
        PRUEBAS = '1', 'Pruebas'
        PRODUCCION = '2', 'Producción'

    cliente = models.OneToOneField(
        'store.Cliente',
        on_delete=models.PROTECT,
        related_name='parametros',
        db_column='ruccedcli',
    )
    ambiente = models.CharField(
        max_length=1,
        choices=Ambiente.choices,
        default=Ambiente.PRUEBAS,
    )
    certificado_archivo = models.ForeignKey(
        'store.Archivo',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='certificados_parametros',
        db_constraint=True,
    )
    clave_p12 = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'parametros_clientes'
        verbose_name = 'Parámetro del cliente'
        verbose_name_plural = 'Parámetros de clientes'

    def __str__(self):
        return f'Parámetros - {self.cliente.nomclient}'


class Establecimiento(models.Model):
    cliente = models.ForeignKey(
        'store.Cliente',
        on_delete=models.PROTECT,
        related_name='establecimientos',
        db_column='ruccedcli',
    )
    codigo = models.CharField(max_length=3)
    nombre = models.CharField(max_length=255, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'establecimientos'
        ordering = ['codigo']
        constraints = [
            models.UniqueConstraint(
                fields=['cliente', 'codigo'],
                name='uq_establecimiento_cliente_codigo',
            ),
        ]

    def __str__(self):
        return f'{self.codigo} - {self.nombre or "Establecimiento"}'


class PuntoEmision(models.Model):
    establecimiento = models.ForeignKey(
        Establecimiento,
        on_delete=models.PROTECT,
        related_name='puntos_emision',
    )
    codigo = models.CharField(max_length=3)
    nombre = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'puntos_emision'
        ordering = ['establecimiento__codigo', 'codigo']
        constraints = [
            models.UniqueConstraint(
                fields=['establecimiento', 'codigo'],
                name='uq_punto_establecimiento_codigo',
            ),
        ]

    def __str__(self):
        return f'{self.establecimiento.codigo}-{self.codigo}'


class SecuencialDocumento(models.Model):
    class TipoDocumento(models.TextChoices):
        FACTURA = '01', 'Factura'
        LIQUIDACION = '03', 'Liquidación de compra'
        NOTA_CREDITO = '04', 'Nota de crédito'
        NOTA_DEBITO = '05', 'Nota de débito'
        GUIA_REMISION = '06', 'Guía de remisión'
        RETENCION = '07', 'Comprobante de retención'

    punto_emision = models.ForeignKey(
        PuntoEmision,
        on_delete=models.PROTECT,
        related_name='secuenciales',
    )
    tipo_documento = models.CharField(max_length=2, choices=TipoDocumento.choices)
    secuencial_actual = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'secuenciales_documentos'
        ordering = ['tipo_documento']
        constraints = [
            models.UniqueConstraint(
                fields=['punto_emision', 'tipo_documento'],
                name='uq_secuencial_punto_tipo',
            ),
        ]

    def __str__(self):
        return f'{self.punto_emision} - {self.get_tipo_documento_display()} - {self.secuencial_actual}'
