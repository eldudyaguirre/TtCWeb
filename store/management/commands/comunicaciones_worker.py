import time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from store.models.comunicacion_cliente import ComunicacionCliente

BATCH_SIZE = 40
POLL_SECONDS = 5


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
            comunicacion = (ComunicacionCliente.objects.select_for_update(skip_locked=True)
                .filter(estado=ComunicacionCliente.Estado.PENDIENTE)
                .order_by("creado_en").first())
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
        for inicio in range(0, len(pendientes), BATCH_SIZE):
            grupo = pendientes[inicio:inicio + BATCH_SIZE]
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
                comunicacion.enviados += len(grupo)
                pendientes = pendientes[len(grupo):]
                comunicacion.correos_pendientes = "\\n".join(pendientes)
            except Exception as exc:
                comunicacion.fallidos = len(pendientes)
                errores.append(f"Grupo {inicio + 1}-{inicio + len(grupo)}: {str(exc)[:500]}")
                comunicacion.error_detalle = "\\n".join(errores)
                comunicacion.estado = ComunicacionCliente.Estado.ERROR
                comunicacion.enviado_en = timezone.now()
                comunicacion.save(update_fields=["fallidos", "error_detalle", "estado", "enviado_en", "correos_pendientes"])
                self.stdout.write(self.style.ERROR(f"Comunicación {comunicacion.id}: error; quedan {len(pendientes)} pendientes."))
                return True

            comunicacion.fallidos = len(pendientes)
            comunicacion.save(update_fields=["enviados", "fallidos", "correos_pendientes"])
            self.stdout.write(f"Comunicación {comunicacion.id}: {comunicacion.enviados} enviados, {len(pendientes)} pendientes.")

        comunicacion.estado = ComunicacionCliente.Estado.ENVIADO
        comunicacion.fallidos = 0
        comunicacion.enviado_en = timezone.now()
        comunicacion.error_detalle = ""
        comunicacion.save(update_fields=["estado", "fallidos", "enviado_en", "error_detalle"])
        return True
