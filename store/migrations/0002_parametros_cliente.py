from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Archivo',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tipo', models.CharField(choices=[
                    ('CERTIFICADO_P12', 'Certificado P12'),
                    ('XML', 'XML'),
                    ('PDF', 'PDF'),
                    ('DOCUMENTO', 'Documento'),
                    ('REPORTE', 'Reporte'),
                    ('OTRO', 'Otro'),
                ], max_length=30)),
                ('nombre_original', models.CharField(max_length=255)),
                ('nombre_fisico', models.CharField(max_length=255)),
                ('ruta_relativa', models.CharField(max_length=1000, unique=True)),
                ('extension', models.CharField(blank=True, max_length=20)),
                ('mime_type', models.CharField(blank=True, max_length=150)),
                ('tamano', models.BigIntegerField(default=0)),
                ('sha256', models.CharField(blank=True, max_length=64)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('activo', models.BooleanField(default=True)),
                ('cliente', models.ForeignKey(
                    db_column='ruccedcli',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='archivos',
                    to='store.cliente',
                )),
                ('creado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='archivos_creados',
                    to='auth.user',
                )),
            ],
            options={
                'db_table': 'archivos',
                'ordering': ['-creado_en'],
            },
        ),
        migrations.AddIndex(
            model_name='archivo',
            index=models.Index(
                fields=['cliente', 'tipo'],
                name='idx_archivos_cliente_tipo',
            ),
        ),
        migrations.AddIndex(
            model_name='archivo',
            index=models.Index(
                fields=['sha256'],
                name='idx_archivos_sha256',
            ),
        ),
        migrations.CreateModel(
            name='ParametrosCliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ambiente', models.CharField(
                    choices=[('1', 'Pruebas'), ('2', 'Producción')],
                    default='1',
                    max_length=1,
                )),
                ('clave_p12', models.CharField(blank=True, max_length=255)),
                ('activo', models.BooleanField(default=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('certificado_archivo', models.ForeignKey(
                    blank=True,
                    db_constraint=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='certificados_parametros',
                    to='store.archivo',
                )),
                ('cliente', models.OneToOneField(
                    db_column='ruccedcli',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='parametros',
                    to='store.cliente',
                )),
            ],
            options={
                'db_table': 'parametros_clientes',
                'verbose_name': 'Parámetro del cliente',
                'verbose_name_plural': 'Parámetros de clientes',
            },
        ),
        migrations.CreateModel(
            name='Establecimiento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=3)),
                ('nombre', models.CharField(blank=True, max_length=255)),
                ('direccion', models.CharField(blank=True, max_length=255)),
                ('activo', models.BooleanField(default=True)),
                ('cliente', models.ForeignKey(
                    db_column='ruccedcli',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='establecimientos',
                    to='store.cliente',
                )),
            ],
            options={
                'db_table': 'establecimientos',
                'ordering': ['codigo'],
            },
        ),
        migrations.CreateModel(
            name='PuntoEmision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=3)),
                ('nombre', models.CharField(blank=True, max_length=255)),
                ('activo', models.BooleanField(default=True)),
                ('establecimiento', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='puntos_emision',
                    to='store.establecimiento',
                )),
            ],
            options={
                'db_table': 'puntos_emision',
                'ordering': ['establecimiento__codigo', 'codigo'],
            },
        ),
        migrations.CreateModel(
            name='SecuencialDocumento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_documento', models.CharField(
                    choices=[
                        ('01', 'Factura'),
                        ('03', 'Liquidación de compra'),
                        ('04', 'Nota de crédito'),
                        ('05', 'Nota de débito'),
                        ('06', 'Guía de remisión'),
                        ('07', 'Comprobante de retención'),
                    ],
                    max_length=2,
                )),
                ('secuencial_actual', models.PositiveIntegerField(
                    default=1,
                    validators=[MinValueValidator(1)],
                )),
                ('activo', models.BooleanField(default=True)),
                ('punto_emision', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='secuenciales',
                    to='store.puntoemision',
                )),
            ],
            options={
                'db_table': 'secuenciales_documentos',
                'ordering': ['tipo_documento'],
            },
        ),
        migrations.AddConstraint(
            model_name='establecimiento',
            constraint=models.UniqueConstraint(
                fields=('cliente', 'codigo'),
                name='uq_establecimiento_cliente_codigo',
            ),
        ),
        migrations.AddConstraint(
            model_name='puntoemision',
            constraint=models.UniqueConstraint(
                fields=('establecimiento', 'codigo'),
                name='uq_punto_establecimiento_codigo',
            ),
        ),
        migrations.AddConstraint(
            model_name='secuencialdocumento',
            constraint=models.UniqueConstraint(
                fields=('punto_emision', 'tipo_documento'),
                name='uq_secuencial_punto_tipo',
            ),
        ),
    ]
