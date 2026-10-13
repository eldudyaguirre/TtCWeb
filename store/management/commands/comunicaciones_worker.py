import time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from store.models.cliente import Cliente
from store.models.comunicacion_cliente import ComunicacionCliente

BATCH_SIZE = 40
POLL_SECONDS = 5


def destinatarios():
    valores = Cliente.objects.filter(activo=True).exclude(corelectr__isnull=True).exclude(corelectr__exact="").values_list("corelectr", flat=True)
    resultado = set()
    for valor in valores:
        correo = (valor or "").strip().lower()
        try:
            validate_email(correo)
        except ValidationError:
            continue
        resultado.add(correo)
    return sorted(resultado)


def html_comunicacion(c):
    return f'<div style="font-family:Arial,sans-serif;max-width:680px;margin:auto"><div style="padding:25px;text-align:center"><img src="https://www.totalcounts.com.ec/static/images/logosvg.svg" alt="TotalCounts" width="190"></div><div style="padding:30px"><div style="color:#bd1020;font-weight:bold">COMUNICACIÓN A CLIENTES</div><h1>{escape(c.titulo or c.asunto)}</h1><div style="font-size:15px;line-height:1.75">{escape(c.mensaje).replace(chr(10), "<br>")}</div></div><div style="padding:18px;text-align:center;color:#718096">TotalCounts · Cuentas con nosotros</div></div>'


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
            comunicacion = (ComunicacionCliente.objects.select_for_update(skip_locked=True).filter(estado=ComunicacionCliente.Estado.PENDIENTE).order_by("creado_en").first())
            if not comunicacion:
                return False
            comunicacion.estado = ComunicacionCliente.Estado.ENVIANDO
            comunicacion.save(update_fields=["estado"])

        lista = destinatarios()
        if not lista:
            comunicacion.estado = ComunicacionCliente.Estado.ERROR
            comunicacion.error_detalle = "No existen clientes activos con correo válido al iniciar el envío."
            comunicacion.enviado_en = timezone.now()
            comunicacion.save(update_fields=["estado", "error_detalle", "enviado_en"])
            return True

        comunicacion.destinatarios = len(lista)
        comunicacion.save(update_fields=["destinatarios"])
        enviados = 0
        fallidos = 0
        errores = []

        for inicio in range(0, len(lista), BATCH_SIZE):
            grupo = lista[inicio:inicio + BATCH_SIZE]
            try:
                mensaje = EmailMultiAlternatives(
                    comunicacion.asunto,
                    comunicacion.mensaje,
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.DEFAULT_FROM_EMAIL],
                    bcc=grupo,
                )
                mensaje.attach_alternative(html_comunicacion(comunicacion), "text/html")
                mensaje.send(fail_silently=False)
                enviados += len(grupo)
            except Exception as exc:
                fallidos += len(grupo)
                errores.append(f"Grupo {inicio + 1}-{inicio + len(grupo)}: {str(exc)[:500]}")

            comunicacion.enviados = enviados
            comunicacion.fallidos = fallidos
            comunicacion.error_detalle = "\\n".join(errores)
            comunicacion.save(update_fields=["enviados", "fallidos", "error_detalle"])
            self.stdout.write(f"Comunicación {comunicacion.id}: {enviados} enviados, {fallidos} fallidos.")

        comunicacion.estado = ComunicacionCliente.Estado.ENVIADO if not fallidos else ComunicacionCliente.Estado.ERROR
        comunicacion.enviado_en = timezone.now()
        comunicacion.save(update_fields=["estado", "enviado_en"])
        return True
