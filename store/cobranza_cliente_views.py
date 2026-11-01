import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.db import connections
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .admin_views import admin_required
from .models import Cliente

logger = logging.getLogger(__name__)


def _conexion_cliente(ruc=None):
    """Conecta a la base central BdTotal; la cobranza no vive en la BD del cliente."""
    alias = "bdtotal_cobranza"
    if alias not in connections.databases:
        config = settings.DATABASES["default"].copy()
        config["NAME"] = "BdTotal"
        connections.databases[alias] = config
    return connections[alias]


def _fecha_filtro(valor, defecto):
    try:
        return date.fromisoformat(valor) if valor else defecto
    except (TypeError, ValueError):
        return defecto


@admin_required
def admin_cobranza_cliente(request, ruc):
    """Panel de cobranza consultando la base central BdTotal."""
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
    items_catalogo = []
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
            filtros_cxc = ["LPAD(TRIM(COALESCE(cc.ruccedcli::text, '')), 13, '0') = LPAD(%s, 13, '0')", "UPPER(TRIM(COALESCE(cc.estpagcue, ''))) = 'PENDIENTE'", "COALESCE(cc.valpagpar, 0) > 0"]
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
                parametros_cxc.extend([termino, termino])
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

            # Diagnóstico temporal para confirmar base y registros que realmente lee Cobranza.
            cursor.execute(
                """
                SELECT current_database(),
                       COUNT(*),
                       COALESCE(SUM(COALESCE(valpagpar, 0)), 0),
                       COALESCE(STRING_AGG(
                           CONCAT(COALESCE(numfactur::text, ''), ':',
                                  COALESCE(estpagcue, ''), ':',
                                  COALESCE(valpagpar::text, '')),
                           ' | ' ORDER BY numfactur::text
                       ), '')
                FROM public.cuentascobrar
                WHERE LPAD(TRIM(COALESCE(ruccedcli::text, '')), 13, '0') = LPAD(%s, 13, '0')
                """,
                [cliente.ruccedcli],
            )
            diag_db, diag_cantidad, diag_suma, diag_filas = cursor.fetchone()
            resumen["diagnostico"] = {
                "base": diag_db,
                "cantidad": int(diag_cantidad or 0),
                "suma": Decimal(str(diag_suma or 0)),
                "filas": diag_filas or "",
            }

            # Las retenciones son complementarias; si una base antigua no tiene la tabla,
            # eso no debe impedir mostrar la cartera de cuentascobrar.
            try:
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(COALESCE(rc.totretenc, 0)), 0)
                    FROM public.retencclient rc
                    WHERE LPAD(TRIM(COALESCE(rc.ruccedcli::text, '')), 13, '0') = LPAD(%s, 13, '0')
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
            factura["tiene_retencion"] = factura["retenciones"] > 0 or bool(
                retenciones_por_factura.get((numero, ruc_deudor), None)
            )
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

                # El resumen debe considerar todos los registros de prefactura, no solo
                # los 500 que se muestran en la tabla.
                cursor.execute(
                    """
                    SELECT COUNT(*),
                           COALESCE(SUM(COALESCE(canfactur, 0) * COALESCE(preitefac, 0)), 0)
                    FROM public.prefactura
                    WHERE ruc = %s
                    """,
                    [cliente.ruccedcli],
                )
                cantidad_servicios, total_servicios = cursor.fetchone()
                resumen_servicios["cantidad"] = int(cantidad_servicios or 0)
                resumen_servicios["total"] = Decimal(str(total_servicios or 0))
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

    if request.GET.get("vista") == "servicios" and not db_error:
        try:
            with _conexion_cliente(cliente.ruccedcli).cursor() as cursor:
                cursor.execute("""
                    SELECT coditem, desitem, COALESCE(cositem, 0) AS precio
                    FROM public.items
                    WHERE iteactivo IS TRUE
                    ORDER BY coditem, desitem
                """)
                items_catalogo = [
                    {"codigo": row[0], "descripcion": row[1], "precio": Decimal(str(row[2] or 0))}
                    for row in cursor.fetchall()
                ]
        except Exception:
            logger.exception("No se pudo cargar el catálogo para prefactura: ruc=%s", cliente.ruccedcli)
            try:
                _conexion_cliente(cliente.ruccedcli).rollback()
            except Exception:
                pass

    contexto = {
            "cliente": cliente,
            "facturas": facturas,
            "servicios_pendientes": servicios_pendientes,
            "resumen_servicios": resumen_servicios,
            "items_catalogo": items_catalogo,
            "servicios_accion_url": f"/totalcounts/clientes/{cliente.ruccedcli}/cobranza/servicios/accion/",
            "hoy": hoy,
            "resumen": resumen,
            "db_error": db_error,
            "filtros": {
                "fecha_desde": fecha_desde.isoformat() if fecha_desde else "",
                "fecha_hasta": fecha_hasta.isoformat() if fecha_hasta else "",
                "q": busqueda,
            },
            "limite_resultados": len(facturas) >= 500,
            "limite_servicios": len(servicios_pendientes) >= 500,
        }
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        if request.GET.get("vista") == "servicios":
            return render(request, "admin/servicios_pendientes_popup.html", contexto)
        return render(request, "admin/facturas_pendientes_popup.html", contexto)
    return render(request, "admin/cobranza_cliente.html", contexto)



@admin_required
def admin_prefactura_servicio_accion(request, ruc):
    """Agrega, edita o elimina líneas de prefactura sin afectar facturas ni contabilidad."""
    from django.db import transaction
    from django.http import JsonResponse

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido."}, status=405)

    cliente = get_object_or_404(Cliente, pk=ruc)
    conexion = _conexion_cliente(cliente.ruccedcli)

    try:
        accion = request.POST.get("accion", "").strip().lower()
        numero_linea = request.POST.get("numdetfac", "").strip()

        with transaction.atomic(using=conexion.alias):
            with conexion.cursor() as cursor:
                if accion == "eliminar":
                    if not numero_linea:
                        raise ValueError("No se identificó el servicio seleccionado.")
                    cursor.execute(
                        """
                        DELETE FROM public.prefactura
                        WHERE numdetfac::text = %s AND ruc = %s
                        """,
                        [numero_linea, cliente.ruccedcli],
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("El servicio ya no existe o no pertenece a este cliente.")
                    return JsonResponse({"ok": True, "mensaje": "Servicio eliminado correctamente."})

                if accion not in {"agregar", "editar"}:
                    raise ValueError("La acción solicitada no es válida.")

                linea_actual = None
                if accion == "editar":
                    if not numero_linea:
                        raise ValueError("No se identificó el servicio que deseas editar.")
                    cursor.execute(
                        """
                        SELECT coditeinv, desiteinv
                        FROM public.prefactura
                        WHERE numdetfac::text = %s AND ruc = %s
                        FOR UPDATE
                        """,
                        [numero_linea, cliente.ruccedcli],
                    )
                    linea_actual = cursor.fetchone()
                    if not linea_actual:
                        raise ValueError("El servicio ya no existe o no pertenece a este cliente.")

                codigo = request.POST.get("coditeinv", "").strip()
                if not codigo:
                    raise ValueError("Selecciona un servicio del catálogo.")

                try:
                    cantidad = Decimal(request.POST.get("canfactur", "").strip().replace(",", "."))
                    precio = Decimal(request.POST.get("preitefac", "").strip().replace(",", "."))
                except (InvalidOperation, ValueError, TypeError):
                    raise ValueError("Ingresa una cantidad y un precio válidos.")

                if not cantidad.is_finite() or cantidad <= 0:
                    raise ValueError("La cantidad debe ser mayor que cero.")
                if not precio.is_finite() or precio < 0:
                    raise ValueError("El precio no puede ser negativo.")

                try:
                    fecha_servicio = date.fromisoformat(
                        request.POST.get("fecha", "").strip() or timezone.localdate().isoformat()
                    )
                except (TypeError, ValueError):
                    raise ValueError("La fecha del servicio no es válida.")

                cursor.execute(
                    """
                    SELECT coditem, desitem, COALESCE(cositem, 0)
                    FROM public.items
                    WHERE coditem = %s AND iteactivo IS TRUE
                    LIMIT 1
                    """,
                    [codigo],
                )
                item = cursor.fetchone()
                if not item and linea_actual and codigo == str(linea_actual[0] or ""):
                    # Permite mantener/ajustar un servicio ya registrado aunque
                    # posteriormente se haya desactivado o retirado del catálogo.
                    item = (codigo, linea_actual[1], precio)
                if not item:
                    raise ValueError("El servicio seleccionado no existe o está inactivo.")

                descripcion = str(item[1] or "").strip()
                if not descripcion:
                    raise ValueError("El servicio seleccionado no tiene descripción.")

                cursor.execute(
                    """
                    SELECT column_name, is_nullable, column_default, is_identity
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'prefactura'
                    ORDER BY ordinal_position
                    """
                )
                columnas = cursor.fetchall()
                disponibles = {row[0] for row in columnas}
                requeridas = {"numdetfac", "ruc", "coditeinv", "desiteinv", "canfactur", "preitefac", "fecha"}
                faltantes = requeridas - disponibles
                if faltantes:
                    raise RuntimeError(
                        "La tabla prefactura no contiene los campos necesarios: "
                        + ", ".join(sorted(faltantes))
                    )

                total_linea = (cantidad * precio).quantize(Decimal("0.01"))
                valores = {
                    "ruc": cliente.ruccedcli,
                    "coditeinv": str(item[0]),
                    "desiteinv": descripcion,
                    "canfactur": float(cantidad),
                    "preitefac": float(precio),
                    "fecha": fecha_servicio,
                }
                # El año corresponde al año de la fecha del servicio, no al año actual.
                if "año" in disponibles:
                    valores["año"] = str(fecha_servicio.year)
                if "dscitefac" in disponibles:
                    valores["dscitefac"] = 0
                if "totitefac" in disponibles:
                    valores["totitefac"] = float(total_linea)

                # No intentamos insertar columnas nuevas que la tabla declare obligatorias
                # pero que esta operación no conozca. Así evitamos crear filas incompletas.
                if accion == "agregar":
                    for nombre, nullable, default, identity in columnas:
                        if (
                            nullable == "NO"
                            and default is None
                            and identity != "YES"
                            and nombre not in valores
                            and nombre != "numdetfac"
                        ):
                            raise RuntimeError(
                                f"El campo obligatorio {nombre} de prefactura no tiene un valor definido."
                            )

                if accion == "editar":
                    campos = list(valores)
                    cursor.execute(
                        "UPDATE public.prefactura SET "
                        + ", ".join(f"{campo} = %s" for campo in campos)
                        + " WHERE numdetfac::text = %s AND ruc = %s",
                        [valores[campo] for campo in campos] + [numero_linea, cliente.ruccedcli],
                    )
                    if cursor.rowcount != 1:
                        raise ValueError("No se pudo actualizar la línea seleccionada.")
                    mensaje = "Servicio actualizado correctamente."
                else:
                    # Registrar el usuario administrativo que crea la línea.
                    if "creadopor" in disponibles:
                        valores["creadopor"] = str(
                            request.session.get("admin_username") or "ADMIN"
                        ).strip()[:20]
                    cursor.execute("SELECT siguiente_parametro('numdetfac')")
                    numero_nuevo = cursor.fetchone()[0]
                    valores_con_id = {"numdetfac": numero_nuevo, **valores}
                    campos = list(valores_con_id)
                    cursor.execute(
                        "INSERT INTO public.prefactura ("
                        + ", ".join(campos)
                        + ") VALUES ("
                        + ", ".join(["%s"] * len(campos))
                        + ")",
                        [valores_con_id[campo] for campo in campos],
                    )
                    mensaje = "Servicio agregado correctamente."

        return JsonResponse({"ok": True, "mensaje": mensaje})
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception:
        logger.exception(
            "Error modificando prefactura: ruc=%s accion=%s numdetfac=%s",
            cliente.ruccedcli,
            request.POST.get("accion", ""),
            request.POST.get("numdetfac", ""),
        )
        return JsonResponse(
            {"ok": False, "error": "No se pudo guardar el servicio. Verifica la estructura de prefactura."},
            status=500,
        )


@admin_required
def admin_estado_cuenta_cliente(request, ruc):
    """Popup de movimientos de cuenta del cliente, replicando el formulario VB6."""
    cliente = get_object_or_404(Cliente, pk=ruc)
    hoy = timezone.localdate()
    desde_defecto = hoy.replace(day=1)

    desde = _fecha_filtro(request.GET.get("desde", ""), desde_defecto)
    hasta = _fecha_filtro(request.GET.get("hasta", ""), hoy)
    if desde > hoy:
        desde = hoy
    if hasta > hoy:
        hasta = hoy
    if desde > hasta:
        desde, hasta = hasta, desde

    movimientos = []
    saldo_vencido = Decimal("0.00")
    estado_error = ""
    try:
        conexion = _conexion_cliente(cliente.ruccedcli)
        conexion.ensure_connection()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT fecmovcta,
                       tipmovcta,
                       COALESCE(valmovcta, 0) AS valmovcta,
                       refmovcta,
                       COALESCE(debe, 0) AS debe,
                       COALESCE(haber, 0) AS haber,
                       COALESCE(salcuenta, 0) AS saldocuenta
                FROM public.cuentacliente
                WHERE LPAD(TRIM(COALESCE(ruccedcli::text, '')), 13, '0') = LPAD(%s, 13, '0')
                  AND fecmovcta::date >= %s::date
                  AND fecmovcta::date <= %s::date
                ORDER BY nummovcta, fecmovcta
                """,
                [cliente.ruccedcli, desde.isoformat(), hasta.isoformat()],
            )
            columnas = [col[0] for col in cursor.description]
            movimientos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

            cursor.execute(
                """
                SELECT COALESCE(SUM(COALESCE(valpagpar, 0)), 0)
                FROM public.cuentascobrar
                WHERE LPAD(TRIM(COALESCE(ruccedcli::text, '')), 13, '0') = LPAD(%s, 13, '0')
                  AND fecvencim::date <= %s::date
                  AND COALESCE(valpagpar, 0) > 0
                  AND UPPER(TRIM(COALESCE(estpagcue, ''))) = 'PENDIENTE'
                """,
                [cliente.ruccedcli, hoy.isoformat()],
            )
            saldo_vencido = Decimal(str(cursor.fetchone()[0] or 0))
    except Exception:
        estado_error = (
            "No se pudo consultar el estado de cuenta. Verifica que la base BdTotal "
            "contenga las tablas CuentaCliente y CuentasCobrar con sus campos correspondientes."
        )

    return render(
        request,
        "admin/estado_cuenta_cliente_popup.html",
        {
            "cliente": cliente,
            "movimientos": movimientos,
            "saldo_pagar": Decimal(str(getattr(cliente, "salcuenta", 0) or 0)),
            "saldo_vencido": saldo_vencido,
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "hoy": hoy.isoformat(),
            "estado_error": estado_error,
        },
    )


@admin_required
def admin_factura_detalle_cobranza(request, ruc, numfactur):
    """Consulta la cabecera y las líneas reales de una factura para el popup de cobranza."""
    cliente = get_object_or_404(Cliente, pk=ruc)
    factura = None
    detalles = []
    error = ""
    try:
        conexion = _conexion_cliente(cliente.ruccedcli)
        conexion.ensure_connection()
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT f.numfactur, f.numserfac, f.ruccedcli, f.fecfactur,
                       f.fecvencim, f.subtotfac, f.pordescue, f.valdescue,
                       f.porivafac, f.valivafac, f.totfactur, f.totbieiva,
                       f.totbiesiniva, f.totseriva, f.totsersiniva,
                       f.totconiva, f.totsiniva, f.valpagini, f.valsalfac,
                       f.forpagfac, f.estpagfac, f.observ, c.nomclient
                FROM public.facturas f
                LEFT JOIN public.clientes c ON c.ruccedcli = f.ruccedcli
                WHERE f.numfactur = %s
                  AND LPAD(TRIM(COALESCE(f.ruccedcli::text, '')), 13, '0') = LPAD(%s, 13, '0')
                LIMIT 1
                """,
                [numfactur, cliente.ruccedcli],
            )
            columnas = [col[0] for col in cursor.description]
            fila = cursor.fetchone()
            if fila:
                factura = dict(zip(columnas, fila))
                cursor.execute(
                    """
                    SELECT numdetfac, coditeinv, desiteinv,
                           COALESCE(canfactur, 0) AS cantidad,
                           COALESCE(preitefac, 0) AS precio,
                           COALESCE(dscitefac, 0) AS descuento,
                           COALESCE(totitefac, 0) AS total,
                           COALESCE(candevolu, 0) AS cantidad_devuelta
                    FROM public.detallefacturas
                    WHERE numfactur = %s
                    ORDER BY numdetfac
                    """,
                    [numfactur],
                )
                cols_detalle = [col[0] for col in cursor.description]
                detalles = [dict(zip(cols_detalle, row)) for row in cursor.fetchall()]
            else:
                error = "No se encontró la factura solicitada para este cliente."
    except Exception:
        error = "No se pudo consultar el detalle de la factura. Verifica la conexión y las tablas de facturas y detallefacturas."

    saldo = Decimal(str((factura or {}).get("valsalfac") or 0))
    if factura:
        try:
            with _conexion_cliente(cliente.ruccedcli).cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(COALESCE(valpagpar, 0)), 0)
                    FROM public.cuentascobrar
                    WHERE numfactur = %s
                      AND LPAD(TRIM(COALESCE(ruccedcli::text, '')), 13, '0') = LPAD(%s, 13, '0')
                      AND UPPER(TRIM(COALESCE(estpagcue, ''))) = 'PENDIENTE'
                    """,
                    [numfactur, cliente.ruccedcli],
                )
                saldo = Decimal(str(cursor.fetchone()[0] or 0))
        except Exception:
            pass

    return render(
        request,
        "admin/factura_detalle_cobranza_popup.html",
        {"cliente": cliente, "factura": factura, "detalles": detalles, "saldo_pendiente": saldo, "error": error},
    )


@admin_required
def admin_factura_retencion_cobranza(request, ruc, numfactur):
    """Formulario y registro de retención recibida, basado en el formulario VB6."""
    from datetime import datetime, timedelta
    from django.db import transaction
    from django.http import JsonResponse
    from django.views.decorators.http import require_http_methods

    cliente = get_object_or_404(Cliente, pk=ruc)
    conexion = _conexion_cliente(cliente.ruccedcli)
    error = ""
    exito = False
    factura = None
    datos = {}
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT f.numfactur, f.numserfac, f.ruccedcli, f.fecfactur, f.subtotfac,
                       f.valdescue, f.valivafac, f.valsalfac, f.totbieiva, f.totbiesiniva,
                       f.totseriva, f.totsersiniva, f.porivafac, f.estpagfac,
                       c.nomclient, c.porretfuebie, c.porretfueser, c.porretivabie, c.porretivaser
                FROM public.facturas f
                LEFT JOIN public.clientes c ON c.ruccedcli = f.ruccedcli
                WHERE f.numfactur = %s
                  AND LPAD(TRIM(COALESCE(f.ruccedcli::text,'')),13,'0') = LPAD(%s,13,'0')
                LIMIT 1
            """, [numfactur, cliente.ruccedcli])
            row = cursor.fetchone()
            if row:
                cols = [d[0] for d in cursor.description]
                factura = dict(zip(cols, row))
                cursor.execute("""
                    SELECT COALESCE(SUM(COALESCE(valpagpar,0)),0)
                    FROM public.cuentascobrar
                    WHERE numfactur=%s AND LPAD(TRIM(COALESCE(ruccedcli::text,'')),13,'0')=LPAD(%s,13,'0')
                      AND UPPER(TRIM(COALESCE(estpagcue,''))) <> 'PAGADA'
                """, [numfactur, cliente.ruccedcli])
                saldo_cuentas = Decimal(str(cursor.fetchone()[0] or 0))
                factura["saldo_cuentas"] = saldo_cuentas if saldo_cuentas > 0 else Decimal(str(factura.get("valsalfac") or 0))
                cursor.execute(
                    "SELECT COUNT(*) FROM public.retencclient WHERE numfactur=%s AND LPAD(TRIM(COALESCE(ruccedcli::text,'')),13,'0')=LPAD(%s,13,'0')",
                    [numfactur, cliente.ruccedcli],
                )
                factura["tiene_retencion"] = cursor.fetchone()[0] > 0
            else:
                error = "No se encontró la factura para este cliente."
    except Exception:
        error = "No se pudo consultar la factura y los porcentajes de retención del cliente."

    if factura and factura.get("tiene_retencion"):
        error = "Esta factura ya tiene una retención registrada. No se permite ingresar otra."
        factura = None

    if not factura and not error:
        error = "No se encontró la factura para este cliente."

    if factura:
        factura["base_fue_bie"] = Decimal(str(factura.get("totbieiva") or 0)) + Decimal(str(factura.get("totbiesiniva") or 0))
        factura["base_fue_ser"] = Decimal(str(factura.get("totseriva") or 0)) + Decimal(str(factura.get("totsersiniva") or 0))
        tasa_iva = Decimal(str(factura.get("porivafac") or 0)) / Decimal("100")
        factura["base_iva_bie"] = Decimal(str(factura.get("totbieiva") or 0)) * tasa_iva
        factura["base_iva_ser"] = Decimal(str(factura.get("totseriva") or 0)) * tasa_iva

    if request.method == "POST" and factura and not error:
        try:
            def money(key):
                raw = request.POST.get(key, "0").strip().replace(",", ".")
                value = Decimal(raw or "0")
                if not value.is_finite():
                    raise ValueError()
                return value.quantize(Decimal("0.01"))
            numero = request.POST.get("numdocume", "").strip()
            fecha_ret = date.fromisoformat(request.POST.get("fecretenc", ""))
            fecha_rec = date.fromisoformat(request.POST.get("fecrecepc", ""))
            if len(numero) != 17 or numero[3] != "-" or numero[7] != "-":
                raise ValueError("El número de retención debe tener el formato 001-001-000000001.")
            if fecha_ret > timezone.localdate() or fecha_ret < factura["fecfactur"].date():
                raise ValueError("La fecha de retención debe estar entre la fecha de la factura y hoy.")
            if fecha_rec < fecha_ret or (fecha_rec - fecha_ret).days > 5:
                raise ValueError("La fecha de recepción debe ser igual o posterior a la emisión y no exceder cinco días.")
            bases = {k: money(k) for k in ("basimpfuebie","basimpfueser","basimpivabie","basimpivaser")}
            porcentajes = {k: money(k) for k in ("porretfuebie","porretfueser","porretivabie","porretivaser")}
            if any(v < 0 or v > 100 for v in porcentajes.values()) or any(v < 0 for v in bases.values()):
                raise ValueError("Las bases deben ser positivas y los porcentajes deben estar entre 0 y 100.")
            valores = {
                "valretfuebie": (bases["basimpfuebie"] * porcentajes["porretfuebie"] / 100).quantize(Decimal("0.01")),
                "valretfueser": (bases["basimpfueser"] * porcentajes["porretfueser"] / 100).quantize(Decimal("0.01")),
                "valretivabie": (bases["basimpivabie"] * porcentajes["porretivabie"] / 100).quantize(Decimal("0.01")),
                "valretivaser": (bases["basimpivaser"] * porcentajes["porretivaser"] / 100).quantize(Decimal("0.01")),
            }
            total = sum(valores.values(), Decimal("0.00")).quantize(Decimal("0.01"))
            saldo_actual = Decimal(str(factura.get("valsalfac") or 0))
            if total <= 0:
                raise ValueError("El total de la retención debe ser mayor que cero.")
            if total > saldo_actual:
                raise ValueError("La retención no puede superar el saldo pendiente de la factura.")
            if abs((bases["basimpfuebie"] + bases["basimpfueser"]) - (Decimal(str(factura["subtotfac"] or 0)) - Decimal(str(factura["valdescue"] or 0)))) > Decimal("0.02"):
                raise ValueError("Las bases de retención de renta no coinciden con el subtotal de la factura.")
            if abs((bases["basimpivabie"] + bases["basimpivaser"]) - Decimal(str(factura["valivafac"] or 0))) > Decimal("0.02"):
                raise ValueError("Las bases de retención de IVA no coinciden con el IVA de la factura.")

            with transaction.atomic(using=conexion.alias):
                with conexion.cursor() as cursor:
                    cursor.execute("SELECT valsalfac FROM public.facturas WHERE numfactur=%s AND ruccedcli=%s FOR UPDATE", [numfactur, cliente.ruccedcli])
                    locked = cursor.fetchone()
                    if not locked:
                        raise ValueError("La factura ya no está disponible.")
                    saldo_actual = Decimal(str(locked[0] or 0))
                    cursor.execute(
                        "SELECT 1 FROM public.retencclient WHERE numfactur=%s AND LPAD(TRIM(COALESCE(ruccedcli::text,'')),13,'0')=LPAD(%s,13,'0') LIMIT 1",
                        [numfactur, cliente.ruccedcli],
                    )
                    if cursor.fetchone():
                        raise ValueError("Esta factura ya tiene una retención registrada. No se permite ingresar otra.")
                    if total > saldo_actual:
                        raise ValueError("El total de la retención supera el saldo actual de la factura.")
                    cursor.execute("SELECT 1 FROM public.retencclient WHERE numdocume=%s AND ruccedcli=%s AND numfactur=%s", [numero, cliente.ruccedcli, numfactur])
                    if cursor.fetchone():
                        raise ValueError("Este número de retención ya está registrado para esta factura.")
                    cursor.execute("""
                        INSERT INTO public.retencclient
                        (numdocume,ruccedcli,fecretenc,fecrecepc,numfactur,
                         basimpfuebie,porretfuebie,valretfuebie,basimpfueser,porretfueser,valretfueser,
                         basimpivabie,porretivabie,valretivabie,basimpivaser,porretivaser,valretivaser,totretenc)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, [numero,cliente.ruccedcli,fecha_ret,fecha_rec,numfactur,
                        bases["basimpfuebie"],porcentajes["porretfuebie"],valores["valretfuebie"],
                        bases["basimpfueser"],porcentajes["porretfueser"],valores["valretfueser"],
                        bases["basimpivabie"],porcentajes["porretivabie"],valores["valretivabie"],
                        bases["basimpivaser"],porcentajes["porretivaser"],valores["valretivaser"],total])
                    nuevo_saldo = max(Decimal("0.00"), saldo_actual - total)
                    cursor.execute("UPDATE public.facturas SET valsalfac=%s, estpagfac=%s, retemitid=TRUE WHERE numfactur=%s AND ruccedcli=%s",
                                   [nuevo_saldo, "PAGADA" if nuevo_saldo < Decimal("0.01") else factura.get("estpagfac") or "PENDIENTE", numfactur, cliente.ruccedcli])
                    restante = total
                    cursor.execute("""
                        SELECT numcuecob,valpagpar,estpagcue FROM public.cuentascobrar
                        WHERE numfactur=%s AND ruccedcli=%s AND UPPER(COALESCE(estpagcue,'')) <> 'PAGADA'
                        ORDER BY numcuecob DESC FOR UPDATE
                    """, [numfactur,cliente.ruccedcli])
                    cuentas = cursor.fetchall()
                    for numcue, valpagpar, estado in cuentas:
                        if restante <= 0: break
                        deuda = Decimal(str(valpagpar or 0))
                        aplicado = min(deuda, restante)
                        saldo_cuenta = max(Decimal("0.00"), deuda-aplicado)
                        cursor.execute("UPDATE public.cuentascobrar SET valpagpar=%s, estpagcue=%s WHERE numcuecob=%s",
                                       [saldo_cuenta, "PAGADA" if saldo_cuenta < Decimal("0.01") else estado, numcue])
                        restante -= aplicado
                    cursor.execute("UPDATE public.clientes SET salcuenta=GREATEST(COALESCE(salcuenta,0)-%s,0) WHERE ruccedcli=%s", [total,cliente.ruccedcli])
                    cursor.execute("SELECT COALESCE(MAX(nummovcta),0)+1 FROM public.cuentacliente")
                    num_mov = cursor.fetchone()[0]
                    cursor.execute("SELECT COALESCE(salcuenta,0) FROM public.clientes WHERE ruccedcli=%s", [cliente.ruccedcli])
                    saldo_cliente = cursor.fetchone()[0]
                    cursor.execute("""
                        INSERT INTO public.cuentacliente
                        (nummovcta,ruccedcli,fecmovcta,tipmovcta,valmovcta,refmovcta,fecvencim,numfactur,debe,haber,saldo,salcuenta,tipdocume)
                        VALUES (%s,%s,%s,'CREDITO',%s,%s,%s,%s,0,%s,%s,%s,'RET')
                    """, [num_mov,cliente.ruccedcli,fecha_ret,total,"RETENCIÓN #"+numero,fecha_ret,numfactur,nuevo_saldo,total,nuevo_saldo,saldo_cliente])
            exito = True
        except ValueError as exc:
            error = str(exc)
        except Exception:
            error = "No se pudo guardar la retención. No se confirmaron los cambios; verifica la configuración de la base de datos."

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        if request.method == "POST":
            return JsonResponse({"ok": exito, "error": error, "message": "Retención registrada correctamente." if exito else error})
        return render(request, "admin/retencion_cobranza_popup.html", {"cliente": cliente, "factura": factura, "error": error, "hoy": timezone.localdate().isoformat()})
    return render(request, "admin/retencion_cobranza_popup.html", {"cliente": cliente, "factura": factura, "error": error, "hoy": timezone.localdate().isoformat()})


@admin_required
def admin_factura_pago_cobranza(request, ruc, numfactur):
    """Formulario y registro de abonos de facturas, siguiendo las formas de pago del VB6."""
    from django.db import transaction
    from django.http import JsonResponse
    from django.views.decorators.http import require_http_methods

    try:
        cliente = get_object_or_404(Cliente, pk=ruc)
        conexion = _conexion_cliente(cliente.ruccedcli)
        conexion.ensure_connection()
    except Exception:
        logger.exception(
            "Error inicializando formulario de pago: ruc=%s factura=%s",
            ruc,
            numfactur,
        )
        from django.http import HttpResponse
        return HttpResponse(
            "No se pudo iniciar el formulario de pago. Revisa el registro de errores del servidor.",
            status=500,
        )

    error = ""
    factura = None
    vencimientos = []
    bancos = []
    anticipos = []
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT f.numfactur, f.ruccedcli, f.fecfactur, f.fecvencim,
                       f.totfactur, f.valsalfac, f.estpagfac, c.nomclient,
                       COALESCE(c.salcuenta,0) AS salcuenta, COALESCE(c.salantici,0) AS salantici,
                       COALESCE(c.salnotcre,0), COALESCE(c.codcuecon,''),
                       COALESCE(c.codcueant,'')
                FROM public.facturas f
                LEFT JOIN public.clientes c ON c.ruccedcli=f.ruccedcli
                WHERE f.numfactur=%s
                  AND LPAD(TRIM(COALESCE(f.ruccedcli::text,'')),13,'0')=LPAD(%s,13,'0')
                LIMIT 1
            """, [numfactur, cliente.ruccedcli])
            row=cursor.fetchone()
            if row:
                cols=[d[0] for d in cursor.description]
                factura=dict(zip(cols,row))
                cursor.execute("""
                    SELECT numcuecob, fecvencim, COALESCE(valpagpar,0), COALESCE(refcuecob,'')
                    FROM public.cuentascobrar
                    WHERE numfactur=%s AND ruccedcli=%s
                      AND UPPER(TRIM(COALESCE(estpagcue,'')))='PENDIENTE'
                      AND COALESCE(valpagpar,0)>0
                    ORDER BY fecvencim, numcuecob
                """,[numfactur,cliente.ruccedcli])
                vencimientos=[{"numcuecob":r[0],"fecvencim":r[1],"saldo":Decimal(str(r[2] or 0)),"referencia":r[3]} for r in cursor.fetchall()]
                cursor.execute("SELECT codcuenta,bancocta,COALESCE(saldocta,0),COALESCE(codcuecon,'') FROM public.cuentasbancos ORDER BY bancocta,codcuenta")
                bancos=[{"codigo":r[0],"banco":r[1],"saldo":Decimal(str(r[2] or 0)),"cuenta_contable":r[3]} for r in cursor.fetchall()]
                cursor.execute("""
                    SELECT numantcli, fecantcli, COALESCE(valantcli,0), COALESCE(saldo,0), COALESCE(refantcli,'')
                    FROM public.anticiclient
                    WHERE ruccedcli=%s AND UPPER(TRIM(COALESCE(estantcli,'')))='PENDIENTE'
                      AND COALESCE(saldo,valantcli,0)>0
                    ORDER BY fecantcli,numantcli
                """,[cliente.ruccedcli])
                anticipos=[{"numero":r[0],"fecha":r[1],"valor":Decimal(str(r[2] or 0)),"saldo":Decimal(str(r[3] or r[2] or 0)),"referencia":r[4]} for r in cursor.fetchall()]
            else:
                error="No se encontró la factura para este cliente."
    except Exception:
        logger.exception(
            "Error cargando formulario de pago: ruc=%s factura=%s",
            cliente.ruccedcli,
            numfactur,
        )
        error="No se pudo consultar la factura, sus vencimientos y las formas de pago disponibles."

    if factura and not vencimientos:
        error="La factura no tiene vencimientos pendientes para aplicar pagos."
        factura=None

    if request.method=="POST" and factura:
        try:
            metodo=request.POST.get("forma_pago","").strip().upper()
            permitidos={"EFECTIVO","CAJA","CHEQUE A LA VISTA","TRANSFERENCIA BANCARIA","ANTICIPO","NOTA DE CREDITO","DESCUENTO"}
            if metodo not in permitidos:
                raise ValueError("Selecciona una forma de pago válida.")
            fecha_pago=date.fromisoformat(request.POST.get("fecha_pago",""))
            if fecha_pago>timezone.localdate():
                raise ValueError("La fecha del pago no puede ser posterior a hoy.")
            try:
                importe=Decimal(request.POST.get("valor_abono","0").strip().replace(",",".")).quantize(Decimal("0.01"))
            except Exception:
                raise ValueError("Ingresa un valor de pago válido.")
            if not importe.is_finite() or importe<=0:
                raise ValueError("El valor a pagar debe ser mayor que cero.")
            numcuecob=request.POST.get("numcuecob","").strip()
            referencia=request.POST.get("referencia","").strip()[:100]
            if not referencia:
                raise ValueError("Ingresa la referencia del movimiento.")
            codigo_banco=request.POST.get("cuenta_banco","").strip()
            num_documento=request.POST.get("numero_documento","").strip()
            num_anticipo=request.POST.get("numero_anticipo","").strip()
            vendedor=request.POST.get("cobrador","").strip()[:50]
            if metodo in {"TRANSFERENCIA BANCARIA","CHEQUE A LA VISTA","CAJA"} and not codigo_banco:
                raise ValueError("Selecciona la cuenta bancaria o caja correspondiente.")
            if metodo in {"TRANSFERENCIA BANCARIA","CHEQUE A LA VISTA"} and not num_documento:
                raise ValueError("Ingresa el número de transferencia o cheque.")
            if metodo=="ANTICIPO" and not num_anticipo:
                raise ValueError("Selecciona el anticipo que deseas aplicar.")
            if metodo=="ANTICIPO":
                with conexion.cursor() as cursor:
                    cursor.execute("SELECT COALESCE(saldo,valantcli,0) FROM public.anticiclient WHERE numantcli=%s AND ruccedcli=%s AND estantcli='PENDIENTE'",[num_anticipo,cliente.ruccedcli])
                    anticipo_row=cursor.fetchone()
                if not anticipo_row:
                    raise ValueError("El anticipo seleccionado ya no está disponible.")
                saldo_anticipo=Decimal(str(anticipo_row[0] or 0))
                if importe != saldo_anticipo:
                    raise ValueError("El importe debe coincidir con el saldo total del anticipo seleccionado, como en el formulario VB6.")
            with transaction.atomic(using=conexion.alias):
                with conexion.cursor() as cursor:
                    cursor.execute("""
                        SELECT numcuecob, valpagpar FROM public.cuentascobrar
                        WHERE numcuecob=%s AND numfactur=%s AND ruccedcli=%s
                          AND UPPER(TRIM(COALESCE(estpagcue,'')))='PENDIENTE'
                        FOR UPDATE
                    """,[numcuecob,numfactur,cliente.ruccedcli])
                    venc=cursor.fetchone()
                    if not venc:
                        raise ValueError("El vencimiento seleccionado ya no está pendiente.")
                    saldo_venc=Decimal(str(venc[1] or 0))
                    if importe>saldo_venc:
                        raise ValueError("El abono no puede superar el saldo del vencimiento seleccionado.")
                    cursor.execute("SELECT valsalfac FROM public.facturas WHERE numfactur=%s AND ruccedcli=%s FOR UPDATE",[numfactur,cliente.ruccedcli])
                    facrow=cursor.fetchone()
                    if not facrow:
                        raise ValueError("La factura ya no está disponible.")
                    saldo_factura=Decimal(str(facrow[0] or 0))
                    if importe>saldo_factura:
                        raise ValueError("El abono supera el saldo actual de la factura.")
                    nuevo_venc=max(Decimal("0.00"),saldo_venc-importe)
                    nuevo_factura=max(Decimal("0.00"),saldo_factura-importe)
                    cursor.execute("UPDATE public.cuentascobrar SET valpagpar=%s,estpagcue=%s WHERE numcuecob=%s",
                                   [nuevo_venc,"PAGADA" if nuevo_venc<Decimal("0.01") else "PENDIENTE",numcuecob])
                    cursor.execute("UPDATE public.facturas SET valsalfac=%s,estpagfac=%s WHERE numfactur=%s AND ruccedcli=%s",
                                   [nuevo_factura,"PAGADA" if nuevo_factura<Decimal("0.01") else "PENDIENTE",numfactur,cliente.ruccedcli])
                    cursor.execute("UPDATE public.clientes SET salcuenta=GREATEST(COALESCE(salcuenta,0)-%s,0),fecultpag=%s WHERE ruccedcli=%s",
                                   [importe,fecha_pago,cliente.ruccedcli])
                    cursor.execute("SELECT siguiente_parametro('numctacli')")
                    nummovcta=cursor.fetchone()[0]
                    cursor.execute("""
                        INSERT INTO public.cuentacliente
                        (nummovcta,ruccedcli,fecmovcta,tipmovcta,valmovcta,refmovcta,fecvencim,numfactur,debe,haber,saldo,salcuenta,tipdocume)
                        VALUES (%s,%s,%s,'PAGO',%s,%s,%s,%s,0,%s,%s,
                                (SELECT salcuenta FROM public.clientes WHERE ruccedcli=%s),'FAC')
                    """,[nummovcta,cliente.ruccedcli,fecha_pago,importe,referencia,fecha_pago,numfactur,importe,nuevo_factura,cliente.ruccedcli])

                    if metodo in {"EFECTIVO","CAJA"}:
                        cursor.execute("SELECT siguiente_parametro('nummovcaj')")
                        nummov=cursor.fetchone()[0]
                        cursor.execute("SELECT siguiente_parametro('numcomingcaj')")
                        numcom=cursor.fetchone()[0]
                        cursor.execute("SELECT salcaja FROM public.cajas WHERE codcaja='10' FOR UPDATE")
                        caja=cursor.fetchone()
                        if not caja:
                            raise ValueError("No existe la caja general con código 10.")
                        nuevo_caja=Decimal(str(caja[0] or 0))+importe
                        cursor.execute("UPDATE public.cajas SET salcaja=%s WHERE codcaja='10'",[nuevo_caja])
                        cursor.execute("UPDATE public.parametros SET salcajgen=COALESCE(salcajgen,0)+%s",[importe])
                        cursor.execute("""
                            INSERT INTO public.flujocaja
                            (nummovcaj,fecmovcaj,tipmovcaj,numdocume,valmovcaj,refmovcaj,userid,codcajgen,debe,haber,saldo)
                            VALUES (%s,%s,'I',%s,%s,%s,'WEB','10',%s,0,%s)
                        """,[nummov,fecha_pago,numfactur,importe,referencia,importe,nuevo_caja])
                        cursor.execute("""
                            INSERT INTO public.comingcaja
                            (numcoming,nummovcaj,fecha,beneficia,valor,concepto,bancocaja,cuenta,cheque,referencia,recibido)
                            SELECT %s,%s,%s,%s,%s,%s,'10',codcuecon,'N/A',%s,nomclient
                            FROM public.clientes LEFT JOIN public.cajas ON codcaja='10' WHERE ruccedcli=%s
                        """,[numcom,nummov,fecha_pago,cliente.ruccedcli,importe,numfactur,referencia,cliente.ruccedcli])
                    elif metodo in {"TRANSFERENCIA BANCARIA","CHEQUE A LA VISTA","CAJA"}:
                        cursor.execute("SELECT codcuenta,bancocta,saldocta,codcuecon FROM public.cuentasbancos WHERE codcuenta=%s FOR UPDATE",[codigo_banco])
                        banco=cursor.fetchone()
                        if not banco:
                            raise ValueError("La cuenta bancaria seleccionada no existe.")
                        cursor.execute("UPDATE public.cuentasbancos SET saldocta=COALESCE(saldocta,0)+%s WHERE codcuenta=%s",[importe,codigo_banco])
                        cursor.execute("SELECT siguiente_parametro('nummovban')")
                        seq=cursor.fetchone()[0]
                        cursor.execute("SELECT siguiente_parametro('numcomingban')")
                        numcom=cursor.fetchone()[0]
                        cursor.execute("""
                            INSERT INTO public.movbancos
                            (codcuenta,seqmovimi,numcompro,fecmovimi,tipmovimi,numdocume,valmovimi,detmovimi,commovimi,validados,nombenefi,userid,impdocume,impcompro,codcuecon)
                            VALUES (%s,%s,%s,%s,'N/C',%s,%s,%s,%s,'FALSO','', 'WEB',FALSE,FALSE,%s)
                        """,[codigo_banco,seq,numcom,fecha_pago,num_documento,importe,referencia,"PAGO DE FACTURA "+numfactur,banco[3]])
                        cursor.execute("""
                            INSERT INTO public.comingbancos
                            (numcoming,fecha,beneficia,valor,concepto,bancocaja,cuenta,cheque,referencia,recibido)
                            SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,nomclient FROM public.clientes WHERE ruccedcli=%s
                        """,[numcom,fecha_pago,cliente.ruccedcli,importe,numfactur,banco[1],codigo_banco,num_documento,referencia,cliente.ruccedcli])
                    elif metodo=="ANTICIPO":
                        cursor.execute("SELECT saldo,valantcli FROM public.anticiclient WHERE numantcli=%s AND ruccedcli=%s FOR UPDATE",[num_anticipo,cliente.ruccedcli])
                        ar=cursor.fetchone()
                        if not ar:
                            raise ValueError("El anticipo ya no está disponible.")
                        restante=max(Decimal("0.00"),Decimal(str(ar[0] or ar[1] or 0))-importe)
                        cursor.execute("UPDATE public.anticiclient SET saldo=%s,salantici=%s,estantcli=%s WHERE numantcli=%s AND ruccedcli=%s",
                                       [restante,restante,"PAGADO" if restante<Decimal("0.01") else "PENDIENTE",num_anticipo,cliente.ruccedcli])
                        cursor.execute("UPDATE public.clientes SET salantici=GREATEST(COALESCE(salantici,0)-%s,0) WHERE ruccedcli=%s",[importe,cliente.ruccedcli])
                    elif metodo=="NOTA DE CREDITO":
                        cursor.execute("UPDATE public.clientes SET salnotcre=GREATEST(COALESCE(salnotcre,0)-%s,0) WHERE ruccedcli=%s AND COALESCE(salnotcre,0)>=%s",[importe,cliente.ruccedcli,importe])
                        if cursor.rowcount==0:
                            raise ValueError("El cliente no tiene saldo suficiente de notas de crédito.")
                    elif metodo=="DESCUENTO":
                        # El VB6 descuenta el saldo de la factura y no registra un movimiento de caja/banco.
                        pass
            return JsonResponse({"ok":True,"mensaje":"Pago registrado correctamente."})
        except ValueError as exc:
            return JsonResponse({"ok":False,"error":str(exc)},status=400)
        except Exception:
            return JsonResponse({"ok":False,"error":"No se pudo registrar el pago. No se aplicaron cambios."},status=500)

    if request.method=="POST" and not factura:
        return JsonResponse({"ok":False,"error":error or "No se pudo cargar la factura."},status=400)
    try:
        return render(request,"admin/pago_cobranza_popup.html",{
            "cliente":cliente,"factura":factura,"vencimientos":vencimientos,"bancos":bancos,
            "anticipos":anticipos,"error":error,"hoy":timezone.localdate()
        })
    except Exception:
        logger.exception(
            "Error renderizando formulario de pago: ruc=%s factura=%s",
            cliente.ruccedcli,
            numfactur,
        )
        from django.http import HttpResponse
        return HttpResponse(
            "No se pudo mostrar el formulario de pago. Revisa el registro de errores del servidor.",
            status=500,
        )
