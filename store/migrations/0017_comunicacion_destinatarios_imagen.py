from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0016_comunicacion_pendiente")]

    operations = [
        migrations.AddField(
            model_name="comunicacioncliente",
            name="destinatario_tipo",
            field=models.CharField(
                choices=[("TODOS", "Todos los clientes"), ("INDIVIDUAL", "Un destinatario")],
                default="TODOS",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="comunicacioncliente",
            name="destinatario_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="comunicacioncliente",
            name="imagen_adjunto",
            field=models.ImageField(blank=True, null=True, upload_to="comunicaciones/%Y/%m/"),
        ),
    ]
