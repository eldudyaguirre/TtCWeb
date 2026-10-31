from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db import connections
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

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


def _fecha_filtro(valor, defecto):
    try:
        return date.fromisoformat(valor) if valor else defecto
    except (TypeError, ValueError):
        return defecto


@admin_required
def admin_cobranza_cliente(request, ruc):
    """Panel inicial de cobranza de una base de datos de cliente."""
    cliente = get_object_or_404(Cliente, pk=ruc)
    hoy = timezone.localdate()
    primer_dia_mes = hoy.replace(day=1)
    fecha_desde = _fecha_filtro(request.GET.get("fecha_desde", ""), primer_dia_mes)
    fecha_hasta = _fecha_filtro(request.GET.get("fecha_hasta", ""), hoy)
    busqueda = request.GET.get("q", "").strip()[:120]

    if fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde
        messages.info(request, "Se invirtieron las fechas para consultar el período correcto.")

    filtros_sql = [
        "COALESCE(f.valsalfac, 0) > 0",
        "f.fecfactur::date >= %s::date",
        "f.fecfactur::date <= %s::date",
    ]
    parametros_sql = [fecha_desde, fecha_hasta]
    if busqueda:
        filtros_sql.append(
            "(COALESCE(c.nomclient, '') ILIKE %s OR COALESCE(c.ruccedcli, '') ILIKE %s "
            "OR COALESCE(f.numfactur, '') ILIKE %s OR COALESCE(f.numserfac, '') ILIKE %s)"
        )
        termino = f"%{busqueda}%"
        parametros_sql.extend([termino, termino, termino, termino])
    where_sql = " AND ".join(filtros_sql)

    facturas = []
    resumen = {
        "cantidad": 0,
        "vencidas": 0,
        "saldo": Decimal("0.00"),
        "retenciones": Decimal("0.00"),
    }
    db_error = ""

    try:
        conexion = _conexion_cliente(cliente.ruccedcli)
        conexion.ensure_connection()
        with conexion.cursor() as cursor:
            # retencclient contiene las retenciones relacionadas con facturas de venta.
            # Si una base antigua aún no tiene esa tabla, se muestra la cobranza sin ese dato.
            try:
                cursor.execute(
                    "SELECT numfactur, COALESCE(SUM(totretenc), 0) "
                    "FROM public.retencclient GROUP BY numfactur"
                )
                retenciones_por_factura = {
                    str(numero or "").strip(): Decimal(str(total or 0))
                    for numero, total in cursor.fetchall()
                }
            except Exception:
                conexion.rollback()
                retenciones_por_factura = {}

            cursor.execute(
                f"""
                SELECT
                    f.numfactur,
                    f.numserfac,
                    f.fecfactur,
                    f.fecvencim,
                    COALESCE(f.totfactur, 0) AS total,
                    COALESCE(f.valpagini, 0) AS pagado_inicial,
                    COALESCE(f.valsalfac, 0) AS saldo,
                    COALESCE(f.estpagfac, 'PENDIENTE') AS estado_pago,
                    COALESCE(c.ruccedcli, '') AS ruc_deudor,
                    COALESCE(c.nomclient, 'Cliente sin nombre') AS nombre_deudor
                FROM public.facturas f
                LEFT JOIN public.clientes c ON c.ruccedcli = f.ruccedcli
                WHERE {where_sql}
                ORDER BY f.fecvencim ASC NULLS LAST, f.fecfactur ASC NULLS LAST,
                         f.numfactur ASC
                LIMIT 500
                """,
                parametros_sql,
            )
            columnas = [col[0] for col in cursor.description]
            facturas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

        for factura in facturas:
            numero = str(factura.get("numfactur") or "").strip()
            factura["retenciones"] = retenciones_por_factura.get(numero, Decimal("0.00"))
            factura["vencida"] = bool(
                factura.get("fecvencim")
                and factura["fecvencim"].date() < hoy
                and Decimal(str(factura.get("saldo") or 0)) > 0
            )
            factura["fecha_factura"] = factura["fecfactur"].date() if factura.get("fecfactur") else None
            factura["fecha_vencimiento"] = factura["fecvencim"].date() if factura.get("fecvencim") else None

        resumen["cantidad"] = len(facturas)
        resumen["vencidas"] = sum(1 for factura in facturas if factura["vencida"])
        resumen["saldo"] = sum(
            (Decimal(str(factura.get("saldo") or 0)) for factura in facturas),
            Decimal("0.00"),
        )
        resumen["retenciones"] = sum(
            (factura["retenciones"] for factura in facturas),
            Decimal("0.00"),
        )
    except Exception as exc:
        db_error = str(exc)
        messages.error(
            request,
            f"No se pudo consultar la cobranza de la base {cliente.ruccedcli}. "
            "Verifica la conexión y la estructura de la base del cliente.",
        )

    return render(
        request,
        "admin/cobranza_cliente.html",
        {
            "cliente": cliente,
            "facturas": facturas,
            "resumen": resumen,
            "db_error": db_error,
            "filtros": {
                "fecha_desde": fecha_desde.isoformat(),
                "fecha_hasta": fecha_hasta.isoformat(),
                "q": busqueda,
            },
            "limite_resultados": len(facturas) >= 500,
        },
    )
