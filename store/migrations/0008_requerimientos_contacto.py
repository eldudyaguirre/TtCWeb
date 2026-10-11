# Generated manually for the contact requirements module.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('store', '0007_rebefics_socio'),
    ]

    operations = [
        migrations.CreateModel(
            name='RequerimientoContacto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=120)),
                ('email', models.EmailField(max_length=254)),
                ('celular', models.CharField(blank=True, max_length=30)),
                ('tema', models.CharField(choices=[('Consulta Tributaria', 'Consulta Tributaria'), ('Consulta Contable', 'Consulta Contable'), ('Consulta Laboral', 'Consulta Laboral'), ('Consulta Seguridad Laboral', 'Consulta Seguridad Laboral'), ('Consulta Legal', 'Consulta Legal'), ('Tramites y Requerimientos', 'Trámites y Requerimientos'), ('Otros', 'Otros')], max_length=60)),
                ('mensaje', models.TextField(max_length=5000)),
                ('estado', models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('CONTACTADO', 'Contactado'), ('EN_SEGUIMIENTO', 'En seguimiento'), ('RESUELTO', 'Resuelto'), ('NO_CONCRETADO', 'No concretado')], db_index=True, default='PENDIENTE', max_length=20)),
                ('correo_enviado', models.BooleanField(default=False)),
                ('notas_internas', models.TextField(blank=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('gestionado_por', models.CharField(blank=True, max_length=150)),
            ],
            options={
                'db_table': 'requerimientos_contacto',
                'ordering': ['-creado_en'],
                'verbose_name': 'Requerimiento de contacto',
                'verbose_name_plural': 'Requerimientos de contacto',
            },
        ),
        migrations.CreateModel(
            name='HistorialRequerimientoContacto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado_anterior', models.CharField(blank=True, max_length=20)),
                ('estado_nuevo', models.CharField(max_length=20)),
                ('nota', models.TextField(blank=True)),
                ('usuario', models.CharField(blank=True, max_length=150)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('requerimiento', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historial', to='store.requerimientocontacto')),
            ],
            options={
                'db_table': 'historial_requerimientos_contacto',
                'ordering': ['-creado_en'],
                'verbose_name': 'Historial de requerimiento',
                'verbose_name_plural': 'Historial de requerimientos',
            },
        ),
    ]
