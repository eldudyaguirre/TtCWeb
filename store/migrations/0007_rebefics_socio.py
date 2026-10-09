import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0006_visitaweb'),
    ]

    operations = [
        migrations.CreateModel(
            name='RebeficsSocio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_sujeto', models.CharField(choices=[('PN', 'Persona natural'), ('PJ', 'Persona jurídica'), ('EJ', 'Estructura jurídica')], default='PN', max_length=2)),
                ('tipo_identificacion', models.CharField(choices=[('RUC', 'RUC'), ('CEDULA', 'Cédula'), ('PASAPORTE', 'Pasaporte'), ('EXTERIOR', 'Identificación del exterior'), ('OTRO', 'Otro')], default='CEDULA', max_length=12)),
                ('identificacion', models.CharField(max_length=30)),
                ('primer_nombre', models.CharField(blank=True, max_length=100)),
                ('segundo_nombre', models.CharField(blank=True, max_length=100)),
                ('primer_apellido', models.CharField(blank=True, max_length=100)),
                ('segundo_apellido', models.CharField(blank=True, max_length=100)),
                ('razon_social', models.CharField(blank=True, max_length=255)),
                ('fecha_nacimiento', models.DateField(blank=True, null=True)),
                ('nacionalidad', models.CharField(blank=True, max_length=100)),
                ('pais_residencia_fiscal', models.CharField(blank=True, max_length=100)),
                ('tipo_regimen_fiscal', models.CharField(blank=True, max_length=100)),
                ('es_parte_relacionada', models.BooleanField(default=False)),
                ('regimen_paraiso_fiscal', models.BooleanField(default=False)),
                ('pais_relacionado_paraiso', models.CharField(blank=True, max_length=100)),
                ('pais_regimen_fiscal_preferente', models.CharField(blank=True, max_length=100)),
                ('regimen_fiscal_preferente', models.CharField(blank=True, max_length=150)),
                ('estado_jurisdiccion', models.CharField(blank=True, max_length=120)),
                ('ciudad', models.CharField(blank=True, max_length=120)),
                ('calle', models.CharField(blank=True, max_length=180)),
                ('interseccion', models.CharField(blank=True, max_length=180)),
                ('numero_domicilio', models.CharField(blank=True, max_length=50)),
                ('codigo_postal', models.CharField(blank=True, max_length=20)),
                ('referencia_direccion', models.CharField(blank=True, max_length=255)),
                ('tipo_relacion_sujeto', models.CharField(choices=[('SOCIO', 'Socio'), ('ACCIONISTA', 'Accionista'), ('DIRECTOR', 'Miembro del directorio'), ('ADMINISTRADOR', 'Administrador'), ('APODERADO', 'Apoderado general'), ('CONTROL', 'Persona con poder de decisión o control'), ('OTRO', 'Otro')], default='SOCIO', max_length=20)),
                ('porcentaje_participacion', models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ('es_beneficiario_final', models.BooleanField(default=False)),
                ('beneficiario_por_propiedad', models.BooleanField(default=False)),
                ('beneficiario_por_control', models.BooleanField(default=False)),
                ('beneficiario_por_administracion', models.BooleanField(default=False)),
                ('porcentaje_participacion_efectiva', models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ('observaciones', models.TextField(blank=True)),
                ('activo', models.BooleanField(default=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('cliente', models.ForeignKey(db_column='ruccedcli', on_delete=django.db.models.deletion.PROTECT, related_name='rebefics_socios', to='store.cliente')),
                ('relacionado_con', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='integrantes_cadena', to='store.rebeficssocio')),
            ],
            options={
                'db_table': 'rebefics_socios',
                'ordering': ['primer_apellido', 'primer_nombre', 'razon_social'],
                'indexes': [
                    models.Index(fields=['cliente', 'activo'], name='idx_rebefics_cliente_activo'),
                    models.Index(fields=['identificacion'], name='idx_rebefics_identificacion'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=('cliente', 'identificacion', 'tipo_relacion_sujeto'), name='uq_rebefics_cliente_ident_rel'),
                ],
            },
        ),
    ]
