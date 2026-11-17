from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.db import connections, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date

from .admin_views import admin_required


DB_ALIAS = "bdtotal_facturacion_admin"


def _db():
    if DB_ALIAS not in connections.databases:
        config = settings.DATABASES["default"].copy()
        config["NAME"] = "BdTotal"
        connections.databases[DB_ALIAS] = config
    return connections[DB_ALIAS]


def _rows(sql, params=None):
    with _db().cursor() as cursor:
        cursor.execute(sql, params or [])
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


def _siguiente_parametro(cursor, nombre):
    cursor.execute("SELECT siguiente_parametro(%s)", [nombre])
    row = cursor.fetchone()
    if not row or row[0] is None:
        raise RuntimeError(f"No se pudo obtener el siguiente valor de {nombre}.")
    return int(row[0])


@admin_required
@require_http_methods(["GET"])
def admin_facturacion(request):
    try:
        fecha_desde = request.GET.get("fecha_desde", "").strip()
        fecha_hasta = request.GET.get("fecha_hasta", "").strip()
        desde = parse_date(fecha_desde) if fecha_desde else None
        hasta = parse_date(fecha_hasta) if fecha_hasta else None

        if fecha_desde and desde is None:
            raise ValueError("La fecha inicial no tiene un formato válido.")
        if fecha_hasta and hasta is None:
            raise ValueError("La fecha final no tiene un formato válido.")
        if desde and hasta and desde > hasta:
            raise ValueError("La fecha inicial no puede ser posterior a la fecha final.")

        where = []
        params_sql = []
        if desde:
            where.append("f.fecfactur >= %s")
            params_sql.append(desde)
        if hasta:
            where.append("f.fecfactur < %s")
            params_sql.append(hasta.fromordinal(hasta.toordinal() + 1))

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        facturas = _rows(f"""
            SELECT f.numfactur, f.numserfac, f.fecfactur, f.ruccedcli,
                   c.nomclient, f.totfactur, f.estprofac, f.autorizacion
            FROM public.facturas f
            LEFT JOIN public.clientes c ON c.ruccedcli = f.ruccedcli
            {where_sql}
            ORDER BY f.fecfactur DESC NULLS LAST, f.numfactur DESC
        """, params_sql)
        paginator = Paginator(facturas, 15)
        page_obj = paginator.get_page(request.GET.get("page"))
        datos = _rows("""
            SELECT numserfac, numfactur, numfactem, poriva
            FROM public.parametros ORDER BY id LIMIT 1
        """)
        return render(request, "admin/facturacion.html", {
            "facturas": page_obj.object_list,
            "page_obj": page_obj,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "parametros": datos[0] if datos else {},
        })
    except Exception as exc:
        messages.error(request, f"No se pudo consultar la facturación de BdTotal: {exc}")
        return render(request, "admin/facturacion.html", {
            "facturas": [], "parametros": {}, "load_error": True,
        })


@admin_required
@require_http_methods(["GET"])
def admin_factura_detalle(request, numfactur):
    """Devuelve cabecera y líneas de una factura para el popup del módulo de facturación."""
    try:
        cabeceras = _rows("""
            SELECT f.numfactur, f.numserfac, f.fecfactur, f.ruccedcli,
                   c.nomclient, f.subtotfac, f.valdescue, f.porivafac,
                   f.valivafac, f.totfactur, f.forpagfac, f.estpagfac,
                   f.estprofac, f.autorizacion, f.observ
            FROM public.facturas f
            LEFT JOIN public.clientes c ON c.ruccedcli = f.ruccedcli
            WHERE f.numfactur::text = %s
            LIMIT 1
        """, [str(numfactur)])
        if not cabeceras:
            return JsonResponse({"ok": False, "error": "No se encontró la factura solicitada."}, status=404)

        lineas = _rows("""
            SELECT numdetfac, coditeinv, desiteinv, canfactur,
                   preitefac, dscitefac, totitefac
            FROM public.detallefacturas
            WHERE numfactur::text = %s
            ORDER BY numdetfac
        """, [str(numfactur)])

        def serializar(valor):
            if valor is None:
                return ""
            if hasattr(valor, "isoformat"):
                return valor.isoformat()
            return str(valor)

        return JsonResponse({
            "ok": True,
            "factura": {k: serializar(v) for k, v in cabeceras[0].items()},
            "detalles": [{k: serializar(v) for k, v in linea.items()} for linea in lineas],
        })
    except Exception as exc:
        return JsonResponse({
            "ok": False,
            "error": f"No se pudo consultar el detalle de la factura: {type(exc).__name__}: {exc}",
        }, status=500)


@admin_required
@require_http_methods(["GET", "POST"])
def admin_factura_nueva(request):
    errores = []
    cliente_seleccionado = request.POST.get("ruccedcli", "").strip()
    observ = request.POST.get("observ", "").strip()
    fecha = request.POST.get("fecfactur", date.today().isoformat())
    forma_pago = request.POST.get("forpagfac", "CONTADO").strip().upper()

    try:
        clientes = _rows("""
            SELECT ruccedcli, nomclient FROM public.clientes
            ORDER BY nomclient NULLS LAST
        """)
        items = _rows("""
            SELECT coditem, desitem, pvpunoite, pvpunoiva, aplivaite
            FROM public.items
            WHERE iteactivo IS TRUE
            ORDER BY coditem
        """)
        datos = _rows("SELECT numserfac, poriva FROM public.parametros ORDER BY id LIMIT 1")
        parametros = datos[0] if datos else {}
    except Exception as exc:
        messages.error(request, f"No se pudieron cargar clientes, items o parámetros: {exc}")
        return render(request, "admin/factura_form.html", {
            "clientes": [], "items": [], "errores": [], "load_error": True,
            "cliente_seleccionado": cliente_seleccionado, "fecha": fecha,
            "observ": observ, "forma_pago": forma_pago, "parametros": {},
        })

    if request.method == "POST":
        codigos = request.POST.getlist("coditem[]")
        cantidades = request.POST.getlist("cantidad[]")
        precios = request.POST.getlist("precio[]")
        descuentos = request.POST.getlist("descuento[]")

        try:
            fecha_factura = date.fromisoformat(fecha)
        except (ValueError, TypeError):
            fecha_factura = None
            errores.append("La fecha de la factura no es válida.")

        cliente = next((c for c in clientes if c["ruccedcli"] == cliente_seleccionado), None)
        if cliente is None:
            errores.append("Selecciona un cliente válido.")

        iva_pct = Decimal(str(parametros.get("poriva") or 0))
        items_por_codigo = {str(item["coditem"]): item for item in items}
        lineas = []
        subtotal = Decimal("0.00")
        base_iva = Decimal("0.00")
        base_cero = Decimal("0.00")

        for indice, codigo in enumerate(codigos):
            codigo = codigo.strip()
            if not codigo:
                continue
            try:
                cantidad = Decimal(cantidades[indice]).quantize(Decimal("0.0001"))
                precio = Decimal(precios[indice]).quantize(Decimal("0.0001"))
                descuento = Decimal(descuentos[indice] or "0")
                if cantidad <= 0 or precio < 0 or descuento < 0 or descuento > 100:
                    raise InvalidOperation
            except (InvalidOperation, ValueError, IndexError):
                errores.append(f"La línea {indice + 1} contiene valores inválidos.")
                continue

            item = items_por_codigo.get(codigo)
            if item is None:
                errores.append(f"El item {codigo} no existe o está inactivo.")
                continue

            total_linea = (cantidad * precio * (Decimal("1") - descuento / Decimal("100"))).quantize(Decimal("0.01"))
            aplica_iva = bool(item.get("aplivaite"))
            subtotal += total_linea
            if aplica_iva:
                base_iva += total_linea
            else:
                base_cero += total_linea
            lineas.append({
                "codigo": codigo,
                "descripcion": str(item.get("desitem") or ""),
                "cantidad": cantidad,
                "precio": precio,
                "descuento": descuento,
                "total": total_linea,
            })

        if not lineas:
            errores.append("Agrega al menos un producto o servicio.")
        if forma_pago not in ("CONTADO", "CREDITO", "CHEQUE A LA VISTA", "TARJETA DE CREDITO"):
            errores.append("La forma de pago seleccionada no es válida.")

        iva_total = (base_iva * iva_pct / Decimal("100")).quantize(Decimal("0.01"))
        total_factura = subtotal + iva_total

        if not errores:
            try:
                with transaction.atomic(using=DB_ALIAS):
                    with _db().cursor() as cursor:
                        numero_temporal = str(_siguiente_parametro(cursor, "numfactem"))
                        serie = str(parametros.get("numserfac") or "")
                        estado_pago = "PAGADA" if forma_pago in (
                            "CONTADO", "CHEQUE A LA VISTA", "TARJETA DE CREDITO"
                        ) else "PENDIENTE"
                        saldo = Decimal("0.00") if estado_pago == "PAGADA" else total_factura

                        cursor.execute("""
                            INSERT INTO public.facturas (
                                numfactur, numserfac, ruccedcli, fecfactur,
                                subtotfac, pordescue, valdescue, porivafac, valivafac,
                                totfactur, totbieiva, totbiesiniva, totseriva, totsersiniva,
                                totconiva, totsiniva, valpagini, valsalfac, forpagfac,
                                estpagfac, estprofac, imprimfac, userid, observ,
                                retemitid, autorizacion, año, mes
                            ) VALUES (
                                %s, %s, %s, %s, %s, 0, 0, %s, %s,
                                %s, %s, %s, 0, 0, %s, %s, 0, %s, %s,
                                %s, 'PENDIENTE', FALSE, %s, %s,
                                FALSE, 'SIN AUTORIZAR', %s, %s
                            )
                        """, [
                            numero_temporal, serie, cliente_seleccionado, fecha_factura,
                            subtotal, iva_pct, iva_total, total_factura, base_iva, base_cero,
                            base_iva + iva_total, base_cero, saldo, forma_pago, estado_pago,
                            request.session.get("admin_username", "ADMIN"), observ,
                            str(fecha_factura.year), f"{fecha_factura.month:02d}",
                        ])

                        for linea in lineas:
                            numero_detalle = _siguiente_parametro(cursor, "numdetfac")
                            cursor.execute("""
                                INSERT INTO public.detallefacturas (
                                    numdetfac, numfactur, coditeinv, desiteinv,
                                    canfactur, preitefac, dscitefac, totitefac, candevolu
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
                            """, [
                                numero_detalle, numero_temporal, linea["codigo"],
                                linea["descripcion"], linea["cantidad"], linea["precio"],
                                linea["descuento"], linea["total"],
                            ])

                messages.success(
                    request,
                    f"Factura temporal {numero_temporal} guardada como PENDIENTE. "
                    "No se ha procesado ni enviado al SRI."
                )
                return redirect("admin_facturacion")
            except Exception as exc:
                errores.append(f"No se pudo guardar la factura temporal: {exc}")

    return render(request, "admin/factura_form.html", {
        "clientes": clientes, "items": items, "errores": errores,
        "fecha": fecha, "cliente_seleccionado": cliente_seleccionado,
        "observ": observ, "forma_pago": forma_pago, "parametros": parametros,
    })
