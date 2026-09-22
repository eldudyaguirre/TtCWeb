from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def certificado_p12_path(instance, filename):
    return f"certificados_p12/{instance.cliente.ruccedcli}/{filename}"


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ParametrosCliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ambiente', models.CharField(choices=[('1', 'Pruebas'), ('2', 'Producción')], default='1', max_length=1)),
                ('certificado_p12', models.FileField(blank=True, max_length=500, upload_to=certificado_p12_path)),
                ('clave_p12', models.CharField(blank=True, max_length=255)),
                ('certificado_nombre', models.CharField(blank=True, max_length=255)),
                ('activo', models.BooleanField(default=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('cliente', models.OneToOneField(db_column='ruccedcli', on_delete=django.db.models.deletion.PROTECT, related_name='parametros', to='store.cliente')),
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
                ('cliente', models.ForeignKey(db_column='ruccedcli', on_delete=django.db.models.deletion.PROTECT, related_name='establecimientos', to='store.cliente')),
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
                ('establecimiento', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='puntos_emision', to='store.establecimiento')),
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
                ('tipo_documento', models.CharField(choices=[('01', 'Factura'), ('03', 'Liquidación de compra'), ('04', 'Nota de crédito'), ('05', 'Nota de débito'), ('06', 'Guía de remisión'), ('07', 'Comprobante de retención')], max_length=2)),
                ('secuencial_actual', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
                ('activo', models.BooleanField(default=True)),
                ('punto_emision', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='secuenciales', to='store.puntoemision')),
            ],
            options={
                'db_table': 'secuenciales_documentos',
                'ordering': ['tipo_documento'],
            },
        ),
        migrations.AddConstraint(
            model_name='establecimiento',
            constraint=models.UniqueConstraint(fields=('cliente', 'codigo'), name='uq_establecimiento_cliente_codigo'),
        ),
        migrations.AddConstraint(
            model_name='puntoemision',
            constraint=models.UniqueConstraint(fields=('establecimiento', 'codigo'), name='uq_punto_establecimiento_codigo'),
        ),
        migrations.AddConstraint(
            model_name='secuencialdocumento',
            constraint=models.UniqueConstraint(fields=('punto_emision', 'tipo_documento'), name='uq_secuencial_punto_tipo'),
        ),
    ]
