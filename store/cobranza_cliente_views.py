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
    # La cobranza debe incluir toda la cartera pendiente, aunque la factura sea de meses anteriores.
    # Las fechas son filtros opcionales, no un rango predeterminado limitado al mes actual.
    fecha_desde = _fecha_filtro(request.GET.get("fecha_desde", ""), None)
    fecha_hasta = _fecha_filtro(request.GET.get("fecha_hasta", ""), None)
    busqueda = request.GET.get("q", "").strip()[:120]

    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde
        messages.info(request, "Se invirtieron las fechas para consultar el período correcto.")

    filtros_sql = ["COALESCE(f.valsalfac, 0) > 0"]
    parametros_sql = []
    if fecha_desde:
        filtros_sql.append("f.fecfactur::date >= %s::date")
        parametros_sql.append(fecha_desde)
    if fecha_hasta:
        filtros_sql.append("f.fecfactur::date <= %s::date")
        parametros_sql.append(fecha_hasta)
    if busqueda:
        filtros_sql.append(
            "(COALESCE(c.nomclient, '') ILIKE %s OR COALESCE(c.ruccedcli, '') ILIKE %s "
            "OR COALESCE(f.numfactur, '') ILIKE %s OR COALESCE(f.numserfac, '') ILIKE %s)"
        )
        termino = f"%{busqueda}%"
        parametros_sql.extend([termino, termino, termino, termino])
    where_sql = " AND ".join(filtros_sql)

    facturas = []
    servicios_pendientes = []
    resumen_servicios = {"cantidad": 0, "total": Decimal("0.00")}
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
                    "SELECT numfactur, ruccedcli, COALESCE(SUM(totretenc), 0) "
                    "FROM public.retencclient GROUP BY numfactur, ruccedcli"
                )
                retenciones_por_factura = {
                    (str(numero or "").strip(), str(ruc_cliente or "").strip()): Decimal(str(total or 0))
                    for numero, ruc_cliente, total in cursor.fetchall()
                }
            except Exception:
                conexion.rollback()
                retenciones_por_factura = {}

            try:
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*),
                        COUNT(*) FILTER (
                            WHERE f.fecvencim::date < %s::date
                              AND COALESCE(f.valsalfac, 0) > 0
                        ),
                        COALESCE(SUM(COALESCE(f.valsalfac, 0)), 0),
                        COALESCE(SUM(COALESCE(rc.total_retenciones, 0)), 0)
                    FROM public.facturas f
                    LEFT JOIN public.clientes c ON c.ruccedcli = f.ruccedcli
                    LEFT JOIN (
                        SELECT numfactur, ruccedcli, SUM(totretenc) AS total_retenciones
                        FROM public.retencclient
                        GROUP BY numfactur, ruccedcli
                    ) rc ON rc.numfactur = f.numfactur AND rc.ruccedcli = f.ruccedcli
                    WHERE {where_sql}
                    """,
                    [hoy.isoformat(), *parametros_sql],
                )
                agregado = cursor.fetchone()
                resumen["cantidad"] = int(agregado[0] or 0)
                resumen["vencidas"] = int(agregado[1] or 0)
                resumen["saldo"] = Decimal(str(agregado[2] or 0))
                resumen["retenciones"] = Decimal(str(agregado[3] or 0))
            except Exception:
                # Bases antiguas sin retencclient: el saldo y los contadores siguen disponibles.
                conexion.rollback()
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*),
                        COUNT(*) FILTER (
                            WHERE f.fecvencim::date < %s::date
                              AND COALESCE(f.valsalfac, 0) > 0
                        ),
                        COALESCE(SUM(COALESCE(f.valsalfac, 0)), 0)
                    FROM public.facturas f
                    LEFT JOIN public.clientes c ON c.ruccedcli = f.ruccedcli
                    WHERE {where_sql}
                    """,
                    [hoy.isoformat(), *parametros_sql],
                )
                agregado = cursor.fetchone()
                resumen["cantidad"] = int(agregado[0] or 0)
                resumen["vencidas"] = int(agregado[1] or 0)
                resumen["saldo"] = Decimal(str(agregado[2] or 0))
                resumen["retenciones"] = Decimal("0.00")

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
            ruc_deudor = str(factura.get("ruc_deudor") or "").strip()
            factura["retenciones"] = retenciones_por_factura.get((numero, ruc_deudor), Decimal("0.00"))
            factura["vencida"] = bool(
                factura.get("fecvencim")
                and factura["fecvencim"].date() < hoy
                and Decimal(str(factura.get("saldo") or 0)) > 0
            )
            factura["fecha_factura"] = factura["fecfactur"].date() if factura.get("fecfactur") else None
            factura["fecha_vencimiento"] = factura["fecvencim"].date() if factura.get("fecvencim") else None

        # Servicios registrados en prefactura: solo los que aún no se han facturado.
        # El proceso normal de facturación los traslada a facturas/detallefacturas.
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT numdetfac, coditeinv, desiteinv,
                           COALESCE(canfactur, 0) AS cantidad,
                           COALESCE(preitefac, 0) AS precio,
                           COALESCE(canfactur, 0) * COALESCE(preitefac, 0) AS total,
                           fecha
                    FROM public.prefactura
                    WHERE ruc = %s
                    ORDER BY fecha DESC NULLS LAST, numdetfac DESC
                    LIMIT 500
                    """,
                    [cliente.ruccedcli],
                )
                columnas_serv = [col[0] for col in cursor.description]
                servicios_pendientes = [dict(zip(columnas_serv, fila)) for fila in cursor.fetchall()]
                resumen_servicios["cantidad"] = len(servicios_pendientes)
                resumen_servicios["total"] = sum(
                    (Decimal(str(item.get("total") or 0)) for item in servicios_pendientes),
                    Decimal("0.00"),
                )
        except Exception:
            # Una base que aún no tenga prefactura no debe impedir consultar las facturas.
            conexion.rollback()
            servicios_pendientes = []
            resumen_servicios = {"cantidad": 0, "total": Decimal("0.00")}

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
            "servicios_pendientes": servicios_pendientes,
            "resumen_servicios": resumen_servicios,
            "resumen": resumen,
            "db_error": db_error,
            "filtros": {
                "fecha_desde": fecha_desde.isoformat() if fecha_desde else "",
                "fecha_hasta": fecha_hasta.isoformat() if fecha_hasta else "",
                "q": busqueda,
            },
            "limite_resultados": len(facturas) >= 500,
        },
    )
