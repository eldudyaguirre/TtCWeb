from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0017_comunicacion_destinatarios_imagen"),
    ]

    operations = [
        migrations.CreateModel(
            name="CobranzaEnvioMasivo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("PENDIENTE", "En cola"),
                            ("ENVIANDO", "Enviando"),
                            ("ENVIADO", "Enviado"),
                            ("ERROR", "Con errores"),
                        ],
                        db_index=True,
                        default="PENDIENTE",
                        max_length=12,
                    ),
                ),
                ("destinatarios", models.PositiveIntegerField(default=0)),
                ("enviados", models.PositiveIntegerField(default=0)),
                ("fallidos", models.PositiveIntegerField(default=0)),
                ("omitidos_sin_cliente", models.PositiveIntegerField(default=0)),
                ("omitidos_sin_correo", models.PositiveIntegerField(default=0)),
                ("omitidos_correo_invalido", models.PositiveIntegerField(default=0)),
                ("pendientes_json", models.TextField(blank=True)),
                ("fallidos_json", models.TextField(blank=True)),
                ("creado_por", models.CharField(blank=True, max_length=150)),
                ("creado_en", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("enviado_en", models.DateTimeField(blank=True, null=True)),
                ("error_detalle", models.TextField(blank=True)),
            ],
            options={
                "db_table": "cobranza_envios_masivos",
                "ordering": ["-creado_en"],
                "verbose_name": "Envío masivo de cobranza",
                "verbose_name_plural": "Envíos masivos de cobranza",
            },
        ),
    ]
