import time
import mimetypes

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

from store.blog_utils import sanitize_blog_html
from store.models.comunicacion_cliente import ComunicacionCliente

BATCH_SIZE = 40
POLL_SECONDS = 5


def html_comunicacion(c):
    contenido = sanitize_blog_html(c.mensaje or "")
    titulo = (c.titulo or c.asunto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#263238;background:#fff">'
        '<div style="padding:25px;text-align:center"><img src="https://www.totalcounts.com.ec/static/images/logosvg.svg" '
        'alt="TotalCounts" width="190" style="max-width:100%;height:auto"></div>'
        '<div style="padding:30px"><div style="color:#bd1020;font-weight:bold">COMUNICACIÓN A CLIENTES</div>'
        f'<h1 style="font-size:26px;line-height:1.3">{titulo}</h1>'
        f'<div style="font-size:15px;line-height:1.75">{contenido}</div></div>'
        '<div style="padding:18px;text-align:center;color:#718096">TotalCounts · Cuentas con nosotros</div></div>'
    )


def adjuntar_imagen(mensaje, comunicacion):
    imagen = comunicacion.imagen_adjunto
    if imagen and imagen.name:
        nombre = imagen.name.rsplit("/", 1)[-1].rsplit("\\\\", 1)[-1]
        tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
        imagen.open("rb")
        try:
            contenido = imagen.read()
        finally:
            imagen.close()
        mensaje.attach(nombre, contenido, tipo)
