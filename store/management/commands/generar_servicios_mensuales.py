import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from store.cobranza_general_views import (
    _auditar_columnas_prefactura,
    _db,
    _ejecutar_prefacturacion_mensual,
    _resumen_prefacturacion_mensual,
    _validar_periodo_prefacturacion,
)


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Genera en prefactura los servicios del mes para clientes activos, "
        "mensuales y con procesamiento automatizado."
    )

    def add_arguments(self, parser):
        parser.add_argument("--mes", type=int, help="Mes a generar (1-12). Por defecto usa el mes actual de Ecuador.")
        parser.add_argument("--anio", type=int, help="Año a generar. Por defecto usa el año actual de Ecuador.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Consulta clientes y estructura sin insertar ni modificar consecutivos.",
        )

    def _registrar_log(self, nivel, mensaje):
        try:
            carpeta = Path(settings.BASE_DIR) / "logs"
            carpeta.mkdir(parents=True, exist_ok=True)
            archivo = carpeta / "servicios_mensuales.log"
            marca_tiempo = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
            with archivo.open("a", encoding="utf-8") as salida:
                salida.write(f"[{marca_tiempo}] [{nivel}] {mensaje}\n")
        except OSError:
            logger.exception("No se pudo escribir el log de servicios mensuales.")

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        mes_solicitado = options.get("mes") or hoy.month
        anio_solicitado = options.get("anio") or hoy.year

        try:
            mes, anio, codigo_mes = _validar_periodo_prefacturacion(
                mes_solicitado, anio_solicitado
            )

            if options["dry_run"]:
                conexion = _db()
                conexion.ensure_connection()
                with conexion.cursor() as cursor:
                    resumen = _resumen_prefacturacion_mensual(cursor, mes, anio, codigo_mes)
                    auditoria = _auditar_columnas_prefactura(cursor)
                    cursor.execute("SELECT numdetprefac FROM public.parametros")
                    parametros = cursor.fetchall()
                    if len(parametros) != 1 or parametros[0][0] is None:
                        raise RuntimeError("No existe un único consecutivo numdetprefac configurado.")

                mensaje = (
                    f"Vista previa {mes:02d}/{anio}: "
                    f"{resumen['por_generar']} servicio(s) pendientes; "
                    f"{resumen['ya_generados']} ya registrados; "
                    f"total de tarifas \${resumen['total_tarifas']}. "
                    f"Catálogo: {resumen['descripcion']}."
                )
                if not auditoria["puede_generar"]:
                    mensaje += (
                        " No se puede generar; faltan columnas obligatorias: "
                        + ", ".join(auditoria["incumplimientos"])
                    )
                    self._registrar_log("WARNING", mensaje)
                    raise CommandError(mensaje)

                self.stdout.write(self.style.WARNING(mensaje))
                self._registrar_log("DRY-RUN", mensaje)
                return

            resultado = _ejecutar_prefacturacion_mensual(mes, anio, usuario="AUTOMATICO")
            mensaje = resultado["mensaje"]
            mensaje += (
                f" Consecutivos: {resultado['numdetfac_inicial']} - {resultado['numdetfac_final']}."
                if resultado["numdetfac_inicial"] is not None
                else f" Consecutivo actual: {resultado['consecutivo_actualizado']}."
            )
            self.stdout.write(self.style.SUCCESS(mensaje))
            self._registrar_log(
                "OK",
                f"{mensaje} Periodo={mes:02d}/{anio}; "
                f"generados={resultado['cantidad_generada']}; "
                f"ya_generados={resultado['ya_generados']}; usuario=AUTOMATICO",
            )
        except CommandError:
            raise
        except Exception as exc:
            mensaje = (
                f"Falló la generación automática del periodo "
                f"{mes_solicitado:02d}/{anio_solicitado}: {type(exc).__name__}: {exc}"
            )
            logger.exception("Falló la generación automática de servicios mensuales.")
            self._registrar_log("ERROR", mensaje)
            raise CommandError(mensaje) from exc
