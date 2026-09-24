from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0005_aceptacionlegal_trazabilidad'),
    ]

    operations = [
        migrations.CreateModel(
            name='VisitaWeb',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_hora', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('pagina', models.CharField(max_length=500, db_index=True)),
                ('visitor_id', models.CharField(max_length=64, db_index=True)),
                ('ip_hash', models.CharField(blank=True, max_length=64)),
                ('user_agent', models.TextField(blank=True)),
                ('referencia', models.CharField(blank=True, max_length=1000)),
            ],
            options={
                'db_table': 'visitas_web',
                'ordering': ['-fecha_hora'],
                'indexes': [
                    models.Index(fields=['fecha_hora', 'pagina'], name='idx_visitas_fecha_pagina'),
                    models.Index(fields=['fecha_hora', 'visitor_id'], name='idx_visitas_fecha_visitor'),
                ],
            },
        ),
    ]
