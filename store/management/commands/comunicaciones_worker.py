import time

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
        imagen.open("rb")
        try:
            nombre = imagen.name.rsplit("/", 1)[-1].rsplit("\\\\", 1)[-1]
            contenido = imagen.read()
        finally:
            imagen.close()
        tipo = getattr(imagen.file, "content_type", None) or "application/octet-stream"
        mensaje.attach(nombre, contenido, tipo)


class Command(BaseCommand):
    help = "Procesa las comunicaciones a clientes pendientes."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Procesa una comunicación y termina.")
        parser.add_argument("--interval", type=int, default=POLL_SECONDS, help="Segundos entre revisiones.")

    def handle(self, *args, **options):
        once = options["once"]
        interval = max(1, options["interval"])
        self.stdout.write(self.style.SUCCESS("Comunicaciones worker iniciado."))
        while True:
            procesada = self.procesar_una()
            if once or not procesada:
                if once:
                    return
                time.sleep(interval)

    def procesar_una(self):
        with transaction.atomic():
            comunicacion = (
                ComunicacionCliente.objects.select_for_update(skip_locked=True)
                .filter(estado=ComunicacionCliente.Estado.PENDIENTE)
                .order_by("creado_en").first()
            )
            if not comunicacion:
                return False
            comunicacion.estado = ComunicacionCliente.Estado.ENVIANDO
            comunicacion.save(update_fields=["estado"])

        pendientes = [e.strip() for e in comunicacion.correos_pendientes.splitlines() if e.strip()]
        if not pendientes:
            comunicacion.estado = ComunicacionCliente.Estado.ENVIADO
            comunicacion.enviado_en = timezone.now()
            comunicacion.save(update_fields=["estado", "enviado_en"])
            return True

        errores = []
        while pendientes:
            grupo = pendientes[:BATCH_SIZE]
            try:
                mensaje = EmailMultiAlternatives(
                    subject=comunicacion.asunto,
                    body=strip_tags(comunicacion.mensaje).strip(),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[settings.DEFAULT_FROM_EMAIL],
                    bcc=grupo,
                )
                mensaje.attach_alternative(html_comunicacion(comunicacion), "text/html")
                adjuntar_imagen(mensaje, comunicacion)
                mensaje.send(fail_silently=False)
                comunicacion.enviados += len(grupo)
                pendientes = pendientes[len(grupo):]
                comunicacion.correos_pendientes = "\n".join(pendientes)
                comunicacion.fallidos = len(pendientes)
                comunicacion.save(update_fields=["enviados", "fallidos", "correos_pendientes"])
                self.stdout.write(
                    f"Comunicación {comunicacion.id}: {comunicacion.enviados} enviados, {len(pendientes)} pendientes."
                )
            except Exception as exc:
                errores.append(str(exc)[:500])
                comunicacion.fallidos = len(pendientes)
                comunicacion.error_detalle = "\n".join(errores)
                comunicacion.estado = ComunicacionCliente.Estado.ERROR
                comunicacion.enviado_en = timezone.now()
                comunicacion.save(update_fields=[
                    "fallidos", "error_detalle", "estado", "enviado_en", "correos_pendientes"
                ])
                self.stdout.write(self.style.ERROR(
                    f"Comunicación {comunicacion.id}: error; quedan {len(pendientes)} pendientes."
                ))
                return True

        comunicacion.estado = ComunicacionCliente.Estado.ENVIADO
        comunicacion.fallidos = 0
        comunicacion.enviado_en = timezone.now()
        comunicacion.error_detalle = ""
        comunicacion.save(update_fields=["estado", "fallidos", "enviado_en", "error_detalle"])
        return True
