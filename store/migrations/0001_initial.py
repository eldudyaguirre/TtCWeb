import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='Cliente',
                    fields=[
                        ('ruccedcli', models.CharField(db_column='ruccedcli', max_length=255, primary_key=True, serialize=False)),
                        ('nomclient', models.CharField(blank=True, db_column='nomclient', max_length=255)),
                        ('dirclient', models.CharField(blank=True, db_column='dirclient', max_length=255)),
                        ('ocuclient', models.CharField(blank=True, db_column='ocuclient', max_length=255)),
                        ('corelectr', models.CharField(blank=True, db_column='corelectr', max_length=255)),
                        ('teldomcli', models.CharField(blank=True, db_column='teldomcli', max_length=100)),
                        ('teloficli', models.CharField(blank=True, db_column='teloficli', max_length=100)),
                        ('telcelcli', models.CharField(blank=True, db_column='telcelcli', max_length=100)),
                        ('estcivcli', models.CharField(blank=True, db_column='estcivcli', max_length=100)),
                        ('fecnacimi', models.CharField(blank=True, db_column='fecnacimi', max_length=100)),
                        ('edaclient', models.CharField(blank=True, db_column='edaclient', max_length=100)),
                        ('clavesri', models.CharField(blank=True, db_column='clavesri', max_length=255)),
                        ('cediess', models.CharField(blank=True, db_column='cediess', max_length=255)),
                        ('claveiess', models.CharField(blank=True, db_column='claveiess', max_length=255)),
                        ('mrlcon', models.CharField(blank=True, db_column='mrlcon', max_length=255)),
                        ('mrlsal', models.CharField(blank=True, db_column='mrlsal', max_length=255)),
                        ('clavesuper', models.CharField(blank=True, db_column='clavesuper', max_length=255)),
                        ('iessdomestica', models.CharField(blank=True, db_column='iessdomestica', max_length=255)),
                        ('datiess', models.CharField(blank=True, db_column='datiess', max_length=255)),
                        ('acceso_ttcweb', models.BooleanField(db_column='acceso_ttcweb', default=False)),
                        ('activo', models.BooleanField(db_column='activo', default=False)),
                        ('salcuenta', models.FloatField(default=0, db_column='salcuenta')),
                    ],
                    options={
                        'db_table': 'clientes',
                        'managed': False,
                        'verbose_name': 'Cliente',
                        'verbose_name_plural': 'Clientes',
                    },
                ),
            ],
        ),
        migrations.CreateModel(
            name='UsuarioCliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rol', models.CharField(
                    choices=[
                        ('ADMIN', 'Administrador'),
                        ('OPERADOR', 'Operador'),
                        ('CONSULTA', 'Consulta'),
                    ],
                    default='OPERADOR',
                    max_length=10,
                )),
                ('activo', models.BooleanField(default=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('cliente', models.ForeignKey(
                    db_column='ruccedcli',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='usuarios_asignados',
                    to='store.cliente',
                )),
                ('usuario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='clientes_asignados',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'usuarios_clientes',
                'ordering': ['cliente__nomclient', 'usuario__username'],
                'verbose_name': 'Usuario por cliente',
                'verbose_name_plural': 'Usuarios por cliente',
            },
        ),
        migrations.AddConstraint(
            model_name='usuariocliente',
            constraint=models.UniqueConstraint(
                fields=('usuario', 'cliente'),
                name='uq_usuario_cliente',
            ),
        ),
    ]
