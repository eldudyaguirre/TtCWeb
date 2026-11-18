import logging
import os
import socket
import time
import traceback
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction
from django.utils import timezone

from store.models import Cliente
from store.models.iess_rdep_job import IessRdepJob
from store.models.archivo import Archivo
from store.services.archivos.storage import data_root

logger = logging.getLogger("iess.rdep.worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | IESS-RDEP | %(levelname)s | %(message)s")

LOGIN_URL = "https://www.iess.gob.ec/empleador-web/pages/principal.jsf"
CONSULTA_URL = "https://www.iess.gob.ec/empleador-web/pages/consultas/consultaPlanillas.jsf"


class Command(BaseCommand):
    help = "Worker de consultas consolidadas IESS para RDEP."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=5)
        parser.add_argument("--headful", action="store_true", help="Abre Chromium visible para diagnóstico.")

    def handle(self, *args, **options):
        interval = max(2, options["interval"])
        self.headful = options["headful"]
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}"
        self.stdout.write(self.style.SUCCESS(f"IESS RDEP Worker iniciado: {self.worker_id}"))
        while True:
            close_old_connections()
            try:
                job = self.claim_job()
                if job:
                    self.process_job(job.pk)
                elif options["once"]:
                    return
                else:
                    time.sleep(interval)
            except Exception:
                logger.exception("Error general del worker.")
                if options["once"]:
                    raise
                time.sleep(interval)
            finally:
                close_old_connections()
            if options["once"]:
                return

    def claim_job(self):
        with transaction.atomic():
            job = (
                IessRdepJob.objects.select_for_update(skip_locked=True)
                .filter(estado=IessRdepJob.Estado.PENDIENTE)
                .order_by("creado_en")
                .first()
            )
            if not job:
                return None
            job.estado = IessRdepJob.Estado.PROCESANDO
            job.worker_id = self.worker_id
            job.iniciado_en = timezone.now()
            job.heartbeat_en = timezone.now()
            job.mensaje = "Iniciando sesión en el portal del IESS."
            job.save(update_fields=["estado", "worker_id", "iniciado_en", "heartbeat_en", "mensaje"])
            return job

    def process_job(self, job_id):
        job = IessRdepJob.objects.select_related("cliente").get(pk=job_id)
        cliente = job.cliente
        cedula = str(cliente.cediess or "").strip()
        clave = str(cliente.claveiess or "")
        if not cedula or not clave:
            raise_job_error(job, "El cliente no tiene cédula patronal y clave IESS configuradas.")
            return

        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
        except ImportError:
            raise_job_error(job, "Playwright no está instalado en el entorno de TtCWeb.")
            return

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=not self.headful)
                context = browser.new_context(accept_downloads=True, viewport={"width": 1365, "height": 900})
                page = context.new_page()
                page.set_default_timeout(25000)
                page.goto(LOGIN_URL, wait_until="domcontentloaded")
                campos_texto = page.locator("input[type='text'], input:not([type])")
                campos_clave = page.locator("input[type='password']")
                if campos_texto.count() < 1 or campos_clave.count() < 1:
                    raise RuntimeError("No se reconocieron los campos de acceso del portal IESS.")
                campos_texto.first.fill(cedula)
                campos_clave.first.fill(clave)
                boton = page.get_by_role("button", name="Ingresar")
                if boton.count():
                    boton.first.click()
                else:
                    submit = page.locator("input[type='submit'], button[type='submit']")
                    if not submit.count():
                        raise RuntimeError("No se encontró el botón de ingreso del portal IESS.")
                    submit.first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(1800)
                if "principal.jsf" in page.url and page.locator("input[type='password']").count():
                    raise RuntimeError("El IESS no aceptó el acceso o solicitó una verificación adicional.")
                job.mensaje = "Acceso realizado; abriendo consulta de planillas."
                job.heartbeat_en = timezone.now()
                job.save(update_fields=["mensaje", "heartbeat_en"])
                page.goto(CONSULTA_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                if page.locator("input[type='password']").count():
                    raise RuntimeError("La sesión IESS no quedó autenticada; revisar credenciales o verificación.")
                self.consultar_y_descargar(page, job, cliente)
                context.close()
                browser.close()
        except Exception as exc:
            logger.exception("Falló job IESS RDEP %s (cliente %s, año %s).", job.pk, cliente.pk, job.anio)
            raise_job_error(job, f"{type(exc).__name__}: {exc}")

    def consultar_y_descargar(self, page, job, cliente):
        # El portal es JSF y sus controles pueden cambiar. Se usan etiquetas visibles
        # y se falla de forma explícita si el formulario no coincide, sin descargar
        # un archivo de otra consulta.
        selects = page.locator("select")
        if selects.count() < 2:
            raise RuntimeError("No se encontraron los selectores de Alcance y Tipo de Planilla.")
        selects.nth(0).select_option(label="Consolidado")
        selects.nth(1).select_option(label="Todos")
        entradas = page.locator("input[type='text'], input:not([type])")
        if entradas.count() < 2:
            raise RuntimeError("No se encontraron los campos Desde y Hasta del período.")
        # El primer campo es "Cédula del Afiliado"; no lo modificamos.
        # Los dos últimos campos de texto corresponden a Desde y Hasta.
        entradas.nth(entradas.count() - 2).fill(f"{job.anio}-01")
        entradas.last.fill(f"{job.anio}-12")
        aceptar = page.locator("input[type=submit][value*=Aceptar], input[type=button][value*=Aceptar], button:has-text(Aceptar), a:has-text(Aceptar)")
        if not aceptar.count():
            raise RuntimeError("No se encontró el botón Aceptar de la consulta.")
        aceptar.first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)
        job.mensaje = "Consulta enviada; buscando la descarga Excel."
        job.heartbeat_en = timezone.now()
        job.save(update_fields=["mensaje", "heartbeat_en"])

        excel = page.get_by_role("link", name="XLS")
        if not excel.count():
            excel = page.locator("a, button").filter(has_text="XLS")
        if not excel.count():
            excel = page.locator("a").filter(has=page.locator("img[alt*='XLS'], img[src*='xls'], img[title*='XLS']"))
        if not excel.count():
            raise RuntimeError("La consulta terminó, pero no se identificó el botón Excel/XLS.")
        with page.expect_download(timeout=60000) as descarga:
            excel.first.click()
        archivo = descarga.value
        destino_dir = data_root() / str(cliente.ruccedcli).strip() / "anexos" / "rdep" / str(job.anio)
        destino_dir.mkdir(parents=True, exist_ok=True)
        extension = Path(archivo.suggested_filename or "").suffix.lower()
        if extension not in {".xls", ".xlsx"}:
            extension = ".xls"
        nombre = f"IESS_RDEP_PLANILLAS__{job.anio}{extension}"
        destino = destino_dir / nombre
        archivo.save_as(str(destino))
        if not destino.is_file() or destino.stat().st_size < 100:
            raise RuntimeError("El archivo Excel descargado está vacío o incompleto.")
        relative = (Path(str(cliente.ruccedcli).strip()) / "anexos" / "rdep" / str(job.anio) / nombre).as_posix()
        import hashlib
        digest = hashlib.sha256(destino.read_bytes()).hexdigest()
        Archivo.objects.update_or_create(
            ruta_relativa=relative,
            defaults={
                "cliente": cliente,
                "tipo": Archivo.Tipo.DOCUMENTO,
                "nombre_original": nombre,
                "nombre_fisico": nombre,
                "extension": extension,
                                "mime_type": (
                    "application/vnd.ms-excel" if extension == ".xls"
                    else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                "tamano": destino.stat().st_size,
                "sha256": digest,
                "creado_por": None,
                "activo": True,
            },
        )
        job.estado = IessRdepJob.Estado.COMPLETADO
        job.archivo_relativo = relative
        job.mensaje = "Excel de planillas descargado y guardado correctamente."
        job.terminado_en = timezone.now()
        job.heartbeat_en = timezone.now()
        job.save(update_fields=["estado", "archivo_relativo", "mensaje", "terminado_en", "heartbeat_en"])


def raise_job_error(job, message):
    job.estado = IessRdepJob.Estado.ERROR
    job.mensaje = "La consulta IESS terminó con error."
    job.error_detalle = str(message)[:4000]
    job.terminado_en = timezone.now()
    job.save(update_fields=["estado", "mensaje", "error_detalle", "terminado_en"])
    logger.error("Job %s: %s", job.pk, message)
