from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0012_archivar_noticias"),
    ]

    operations = [
        migrations.AddField(
            model_name="noticia",
            name="autor_nombre",
            field=models.CharField(
                blank=True,
                help_text="Nombre que se mostrará como firma pública del artículo.",
                max_length=150,
            ),
        ),
    ]
