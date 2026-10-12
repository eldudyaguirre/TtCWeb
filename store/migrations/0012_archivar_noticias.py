from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0011_blog_publicaciones"),
    ]

    operations = [
        migrations.AlterField(
            model_name="noticia",
            name="estado",
            field=models.CharField(
                choices=[
                    ("BORRADOR", "Borrador"),
                    ("PUBLICADO", "Publicado"),
                    ("ARCHIVADO", "Archivado"),
                ],
                db_index=True,
                default="BORRADOR",
                max_length=10,
            ),
        ),
    ]
