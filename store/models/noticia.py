from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class CategoriaNoticia(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    descripcion = models.CharField(max_length=255, blank=True)
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'blog_categorias'
        ordering = ['nombre']
        verbose_name = 'Categoría del blog'
        verbose_name_plural = 'Categorías del blog'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class EtiquetaNoticia(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)

    class Meta:
        db_table = 'blog_etiquetas'
        ordering = ['nombre']
        verbose_name = 'Etiqueta'
        verbose_name_plural = 'Etiquetas'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class Noticia(models.Model):
    class Tipo(models.TextChoices):
        NOTICIA = 'NOTICIA', 'Noticia'
        ARTICULO = 'ARTICULO', 'Artículo'

    class Estado(models.TextChoices):
        BORRADOR = 'BORRADOR', 'Borrador'
        PUBLICADO = 'PUBLICADO', 'Publicado'

    titulo = models.CharField(max_length=220)
    slug = models.SlugField(max_length=240, unique=True, blank=True)
    resumen = models.CharField(max_length=320, help_text='Texto breve para la tarjeta del blog y el SEO.')
    contenido = models.TextField(help_text='Contenido del artículo. Se admite HTML escrito por el equipo editorial.')
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.NOTICIA, db_index=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.BORRADOR, db_index=True)
    categoria = models.ForeignKey(
        CategoriaNoticia, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='noticias',
    )
    etiquetas = models.ManyToManyField(EtiquetaNoticia, blank=True, related_name='noticias')
    imagen_destacada = models.ImageField(upload_to='blog/noticias/%Y/%m/', blank=True, null=True)
    texto_alternativo_imagen = models.CharField(max_length=220, blank=True)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='noticias_blog',
    )
    destacada = models.BooleanField(default=False, db_index=True)
    fecha_publicacion = models.DateTimeField(blank=True, null=True, db_index=True)
    meta_titulo = models.CharField(max_length=220, blank=True)
    meta_descripcion = models.CharField(max_length=320, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'blog_noticias'
        ordering = ['-fecha_publicacion', '-creado_en']
        verbose_name = 'Noticia o artículo'
        verbose_name_plural = 'Noticias y artículos'
        indexes = [
            models.Index(fields=['estado', 'fecha_publicacion'], name='idx_blog_estado_fecha'),
            models.Index(fields=['tipo', 'estado'], name='idx_blog_tipo_estado'),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.titulo)[:220] or 'publicacion'
            candidate = base_slug
            suffix = 2
            while Noticia.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f'{base_slug[:210]}-{suffix}'
                suffix += 1
            self.slug = candidate
        if self.estado == self.Estado.PUBLICADO and self.fecha_publicacion is None:
            self.fecha_publicacion = timezone.now()
        super().save(*args, **kwargs)

    @property
    def titulo_seo(self):
        return self.meta_titulo or self.titulo

    @property
    def descripcion_seo(self):
        return self.meta_descripcion or self.resumen

    def __str__(self):
        return self.titulo
