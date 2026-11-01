import json
import logging
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import connections, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .admin_views import admin_required
from .models.cobranza_envio_masivo import CobranzaEnvioMasivo


logger = logging.getLogger(__name__)
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

    servicios_sin_cliente = 0
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
                "(COALESCE(p.saldo_pendiente, 0) > 0 OR COALESCE(p.subtotal_servicios, 0) > 0)"
            ]
            parametros = [timezone.localdate().isoformat()]
            if busqueda:
                condiciones.append(
                    "(COALESCE(c.nomclient, '') ILIKE %s OR COALESCE(c.ruccedcli::text, p.identificacion) ILIKE %s)"
                )
                termino = f"%{busqueda}%"
                parametros.extend([termino, termino])
            if tipo == "facturas":
                condiciones.append("COALESCE(p.saldo_pendiente, 0) > 0")
            elif tipo == "servicios":
                condiciones.append("COALESCE(p.subtotal_servicios, 0) > 0")

            cursor.execute(
                f"""
                WITH cartera AS (
                    SELECT
                        COALESCE(cc.ruccedcli::text, '') AS identificacion,
                        COUNT(DISTINCT cc.numfactur) AS cantidad_facturas,
                        COUNT(DISTINCT cc.numfactur) FILTER (
                            WHERE cc.fecvencim::date < %s::date
                        ) AS cantidad_facturas_vencidas,
                        COALESCE(SUM(COALESCE(cc.valpagpar, 0)), 0) AS saldo_pendiente
                    FROM public.cuentascobrar cc
                    WHERE UPPER(TRIM(COALESCE(cc.estpagcue, ''))) = 'PENDIENTE'
                      AND COALESCE(cc.valpagpar, 0) > 0
                    GROUP BY COALESCE(cc.ruccedcli::text, '')
                ),
                servicios AS (
                    SELECT
                        COALESCE(p.ruc::text, '') AS identificacion,
                        COUNT(*) AS cantidad_servicios,
                        COALESCE(
                            SUM(COALESCE(p.canfactur, 0) * COALESCE(p.preitefac, 0)),
                            0
                        ) AS subtotal_servicios
                    FROM public.prefactura p
                    GROUP BY COALESCE(p.ruc::text, '')
                ),
                pendientes AS (
                    SELECT
                        COALESCE(f.identificacion, s.identificacion) AS identificacion,
                        COALESCE(f.cantidad_facturas, 0) AS cantidad_facturas,
                        COALESCE(f.cantidad_facturas_vencidas, 0) AS cantidad_facturas_vencidas,
                        COALESCE(f.saldo_pendiente, 0) AS saldo_pendiente,
                        COALESCE(s.cantidad_servicios, 0) AS cantidad_servicios,
                        COALESCE(s.subtotal_servicios, 0) AS subtotal_servicios
                    FROM cartera f
                    FULL OUTER JOIN servicios s
                        ON s.identificacion = f.identificacion
                )
                SELECT
                    COALESCE(c.ruccedcli::text, p.identificacion) AS ruc,
                    COALESCE(
                        c.nomclient,
                        CASE
                            WHEN p.identificacion = '' THEN 'Servicios sin identificación'
                            ELSE 'Identificación sin cliente asociado'
                        END
                    ) AS cliente,
                    COALESCE(c.activo, FALSE) AS activo,
                    (c.ruccedcli IS NOT NULL) AS cliente_registrado,
                    p.cantidad_facturas,
                    p.cantidad_facturas_vencidas,
                    p.saldo_pendiente,
                    p.cantidad_servicios,
                    p.subtotal_servicios
                FROM pendientes p
                LEFT JOIN public.clientes c
                    ON COALESCE(c.ruccedcli::text, '') = p.identificacion
                WHERE {" AND ".join(condiciones)}
                ORDER BY
                    (
                        COALESCE(p.saldo_pendiente, 0)
                        + COALESCE(p.subtotal_servicios, 0)
                          * (1 + %s::numeric / 100)
                    ) DESC,
                    c.nomclient ASC NULLS LAST
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
                "ruc": str(fila["ruc"] or "").strip() or "Sin identificación",
                "cliente": fila["cliente"],
                "activo": bool(fila["activo"]),
                "cliente_registrado": bool(fila["cliente_registrado"]),
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

            if item["cliente_registrado"]:
                resumen["clientes"] += 1
            resumen["facturas"] += item["cantidad_facturas"]
            resumen["facturas_vencidas"] += item["cantidad_facturas_vencidas"]
            resumen["saldo_facturas"] += saldo_facturas
            resumen["servicios"] += item["cantidad_servicios"]
            resumen["subtotal_servicios"] += subtotal_servicios
            resumen["iva_servicios"] += iva_servicios
            resumen["total_servicios"] += total_servicios
            resumen["total_general"] += total_general

        # El total de servicios debe salir directamente de prefactura.
        # El resumen por cliente anterior puede omitir filas cuyo RUC todavía
        # no está registrado o no coincide con public.clientes.
        filtro_servicios = ""
        parametros_servicios = []
        if busqueda:
            filtro_servicios = """
                WHERE (
                    COALESCE(c.nomclient, '') ILIKE %s
                    OR COALESCE(p.ruc::text, '') ILIKE %s
                )
            """
            termino_servicios = f"%{busqueda}%"
            parametros_servicios.extend([termino_servicios, termino_servicios])

        with conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS cantidad,
                    COALESCE(
                        SUM(COALESCE(p.canfactur, 0) * COALESCE(p.preitefac, 0)),
                        0
                    ) AS subtotal,
                    COUNT(DISTINCT COALESCE(p.ruc::text, '')) FILTER (
                        WHERE c.ruccedcli IS NULL
                    ) AS sin_cliente
                FROM public.prefactura p
                LEFT JOIN public.clientes c
                    ON COALESCE(c.ruccedcli::text, '') = COALESCE(p.ruc::text, '')
                {filtro_servicios}
                """,
                parametros_servicios,
            )
            cantidad_servicios_global, subtotal_servicios_global, servicios_sin_cliente = cursor.fetchone()

        subtotal_servicios_global = Decimal(str(subtotal_servicios_global or 0)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        iva_servicios_global = (
            subtotal_servicios_global * porcentaje_iva / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_servicios_global = subtotal_servicios_global + iva_servicios_global

        resumen["servicios"] = int(cantidad_servicios_global or 0)
        resumen["subtotal_servicios"] = subtotal_servicios_global
        resumen["iva_servicios"] = iva_servicios_global
        resumen["total_servicios"] = total_servicios_global

        if tipo == "facturas":
            resumen["servicios"] = 0
            resumen["subtotal_servicios"] = Decimal("0.00")
            resumen["iva_servicios"] = Decimal("0.00")
            resumen["total_servicios"] = Decimal("0.00")
            resumen["total_general"] = resumen["saldo_facturas"]
            servicios_sin_cliente = 0
        elif tipo == "servicios":
            resumen["facturas"] = 0
            resumen["facturas_vencidas"] = 0
            resumen["saldo_facturas"] = Decimal("0.00")
            resumen["total_general"] = resumen["total_servicios"]
        else:
            resumen["total_general"] = resumen["saldo_facturas"] + resumen["total_servicios"]

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
        "servicios_sin_cliente": servicios_sin_cliente,
        "busqueda": busqueda,
        "tipo": tipo,
        "error": error,
        "envios_masivos": CobranzaEnvioMasivo.objects.all()[:8],
        "mes_actual": timezone.localdate().month,
        "anio_actual": timezone.localdate().year,
    })


def _destinatarios_cobranza_masiva():
    """Prepara destinatarios por identificación exacta con cartera pendiente."""
    conexion = _db()
    conexion.ensure_connection()
    with conexion.cursor() as cursor:
        cursor.execute(
            """
            WITH cartera AS (
                SELECT
                    COALESCE(cc.ruccedcli::text, '') AS identificacion,
                    COALESCE(SUM(COALESCE(cc.valpagpar, 0)), 0) AS saldo_facturas
                FROM public.cuentascobrar cc
                WHERE UPPER(TRIM(COALESCE(cc.estpagcue, ''))) = 'PENDIENTE'
                  AND COALESCE(cc.valpagpar, 0) > 0
                GROUP BY COALESCE(cc.ruccedcli::text, '')
            ),
            servicios AS (
                SELECT
                    COALESCE(p.ruc::text, '') AS identificacion,
                    COALESCE(
                        SUM(COALESCE(p.canfactur, 0) * COALESCE(p.preitefac, 0)),
                        0
                    ) AS subtotal_servicios
                FROM public.prefactura p
                GROUP BY COALESCE(p.ruc::text, '')
            ),
            pendientes AS (
                SELECT
                    COALESCE(f.identificacion, s.identificacion) AS identificacion,
                    COALESCE(f.saldo_facturas, 0) AS saldo_facturas,
                    COALESCE(s.subtotal_servicios, 0) AS subtotal_servicios
                FROM cartera f
                FULL OUTER JOIN servicios s
                    ON s.identificacion = f.identificacion
            )
            SELECT
                p.identificacion,
                COALESCE(c.nomclient, '') AS cliente,
                COALESCE(c.corelectr, '') AS correo,
                (c.ruccedcli IS NOT NULL) AS cliente_registrado
            FROM pendientes p
            LEFT JOIN public.clientes c
                ON COALESCE(c.ruccedcli::text, '') = p.identificacion
            WHERE p.saldo_facturas > 0 OR p.subtotal_servicios > 0
            ORDER BY c.nomclient ASC NULLS LAST, p.identificacion ASC
            """
        )
        filas = cursor.fetchall()

    destinatarios = []
    omitidos_sin_cliente = 0
    omitidos_sin_correo = 0
    omitidos_correo_invalido = 0
    identificaciones_pendientes = len(filas)

    for identificacion, cliente, correo, cliente_registrado in filas:
        if not cliente_registrado:
            omitidos_sin_cliente += 1
            continue

        correo = (correo or "").strip()
        if not correo:
            omitidos_sin_correo += 1
            continue
        try:
            validate_email(correo)
        except ValidationError:
            omitidos_correo_invalido += 1
            continue

        destinatarios.append({
            "ruc": str(identificacion or ""),
            "cliente": str(cliente or "Cliente"),
            "email": correo,
        })

    resumen = {
        "identificaciones_pendientes": identificaciones_pendientes,
        "destinatarios": len(destinatarios),
        "omitidos_sin_cliente": omitidos_sin_cliente,
        "omitidos_sin_correo": omitidos_sin_correo,
        "omitidos_correo_invalido": omitidos_correo_invalido,
    }
    return destinatarios, resumen


@admin_required
def admin_cobranza_masivo_previsualizar(request):
    if request.method != "GET":
        return JsonResponse({"ok": False, "error": "Método no permitido."}, status=405)
    try:
        destinatarios, resumen = _destinatarios_cobranza_masiva()
        if destinatarios:
            if not (settings.DEFAULT_FROM_EMAIL or "").strip():
                raise RuntimeError("DEFAULT_FROM_EMAIL no está configurado en Django.")

            # Prueba una generación real antes de permitir encolar toda la campaña.
            from types import SimpleNamespace
            from .cobranza_cliente_views import _reporte_datos_cobranza, _reporte_cobranza_pdf

            primero = destinatarios[0]
            cliente_prueba = SimpleNamespace(
                ruccedcli=primero["ruc"],
                nomclient=primero["cliente"],
            )
            datos_prueba = _reporte_datos_cobranza(cliente_prueba)
            if not datos_prueba.get("servicios_disponibles"):
                raise RuntimeError("No se pudo consultar prefactura para generar el reporte de prueba.")
            _reporte_cobranza_pdf(cliente_prueba, datos_prueba)

        return JsonResponse({"ok": True, **resumen})
    except Exception as exc:
        logger.exception("No se pudo preparar la vista previa del envío masivo de cobranza.")
        return JsonResponse({
            "ok": False,
            "error": f"No se puede iniciar el envío masivo porque falló la validación previa: {exc}",
        }, status=500)


@admin_required
def admin_cobranza_masivo_encolar(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido."}, status=405)

    try:
        destinatarios, resumen = _destinatarios_cobranza_masiva()
        if not destinatarios:
            return JsonResponse({
                "ok": False,
                "error": "No hay clientes con cartera pendiente y correo electrónico válido.",
                **resumen,
            }, status=400)

        envio = CobranzaEnvioMasivo.objects.create(
            estado=CobranzaEnvioMasivo.Estado.PENDIENTE,
            destinatarios=len(destinatarios),
            omitidos_sin_cliente=resumen["omitidos_sin_cliente"],
            omitidos_sin_correo=resumen["omitidos_sin_correo"],
            omitidos_correo_invalido=resumen["omitidos_correo_invalido"],
            pendientes_json=json.dumps(destinatarios, ensure_ascii=False),
            creado_por=(
                request.session.get("admin_name")
                or request.session.get("admin_username", "")
            ),
        )
        return JsonResponse({
            "ok": True,
            "envio_id": envio.pk,
            "mensaje": (
                f"Envío masivo #{envio.pk} puesto en cola para "
                f"{len(destinatarios)} cliente(s)."
            ),
            **resumen,
        })
    except Exception:
        logger.exception("No se pudo encolar el envío masivo de cobranza.")
        return JsonResponse({
            "ok": False,
            "error": "No se pudo poner el envío masivo en cola.",
        }, status=500)


@admin_required
def admin_cobranza_masivo_reintentar(request, envio_id):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido."}, status=405)

    envio = get_object_or_404(CobranzaEnvioMasivo, pk=envio_id)
    if envio.estado != CobranzaEnvioMasivo.Estado.ERROR:
        return JsonResponse({
            "ok": False,
            "error": "Solo se pueden reintentar envíos que tengan errores.",
        }, status=400)

    try:
        fallidos = json.loads(envio.fallidos_json or "[]")
    except (TypeError, ValueError):
        fallidos = []

    pendientes = [
        {"ruc": item.get("ruc", ""), "cliente": item.get("cliente", "Cliente"), "email": item.get("email", "")}
        for item in fallidos
        if item.get("ruc") and item.get("email")
    ]
    if not pendientes:
        return JsonResponse({"ok": False, "error": "No hay destinatarios fallidos para reintentar."}, status=400)

    envio.estado = CobranzaEnvioMasivo.Estado.PENDIENTE
    envio.pendientes_json = json.dumps(pendientes, ensure_ascii=False)
    envio.fallidos_json = "[]"
    envio.fallidos = 0
    envio.error_detalle = ""
    envio.enviado_en = None
    envio.destinatarios = envio.enviados + len(pendientes)
    envio.save(update_fields=[
        "estado", "pendientes_json", "fallidos_json", "fallidos",
        "error_detalle", "enviado_en", "destinatarios",
    ])
    return JsonResponse({
        "ok": True,
        "mensaje": f"Se pusieron en cola {len(pendientes)} destinatario(s) para reintento.",
    })


def _auditar_columnas_prefactura(cursor):
    """Inspecciona todas las columnas reales y determina cómo quedará cada una."""
    cursor.execute(
        """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            is_identity,
            is_generated
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'prefactura'
        ORDER BY ordinal_position
        """
    )
    filas = cursor.fetchall()
    if not filas:
        raise RuntimeError("No se encontró la tabla public.prefactura o no hay permisos para leer su estructura.")

    expresiones = {
        "numdetfac": "Número de línea de prefactura; se asigna desde parametros.numdetprefac",
        "ruc": "Identificación exacta de clientes.ruccedcli",
        "coditeinv": "Código del mes (001 a 012)",
        "desiteinv": "Descripción de public.items",
        "canfactur": "Cantidad 1",
        "preitefac": "Tarifa del cliente",
        "año": "Año seleccionado",
        "creadopor": "Usuario administrativo",
        "fecha": "Fecha de generación",
        "dscitefac": "Descuento 0",
        "totitefac": "Cantidad × tarifa (antes de IVA)",
    }
    requeridas = {
        "numdetfac", "ruc", "coditeinv", "desiteinv",
        "canfactur", "preitefac", "año", "creadopor", "fecha",
    }
    existentes = {fila[0] for fila in filas}
    incumplimientos = []
    resultado = []

    for nombre, tipo, nullable, default, identidad, generada in filas:
        if nombre in expresiones:
            estado = "Valor asignado por el proceso"
            detalle = expresiones[nombre]
        elif identidad == "YES" or generada not in ("NEVER", None):
            estado = "Generada por la base de datos"
            detalle = "Columna identity o generada"
        elif default is not None:
            estado = "Valor por defecto de la base de datos"
            detalle = str(default)
        elif nullable == "YES":
            estado = "Sin valor explícito (se guarda NULL)"
            detalle = "La columna permite NULL"
        else:
            estado = "FALTA VALOR OBLIGATORIO"
            detalle = "No tiene valor asignado, DEFAULT, identity ni permite NULL"
            incumplimientos.append(nombre)

        resultado.append({
            "nombre": nombre,
            "tipo": tipo,
            "nullable": nullable == "YES",
            "estado": estado,
            "detalle": detalle,
        })

    ausentes = sorted(requeridas - existentes)
    for nombre in ausentes:
        incumplimientos.append(nombre)
        resultado.append({
            "nombre": nombre,
            "tipo": "No existe",
            "nullable": False,
            "estado": "FALTA COLUMNA REQUERIDA",
            "detalle": "La generación mensual necesita esta columna.",
        })

    return {
        "columnas": resultado,
        "incumplimientos": sorted(set(incumplimientos)),
        "puede_generar": not incumplimientos,
    }


def _insertar_prefacturas_mensuales(
    cursor, columnas, consecutivo, codigo_mes, descripcion, anio, usuario, fecha_generacion
):
    """Inserta todos los campos que el proceso conoce y detecta columnas no cubiertas."""
    disponibles = {columna["nombre"] for columna in columnas["columnas"]}
    expresiones = {
        "numdetfac": ("%s + candidatos.orden", [consecutivo]),
        "ruc": ("candidatos.ruccedcli", []),
        "coditeinv": ("%s", [codigo_mes]),
        "desiteinv": ("%s", [descripcion]),
        "canfactur": ("1", []),
        "preitefac": ("candidatos.tarifa", []),
        "año": ("%s", [anio]),
        "creadopor": ("%s", [usuario]),
        "fecha": ("%s", [fecha_generacion]),
        "dscitefac": ("0", []),
        "totitefac": (
            "ROUND(COALESCE(candidatos.tarifa, 0)::numeric, 2)::double precision",
            [],
        ),
    }
    campos = [nombre for nombre in expresiones if nombre in disponibles]
    columnas_sql = ", ".join('"' + nombre.replace('"', '""') + '"' for nombre in campos)
    expresiones_sql = ", ".join(expresiones[nombre][0] for nombre in campos)
    parametros_sql = [codigo_mes, anio]
    for nombre in campos:
        parametros_sql.extend(expresiones[nombre][1])

    cursor.execute(
        f"""
        WITH candidatos AS (
            SELECT
                c.ruccedcli,
                COALESCE(c.tarifa, 0) AS tarifa,
                ROW_NUMBER() OVER (ORDER BY c.ruccedcli) AS orden
            FROM public.clientes c
            WHERE c.activo IS TRUE
              AND c.automatizado IS TRUE
              AND UPPER(TRIM(COALESCE(c.semensual, ''))) = 'MENSUAL'
              AND NOT EXISTS (
                  SELECT 1
                  FROM public.prefactura p
                  WHERE p.ruc = c.ruccedcli
                    AND p.coditeinv = %s
                    AND p."año" = %s
              )
        )
        INSERT INTO public.prefactura ({columnas_sql})
        SELECT {expresiones_sql}
        FROM candidatos
        ORDER BY candidatos.ruccedcli
        """,
        parametros_sql,
    )
    return cursor.rowcount


def _validar_periodo_prefacturacion(mes, anio):
    try:
        mes = int(mes)
    except (TypeError, ValueError):
        raise ValueError("Selecciona un mes válido.")

    anio = str(anio or "").strip()
    if mes < 1 or mes > 12:
        raise ValueError("El mes debe estar entre 1 y 12.")
    if len(anio) != 4 or not anio.isdigit() or int(anio) < 2000:
        raise ValueError("Indica un año válido de cuatro dígitos.")

    return mes, anio, str(mes).zfill(3)


def _resumen_prefacturacion_mensual(cursor, mes, anio, codigo_mes):
    cursor.execute(
        "SELECT coditem, desitem FROM public.items WHERE coditem = %s",
        [codigo_mes],
    )
    item = cursor.fetchone()
    if item is None or item[1] is None or not str(item[1]).strip():
        raise ValueError(
            f"No existe un servicio con descripción válida para el código {codigo_mes} en el catálogo de items."
        )

    cursor.execute(
        """
        SELECT
            COUNT(*) AS clientes_mensuales,
            COUNT(*) FILTER (
                WHERE EXISTS (
                    SELECT 1
                    FROM public.prefactura p
                    WHERE p.ruc = c.ruccedcli
                      AND p.coditeinv = %s
                      AND p."año" = %s
                )
            ) AS ya_generados,
            COUNT(*) FILTER (
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM public.prefactura p
                    WHERE p.ruc = c.ruccedcli
                      AND p.coditeinv = %s
                      AND p."año" = %s
                )
            ) AS por_generar,
            COALESCE(
                SUM(COALESCE(c.tarifa, 0)) FILTER (
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM public.prefactura p
                        WHERE p.ruc = c.ruccedcli
                          AND p.coditeinv = %s
                          AND p."año" = %s
                    )
                ),
                0
            ) AS total_tarifas
        FROM public.clientes c
        WHERE c.activo IS TRUE
          AND c.automatizado IS TRUE
          AND UPPER(TRIM(COALESCE(c.semensual, ''))) = 'MENSUAL'
        """,
        [
            codigo_mes, anio,
            codigo_mes, anio,
            codigo_mes, anio,
        ],
    )
    clientes_mensuales, ya_generados, por_generar, total_tarifas = cursor.fetchone()
    return {
        "codigo_mes": codigo_mes,
        "descripcion": item[1],
        "clientes_mensuales": int(clientes_mensuales or 0),
        "ya_generados": int(ya_generados or 0),
        "por_generar": int(por_generar or 0),
        "total_tarifas": Decimal(str(total_tarifas or 0)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
    }


@admin_required
def admin_prefacturacion_mensual_previsualizar(request):
    if request.method != "GET":
        return JsonResponse({"ok": False, "error": "Método no permitido."}, status=405)
    try:
        mes, anio, codigo_mes = _validar_periodo_prefacturacion(
            request.GET.get("mes"),
            request.GET.get("anio"),
        )
        conexion = _db()
        conexion.ensure_connection()
        with conexion.cursor() as cursor:
            cursor.execute("SELECT numdetprefac FROM public.parametros")
            parametros = cursor.fetchall()
            if len(parametros) != 1 or parametros[0][0] is None:
                raise RuntimeError(
                    "Se esperaba un único consecutivo numdetprefac configurado en public.parametros."
                )
            cursor.execute(
                "SELECT COALESCE(MAX(numdetfac), 0) FROM public.prefactura"
            )
            maximo_prefactura = int(cursor.fetchone()[0] or 0)
            consecutivo_actual = int(parametros[0][0])
            resumen = _resumen_prefacturacion_mensual(cursor, mes, anio, codigo_mes)
            resumen["consecutivo_actual"] = consecutivo_actual
            resumen["consecutivo_maximo_prefactura"] = maximo_prefactura
            resumen["consecutivo_coherente"] = consecutivo_actual >= maximo_prefactura
            resumen["consecutivo_siguiente"] = max(
                consecutivo_actual, maximo_prefactura
            ) + 1
            auditoria = _auditar_columnas_prefactura(cursor)
        return JsonResponse({
            "ok": True,
            "mes": mes,
            "anio": anio,
            **resumen,
            "puede_generar": auditoria["puede_generar"],
        })
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("No se pudo preparar la generación de prefacturación mensual.")
        return JsonResponse({
            "ok": False,
            "error": (
                "No se pudo consultar clientes, catálogo o consecutivo de prefacturación. "
                f"Detalle: {type(exc).__name__}: {str(exc)[:350]}"
            ),
        }, status=500)


@admin_required
def admin_prefacturacion_mensual_generar(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido."}, status=405)

    try:
        mes, anio, codigo_mes = _validar_periodo_prefacturacion(
            request.POST.get("mes"),
            request.POST.get("anio"),
        )
        conexion = _db()
        conexion.ensure_connection()
        fecha_generacion = timezone.localdate()
        usuario = (
            request.session.get("admin_username")
            or request.session.get("admin_name")
            or "ADMIN"
        )[:20]

        with transaction.atomic(using=DB_ALIAS):
            with conexion.cursor() as cursor:
                # Bloquea el único registro de parámetros para serializar
                # ejecuciones simultáneas y proteger numdetprefac.
                cursor.execute(
                    "SELECT numdetprefac FROM public.parametros FOR UPDATE"
                )
                parametros = cursor.fetchall()
                if len(parametros) != 1:
                    raise RuntimeError(
                        "Se esperaba un único registro en public.parametros para bloquear numdetprefac."
                    )
                consecutivo = parametros[0][0]
                if consecutivo is None:
                    raise RuntimeError("El consecutivo numdetprefac no está configurado.")
                consecutivo = int(consecutivo)
                cursor.execute(
                    "SELECT COALESCE(MAX(numdetfac), 0) FROM public.prefactura"
                )
                maximo_prefactura = int(cursor.fetchone()[0] or 0)
                # Si el parámetro quedó atrás por inserciones históricas,
                # se alinea con el mayor ID real antes de asignar nuevas líneas.
                consecutivo_original = consecutivo
                consecutivo = max(consecutivo, maximo_prefactura)

                resumen = _resumen_prefacturacion_mensual(
                    cursor, mes, anio, codigo_mes
                )
                auditoria = _auditar_columnas_prefactura(cursor)
                if not auditoria["puede_generar"]:
                    raise RuntimeError(
                        "No se puede generar porque existen columnas obligatorias sin cubrir: "
                        + ", ".join(auditoria["incumplimientos"])
                    )
                cantidad_generada = _insertar_prefacturas_mensuales(
                    cursor=cursor,
                    columnas=auditoria,
                    consecutivo=int(consecutivo),
                    codigo_mes=codigo_mes,
                    descripcion=resumen["descripcion"],
                    anio=anio,
                    usuario=usuario,
                    fecha_generacion=fecha_generacion,
                )

                if cantidad_generada:
                    nuevo_consecutivo = int(consecutivo) + cantidad_generada
                    cursor.execute(
                        "UPDATE public.parametros SET numdetprefac = %s",
                        [nuevo_consecutivo],
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError(
                            "No se pudo actualizar de forma única el consecutivo numdetfac."
                        )
                    consecutivo_inicial = int(consecutivo) + 1
                    consecutivo_final = nuevo_consecutivo
                else:
                    consecutivo_inicial = None
                    consecutivo_final = None
                    nuevo_consecutivo = int(consecutivo)
                    if consecutivo != consecutivo_original:
                        cursor.execute(
                            "UPDATE public.parametros SET numdetprefac = %s",
                            [nuevo_consecutivo],
                        )
                        if cursor.rowcount != 1:
                            raise RuntimeError(
                                "No se pudo sincronizar el consecutivo numdetprefac."
                            )

        logger.info(
            "Prefacturación mensual %02d/%s: generados=%s consecutivos=%s-%s usuario=%s",
            mes,
            anio,
            cantidad_generada,
            consecutivo_inicial,
            consecutivo_final,
            usuario,
        )
        return JsonResponse({
            "ok": True,
            "cantidad_generada": cantidad_generada,
            "numdetfac_inicial": consecutivo_inicial,
            "numdetfac_final": consecutivo_final,
            "codigo_mes": codigo_mes,
            "descripcion": resumen["descripcion"],
            "mes": mes,
            "anio": anio,
            "ya_generados": resumen["ya_generados"],
            "consecutivo_actualizado": nuevo_consecutivo,
            "consecutivo_sincronizado": consecutivo != consecutivo_original,
            "mensaje": (
                (
                    f"Se generaron {cantidad_generada} servicio(s) de "
                    f"{resumen['descripcion']} para {mes:02d}/{anio}."
                    if cantidad_generada
                    else f"No había servicios pendientes de generar para {mes:02d}/{anio}. "
                         "Los clientes ya tenían el servicio registrado."
                )
                + (
                    f" El consecutivo se sincronizó con el máximo existente ({maximo_prefactura})."
                    if consecutivo != consecutivo_original else ""
                )
            ),
        })
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Error al generar prefacturación mensual.")
        return JsonResponse({
            "ok": False,
            "error": (
                "No se pudo generar la prefacturación mensual. "
                f"Detalle: {type(exc).__name__}: {str(exc)[:350]}"
            ),
        }, status=500)
