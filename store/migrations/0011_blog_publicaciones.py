# Migración del módulo de publicaciones del blog TotalCounts.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('store', '0010_merge_20261011_1044'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CategoriaNoticia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
                ('slug', models.SlugField(blank=True, max_length=120, unique=True)),
                ('descripcion', models.CharField(blank=True, max_length=255)),
                ('activa', models.BooleanField(default=True)),
                ('creada_en', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'blog_categorias',
                'ordering': ['nombre'],
                'verbose_name': 'Categoría del blog',
                'verbose_name_plural': 'Categorías del blog',
            },
        ),
        migrations.CreateModel(
            name='EtiquetaNoticia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=60, unique=True)),
                ('slug', models.SlugField(blank=True, max_length=80, unique=True)),
            ],
            options={
                'db_table': 'blog_etiquetas',
                'ordering': ['nombre'],
                'verbose_name': 'Etiqueta',
                'verbose_name_plural': 'Etiquetas',
            },
        ),
        migrations.CreateModel(
            name='Noticia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=220)),
                ('slug', models.SlugField(blank=True, max_length=240, unique=True)),
                ('resumen', models.CharField(help_text='Texto breve para la tarjeta del blog y el SEO.', max_length=320)),
                ('contenido', models.TextField(help_text='Contenido del artículo. Se admite HTML escrito por el equipo editorial.')),
                ('tipo', models.CharField(choices=[('NOTICIA', 'Noticia'), ('ARTICULO', 'Artículo')], db_index=True, default='NOTICIA', max_length=10)),
                ('estado', models.CharField(choices=[('BORRADOR', 'Borrador'), ('PUBLICADO', 'Publicado')], db_index=True, default='BORRADOR', max_length=10)),
                ('imagen_destacada', models.ImageField(blank=True, null=True, upload_to='blog/noticias/%Y/%m/')),
                ('texto_alternativo_imagen', models.CharField(blank=True, max_length=220)),
                ('destacada', models.BooleanField(db_index=True, default=False)),
                ('fecha_publicacion', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('meta_titulo', models.CharField(blank=True, max_length=220)),
                ('meta_descripcion', models.CharField(blank=True, max_length=320)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('autor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='noticias_blog', to=settings.AUTH_USER_MODEL)),
                ('categoria', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='noticias', to='store.categorianoticia')),
                ('etiquetas', models.ManyToManyField(blank=True, related_name='noticias', to='store.etiquetanoticia')),
            ],
            options={
                'db_table': 'blog_noticias',
                'ordering': ['-fecha_publicacion', '-creado_en'],
                'verbose_name': 'Noticia o artículo',
                'verbose_name_plural': 'Noticias y artículos',
                'indexes': [
                    models.Index(fields=['estado', 'fecha_publicacion'], name='idx_blog_estado_fecha'),
                    models.Index(fields=['tipo', 'estado'], name='idx_blog_tipo_estado'),
                ],
            },
        ),
    ]
