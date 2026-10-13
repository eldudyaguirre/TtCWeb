from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0015_comunicacion_cliente")]

    operations = [
        migrations.AlterField(
            model_name="comunicacioncliente",
            name="estado",
            field=models.CharField(
                choices=[
                    ("BORRADOR", "Borrador"),
                    ("PENDIENTE", "Pendiente"),
                    ("ENVIANDO", "Enviando"),
                    ("ENVIADO", "Enviado"),
                    ("ERROR", "Con errores"),
                ], db_index=True, default="BORRADOR", max_length=12),
        ),
        migrations.AddField(
            model_name="comunicacioncliente",
            name="correos_pendientes",
            field=models.TextField(blank=True),
        ),
    ]
