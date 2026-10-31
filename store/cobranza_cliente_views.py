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

            # La cartera pendiente se calcula desde cuentascobrar, que es la fuente contable
            # de los saldos por cobrar. No se calcula desde facturas.valsalfac.
            filtros_cxc = ["TRIM(COALESCE(cc.ruccedcli, '')) = %s", "UPPER(TRIM(COALESCE(cc.estpagcue, ''))) = 'PENDIENTE'"]
            parametros_cxc = [cliente.ruccedcli]
            if fecha_desde:
                filtros_cxc.append("cc.fecinicio::date >= %s::date")
                parametros_cxc.append(fecha_desde)
            if fecha_hasta:
                filtros_cxc.append("cc.fecinicio::date <= %s::date")
                parametros_cxc.append(fecha_hasta)
            if busqueda:
                filtros_cxc.append(
                    "(COALESCE(c.nomclient, '') ILIKE %s OR COALESCE(cc.numfactur::text, '') ILIKE %s)"
                )
                termino = f"%{busqueda}%"
                parametros_cxc.extend([termino, termino, termino])
            where_cxc = " AND ".join(filtros_cxc)

            cursor.execute(
                f"""
                SELECT
                    COUNT(*),
                    COUNT(*) FILTER (
                        WHERE cc.fecvencim::date < %s::date
                    ),
                    COALESCE(SUM(COALESCE(cc.valpagpar, 0)), 0)
                FROM public.cuentascobrar cc
                LEFT JOIN public.clientes c ON c.ruccedcli = cc.ruccedcli
                WHERE {where_cxc}
                """,
                [hoy.isoformat(), *parametros_cxc],
            )
            agregado = cursor.fetchone()
            resumen["cantidad"] = int(agregado[0] or 0)
            resumen["vencidas"] = int(agregado[1] or 0)
            resumen["saldo"] = Decimal(str(agregado[2] or 0))

            # Las retenciones son complementarias; si una base antigua no tiene la tabla,
            # eso no debe impedir mostrar la cartera de cuentascobrar.
            try:
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(COALESCE(rc.totretenc, 0)), 0)
                    FROM public.retencclient rc
                    WHERE rc.ruccedcli = %s
                      AND EXISTS (
                          SELECT 1 FROM public.cuentascobrar cc
                          WHERE cc.ruccedcli = rc.ruccedcli
                            AND cc.numfactur = rc.numfactur
                            AND cc.estpagcue = 'PENDIENTE'
                      )
                    """,
                    [cliente.ruccedcli],
                )
                resumen["retenciones"] = Decimal(str(cursor.fetchone()[0] or 0))
            except Exception:
                conexion.rollback()
                resumen["retenciones"] = Decimal("0.00")

            cursor.execute(
                f"""
                SELECT
                    cc.numfactur,
                    f.numserfac,
                    COALESCE(cc.fecinicio, f.fecfactur) AS fecfactur,
                    cc.fecvencim,
                    COALESCE(f.totfactur, 0) AS total,
                    COALESCE(f.valpagini, 0) AS pagado_inicial,
                    COALESCE(cc.valpagpar, 0) AS saldo,
                    COALESCE(cc.estpagcue, 'PENDIENTE') AS estado_pago,
                    COALESCE(cc.ruccedcli, '') AS ruc_deudor,
                    COALESCE(c.nomclient, 'Cliente sin nombre') AS nombre_deudor
                FROM public.cuentascobrar cc
                LEFT JOIN public.facturas f ON f.numfactur = cc.numfactur
                LEFT JOIN public.clientes c ON c.ruccedcli = cc.ruccedcli
                WHERE {where_cxc}
                ORDER BY cc.fecvencim ASC NULLS LAST, cc.fecinicio ASC NULLS LAST,
                         cc.numfactur ASC
                LIMIT 500
                """,
                parametros_cxc,
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
            fecha_factura = factura.get("fecfactur")
            fecha_vencimiento = factura.get("fecvencim")
            factura["fecha_factura"] = (
                fecha_factura.date() if hasattr(fecha_factura, "date") else fecha_factura
            )
            factura["fecha_vencimiento"] = (
                fecha_vencimiento.date() if hasattr(fecha_vencimiento, "date") else fecha_vencimiento
            )

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
