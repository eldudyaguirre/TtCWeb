from django.db import models


class RebeficsSocio(models.Model):
    """Datos persistentes de composición societaria y beneficiarios finales por cliente."""

    class TipoSujeto(models.TextChoices):
        PERSONA_NATURAL = 'PN', 'Persona natural'
        PERSONA_JURIDICA = 'PJ', 'Persona jurídica'
        ESTRUCTURA_JURIDICA = 'EJ', 'Estructura jurídica'

    class TipoIdentificacion(models.TextChoices):
        RUC = 'RUC', 'RUC'
        CEDULA = 'CEDULA', 'Cédula'
        PASAPORTE = 'PASAPORTE', 'Pasaporte'
        EXTERIOR = 'EXTERIOR', 'Identificación del exterior'
        OTRO = 'OTRO', 'Otro'

    class TipoRelacion(models.TextChoices):
        SOCIO = 'SOCIO', 'Socio'
        ACCIONISTA = 'ACCIONISTA', 'Accionista'
        DIRECTOR = 'DIRECTOR', 'Miembro del directorio'
        ADMINISTRADOR = 'ADMINISTRADOR', 'Administrador'
        APODERADO = 'APODERADO', 'Apoderado general'
        CONTROL = 'CONTROL', 'Persona con poder de decisión o control'
        OTRO = 'OTRO', 'Otro'

    cliente = models.ForeignKey(
        'store.Cliente',
        on_delete=models.PROTECT,
        related_name='rebefics_socios',
        db_column='ruccedcli',
    )
    tipo_sujeto = models.CharField(max_length=2, choices=TipoSujeto.choices, default=TipoSujeto.PERSONA_NATURAL)
    tipo_identificacion = models.CharField(max_length=12, choices=TipoIdentificacion.choices, default=TipoIdentificacion.CEDULA)
    identificacion = models.CharField(max_length=30)
    primer_nombre = models.CharField(max_length=100, blank=True)
    segundo_nombre = models.CharField(max_length=100, blank=True)
    primer_apellido = models.CharField(max_length=100, blank=True)
    segundo_apellido = models.CharField(max_length=100, blank=True)
    razon_social = models.CharField(max_length=255, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    nacionalidad = models.CharField(max_length=100, blank=True)
    pais_residencia_fiscal = models.CharField(max_length=100, blank=True)
    tipo_regimen_fiscal = models.CharField(max_length=100, blank=True)
    es_parte_relacionada = models.BooleanField(default=False)
    regimen_paraiso_fiscal = models.BooleanField(default=False)
    pais_relacionado_paraiso = models.CharField(max_length=100, blank=True)
    pais_regimen_fiscal_preferente = models.CharField(max_length=100, blank=True)
    regimen_fiscal_preferente = models.CharField(max_length=150, blank=True)
    estado_jurisdiccion = models.CharField(max_length=120, blank=True)
    ciudad = models.CharField(max_length=120, blank=True)
    calle = models.CharField(max_length=180, blank=True)
    interseccion = models.CharField(max_length=180, blank=True)
    numero_domicilio = models.CharField(max_length=50, blank=True)
    codigo_postal = models.CharField(max_length=20, blank=True)
    referencia_direccion = models.CharField(max_length=255, blank=True)
    tipo_relacion_sujeto = models.CharField(max_length=20, choices=TipoRelacion.choices, default=TipoRelacion.SOCIO)
    porcentaje_participacion = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    relacionado_con = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='integrantes_cadena',
    )
    es_beneficiario_final = models.BooleanField(default=False)
    beneficiario_por_propiedad = models.BooleanField(default=False)
    beneficiario_por_control = models.BooleanField(default=False)
    beneficiario_por_administracion = models.BooleanField(default=False)
    porcentaje_participacion_efectiva = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    observaciones = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rebefics_socios'
        ordering = ['primer_apellido', 'primer_nombre', 'razon_social']
        constraints = [
            models.UniqueConstraint(
                fields=['cliente', 'identificacion', 'tipo_relacion_sujeto'],
                name='uq_rebefics_cliente_ident_rel',
            ),
        ]
        indexes = [
            models.Index(fields=['cliente', 'activo'], name='idx_rebefics_cliente_activo'),
            models.Index(fields=['identificacion'], name='idx_rebefics_identificacion'),
        ]

    @property
    def nombre_completo(self):
        return self.razon_social or ' '.join(
            parte for parte in (
                self.primer_nombre, self.segundo_nombre,
                self.primer_apellido, self.segundo_apellido,
            ) if parte
        ).strip() or self.identificacion

    def __str__(self):
        return f'{self.cliente_id} - {self.nombre_completo}'
