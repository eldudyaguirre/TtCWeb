from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0001_initial'),
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
    ]
