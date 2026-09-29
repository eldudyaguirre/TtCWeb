from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Suscriptor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('nombre', models.CharField(blank=True, max_length=150)),
                ('activo', models.BooleanField(default=True)),
                ('consentimiento_marketing', models.BooleanField(default=True)),
                ('consentimiento_en', models.DateTimeField(auto_now_add=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('origen', models.CharField(default='WEB', max_length=30)),
            ],
            options={
                'db_table': 'suscriptores',
                'ordering': ['-creado_en'],
                'verbose_name': 'Suscriptor',
                'verbose_name_plural': 'Suscriptores',
            },
        ),
    ]
