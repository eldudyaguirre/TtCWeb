from django.db import migrations
from django.utils.text import slugify


CATEGORIAS = [
    ("Tributario", "Impuestos, declaraciones y obligaciones ante el SRI."),
    ("Contable", "Información y buenas prácticas de gestión contable."),
    ("Laboral", "Obligaciones laborales, nómina y seguridad social."),
    ("Societario", "Constitución, administración y obligaciones societarias."),
    ("Tecnología", "Herramientas digitales, automatización y tecnología empresarial."),
    ("Actualidad empresarial", "Noticias y novedades de interés para empresas y emprendedores."),
]

ETIQUETAS = [
    "SRI",
    "Impuestos",
    "IVA",
    "Impuesto a la Renta",
    "Retenciones",
    "RUC",
    "Facturación electrónica",
    "Anexos tributarios",
    "Obligaciones tributarias",
    "Contabilidad",
    "Nómina",
    "IESS",
    "Emprendimiento",
    "Empresas",
    "Tecnología",
]


def crear_catalogos_blog(apps, schema_editor):
    Categoria = apps.get_model("store", "CategoriaNoticia")
    Etiqueta = apps.get_model("store", "EtiquetaNoticia")

    for nombre, descripcion in CATEGORIAS:
        Categoria.objects.get_or_create(
            nombre=nombre,
            defaults={
                "slug": slugify(nombre)[:120],
                "descripcion": descripcion,
                "activa": True,
            },
        )

    for nombre in ETIQUETAS:
        Etiqueta.objects.get_or_create(
            nombre=nombre,
            defaults={"slug": slugify(nombre)[:80]},
        )


def revertir_catalogos_blog(apps, schema_editor):
    # No eliminar categorías ni etiquetas: podrían haberse usado en publicaciones.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0013_noticia_autor_nombre"),
    ]

    operations = [
        migrations.RunPython(crear_catalogos_blog, revertir_catalogos_blog),
    ]
