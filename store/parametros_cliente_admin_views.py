from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.db import connections, transaction
from django.shortcuts import get_object_or_404, redirect, render

from .admin_views import admin_required
from .models import Cliente


def _conexion_cliente(ruc):
    db_name = str(ruc or "").strip()
    alias = f"cliente_{db_name}"
    if alias not in connections.databases:
        config = settings.DATABASES["default"].copy()
        config["NAME"] = db_name
        connections.databases[alias] = config
    return connections[alias]


def _a_fecha(valor):
    if not valor:
        return None
    return valor.date() if isinstance(valor, datetime) else valor


def _leer_fila(cursor, tabla, columnas):
    cursor.execute(f"SELECT {', '.join(columnas)} FROM public.{tabla} LIMIT 1")
    fila = cursor.fetchone()
    if fila is None:
        raise RuntimeError(f"La tabla {tabla} no contiene una fila de parámetros.")
    return dict(zip(columnas, fila))


@admin_required
def admin_parametros_cliente(request, ruc):
    cliente = get_object_or_404(Cliente, pk=ruc)
    alias = f"cliente_{str(cliente.ruccedcli).strip()}"
    db_name = str(cliente.ruccedcli).strip()
    parametros_columnas = [
        "numfactur", "numserfac", "numautfac", "fecautfac",
        "numretenc", "numserret", "numautret", "fecautret",
        "numnc", "numsernc", "numautnc", "fecautnc",
        "poriva", "numdialisfac", "obliconta", "tipcontab",
        "contrespec", "codcontrespec", "asumeiess", "trabacti",
        "calculoice", "codest", "ptoemi", "codval", "facemi",
        "retemi", "ncemi", "facfiselec",
    ]

    try:
        conexion = _conexion_cliente(db_name)
        conexion.ensure_connection()
        with conexion.cursor() as cursor:
            parametros = _leer_fila(cursor, "parametros", parametros_columnas)
            columnas_contables = ["actperiod", "ultperiod", "ultpercon"]
            try:
                contables = _leer_fila(cursor, "parametroscontables", columnas_contables)
            except RuntimeError:
                contables = {nombre: None for nombre in columnas_contables}
    except Exception as exc:
        messages.error(request, f"No se pudo leer la configuración de la base {db_name}: {exc}")
        return redirect("admin_cliente", ruc=cliente.ruccedcli)

    if request.method == "POST":
        try:
            def entero(nombre, defecto=0):
                valor = request.POST.get(nombre, "").strip()
                return int(valor) if valor else defecto

            def fecha(nombre):
                valor = request.POST.get(nombre, "").strip()
                return date.fromisoformat(valor) if valor else None

            def texto(nombre, defecto=""):
                return request.POST.get(nombre, defecto).strip()

            obligado = "SI" if request.POST.get("obliconta") == "SI" else "NO"
            especial = "SI" if request.POST.get("contrespec") == "SI" else "NO"
            asume_iess = "SI" if request.POST.get("asumeiess") == "SI" else "NO"
            trabajadores = "SI" if request.POST.get("trabacti") == "SI" else "NO"
            calculo_ice = request.POST.get("calculoice") == "1"
            emision = texto("facfiselec", "ELECTRONICA").upper()
            if emision not in ("FISICA", "ELECTRONICA"):
                raise ValueError("Selecciona emisión física o electrónica.")

            iva_texto = texto("poriva", "0").replace(",", ".")
            iva = float(iva_texto)
            dias_listado = entero("numdialisfac")
            if dias_listado < 0:
                raise ValueError("Los días para listar facturas no pueden ser negativos.")
            if not 0 <= iva <= 100:
                raise ValueError("El porcentaje de IVA debe estar entre 0 y 100.")

            valores = {
                "numfactur": entero("numfactur"),
                "numserfac": texto("numserfac"),
                "numautfac": texto("numautfac"),
                "fecautfac": fecha("fecautfac"),
                "numretenc": entero("numretenc"),
                "numserret": texto("numserret"),
                "numautret": entero("numautret"),
                "fecautret": fecha("fecautret"),
                "numnc": entero("numnc"),
                "numsernc": texto("numsernc"),
                "numautnc": entero("numautnc"),
                "fecautnc": fecha("fecautnc"),
                "poriva": iva,
                "numdialisfac": dias_listado,
                "obliconta": obligado,
                "tipcontab": "Automática" if obligado == "SI" else "Manual",
                "contrespec": especial,
                "codcontrespec": texto("codcontrespec", "0") or "0",
                "asumeiess": asume_iess,
                "trabacti": trabajadores,
                "calculoice": calculo_ice,
                "codest": texto("codest"),
                "ptoemi": texto("ptoemi"),
                "codval": texto("codval"),
                "facemi": texto("facemi"),
                "retemi": texto("retemi"),
                "ncemi": texto("ncemi"),
                "facfiselec": emision,
            }

            periodo_texto = texto("actperiod")
            periodo = datetime.strptime(periodo_texto, "%Y-%m").date().replace(day=1) if periodo_texto else None
            ultimo_periodo = periodo - timedelta(days=1) if periodo else None
            ultimo_periodo_codigo = periodo.strftime("%Y%m") if periodo else None

            with transaction.atomic(using=alias):
                with conexion.cursor() as cursor:
                    asignaciones = ", ".join(f"{columna} = %s" for columna in valores)
                    cursor.execute(
                        f"UPDATE public.parametros SET {asignaciones} "
                        "WHERE ctid = (SELECT ctid FROM public.parametros LIMIT 1)",
                        list(valores.values()),
                    )
                    if cursor.rowcount == 0:
                        raise RuntimeError("No existe una fila en la tabla parametros para actualizar.")

                    cursor.execute("SELECT 1 FROM public.parametroscontables LIMIT 1")
                    existe_contable = cursor.fetchone() is not None
                    if existe_contable:
                        cursor.execute(
                            """
                            UPDATE public.parametroscontables
                            SET actperiod = %s, ultperiod = %s, ultpercon = %s
                            WHERE ctid = (
                                SELECT ctid FROM public.parametroscontables LIMIT 1
                            )
                            """,
                            [periodo, ultimo_periodo, ultimo_periodo_codigo],
                        )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO public.parametroscontables (actperiod, ultperiod, ultpercon)
                            VALUES (%s, %s, %s)
                            """,
                            [periodo, ultimo_periodo, ultimo_periodo_codigo],
                        )

            messages.success(request, "La configuración del cliente se guardó correctamente.")
            return redirect("admin_parametros_cliente", ruc=cliente.ruccedcli)
        except (ValueError, TypeError) as exc:
            messages.error(request, f"Revisa los datos ingresados: {exc}")
        except Exception as exc:
            messages.error(request, f"No se pudo guardar la configuración: {exc}")

    parametros["fecautfac"] = _a_fecha(parametros.get("fecautfac"))
    parametros["fecautret"] = _a_fecha(parametros.get("fecautret"))
    parametros["fecautnc"] = _a_fecha(parametros.get("fecautnc"))
    periodo_contable = contables.get("actperiod")
    if isinstance(periodo_contable, datetime):
        periodo_contable = periodo_contable.strftime("%Y-%m")
    elif isinstance(periodo_contable, date):
        periodo_contable = periodo_contable.strftime("%Y-%m")
    else:
        periodo_contable = ""

    return render(request, "admin/parametros_cliente.html", {
        "cliente": cliente,
        "ruc": db_name,
        "db_name": db_name,
        "parametros": parametros,
        "periodo_contable": periodo_contable,
        "db_status": "Conectada",
    })
