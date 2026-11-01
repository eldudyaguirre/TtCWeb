import json
import re
import time
import mimetypes
from types import SimpleNamespace

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.validators import validate_email
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

from store.blog_utils import sanitize_blog_html
from store.cobranza_cliente_views import _reporte_datos_cobranza, _reporte_cobranza_pdf
from store.models.comunicacion_cliente import ComunicacionCliente
from store.models.cobranza_envio_masivo import CobranzaEnvioMasivo

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
            if once:
                return
            if not procesada:
                time.sleep(interval)

    def procesar_una(self):
        # Los reportes de cobranza se procesan uno por uno, cada uno con su PDF
        # particular. Se revisan antes de las comunicaciones BCC tradicionales.
        with transaction.atomic():
            envio = (
                CobranzaEnvioMasivo.objects.select_for_update(skip_locked=True)
                .filter(estado=CobranzaEnvioMasivo.Estado.PENDIENTE)
                .order_by("creado_en")
                .first()
            )
            if envio:
                envio.estado = CobranzaEnvioMasivo.Estado.ENVIANDO
                envio.save(update_fields=["estado"])
                envio_id = envio.pk
            else:
                envio_id = None

            if envio_id is None:
                comunicacion = (
                    ComunicacionCliente.objects.select_for_update(skip_locked=True)
                    .filter(estado=ComunicacionCliente.Estado.PENDIENTE)
                    .order_by("creado_en")
                    .first()
                )
                if not comunicacion:
                    return False
                comunicacion.estado = ComunicacionCliente.Estado.ENVIANDO
                comunicacion.save(update_fields=["estado"])

        if envio_id is not None:
            return self.procesar_destinatario_cobranza(envio_id)

        pendientes = [
            correo.strip()
            for correo in (comunicacion.correos_pendientes or "").splitlines()
            if correo.strip()
        ]
        if not pendientes:
            comunicacion.estado = ComunicacionCliente.Estado.ENVIADO
            comunicacion.fallidos = 0
            comunicacion.enviado_en = timezone.now()
            comunicacion.save(update_fields=["estado", "fallidos", "enviado_en"])
            return True

        while pendientes:
            grupo = pendientes[:BATCH_SIZE]
            try:
                mensaje = EmailMultiAlternatives(
                    subject=comunicacion.asunto,
                    body=strip_tags(comunicacion.mensaje or "").strip(),
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
                comunicacion.save(update_fields=[
                    "enviados", "fallidos", "correos_pendientes"
                ])
                self.stdout.write(
                    f"Comunicación {comunicacion.id}: {comunicacion.enviados} enviados, "
                    f"{len(pendientes)} pendientes."
                )
            except Exception as exc:
                comunicacion.fallidos = len(pendientes)
                comunicacion.error_detalle = str(exc)[:2000]
                comunicacion.estado = ComunicacionCliente.Estado.ERROR
                comunicacion.enviado_en = timezone.now()
                comunicacion.correos_pendientes = "\n".join(pendientes)
                comunicacion.save(update_fields=[
                    "fallidos", "error_detalle", "estado", "enviado_en",
                    "correos_pendientes"
                ])
                self.stdout.write(self.style.ERROR(
                    f"Comunicación {comunicacion.id}: error; quedan {len(pendientes)} pendientes."
                ))
                return True

        comunicacion.estado = ComunicacionCliente.Estado.ENVIADO
        comunicacion.fallidos = 0
        comunicacion.enviado_en = timezone.now()
        comunicacion.error_detalle = ""
        comunicacion.correos_pendientes = ""
        comunicacion.save(update_fields=[
            "estado", "fallidos", "enviado_en", "error_detalle", "correos_pendientes"
        ])
        return True

    def procesar_destinatario_cobranza(self, envio_id):
        envio = CobranzaEnvioMasivo.objects.get(pk=envio_id)
        try:
            pendientes = json.loads(envio.pendientes_json or "[]")
        except (TypeError, ValueError):
            pendientes = []

        try:
            fallidos = json.loads(envio.fallidos_json or "[]")
        except (TypeError, ValueError):
            fallidos = []

        if not pendientes:
            envio.estado = (
                CobranzaEnvioMasivo.Estado.ERROR
                if fallidos else CobranzaEnvioMasivo.Estado.ENVIADO
            )
            envio.enviado_en = timezone.now()
            envio.fallidos = len(fallidos)
            envio.save(update_fields=["estado", "enviado_en", "fallidos"])
            return True

        destinatario = pendientes[0]
        identificacion = str(destinatario.get("ruc") or "")
        correo = str(destinatario.get("email") or "").strip()
        nombre = str(destinatario.get("cliente") or "Cliente").replace("\r", " ").replace("\n", " ").strip()

        try:
            validate_email(correo)
            cliente = SimpleNamespace(
                ruccedcli=identificacion,
                nomclient=nombre,
            )
            datos = _reporte_datos_cobranza(cliente)
            if not datos.get("servicios_disponibles"):
                raise RuntimeError("No se pudo consultar la lista de servicios pendientes.")

            pdf = _reporte_cobranza_pdf(cliente, datos)
            asunto_nombre = nombre.replace("\r", " ").replace("\n", " ")[:150]
            mensaje = EmailMessage(
                subject=f"Valores pendientes de pago - {asunto_nombre}",
                body=(
                    f"Estimado/a {nombre}:\n\n"
                    "Adjuntamos el reporte actualizado de sus facturas pendientes de cobro "
                    "y servicios pendientes de facturar.\n\n"
                    "El documento incluye el detalle de los valores pendientes y las "
                    "instrucciones para realizar el pago.\n\n"
                    "Saludos cordiales,\nTotalCounts"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[correo],
            )
            nombre_archivo = re.sub(r"[^A-Za-z0-9_-]", "_", identificacion) or "cliente"
            mensaje.attach(
                f"valores_pendientes_{nombre_archivo}.pdf",
                pdf,
                "application/pdf",
            )
            enviados = mensaje.send(fail_silently=False)
            if enviados != 1:
                raise RuntimeError("El servidor de correo no confirmó el envío.")

            envio.enviados += 1
            self.stdout.write(self.style.SUCCESS(
                f"Cobranza masiva {envio.id}: reporte enviado a la identificación {identificacion}."
            ))
        except Exception as exc:
            detalle = {
                "ruc": identificacion,
                "cliente": nombre,
                "email": correo,
                "error": str(exc)[:1000],
            }
            fallidos.append(detalle)
            self.stdout.write(self.style.ERROR(
                f"Cobranza masiva {envio.id}: fallo para la identificación {identificacion}: {exc}"
            ))

        pendientes = pendientes[1:]
        envio.pendientes_json = json.dumps(pendientes, ensure_ascii=False)
        envio.fallidos_json = json.dumps(fallidos, ensure_ascii=False)
        envio.fallidos = len(fallidos)

        if pendientes:
            envio.estado = CobranzaEnvioMasivo.Estado.PENDIENTE
        else:
            envio.estado = (
                CobranzaEnvioMasivo.Estado.ERROR
                if fallidos else CobranzaEnvioMasivo.Estado.ENVIADO
            )
            envio.enviado_en = timezone.now()

        errores = [
            item.get("error", "")
            for item in fallidos[-10:]
            if item.get("error")
        ]
        envio.error_detalle = "\n".join(errores)[:4000]
        envio.save(update_fields=[
            "estado", "enviados", "fallidos", "pendientes_json",
            "fallidos_json", "enviado_en", "error_detalle",
        ])
        return True
