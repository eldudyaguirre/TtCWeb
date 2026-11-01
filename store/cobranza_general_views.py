from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import connections
from django.shortcuts import render
from django.utils import timezone

from .admin_views import admin_required


DB_ALIAS = "bdtotal_cobranza_general"


def _db():
    if DB_ALIAS not in connections.databases:
        config = settings.DATABASES["default"].copy()
        config["NAME"] = "BdTotal"
        connections.databases[DB_ALIAS] = config
    return connections[DB_ALIAS]


@admin_required
def admin_cobranza_general(request):
    """Consolida la cartera de facturas y los servicios por facturar de todos los clientes."""
    busqueda = request.GET.get("q", "").strip()[:120]
    tipo = request.GET.get("tipo", "todos").strip().lower()
    if tipo not in {"todos", "facturas", "servicios"}:
        tipo = "todos"

    try:
        conexion = _db()
        conexion.ensure_connection()
        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT poriva FROM public.parametros ORDER BY id LIMIT 1"
            )
            fila_iva = cursor.fetchone()
            if fila_iva is None:
                raise RuntimeError("No existe un registro en public.parametros para consultar el IVA.")
            porcentaje_iva = Decimal(str(fila_iva[0] if fila_iva[0] is not None else 15))
            if not porcentaje_iva.is_finite() or porcentaje_iva < 0 or porcentaje_iva > 100:
                raise RuntimeError("El porcentaje de IVA configurado en public.parametros.poriva no es válido.")

            condiciones = [
                "(COALESCE(f.saldo_pendiente, 0) > 0 OR COALESCE(s.subtotal_servicios, 0) > 0)"
            ]
            parametros = [timezone.localdate().isoformat()]
            if busqueda:
                condiciones.append(
                    "(COALESCE(c.nomclient, '') ILIKE %s OR COALESCE(c.ruccedcli::text, '') ILIKE %s)"
                )
                termino = f"%{busqueda}%"
                parametros.extend([termino, termino])
            if tipo == "facturas":
                condiciones.append("COALESCE(f.saldo_pendiente, 0) > 0")
            elif tipo == "servicios":
                condiciones.append("COALESCE(s.subtotal_servicios, 0) > 0")

            cursor.execute(
                f"""
                WITH cartera AS (
                    SELECT
                        LPAD(TRIM(COALESCE(cc.ruccedcli::text, '')), 13, '0') AS ruc_normalizado,
                        COUNT(DISTINCT cc.numfactur) AS cantidad_facturas,
                        COUNT(DISTINCT cc.numfactur) FILTER (
                            WHERE cc.fecvencim::date < %s::date
                        ) AS cantidad_facturas_vencidas,
                        COALESCE(SUM(COALESCE(cc.valpagpar, 0)), 0) AS saldo_pendiente
                    FROM public.cuentascobrar cc
                    WHERE UPPER(TRIM(COALESCE(cc.estpagcue, ''))) = 'PENDIENTE'
                      AND COALESCE(cc.valpagpar, 0) > 0
                    GROUP BY LPAD(TRIM(COALESCE(cc.ruccedcli::text, '')), 13, '0')
                ),
                servicios AS (
                    SELECT
                        LPAD(TRIM(COALESCE(p.ruc::text, '')), 13, '0') AS ruc_normalizado,
                        COUNT(*) AS cantidad_servicios,
                        COALESCE(
                            SUM(COALESCE(p.canfactur, 0) * COALESCE(p.preitefac, 0)),
                            0
                        ) AS subtotal_servicios
                    FROM public.prefactura p
                    GROUP BY LPAD(TRIM(COALESCE(p.ruc::text, '')), 13, '0')
                )
                SELECT
                    c.ruccedcli::text AS ruc,
                    COALESCE(c.nomclient, 'Cliente sin nombre') AS cliente,
                    COALESCE(c.activo, FALSE) AS activo,
                    COALESCE(f.cantidad_facturas, 0) AS cantidad_facturas,
                    COALESCE(f.cantidad_facturas_vencidas, 0) AS cantidad_facturas_vencidas,
                    COALESCE(f.saldo_pendiente, 0) AS saldo_pendiente,
                    COALESCE(s.cantidad_servicios, 0) AS cantidad_servicios,
                    COALESCE(s.subtotal_servicios, 0) AS subtotal_servicios
                FROM public.clientes c
                LEFT JOIN cartera f
                    ON f.ruc_normalizado = LPAD(TRIM(COALESCE(c.ruccedcli::text, '')), 13, '0')
                LEFT JOIN servicios s
                    ON s.ruc_normalizado = LPAD(TRIM(COALESCE(c.ruccedcli::text, '')), 13, '0')
                WHERE {" AND ".join(condiciones)}
                ORDER BY
                    (
                        COALESCE(f.saldo_pendiente, 0)
                        + COALESCE(s.subtotal_servicios, 0)
                          * (1 + %s::numeric / 100)
                    ) DESC,
                    c.nomclient ASC
                """,
                [*parametros, porcentaje_iva],
            )
            columnas = [col[0] for col in cursor.description]
            resultados = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

        filas = []
        resumen = {
            "clientes": 0,
            "facturas": 0,
            "facturas_vencidas": 0,
            "saldo_facturas": Decimal("0.00"),
            "servicios": 0,
            "subtotal_servicios": Decimal("0.00"),
            "iva_servicios": Decimal("0.00"),
            "total_servicios": Decimal("0.00"),
            "total_general": Decimal("0.00"),
        }

        for fila in resultados:
            saldo_facturas = Decimal(str(fila["saldo_pendiente"] or 0)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            subtotal_servicios = Decimal(str(fila["subtotal_servicios"] or 0)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            iva_servicios = (
                subtotal_servicios * porcentaje_iva / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_servicios = subtotal_servicios + iva_servicios
            total_general = saldo_facturas + total_servicios

            item = {
                "ruc": str(fila["ruc"] or "").strip(),
                "cliente": fila["cliente"],
                "activo": bool(fila["activo"]),
                "cantidad_facturas": int(fila["cantidad_facturas"] or 0),
                "cantidad_facturas_vencidas": int(fila["cantidad_facturas_vencidas"] or 0),
                "saldo_facturas": saldo_facturas,
                "cantidad_servicios": int(fila["cantidad_servicios"] or 0),
                "subtotal_servicios": subtotal_servicios,
                "iva_servicios": iva_servicios,
                "total_servicios": total_servicios,
                "total_general": total_general,
            }
            filas.append(item)

            resumen["clientes"] += 1
            resumen["facturas"] += item["cantidad_facturas"]
            resumen["facturas_vencidas"] += item["cantidad_facturas_vencidas"]
            resumen["saldo_facturas"] += saldo_facturas
            resumen["servicios"] += item["cantidad_servicios"]
            resumen["subtotal_servicios"] += subtotal_servicios
            resumen["iva_servicios"] += iva_servicios
            resumen["total_servicios"] += total_servicios
            resumen["total_general"] += total_general

        if tipo == "facturas":
            resumen["servicios"] = 0
            resumen["subtotal_servicios"] = Decimal("0.00")
            resumen["iva_servicios"] = Decimal("0.00")
            resumen["total_servicios"] = Decimal("0.00")
            resumen["total_general"] = resumen["saldo_facturas"]
        elif tipo == "servicios":
            resumen["facturas"] = 0
            resumen["facturas_vencidas"] = 0
            resumen["saldo_facturas"] = Decimal("0.00")
            resumen["total_general"] = resumen["total_servicios"]

        error = ""
    except Exception as exc:
        filas = []
        porcentaje_iva = Decimal("0.00")
        resumen = {
            "clientes": 0,
            "facturas": 0,
            "facturas_vencidas": 0,
            "saldo_facturas": Decimal("0.00"),
            "servicios": 0,
            "subtotal_servicios": Decimal("0.00"),
            "iva_servicios": Decimal("0.00"),
            "total_servicios": Decimal("0.00"),
            "total_general": Decimal("0.00"),
        }
        error = str(exc)

    return render(request, "admin/cobranzageneral.html", {
        "filas": filas,
        "resumen": resumen,
        "porcentaje_iva": porcentaje_iva,
        "busqueda": busqueda,
        "tipo": tipo,
        "error": error,
    })
