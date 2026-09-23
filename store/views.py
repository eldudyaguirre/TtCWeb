from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.conf import settings
from django.db import IntegrityError, connection, connections, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from io import BytesIO
from datetime import datetime
from django.views.decorators.http import require_POST

from .models import (
    Archivo,
    Establecimiento,
    ParametrosCliente,
    PuntoEmision,
    SecuencialDocumento,
    UsuarioCliente,
)
from .services.acceso import obtener_resumen_cliente, validar_acceso_cliente
from .services.archivos import eliminar_archivo, guardar_archivo
from .services.legales import obtener_aceptaciones_pendientes, versiones_legales_vigentes


TEMPLATE_PREVIEWS = {
    'page-404-1': 'page-404-1.html',
    'page-about-1': 'page-about-1.html',
    'page-blog-1': 'page-blog-1.html',
    'page-blog-2': 'page-blog-2.html',
    'page-contact-1': 'page-contact-1.html',
    'page-contact-2': 'page-contact-2.html',
    'page-our-people-1': 'page-our-people-1.html',
    'page-partners-1': 'page-partners-1.html',
    'page-pricing-table-1': 'page-pricing-table-1.html',
    'page-pricing-table-2': 'page-pricing-table-2.html',
    'page-projects-1': 'page-projects-1.html',
    'page-search-1': 'page-search-1.html',
    'page-services-1': 'page-services-1.html',
    'page-single-post-1': 'page-single-post-1.html',
    'page-single-project-1': 'page-single-project-1.html',
    'page-single-service-1': 'page-single-service-1.html',
    'page-testimonials-1': 'page-testimonials-1.html',
    'quienes': 'quienes.html',
}


def home(request):
    return render(request, 'index.html')


def do_signin(request):
    if request.user.is_authenticated:
        return redirect('portal')

    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                if user.is_staff or user.is_superuser:
                    login(request, user)
                    return redirect('portal')

                asignaciones = UsuarioCliente.objects.filter(
                    usuario=user,
                    activo=True,
                ).select_related('cliente')

                if not asignaciones.exists():
                    messages.error(
                        request,
                        'Tu usuario no tiene un cliente activo asignado al portal.',
                    )
                else:
                    acceso_permitido = False
                    ultimo_motivo = None

                    for asignacion in asignaciones:
                        permitido, _, detalle = validar_acceso_cliente(
                            asignacion.cliente
                        )

                        if permitido:
                            request.session['cliente_ruccedcli'] = (
                                asignacion.cliente.ruccedcli
                            )
                            login(request, user)
                            return redirect('portal')

                        ultimo_motivo = detalle

                    messages.error(
                        request,
                        ultimo_motivo or 'El acceso al portal está restringido.',
                    )
        else:
            messages.error(request, 'Usuario o contraseña inválidos.')

    return render(request, 'sign-in.html', {'signin_form': form})


@login_required
def mi_empresa(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect('portal')

    asignacion = (
        UsuarioCliente.objects
        .filter(usuario=request.user, activo=True)
        .select_related('cliente')
        .first()
    )

    if asignacion is None:
        logout(request)
        messages.error(
            request,
            'No tienes una empresa activa asignada a tu usuario.',
        )
        return redirect('signin')

    permitido, _, detalle = validar_acceso_cliente(asignacion.cliente)

    if not permitido:
        logout(request)
        messages.error(request, detalle)
        return redirect('signin')

    cliente = asignacion.cliente

    if request.method == 'POST':
        if asignacion.rol == UsuarioCliente.Rol.CONSULTA:
            messages.error(request, 'Tu usuario tiene permisos de consulta y no puede modificar los datos.')
        else:
            campos_editables = [
                'dirclient', 'ocuclient', 'corelectr',
                'teldomcli', 'teloficli', 'telcelcli',
                'estcivcli', 'fecnacimi',
                'clavesri', 'cediess', 'claveiess',
                'mrlcon', 'mrlsal', 'clavesuper',
                'iessdomestica', 'datiess',
            ]

            for campo in campos_editables:
                setattr(cliente, campo, request.POST.get(campo, '').strip())

            cliente.save(update_fields=campos_editables)
            messages.success(request, 'Los datos de la empresa fueron actualizados correctamente.')

        return redirect('mi_empresa')

    return render(
        request,
        'mi-empresa.html',
        {
            'cliente': cliente,
            'rol': asignacion.rol,
            'puede_editar': asignacion.rol != UsuarioCliente.Rol.CONSULTA,
        },
    )


@login_required
def parametros(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect('portal')

    asignacion = (
        UsuarioCliente.objects
        .filter(usuario=request.user, activo=True)
        .select_related('cliente')
        .first()
    )

    if asignacion is None:
        logout(request)
        messages.error(request, 'No tienes una empresa activa asignada a tu usuario.')
        return redirect('signin')

    permitido, _, detalle = validar_acceso_cliente(asignacion.cliente)
    if not permitido:
        logout(request)
        messages.error(request, detalle)
        return redirect('signin')

    cliente = asignacion.cliente
    puede_editar = asignacion.rol != UsuarioCliente.Rol.CONSULTA
    parametros_cliente, _ = ParametrosCliente.objects.get_or_create(cliente=cliente)

    if request.method == 'POST':
        if not puede_editar:
            messages.error(request, 'Tu usuario tiene permisos de consulta y no puede modificar los parámetros.')
            return redirect('parametros')

        accion = request.POST.get('accion', '').strip()

        try:
            with transaction.atomic():
                if accion == 'guardar_certificado':
                    ambiente = request.POST.get('ambiente', ParametrosCliente.Ambiente.PRUEBAS)
                    if ambiente not in dict(ParametrosCliente.Ambiente.choices):
                        raise ValueError('El ambiente seleccionado no es válido.')

                    parametros_cliente.ambiente = ambiente
                    clave_p12 = request.POST.get('clave_p12', '').strip()
                    if clave_p12:
                        parametros_cliente.clave_p12 = clave_p12

                    archivo = request.FILES.get('certificado_p12')
                    if archivo:
                        if not archivo.name.lower().endswith('.p12'):
                            raise ValueError('El certificado debe ser un archivo con extensión .p12.')
                        if archivo.size > 10 * 1024 * 1024:
                            raise ValueError('El archivo P12 no puede superar los 10 MB.')

                        archivo_anterior = parametros_cliente.certificado_archivo
                        nuevo_archivo = guardar_archivo(
                            cliente=cliente,
                            uploaded_file=archivo,
                            tipo=Archivo.Tipo.CERTIFICADO_P12,
                            subcarpeta='certificados',
                            usuario=request.user,
                        )
                        parametros_cliente.certificado_archivo = nuevo_archivo
                        parametros_cliente.save(
                            update_fields=['ambiente', 'clave_p12', 'certificado_archivo', 'actualizado_en']
                        )

                        if archivo_anterior and archivo_anterior.pk != nuevo_archivo.pk:
                            transaction.on_commit(
                                lambda archivo_anterior=archivo_anterior: eliminar_archivo(archivo_anterior)
                            )
                    else:
                        parametros_cliente.save(update_fields=['ambiente', 'clave_p12', 'actualizado_en'])

                    messages.success(request, 'Los parámetros de firma electrónica fueron actualizados.')

                elif accion == 'agregar_establecimiento':
                    codigo = request.POST.get('codigo', '').strip()
                    nombre = request.POST.get('nombre', '').strip()
                    direccion = request.POST.get('direccion', '').strip()
                    if len(codigo) != 3 or not codigo.isdigit():
                        raise ValueError('El código del establecimiento debe tener exactamente 3 dígitos.')
                    Establecimiento.objects.create(
                        cliente=cliente,
                        codigo=codigo,
                        nombre=nombre,
                        direccion=direccion,
                    )
                    messages.success(request, 'Establecimiento agregado correctamente.')

                elif accion == 'editar_establecimiento':
                    establecimiento = Establecimiento.objects.get(id=request.POST.get('id'), cliente=cliente)
                    codigo = request.POST.get('codigo', '').strip()
                    if len(codigo) != 3 or not codigo.isdigit():
                        raise ValueError('El código del establecimiento debe tener exactamente 3 dígitos.')
                    establecimiento.codigo = codigo
                    establecimiento.nombre = request.POST.get('nombre', '').strip()
                    establecimiento.direccion = request.POST.get('direccion', '').strip()
                    establecimiento.activo = request.POST.get('activo') == '1'
                    establecimiento.save(update_fields=['codigo', 'nombre', 'direccion', 'activo'])
                    messages.success(request, 'Establecimiento actualizado correctamente.')

                elif accion == 'agregar_punto':
                    establecimiento = Establecimiento.objects.get(id=request.POST.get('establecimiento_id'), cliente=cliente)
                    codigo = request.POST.get('codigo', '').strip()
                    if len(codigo) != 3 or not codigo.isdigit():
                        raise ValueError('El código del punto de emisión debe tener exactamente 3 dígitos.')
                    PuntoEmision.objects.create(
                        establecimiento=establecimiento,
                        codigo=codigo,
                        nombre=request.POST.get('nombre', '').strip(),
                    )
                    messages.success(request, 'Punto de emisión agregado correctamente.')

                elif accion == 'editar_punto':
                    punto = PuntoEmision.objects.select_related('establecimiento').get(
                        id=request.POST.get('id'),
                        establecimiento__cliente=cliente,
                    )
                    codigo = request.POST.get('codigo', '').strip()
                    if len(codigo) != 3 or not codigo.isdigit():
                        raise ValueError('El código del punto de emisión debe tener exactamente 3 dígitos.')
                    punto.codigo = codigo
                    punto.nombre = request.POST.get('nombre', '').strip()
                    punto.activo = request.POST.get('activo') == '1'
                    punto.save(update_fields=['codigo', 'nombre', 'activo'])
                    messages.success(request, 'Punto de emisión actualizado correctamente.')

                elif accion == 'guardar_secuencial':
                    punto = PuntoEmision.objects.select_related('establecimiento').get(
                        id=request.POST.get('punto_id'),
                        establecimiento__cliente=cliente,
                    )
                    tipo = request.POST.get('tipo_documento', '').strip()
                    secuencial = int(request.POST.get('secuencial_actual', '0'))
                    tipos_validos = dict(SecuencialDocumento.TipoDocumento.choices)
                    if tipo not in tipos_validos:
                        raise ValueError('El tipo de documento no es válido.')
                    if secuencial < 1:
                        raise ValueError('El secuencial debe ser mayor que cero.')
                    sec, creado = SecuencialDocumento.objects.get_or_create(
                        punto_emision=punto,
                        tipo_documento=tipo,
                        defaults={'secuencial_actual': secuencial},
                    )
                    if not creado:
                        sec.secuencial_actual = secuencial
                        sec.activo = request.POST.get('activo') == '1'
                        sec.save(update_fields=['secuencial_actual', 'activo'])
                    messages.success(request, 'Secuencial guardado correctamente.')

                else:
                    raise ValueError('La operación solicitada no es válida.')

        except (ValueError, TypeError, Establecimiento.DoesNotExist, PuntoEmision.DoesNotExist, SecuencialDocumento.DoesNotExist) as exc:
            messages.error(request, str(exc) or 'No fue posible completar la operación.')
        except IntegrityError:
            messages.error(request, 'No se pudo guardar porque el código o secuencial ya está registrado.')

        return redirect('parametros')

    establecimientos = cliente.establecimientos.prefetch_related('puntos_emision__secuenciales').all()
    return render(
        request,
        'parametros.html',
        {
            'cliente': cliente,
            'parametros_cliente': parametros_cliente,
            'establecimientos': establecimientos,
            'puede_editar': puede_editar,
            'tipos_documento': SecuencialDocumento.TipoDocumento.choices,
            'ambientes': ParametrosCliente.Ambiente.choices,
        },
    )


@login_required
def cambiar_contrasena(request):
    form = PasswordChangeForm(request.user, request.POST or None)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(
            request,
            'Tu contraseña fue actualizada correctamente.',
        )
        return redirect('cambiar_contrasena')

    context = {'form': form}

    if not request.user.is_staff and not request.user.is_superuser:
        asignacion = (
            UsuarioCliente.objects
            .filter(usuario=request.user, activo=True)
            .select_related('cliente')
            .first()
        )
        if asignacion is not None:
            context['cliente'] = asignacion.cliente

    return render(
        request,
        'cambiar-contrasena.html',
        context,
    )


def do_logout(request):
    logout(request)
    return redirect('home')


@login_required
def portal(request):
    if request.user.is_staff or request.user.is_superuser:
        return render(request, 'portal.html', {'es_administrador': True})

    asignaciones = UsuarioCliente.objects.filter(
        usuario=request.user,
        activo=True,
    ).select_related('cliente')

    for asignacion in asignaciones:
        permitido, _, _ = validar_acceso_cliente(asignacion.cliente)

        if permitido:
            request.session['cliente_ruccedcli'] = asignacion.cliente.ruccedcli
            resumen = obtener_resumen_cliente(asignacion.cliente)

            return render(
                request,
                'portal.html',
                {
                    'cliente': asignacion.cliente,
                    'resumen': resumen,
                    'rol': asignacion.rol,
                    'pendientes_legales': obtener_aceptaciones_pendientes(request.user),
                    'versiones_legales': versiones_legales_vigentes(),
                },
            )

    logout(request)
    messages.error(
        request,
        'El acceso al portal está restringido. Verifica el estado de tu cuenta.',
    )
    return redirect('signin')


@login_required
@require_POST
def aceptar_documento_legal(request):
    from .models import AceptacionLegal

    tipo = request.POST.get('tipo', '').strip()
    versiones = versiones_legales_vigentes()

    if tipo not in versiones:
        messages.error(request, 'El documento legal solicitado no es válido.')
        return redirect('portal')

    if tipo == AceptacionLegal.Tipo.POLITICA_DATOS:
        confirmado = request.POST.get('informado') == '1'
        if not confirmado:
            messages.error(request, 'Debes confirmar que has sido informado sobre la Política de Protección de Datos.')
            return redirect('portal')
    elif tipo == AceptacionLegal.Tipo.TERMINOS_USO:
        confirmado = request.POST.get('acepto') == '1'
        if not confirmado:
            messages.error(request, 'Debes aceptar los Términos y Condiciones de Uso para continuar.')

            return redirect('portal')

    version = versiones[tipo]
    AceptacionLegal.objects.get_or_create(
        usuario=request.user,
        tipo=tipo,
        version=version,
        defaults={
            'ip_address': request.META.get('REMOTE_ADDR'),
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:1000],
        },
    )
    return redirect('portal')


COMPRAS_COLUMNS = [
    ('numero', 'N°'),
    ('proveedor', 'PROVEEDOR'),
    ('ruc', 'RUC'),
    ('tipcom', 'TIP COM'),
    ('fecha', 'FECHA'),
    ('numfactura', 'NUMERO FACTURA'),
    ('numaut', 'NUM AUT.'),
    ('bases_sin_iva', 'BASES SIN IVA'),
    ('bases_con_iva', 'BASES CON IVA'),
    ('iva', 'IVA'),
    ('total', 'TOTAL'),
    ('retiva', 'RET IVA'),
    ('codret', 'COD RET'),
    ('retrenta', 'RET RENTA'),
    ('numret', 'NUM RET.'),
]


def _cliente_portal(request):
    if request.user.is_staff or request.user.is_superuser:
        return None

    asignacion = (
        UsuarioCliente.objects
        .filter(usuario=request.user, activo=True)
        .select_related('cliente')
        .first()
    )
    if asignacion is None:
        return None

    permitido, _, _ = validar_acceso_cliente(asignacion.cliente)
    return asignacion.cliente if permitido else None


def _cliente_db(cliente):
    """Obtiene una conexión PostgreSQL a la base de datos del cliente."""
    alias = f"cliente_{cliente.ruccedcli}"
    if alias not in connections.databases:
        base = settings.DATABASES['default'].copy()
        base['NAME'] = cliente.ruccedcli
        connections.databases[alias] = base
    return connections[alias]


def _compras_where(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return None, [], None

    where = []
    params = []

    hoy = datetime.now().date()
    primer_dia_mes = hoy.replace(day=1)

    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    proveedor = request.GET.get('proveedor', '').strip()

    if not fecha_desde:
        fecha_desde = primer_dia_mes.strftime('%Y-%m-%d')
    if not fecha_hasta:
        fecha_hasta = hoy.strftime('%Y-%m-%d')

    if fecha_desde:
        try:
            datetime.strptime(fecha_desde, '%Y-%m-%d')
            where.append("fecemi::date >= %s::date")
            params.append(fecha_desde)
        except ValueError:
            fecha_desde = ''

    if fecha_hasta:
        try:
            datetime.strptime(fecha_hasta, '%Y-%m-%d')
            where.append("fecemi::date < (%s::date + INTERVAL '1 day')")
            params.append(fecha_hasta)
        except ValueError:
            fecha_hasta = ''

    if proveedor:
        where.append("(ruccedprovee ILIKE %s OR nomprovee ILIKE %s)")
        params.extend([f'%{proveedor}%', f'%{proveedor}%'])

    return " AND ".join(where) if where else "1=1", params, {
        'cliente': cliente,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'proveedor': proveedor,
    }


def _compras_base_sql():
    return """
        SELECT
            c.fecemi,
            c.ruccedprovee,
            c.nomprovee,
            TRIM(c.tipcom::text) AS tipcom,
            c.numest,
            c.numptoemi,
            c.numsec,
            c.numaut,
            c.baseimpnoobj,
            c.baseimpiva0,
            c.baseexenta,
            c.baseimpiva5,
            c.baseimpiva8,
            c.baseimpiva12,
            c.baseimpiva14,
            c.baseimpiva15,
            c.montoiva5,
            c.montoiva8,
            c.montoiva12,
            c.montoiva14,
            c.montoiva15,
            c.retencioniva10,
            c.retencioniva20,
            c.retencioniva30,
            c.retencioniva70,
            c.retencioniva100,
            c.codret,
            c.valret,
            c.numestret,
            c.numptoemiret,
            c.numsecret
        FROM comprasnue c
        WHERE TRIM(c.tipcom::text) IN ('01', '02')
    """


def _compras_query(where, params, cliente, limit=None, offset=None):
    sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY fecemi::date ASC) AS numero,
            nomprovee AS proveedor,
            ruccedprovee AS ruc,
            CASE
                WHEN tipcom = '01' THEN 'FAC'
                WHEN tipcom = '02' THEN 'N/V'
                ELSE tipcom
            END AS tipcom,
            fecemi AS fecha,
            CONCAT(numest, '-', numptoemi, '-', numsec) AS numfactura,
            numaut,
            (
                COALESCE(NULLIF(baseimpnoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva0::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseexenta::text, ''), '0')::numeric
            ) AS bases_sin_iva,
            (
                COALESCE(NULLIF(baseimpiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva15::text, ''), '0')::numeric
            ) AS bases_con_iva,
            (
                COALESCE(NULLIF(montoiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva15::text, ''), '0')::numeric
            ) AS iva,
            (
                COALESCE(NULLIF(baseimpnoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva0::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseexenta::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva15::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva15::text, ''), '0')::numeric
            ) AS total,
            (
                COALESCE(NULLIF(retencioniva10::text, ''), '0')::numeric
                + COALESCE(NULLIF(retencioniva20::text, ''), '0')::numeric
                + COALESCE(NULLIF(retencioniva30::text, ''), '0')::numeric
                + COALESCE(NULLIF(retencioniva70::text, ''), '0')::numeric
                + COALESCE(NULLIF(retencioniva100::text, ''), '0')::numeric
            ) AS retiva,
            codret,
            COALESCE(NULLIF(valret::text, ''), '0')::numeric AS retrenta,
            CONCAT(numestret, '-', numptoemiret, '-', numsecret) AS numret
        FROM ({_compras_base_sql()}) compras_reporte
        WHERE {where}
        ORDER BY fecemi::date ASC
    """

    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params = [*params, limit, offset or 0]

    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _compras_resumen(where, params, cliente):
    sql = f"""
        SELECT
            COALESCE(SUM(
                COALESCE(NULLIF(baseimpnoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva0::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseexenta::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(
                COALESCE(NULLIF(baseimpiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva15::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(
                COALESCE(NULLIF(montoiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva15::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(
                COALESCE(NULLIF(baseimpnoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva0::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseexenta::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva15::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva15::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(
                COALESCE(NULLIF(retencioniva10::text, ''), '0')::numeric
                + COALESCE(NULLIF(retencioniva20::text, ''), '0')::numeric
                + COALESCE(NULLIF(retencioniva30::text, ''), '0')::numeric
                + COALESCE(NULLIF(retencioniva70::text, ''), '0')::numeric
                + COALESCE(NULLIF(retencioniva100::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(COALESCE(NULLIF(valret::text, ''), '0')::numeric), 0)
        FROM ({_compras_base_sql()}) compras_reporte
        WHERE {where}
    """

    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()

    return dict(zip(
        ['bases_sin_iva', 'bases_con_iva', 'iva', 'total', 'retiva', 'retrenta'],
        [float(value or 0) for value in row],
    ))


def _compras_datos_exportacion(request):
    where, params, filtros = _compras_where(request)
    if where is None:
        return None, [], None, None

    cliente = filtros['cliente']
    filas = _compras_query(where, params, cliente)
    resumen = _compras_resumen(where, params, cliente)
    return filtros, filas, resumen, where


@login_required
def compras(request):
    try:
        filtros, _, resumen, _ = _compras_datos_exportacion(request)
        if filtros is None:
            return redirect('portal')

        try:
            pagina = max(1, int(request.GET.get('pagina', '1')))
        except ValueError:
            pagina = 1

        por_pagina = 50
        where, params, _ = _compras_where(request)

        count_sql = f"SELECT COUNT(*) FROM ({_compras_base_sql()}) compras_reporte WHERE {where}"
        with _cliente_db(filtros['cliente']).cursor() as cursor:
            cursor.execute(count_sql, params)
            total_registros = cursor.fetchone()[0]

        offset = (pagina - 1) * por_pagina
        filas = _compras_query(where, params, filtros['cliente'], por_pagina, offset)
        total_paginas = max(1, (total_registros + por_pagina - 1) // por_pagina)

        return render(request, 'compras.html', {
            'cliente': filtros['cliente'],
            'filas': filas,
            'resumen': resumen,
            'filtros': filtros,
            'pagina': pagina,
            'total_paginas': total_paginas,
            'total_registros': total_registros,
        })
    except Exception as exc:
        return HttpResponse(
            f"Error en reporte de compras: {type(exc).__name__}: {exc}",
            status=500,
            content_type='text/plain; charset=utf-8',
        )



PROVEEDORES_COLUMNS = [
    ('numero', 'N°'),
    ('ruc', 'RUC'),
    ('proveedor', 'PROVEEDOR'),
]


def _proveedores_anios(cliente):
    sql = """
        SELECT DISTINCT EXTRACT(YEAR FROM fecemi::date)::integer AS anio
        FROM comprasnue
        WHERE fecemi IS NOT NULL
          AND EXTRACT(YEAR FROM fecemi::date)::integer BETWEEN %s AND %s
        ORDER BY anio DESC
    """
    hoy = datetime.now().date()
    anio_actual = hoy.year
    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, [anio_actual - 6, anio_actual])
        return [row[0] for row in cursor.fetchall()]


def _proveedores_datos(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return None, [], []

    anios = _proveedores_anios(cliente)
    try:
        anio = int(request.GET.get('anio', anios[0] if anios else datetime.now().year))
    except (TypeError, ValueError):
        anio = anios[0] if anios else datetime.now().year

    if anio not in anios:
        anio = anios[0] if anios else datetime.now().year

    sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY nomprovee, ruccedprovee) AS numero,
            ruccedprovee AS ruc,
            nomprovee AS proveedor
        FROM (
            SELECT
                TRIM(ruccedprovee::text) AS ruccedprovee,
                TRIM(nomprovee::text) AS nomprovee
            FROM comprasnue
            WHERE EXTRACT(YEAR FROM fecemi::date)::integer = %s
              AND COALESCE(TRIM(ruccedprovee::text), '') <> ''
            GROUP BY TRIM(ruccedprovee::text), TRIM(nomprovee::text)
        ) proveedores
        ORDER BY nomprovee, ruccedprovee
    """
    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, [anio])
        filas = cursor.fetchall()

    return {'cliente': cliente, 'anio': anio, 'anios': anios}, filas, anios


@login_required
def listado_proveedores(request):
    try:
        filtros, filas, _ = _proveedores_datos(request)
        if filtros is None:
            return redirect('portal')
        return render(request, 'listado-proveedores.html', {
            'cliente': filtros['cliente'],
            'filas': filas,
            'anio': filtros['anio'],
            'anios': filtros['anios'],
            'total_registros': len(filas),
        })
    except Exception as exc:
        return HttpResponse(
            f"Error en listado de proveedores: {type(exc).__name__}: {exc}",
            status=500,
            content_type='text/plain; charset=utf-8',
        )


@login_required
def listado_proveedores_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    filtros, filas, _ = _proveedores_datos(request)
    if filtros is None:
        return redirect('portal')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=35,
        rightMargin=35,
        topMargin=30,
        bottomMargin=30,
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'ProveedoresTitulo',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    cabecera = ParagraphStyle(
        'ProveedoresCabecera',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
    )
    tabla = ParagraphStyle(
        'ProveedoresTabla',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
    )
    encabezado = ParagraphStyle(
        'ProveedoresEncabezado',
        parent=tabla,
        fontName='Helvetica-Bold',
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    elements = [
        Paragraph('LISTADO DE PROVEEDORES', titulo),
        Paragraph(f'PERÍODO FISCAL {filtros["anio"]}', cabecera),
        Paragraph(
            f'{filtros["cliente"].nomclient} | RUC. {filtros["cliente"].ruccedcli}',
            cabecera,
        ),
        Spacer(1, 12),
    ]

    data = [[Paragraph(label, encabezado) for _, label in PROVEEDORES_COLUMNS]]
    for row in filas:
        data.append([
            Paragraph(str(row[0]), tabla),
            Paragraph(str(row[1] or ''), tabla),
            Paragraph(str(row[2] or ''), tabla),
        ])

    table = Table(data, repeatRows=1, colWidths=[45, 130, 330])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#21333e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#d8e0e3')),
        ('ALIGN', (0, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef5f5')),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f'Total de proveedores: {len(filas)}', tabla))
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="listado_proveedores_{filtros["anio"]}.pdf"'
    )
    return response


@login_required
def listado_proveedores_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    filtros, filas, _ = _proveedores_datos(request)
    if filtros is None:
        return redirect('portal')

    wb = Workbook()
    ws = wb.active
    ws.title = 'Proveedores'
    ws.append([label for _, label in PROVEEDORES_COLUMNS])

    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='21333E')
        cell.alignment = Alignment(horizontal='center')

    for row in filas:
        ws.append(list(row))

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 55

    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="listado_proveedores_{filtros["anio"]}.xlsx"'
    )
    return response


CLIENTES_COLUMNS = [
    ('numero', 'N°'),
    ('ruc', 'RUC'),
    ('cliente', 'CLIENTE'),
]


def _clientes_anios(cliente):
    sql = """
        SELECT DISTINCT EXTRACT(YEAR FROM fecfactur::date)::integer AS anio
        FROM ventas
        WHERE fecfactur IS NOT NULL
          AND EXTRACT(YEAR FROM fecfactur::date)::integer BETWEEN %s AND %s
        ORDER BY anio DESC
    """
    hoy = datetime.now().date()
    anio_actual = hoy.year
    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, [anio_actual - 6, anio_actual])
        return [row[0] for row in cursor.fetchall()]


def _clientes_datos(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return None, [], []

    anios = _clientes_anios(cliente)
    try:
        anio = int(request.GET.get('anio', anios[0] if anios else datetime.now().year))
    except (TypeError, ValueError):
        anio = anios[0] if anios else datetime.now().year

    if anio not in anios:
        anio = anios[0] if anios else datetime.now().year

    sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY cliente, ruc) AS numero,
            ruc,
            cliente
        FROM (
            SELECT DISTINCT ON (TRIM(ruccedcli::text))
                TRIM(ruccedcli::text) AS ruc,
                TRIM(nomcli::text) AS cliente
            FROM ventas
            WHERE EXTRACT(YEAR FROM fecfactur::date)::integer = %s
              AND COALESCE(TRIM(ruccedcli::text), '') <> ''
            ORDER BY
                TRIM(ruccedcli::text),
                fecfactur DESC NULLS LAST,
                TRIM(nomcli::text)
        ) clientes
        ORDER BY cliente, ruc
    """
    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, [anio])
        filas = cursor.fetchall()

    return {'cliente': cliente, 'anio': anio, 'anios': anios}, filas, anios


@login_required
def listado_clientes(request):
    try:
        filtros, filas, _ = _clientes_datos(request)
        if filtros is None:
            return redirect('portal')
        return render(request, 'listado-clientes.html', {
            'cliente': filtros['cliente'],
            'filas': filas,
            'anio': filtros['anio'],
            'anios': filtros['anios'],
            'total_registros': len(filas),
        })
    except Exception as exc:
        return HttpResponse(
            f"Error en listado de clientes: {type(exc).__name__}: {exc}",
            status=500,
            content_type='text/plain; charset=utf-8',
        )


@login_required
def listado_clientes_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    filtros, filas, _ = _clientes_datos(request)
    if filtros is None:
        return redirect('portal')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=35,
        rightMargin=35,
        topMargin=30,
        bottomMargin=30,
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'ClientesTitulo',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    cabecera = ParagraphStyle(
        'ClientesCabecera',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
    )
    tabla = ParagraphStyle(
        'ClientesTabla',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
    )
    encabezado = ParagraphStyle(
        'ClientesEncabezado',
        parent=tabla,
        fontName='Helvetica-Bold',
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    elements = [
        Paragraph('LISTADO DE CLIENTES', titulo),
        Paragraph(f'PERÍODO FISCAL {filtros["anio"]}', cabecera),
        Paragraph(
            f'{filtros["cliente"].nomclient} | RUC. {filtros["cliente"].ruccedcli}',
            cabecera,
        ),
        Spacer(1, 12),
    ]

    data = [[Paragraph(label, encabezado) for _, label in CLIENTES_COLUMNS]]
    for row in filas:
        data.append([
            Paragraph(str(row[0]), tabla),
            Paragraph(str(row[1] or ''), tabla),
            Paragraph(str(row[2] or ''), tabla),
        ])

    table = Table(data, repeatRows=1, colWidths=[45, 130, 330])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#21333e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#d8e0e3')),
        ('ALIGN', (0, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef5f5')),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f'Total de clientes: {len(filas)}', tabla))
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="listado_clientes_{filtros["anio"]}.pdf"'
    )
    return response


@login_required
def listado_clientes_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    filtros, filas, _ = _clientes_datos(request)
    if filtros is None:
        return redirect('portal')

    wb = Workbook()
    ws = wb.active
    ws.title = 'Clientes'
    ws.append([label for _, label in CLIENTES_COLUMNS])

    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='21333E')
        cell.alignment = Alignment(horizontal='center')

    for row in filas:
        ws.append(list(row))

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 55

    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="listado_clientes_{filtros["anio"]}.xlsx"'
    )
    return response


TRABAJADORES_COLUMNS = [
    ('numero', 'N°'),
    ('cedula', 'CÉDULA'),
    ('trabajador', 'TRABAJADOR'),
    ('cargo', 'CARGO'),
    ('tipojornada', 'TIPO JORNADA'),
    ('fecentrada', 'FECHA ENTRADA'),
    ('sueldo', 'SUELDO'),
]


def _trabajadores_datos(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return None, []

    sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY nombres, cedula) AS numero,
            TRIM(cedula::text) AS cedula,
            TRIM(nombres::text) AS trabajador,
            TRIM(COALESCE(cargo::text, '')) AS cargo,
            TRIM(COALESCE(tipojornada::text, '')) AS tipojornada,
            fecentrada,
            sueldo
        FROM trabajadores
        WHERE activo = TRUE
          AND COALESCE(TRIM(comisionsec::text), '') <> 'SERVICIO DOMESTICO'
        ORDER BY nombres, cedula
    """
    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    return {'cliente': cliente}, filas


@login_required
def trabajadores(request):
    try:
        filtros, filas = _trabajadores_datos(request)
        if filtros is None:
            return redirect('portal')

        return render(request, 'trabajadores.html', {
            'cliente': filtros['cliente'],
            'filas': filas,
            'total_registros': len(filas),
        })
    except Exception as exc:
        return HttpResponse(
            f"Error en listado de trabajadores: {type(exc).__name__}: {exc}",
            status=500,
            content_type='text/plain; charset=utf-8',
        )


@login_required
def trabajador_detalle(request, cedula):
    cliente = _cliente_portal(request)
    if cliente is None:
        return JsonResponse({'error': 'No autorizado.'}, status=403)

    sql = """
        SELECT
            cedula,
            nombres,
            sexo,
            fecnac,
            cargas,
            direccion,
            telefono,
            activo,
            fecentrada,
            comisionsec,
            cargo,
            tipojornada,
            sueldo,
            codcomision,
            fecsalida,
            motivos,
            fr,
            xiv,
            xiii,
            notastra,
            jn,
            horaslab
        FROM trabajadores
        WHERE TRIM(cedula::text) = %s
          AND activo = TRUE
          AND COALESCE(TRIM(comisionsec::text), '') <> 'SERVICIO DOMESTICO'
        LIMIT 1
    """

    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, [cedula.strip()])
        row = cursor.fetchone()

    if row is None:
        return JsonResponse({'error': 'Trabajador no encontrado.'}, status=404)

    campos = [
        'cedula', 'nombres', 'sexo', 'fecnac', 'cargas', 'direccion',
        'telefono', 'activo', 'fecentrada', 'comisionsec', 'cargo',
        'tipojornada', 'sueldo', 'codcomision', 'fecsalida', 'motivos',
        'fr', 'xiv', 'xiii', 'notastra', 'jn', 'horaslab',
    ]

    def serializar(valor):
        if hasattr(valor, 'isoformat'):
            return valor.isoformat()
        return valor

    return JsonResponse({
        campo: serializar(valor)
        for campo, valor in zip(campos, row)
    })


@login_required
def trabajador_pdf(request, cedula):
    cliente = _cliente_portal(request)
    if cliente is None:
        return redirect('portal')

    sql = """
        SELECT
            cedula, nombres, sexo, fecnac, cargas, direccion, telefono,
            activo, fecentrada, comisionsec, cargo, tipojornada, sueldo,
            codcomision, fecsalida, motivos, fr, xiv, xiii, notastra,
            jn, horaslab
        FROM trabajadores
        WHERE TRIM(cedula::text) = %s
          AND activo = TRUE
          AND COALESCE(TRIM(comisionsec::text), '') <> 'SERVICIO DOMESTICO'
        LIMIT 1
    """

    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, [cedula.strip()])
        row = cursor.fetchone()

    if row is None:
        return HttpResponse('Trabajador no encontrado.', status=404, content_type='text/plain; charset=utf-8')

    (
        cedula_db, nombres, sexo, fecnac, cargas, direccion, telefono,
        activo, fecentrada, comisionsec, cargo, tipojornada, sueldo,
        codcomision, fecsalida, motivos, fr, xiv, xiii, notastra,
        jn, horaslab
    ) = row

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    def valor(v):
        return '' if v is None else str(v)

    def fecha(v):
        return v.strftime('%d/%m/%Y') if v else ''

    def si_no(v):
        return 'Sí' if v else 'No'

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=35,
        bottomMargin=35,
    )

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'TrabajadorPDFTitulo',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=19,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    subtitulo = ParagraphStyle(
        'TrabajadorPDFSubtitulo',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    etiqueta = ParagraphStyle(
        'TrabajadorPDFEtiqueta',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
    )
    dato = ParagraphStyle(
        'TrabajadorPDFDato',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
    )

    elements = [
        Paragraph('FICHA DEL TRABAJADOR', titulo),
        Paragraph(f'{valor(nombres)} | CÉDULA {valor(cedula_db)}', subtitulo),
    ]

    datos = [
        ('Cédula', cedula_db),
        ('Nombres', nombres),
        ('Sexo', sexo),
        ('Fecha de nacimiento', fecha(fecnac)),
        ('Cargas familiares', cargas),
        ('Dirección de contacto', direccion),
        ('Teléfono de contacto', telefono),
        ('Estado', si_no(activo)),
        ('Fecha de ingreso', fecha(fecentrada)),
        ('Comisión sectorial', comisionsec),
        ('Cargo', cargo),
        ('Jornada laboral', tipojornada),
        ('Horas de jornada', horaslab),
        ('Sueldo', f'{float(sueldo or 0):,.2f}'),
        ('Código sectorial', codcomision),
        ('Fecha de salida', fecha(fecsalida)),
        ('Motivos', motivos),
        ('Acumulación F.P.', si_no(fr)),
        ('XIV mensualizado', si_no(xiv)),
        ('XIII mensualizado', si_no(xiii)),
        ('Jornada nocturna', si_no(jn)),
        ('Notas', notastra),
    ]

    data = []
    for etiqueta_texto, dato_valor in datos:
        data.append([
            Paragraph(etiqueta_texto, etiqueta),
            Paragraph(valor(dato_valor), dato),
        ])

    table = Table(data, colWidths=[145, 365])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#eef5f5')),
        ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#d8e0e3')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 12))
    elements.append(
        Paragraph(
            f'{cliente.nomclient} | RUC. {cliente.ruccedcli}',
            subtitulo,
        )
    )

    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="trabajador_{cedula_db}.pdf"'
    )
    return response


@login_required
def trabajadores_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    filtros, filas = _trabajadores_datos(request)
    if filtros is None:
        return redirect('portal')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25,
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'TrabajadoresTitulo',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    cabecera = ParagraphStyle(
        'TrabajadoresCabecera',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
    )
    tabla = ParagraphStyle(
        'TrabajadoresTabla',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
    )
    encabezado = ParagraphStyle(
        'TrabajadoresEncabezado',
        parent=tabla,
        fontName='Helvetica-Bold',
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    elements = [
        Paragraph('LISTADO DE TRABAJADORES', titulo),
        Paragraph('TRABAJADORES ACTIVOS', cabecera),
        Paragraph(
            f'{filtros["cliente"].nomclient} | RUC. {filtros["cliente"].ruccedcli}',
            cabecera,
        ),
        Spacer(1, 12),
    ]

    data = [[Paragraph(label, encabezado) for _, label in TRABAJADORES_COLUMNS]]
    for row in filas:
        data.append([
            Paragraph(str(row[0]), tabla),
            Paragraph(str(row[1] or ''), tabla),
            Paragraph(str(row[2] or ''), tabla),
            Paragraph(str(row[3] or ''), tabla),
            Paragraph(str(row[4] or ''), tabla),
            Paragraph(
                row[5].strftime('%d/%m/%Y') if row[5] else '',
                tabla,
            ),
            Paragraph(f'{float(row[6] or 0):.2f}', tabla),
        ])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[35, 85, 180, 115, 100, 90, 75],
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#21333e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#d8e0e3')),
        ('ALIGN', (0, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (4, -1), 'LEFT'),
        ('ALIGN', (5, 1), (6, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef5f5')),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f'Total de trabajadores activos: {len(filas)}', tabla))
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="listado_trabajadores.pdf"'
    return response


@login_required
def trabajadores_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    filtros, filas = _trabajadores_datos(request)
    if filtros is None:
        return redirect('portal')

    wb = Workbook()
    ws = wb.active
    ws.title = 'Trabajadores'
    ws.append([label for _, label in TRABAJADORES_COLUMNS])

    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='21333E')
        cell.alignment = Alignment(horizontal='center')

    for row in filas:
        ws.append([
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            float(row[6] or 0),
        ])

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 16
    ws.column_dimensions['C'].width = 40
    ws.column_dimensions['D'].width = 25
    ws.column_dimensions['E'].width = 20
    ws.column_dimensions['F'].width = 18
    ws.column_dimensions['G'].width = 15

    for cell in ws['F'][1:]:
        if cell.value:
            cell.number_format = 'DD/MM/YYYY'

    for cell in ws['G'][1:]:
        if cell.value is not None:
            cell.number_format = '#,##0.00'

    ws.append([])
    ws.append(['', '', '', '', '', 'TOTAL TRABAJADORES ACTIVOS', len(filas)])

    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="listado_trabajadores.xlsx"'
    return response


VENTAS_COLUMNS = [
    ('numero', 'N°'),
    ('cliente', 'CLIENTE'),
    ('ruc', 'RUC'),
    ('fecha', 'FECHA'),
    ('factura', 'FACTURA'),
    ('autorizacion', 'AUTORIZACION'),
    ('base0', 'BASE0'),
    ('baseiva', 'BASE IVA'),
    ('iva', 'IVA'),
    ('total', 'TOTAL'),
    ('retiva', 'RET IVA'),
    ('retrenta', 'RET RENTA'),
    ('numret', 'NUM RET'),
    ('autret', 'AUT RET'),
]


def _ventas_where(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return None, [], None

    where = []
    params = []

    hoy = datetime.now().date()
    primer_dia_mes = hoy.replace(day=1)

    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    cliente_busqueda = request.GET.get('cliente_busqueda', '').strip()

    if not fecha_desde:
        fecha_desde = primer_dia_mes.strftime('%Y-%m-%d')
    if not fecha_hasta:
        fecha_hasta = hoy.strftime('%Y-%m-%d')

    if fecha_desde:
        try:
            datetime.strptime(fecha_desde, '%Y-%m-%d')
            where.append("fecfactur::date >= %s::date")
            params.append(fecha_desde)
        except ValueError:
            fecha_desde = ''

    if fecha_hasta:
        try:
            datetime.strptime(fecha_hasta, '%Y-%m-%d')
            where.append("fecfactur::date < (%s::date + INTERVAL '1 day')")
            params.append(fecha_hasta)
        except ValueError:
            fecha_hasta = ''

    if cliente_busqueda:
        where.append("(ruccedcli ILIKE %s OR nomcli ILIKE %s)")
        params.extend([f'%{cliente_busqueda}%', f'%{cliente_busqueda}%'])

    return " AND ".join(where) if where else "1=1", params, {
        'cliente': cliente,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'cliente_busqueda': cliente_busqueda,
    }


def _ventas_base_sql():
    return """
        SELECT
            v.fecfactur,
            v.nomcli,
            v.ruccedcli,
            v.numfactur,
            v.autorizacion,
            v.basenoobj,
            v.baseiva0,
            v.baseiva12,
            v.iva,
            v.retiva,
            v.retrenta,
            v.numret,
            v.autret
        FROM ventas v
    """


def _ventas_query(where, params, cliente, limit=None, offset=None):
    sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY fecfactur::date ASC, factura ASC) AS numero,
            nomcli AS cliente,
            ruccedcli AS ruc,
            fecfactur AS fecha,
            factura,
            autorizacion,
            (
                COALESCE(NULLIF(basenoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseiva0::text, ''), '0')::numeric
            ) AS base0,
            COALESCE(NULLIF(baseiva12::text, ''), '0')::numeric AS baseiva,
            COALESCE(NULLIF(iva::text, ''), '0')::numeric AS iva,
            (
                COALESCE(NULLIF(basenoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseiva0::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(iva::text, ''), '0')::numeric
            ) AS total,
            COALESCE(NULLIF(retiva::text, ''), '0')::numeric AS retiva,
            COALESCE(NULLIF(retrenta::text, ''), '0')::numeric AS retrenta,
            numret,
            autret
        FROM (
            SELECT
                fecfactur,
                nomcli,
                ruccedcli,
                numfactur AS factura,
                autorizacion,
                basenoobj,
                baseiva0,
                baseiva12,
                iva,
                retiva,
                retrenta,
                numret,
                autret
            FROM ({_ventas_base_sql()}) ventas_reporte
        ) ventas_datos
        WHERE {where}
        ORDER BY fecfactur::date ASC, factura ASC
    """

    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params = [*params, limit, offset or 0]

    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _ventas_resumen(where, params, cliente):
    sql = f"""
        SELECT
            COALESCE(SUM(
                COALESCE(NULLIF(basenoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseiva0::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(
                COALESCE(NULLIF(baseiva12::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(
                COALESCE(NULLIF(iva::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(
                COALESCE(NULLIF(basenoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseiva0::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(iva::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(COALESCE(NULLIF(retiva::text, ''), '0')::numeric), 0),
            COALESCE(SUM(COALESCE(NULLIF(retrenta::text, ''), '0')::numeric), 0)
        FROM ({_ventas_base_sql()}) ventas_reporte
        WHERE {where}
    """
    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()

    base0, baseiva, iva, total, retiva, retrenta = [float(x or 0) for x in row]
    return {
        'base0': base0,
        'baseiva': baseiva,
        'iva': iva,
        'total': total,
        'retiva': retiva,
        'retrenta': retrenta,
    }


def _ventas_datos_exportacion(request):
    where, params, filtros = _ventas_where(request)
    if where is None:
        return None, [], None, None
    cliente = filtros['cliente']
    filas = _ventas_query(where, params, cliente)
    resumen = _ventas_resumen(where, params, cliente)
    return filtros, filas, resumen, where


@login_required
def ventas(request):
    try:
        filtros, _, resumen, _ = _ventas_datos_exportacion(request)
        if filtros is None:
            return redirect('portal')

        try:
            pagina = max(1, int(request.GET.get('pagina', '1')))
        except ValueError:
            pagina = 1

        por_pagina = 50
        where, params, _ = _ventas_where(request)

        count_sql = f"SELECT COUNT(*) FROM ({_ventas_base_sql()}) ventas_reporte WHERE {where}"
        with _cliente_db(filtros['cliente']).cursor() as cursor:
            cursor.execute(count_sql, params)
            total_registros = cursor.fetchone()[0]

        offset = (pagina - 1) * por_pagina
        filas = _ventas_query(where, params, filtros['cliente'], por_pagina, offset)
        total_paginas = max(1, (total_registros + por_pagina - 1) // por_pagina)

        return render(request, 'ventas.html', {
            'cliente': filtros['cliente'],
            'filas': filas,
            'resumen': resumen,
            'filtros': filtros,
            'pagina': pagina,
            'total_paginas': total_paginas,
            'total_registros': total_registros,
        })
    except Exception as exc:
        return HttpResponse(
            f"Error en reporte de facturas: {type(exc).__name__}: {exc}",
            status=500,
            content_type='text/plain; charset=utf-8',
        )


@login_required
def ventas_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    filtros, filas, resumen, _ = _ventas_datos_exportacion(request)
    if filtros is None:
        return redirect('portal')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=20,
        rightMargin=20,
        topMargin=20,
        bottomMargin=20,
    )
    styles = getSampleStyleSheet()

    titulo = ParagraphStyle(
        'VentasTitulo',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=3,
    )
    cabecera = ParagraphStyle(
        'VentasCabecera',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    tabla = ParagraphStyle(
        'VentasTabla',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=5.2,
        leading=6,
        alignment=TA_CENTER,
        wordWrap='CJK',
    )
    tabla_izq = ParagraphStyle(
        'VentasTablaIzq',
        parent=tabla,
        alignment=0,
    )
    encabezado = ParagraphStyle(
        'VentasEncabezado',
        parent=tabla,
        fontName='Helvetica-Bold',
        textColor=colors.white,
        leading=6.4,
    )

    elements = [
        Paragraph('REPORTE DE FACTURAS', titulo),
        Paragraph(
            f"FACTURAS DESDE {filtros['fecha_desde'] or '—'} A {filtros['fecha_hasta'] or '—'}",
            cabecera,
        ),
        Paragraph(
            f"{filtros['cliente'].nomclient} | RUC. {filtros['cliente'].ruccedcli}",
            cabecera,
        ),
        Spacer(1, 10),
    ]

    data = [[Paragraph(label, encabezado) for _, label in VENTAS_COLUMNS]]
    for row in filas:
        formatted = []
        for index, value in enumerate(row):
            if index in (1, 2, 3, 4, 5, 12, 13):
                formatted.append(Paragraph(str(value or ''), tabla if index != 1 else tabla_izq))
            else:
                formatted.append(f"{float(value or 0):.2f}" if index in (6, 7, 8, 9, 10, 11) else Paragraph(str(value or ''), tabla))
        data.append(formatted)

    data.append([
        '', '', '', '', '', '',
        f"{resumen['base0']:.2f}",
        f"{resumen['baseiva']:.2f}",
        f"{resumen['iva']:.2f}",
        f"{resumen['total']:.2f}",
        f"{resumen['retiva']:.2f}",
        f"{resumen['retrenta']:.2f}",
        '', '',
    ])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[22, 105, 68, 48, 72, 76, 52, 52, 42, 52, 45, 50, 52, 60],
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#21333e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 5.2),
        ('GRID', (0, 0), (-1, -1), .25, colors.HexColor('#d8e0e3')),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (13, -1), 'CENTER'),
        ('ALIGN', (6, 1), (11, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef5f5')),
    ]))
    elements.append(table)
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_facturas.pdf"'
    return response


@login_required
def ventas_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    filtros, filas, resumen, _ = _ventas_datos_exportacion(request)
    if filtros is None:
        return redirect('portal')

    wb = Workbook()
    ws = wb.active
    ws.title = 'Facturas'
    ws.append([label for _, label in VENTAS_COLUMNS])

    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='21333E')
        cell.alignment = Alignment(horizontal='center')

    for row in filas:
        ws.append(list(row))

    ws.append([])
    ws.append(['', '', '', '', '', '', 'RESUMEN'])
    ws.cell(ws.max_row, 7, resumen['base0'])
    ws.cell(ws.max_row, 8, resumen['baseiva'])
    ws.cell(ws.max_row, 9, resumen['iva'])
    ws.cell(ws.max_row, 10, resumen['total'])
    ws.cell(ws.max_row, 11, resumen['retiva'])
    ws.cell(ws.max_row, 12, resumen['retrenta'])

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

    widths = [7, 35, 17, 13, 25, 28, 15, 15, 13, 16, 14, 16, 18, 22]
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width

    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="reporte_facturas.xlsx"'
    return response



NOTAS_CREDITO_COLUMNS = [
    ('numero', 'N°'),
    ('proveedor', 'PROVEEDOR'),
    ('ruc', 'RUC'),
    ('tipdoc', 'TIPO DOC'),
    ('fecha', 'FECHA'),
    ('numdocumento', 'NUMERO DOCUMENTO'),
    ('numaut', 'NUM AUT.'),
    ('bases_sin_iva', 'BASES SIN IVA'),
    ('bases_con_iva', 'BASES CON IVA'),
    ('iva', 'IVA'),
    ('total', 'TOTAL'),
    ('codmod', 'COD MOD'),
    ('documentomod', 'DOCUMENTO MODIFICADO'),
    ('numautmod', 'NUM AUT'),
]


def _notas_credito_base_sql():
    return """
        SELECT
            c.fecemi,
            c.ruccedprovee,
            c.nomprovee,
            TRIM(c.tipcom::text) AS tipcom,
            c.numest,
            c.numptoemi,
            c.numsec,
            c.numaut,
            c.baseimpnoobj,
            c.baseimpiva0,
            c.baseexenta,
            c.baseimpiva5,
            c.baseimpiva8,
            c.baseimpiva12,
            c.baseimpiva14,
            c.baseimpiva15,
            c.montoiva5,
            c.montoiva8,
            c.montoiva12,
            c.montoiva14,
            c.montoiva15,
            c.codtipodoc,
            c.numestmod,
            c.numptoemimod,
            c.numsecmod,
            c.numautmod
        FROM comprasnue c
        WHERE TRIM(c.tipcom::text) = '04'
    """


def _notas_credito_query(where, params, cliente, limit=None, offset=None):
    sql = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY fecemi::date ASC) AS numero,
            nomprovee AS proveedor,
            ruccedprovee AS ruc,
            'N/C' AS tipdoc,
            fecemi AS fecha,
            CONCAT(numest, '-', numptoemi, '-', numsec) AS numdocumento,
            numaut,
            (
                COALESCE(NULLIF(baseimpnoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva0::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseexenta::text, ''), '0')::numeric
            ) AS bases_sin_iva,
            (
                COALESCE(NULLIF(baseimpiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva15::text, ''), '0')::numeric
            ) AS bases_con_iva,
            (
                COALESCE(NULLIF(montoiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva15::text, ''), '0')::numeric
            ) AS iva,
            (
                COALESCE(NULLIF(baseimpnoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva0::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseexenta::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva15::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva15::text, ''), '0')::numeric
            ) AS total,
            codtipodoc AS codmod,
            CONCAT(numestmod, '-', numptoemimod, '-', numsecmod) AS documentomod,
            numautmod
        FROM ({_notas_credito_base_sql()}) notas_reporte
        WHERE {where}
        ORDER BY fecemi::date ASC
    """
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params = [*params, limit, offset or 0]
    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _notas_credito_resumen(where, params, cliente):
    sql = f"""
        SELECT
            COALESCE(SUM(
                COALESCE(NULLIF(baseimpnoobj::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva0::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseexenta::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(
                COALESCE(NULLIF(baseimpiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(baseimpiva15::text, ''), '0')::numeric
            ), 0),
            COALESCE(SUM(
                COALESCE(NULLIF(montoiva5::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva8::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva12::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva14::text, ''), '0')::numeric
                + COALESCE(NULLIF(montoiva15::text, ''), '0')::numeric
            ), 0)
        FROM ({_notas_credito_base_sql()}) notas_reporte
        WHERE {where}
    """
    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(sql, params)
        row=cursor.fetchone()
    bases_sin, bases_con, iva = [float(x or 0) for x in row]
    return {'bases_sin_iva': bases_sin, 'bases_con_iva': bases_con, 'iva': iva, 'total': bases_sin + bases_con + iva}


def _notas_credito_datos(request):
    where, params, filtros = _compras_where(request)
    if where is None:
        return None, [], None, None
    cliente=filtros['cliente']
    return filtros, _notas_credito_query(where, params, cliente), _notas_credito_resumen(where, params, cliente), where


@login_required
def notas_credito(request):
    try:
        filtros, _, resumen, _ = _notas_credito_datos(request)
        if filtros is None:
            return redirect('portal')
        try:
            pagina=max(1, int(request.GET.get('pagina','1')))
        except ValueError:
            pagina=1
        por_pagina=50
        where, params, _ = _compras_where(request)
        count_sql=f"SELECT COUNT(*) FROM ({_notas_credito_base_sql()}) notas_reporte WHERE {where}"
        with _cliente_db(filtros['cliente']).cursor() as cursor:
            cursor.execute(count_sql, params)
            total_registros=cursor.fetchone()[0]
        offset=(pagina-1)*por_pagina
        filas=_notas_credito_query(where, params, filtros['cliente'], por_pagina, offset)
        total_paginas=max(1,(total_registros+por_pagina-1)//por_pagina)
        return render(request,'notas-credito.html',{
            'cliente':filtros['cliente'],'filas':filas,'resumen':resumen,'filtros':filtros,
            'pagina':pagina,'total_paginas':total_paginas,'total_registros':total_registros,
        })
    except Exception as exc:
        return HttpResponse(f"Error en reporte de notas de crédito: {type(exc).__name__}: {exc}",status=500,content_type='text/plain; charset=utf-8')


@login_required
def notas_credito_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    filtros, filas, resumen, _ = _notas_credito_datos(request)
    if filtros is None: return redirect('portal')
    buffer=BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=landscape(A4),leftMargin=20,rightMargin=20,topMargin=20,bottomMargin=20)
    styles=getSampleStyleSheet()
    titulo=ParagraphStyle('NCtitulo',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=14,leading=16,alignment=TA_CENTER,spaceAfter=3)
    cab=ParagraphStyle('NCcab',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=8.5,leading=11,alignment=TA_CENTER,spaceAfter=2)
    tabla=ParagraphStyle('NCtabla',parent=styles['Normal'],fontName='Helvetica',fontSize=5.4,leading=6.2,alignment=TA_CENTER,wordWrap='CJK')
    tabla_izq=ParagraphStyle('NCtablaIzq',parent=tabla,alignment=0)
    enc=ParagraphStyle('NCenc',parent=tabla,fontName='Helvetica-Bold',textColor=colors.white,leading=6.5)
    elements=[Paragraph('REPORTE DE NOTAS DE CRÉDITO',titulo),
              Paragraph(f"NOTAS DE CRÉDITO DESDE {filtros['fecha_desde'] or '—'} A {filtros['fecha_hasta'] or '—'}",cab),
              Paragraph(f"{filtros['cliente'].nomclient} | RUC. {filtros['cliente'].ruccedcli}",cab),Spacer(1,10)]
    data=[[Paragraph(label,enc) for _,label in NOTAS_CREDITO_COLUMNS]]
    for row in filas:
        vals=[]
        for i,v in enumerate(row):
            if i==1: vals.append(Paragraph(str(v or ''),tabla_izq))
            elif i in (0,2,3,4,5,6,11,12,13): vals.append(Paragraph(str(v or ''),tabla))
            else: vals.append(f"{float(v or 0):.2f}")
        data.append(vals)
    data.append(['','','','','','','',
                 f"{resumen['bases_sin_iva']:.2f}",f"{resumen['bases_con_iva']:.2f}",
                 f"{resumen['iva']:.2f}",f"{resumen['total']:.2f}",'','',''])
    table=Table(data,repeatRows=1,colWidths=[22,105,68,38,48,72,50,54,54,42,54,42,70,55])
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#21333e')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,-1),5.4),
        ('GRID',(0,0),(-1,-1),.25,colors.HexColor('#d8e0e3')),
        ('ALIGN',(0,1),(0,-1),'CENTER'),('ALIGN',(2,1),(6,-1),'CENTER'),('ALIGN',(7,1),(13,-1),'RIGHT'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#eef5f5')),
    ]))
    elements.append(table)
    doc.build(elements)
    response=HttpResponse(buffer.getvalue(),content_type='application/pdf')
    response['Content-Disposition']='attachment; filename="reporte_notas_credito.pdf"'
    return response


@login_required
def notas_credito_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    filtros, filas, resumen, _ = _notas_credito_datos(request)
    if filtros is None: return redirect('portal')
    wb=Workbook(); ws=wb.active; ws.title='Notas de crédito'
    ws.append([label for _,label in NOTAS_CREDITO_COLUMNS])
    for cell in ws[1]:
        cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill('solid',fgColor='21333E'); cell.alignment=Alignment(horizontal='center')
    for row in filas: ws.append(list(row))
    ws.append([])
    ws.append(['','','','','','','RESUMEN'])
    ws.cell(ws.max_row,8,resumen['bases_sin_iva']); ws.cell(ws.max_row,9,resumen['bases_con_iva'])
    ws.cell(ws.max_row,10,resumen['iva']); ws.cell(ws.max_row,11,resumen['total'])
    ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    widths=[7,38,17,10,13,25,18,16,16,13,16,11,24,18]
    for i,width in enumerate(widths,1): ws.column_dimensions[chr(64+i)].width=width
    buffer=BytesIO(); wb.save(buffer)
    response=HttpResponse(buffer.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition']='attachment; filename="reporte_notas_credito.xlsx"'
    return response

@login_required
def compras_pdf(request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    filtros, filas, resumen, _ = _compras_datos_exportacion(request)
    if filtros is None:
        return redirect('portal')

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()

    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle

    estilo_titulo = ParagraphStyle(
        'ReporteComprasTitulo',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=3,
    )
    estilo_cabecera = ParagraphStyle(
        'ReporteComprasCabecera',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        alignment=TA_CENTER,
        spaceAfter=2,
    )

    elements = [
        Paragraph('REPORTE DE COMPRAS', estilo_titulo),
        Paragraph(
            f"COMPRAS DESDE {filtros['fecha_desde'] or '—'} A {filtros['fecha_hasta'] or '—'}",
            estilo_cabecera,
        ),
        Paragraph(
            f"{filtros['cliente'].nomclient} | RUC. {filtros['cliente'].ruccedcli}",
            estilo_cabecera,
        ),
        Spacer(1, 10),
    ]

    estilo_tabla = ParagraphStyle(
        'ReporteComprasTabla',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=5.4,
        leading=6.2,
        alignment=TA_CENTER,
        wordWrap='CJK',
    )
    estilo_tabla_izquierda = ParagraphStyle(
        'ReporteComprasTablaIzquierda',
        parent=estilo_tabla,
        alignment=0,
    )
    estilo_encabezado_tabla = ParagraphStyle(
        'ReporteComprasEncabezadoTabla',
        parent=estilo_tabla,
        fontName='Helvetica-Bold',
        textColor=colors.white,
        alignment=TA_CENTER,
        leading=6.5,
    )

    data = [[Paragraph(label, estilo_encabezado_tabla) for _, label in COMPRAS_COLUMNS]]
    for row in filas:
        formatted = []
        for index, value in enumerate(row):
            if index in (1,):
                formatted.append(Paragraph(str(value or ''), estilo_tabla_izquierda))
            elif index in (0, 2, 3, 4, 5, 6, 12, 14):
                formatted.append(Paragraph(str(value or ''), estilo_tabla))
            else:
                formatted.append(f"{float(value or 0):.2f}")
        data.append(formatted)

    data.append([
        '', '', '', '', '', '', '',
        f"{resumen['bases_sin_iva']:.2f}",
        f"{resumen['bases_con_iva']:.2f}",
        f"{resumen['iva']:.2f}",
        f"{resumen['total']:.2f}",
        f"{resumen['retiva']:.2f}",
        '',
        f"{resumen['retrenta']:.2f}",
        '',
    ])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[22, 105, 68, 38, 48, 65, 72, 50, 50, 40, 48, 42, 38, 48, 50],
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#21333e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 5.4),
        ('GRID', (0, 0), (-1, -1), .25, colors.HexColor('#d8e0e3')),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),
        ('ALIGN', (3, 1), (6, -1), 'CENTER'),
        ('ALIGN', (7, 1), (14, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef5f5')),
    ]))
    elements.append(table)
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_compras.pdf"'
    return response


@login_required
def compras_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    filtros, filas, resumen, _ = _compras_datos_exportacion(request)
    if filtros is None:
        return redirect('portal')

    wb = Workbook()
    ws = wb.active
    ws.title = 'Compras'
    ws.append([label for _, label in COMPRAS_COLUMNS])

    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='21333E')
        cell.alignment = Alignment(horizontal='center')

    for row in filas:
        ws.append(list(row))

    ws.append([])
    ws.append(['', '', '', '', '', '', 'RESUMEN'])
    ws.cell(ws.max_row, 8, resumen['bases_sin_iva'])
    ws.cell(ws.max_row, 9, resumen['bases_con_iva'])
    ws.cell(ws.max_row, 10, resumen['iva'])
    ws.cell(ws.max_row, 11, resumen['total'])
    ws.cell(ws.max_row, 12, resumen['retiva'])
    ws.cell(ws.max_row, 14, resumen['retrenta'])

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

    widths = [7, 38, 17, 10, 13, 25, 18, 16, 16, 13, 16, 14, 11, 16, 18]
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width

    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="reporte_compras.xlsx"'
    return response



FACTURA_TIPOS_IDENTIFICACION = [
    ('C', 'Cédula'),
    ('R', 'RUC'),
    ('P', 'Pasaporte'),
    ('E', 'Identificación del exterior'),
    ('F', 'Consumidor final'),
]

FACTURA_FORMAS_PAGO = [
    ('01', 'SIN UTILIZACION DEL SISTEMA FINANCIERO'),
    ('15', 'COMPENSACIÓN DE DEUDAS'),
    ('16', 'TARJETA DE DÉBITO'),
    ('17', 'DINERO ELECTRÓNICO'),
    ('18', 'TARJETA PREPAGO'),
    ('19', 'TARJETA DE CRÉDITO'),
    ('20', 'OTROS CON UTILIZACION DEL SISTEMA FINANCIERO'),
    ('21', 'ENDOSO DE TÍTULOS'),
]

FACTURA_PRODUCT_TABLES = (
    'productos',
    'productosservicios',
    'productos_servicios',
    'producto',
    'items',
    'inventario',
)


def _factura_contexto(cliente):
    establecimientos = []
    for establecimiento in (
        Establecimiento.objects
        .filter(cliente=cliente, activo=True)
        .prefetch_related('puntos_emision')
        .order_by('codigo')
    ):
        puntos = []
        for punto in establecimiento.puntos_emision.filter(activo=True).order_by('codigo'):
            sec = (
                SecuencialDocumento.objects
                .filter(
                    punto_emision=punto,
                    tipo_documento=SecuencialDocumento.TipoDocumento.FACTURA,
                    activo=True,
                )
                .first()
            )
            puntos.append({
                'id': punto.id,
                'codigo': punto.codigo,
                'nombre': punto.nombre,
                'secuencial': sec.secuencial_actual if sec else None,
                'secuencial_id': sec.id if sec else None,
            })
        establecimientos.append({
            'id': establecimiento.id,
            'codigo': establecimiento.codigo,
            'nombre': establecimiento.nombre,
            'direccion': establecimiento.direccion,
            'puntos': puntos,
        })

    return establecimientos


def _factura_buscar_cliente_datos(cliente, identificacion):
    identificacion = (identificacion or '').strip()
    if not identificacion:
        return None

    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(
            """
            SELECT
                TRIM(ruccedcli::text),
                TRIM(COALESCE(nomclient::text, '')),
                TRIM(COALESCE(dirclient::text, '')),
                TRIM(COALESCE(teldomcli::text, '')),
                TRIM(COALESCE(teloficli::text, '')),
                TRIM(COALESCE(telcelcli::text, '')),
                TRIM(COALESCE(corelectr::text, ''))
            FROM clientes
            WHERE TRIM(ruccedcli::text) = %s
            LIMIT 1
            """,
            [identificacion],
        )
        row = cursor.fetchone()

    if not row:
        return None

    ruc = row[0] or ''
    if len(ruc) == 13:
        tipo = 'R'
    elif len(ruc) == 10:
        tipo = 'C'
    else:
        tipo = 'P'

    telefono = next((value for value in row[3:6] if value), '')

    return {
        'identificacion': ruc,
        'tipo_identificacion': tipo,
        'razon_social': row[1] or '',
        'direccion': row[2] or '',
        'telefono': telefono,
        'email': row[6] or '',
    }


def _factura_producto_config(cursor):
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND lower(table_name) = ANY(%s)
        ORDER BY array_position(%s, lower(table_name))
        LIMIT 1
        """,
        [list(FACTURA_PRODUCT_TABLES), list(FACTURA_PRODUCT_TABLES)],
    )
    table_row = cursor.fetchone()
    if not table_row:
        return None

    table_name = table_row[0]
    cursor.execute(
        """
        SELECT lower(column_name)
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        """,
        [table_name],
    )
    columns = {row[0] for row in cursor.fetchall()}

    def pick(*names):
        for name in names:
            if name in columns:
                return name
        return None

    return {
        'table': table_name,
        'codigo': pick('codprod', 'codproducto', 'codigo_principal', 'codprincipal', 'codigo', 'codpro'),
        'descripcion': pick('nomprod', 'nomproducto', 'descripcion', 'descrip', 'detalle', 'nombre'),
        'precio': pick('pvp', 'precio', 'precio_unitario', 'valor', 'precio_venta'),
        'iva': pick('tarifaiva', 'poriva', 'iva', 'tarifa'),
    }


def _factura_buscar_productos_datos(cliente, termino):
    termino = (termino or '').strip()
    if not termino:
        return []

    with _cliente_db(cliente).cursor() as cursor:
        config = _factura_producto_config(cursor)
        if not config or not config['codigo'] or not config['descripcion']:
            return []

        table = '"' + config['table'].replace('"', '""') + '"'
        codigo = '"' + config['codigo'].replace('"', '""') + '"'
        descripcion = '"' + config['descripcion'].replace('"', '""') + '"'
        precio = (
            '"' + config['precio'].replace('"', '""') + '"'
            if config['precio'] else 'NULL'
        )
        iva = (
            '"' + config['iva'].replace('"', '""') + '"'
            if config['iva'] else 'NULL'
        )

        sql = f"""
            SELECT
                TRIM(COALESCE({codigo}::text, '')),
                TRIM(COALESCE({descripcion}::text, '')),
                {precio}::text,
                {iva}::text
            FROM {table}
            WHERE (
                {codigo}::text ILIKE %s
                OR {descripcion}::text ILIKE %s
            )
            ORDER BY {descripcion}::text
            LIMIT 20
        """
        like = f'%{termino}%'
        cursor.execute(sql, [like, like])
        rows = cursor.fetchall()

    result = []
    for row in rows:
        try:
            precio_valor = float(row[2]) if row[2] not in (None, '') else 0
        except (TypeError, ValueError):
            precio_valor = 0
        try:
            iva_valor = float(row[3]) if row[3] not in (None, '') else 0
        except (TypeError, ValueError):
            iva_valor = 0

        result.append({
            'codigo': row[0] or '',
            'descripcion': row[1] or '',
            'precio': precio_valor,
            'iva': iva_valor,
        })
    return result




@login_required
def nota_credito_emitir(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return redirect('portal')

    return render(
        request,
        'nota-credito-emitir.html',
        {
            'cliente': cliente,
            'establecimientos': _factura_contexto(cliente),
            'tipos_identificacion': FACTURA_TIPOS_IDENTIFICACION,
            'fecha_emision': datetime.now().strftime('%Y-%m-%d'),
        },
    )


@login_required
def nota_credito_buscar_sustento(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return JsonResponse({'ok': False, 'error': 'No autorizado.'}, status=403)

    numero = request.GET.get('numero', '').strip()
    if not numero:
        return JsonResponse({'ok': False, 'error': 'Ingrese el número del comprobante de sustento.'}, status=400)

    with _cliente_db(cliente).cursor() as cursor:
        cursor.execute(
            """
            SELECT
                TRIM(COALESCE(numfactur::text, '')),
                fecfactur,
                TRIM(COALESCE(ruccedcli::text, '')),
                TRIM(COALESCE(nomcli::text, '')),
                TRIM(COALESCE(autorizacion::text, ''))
            FROM ventas
            WHERE REPLACE(TRIM(COALESCE(numfactur::text, '')), '-', '') =
                  REPLACE(%s, '-', '')
               OR TRIM(COALESCE(numfactur::text, '')) = %s
            ORDER BY fecfactur DESC NULLS LAST
            LIMIT 1
            """,
            [numero, numero],
        )
        row = cursor.fetchone()

    if not row:
        return JsonResponse(
            {'ok': False, 'error': 'No se encontró la factura de sustento en la base de datos.'},
            status=404,
        )

    fecha = row[1].strftime('%Y-%m-%d') if row[1] else ''

    return JsonResponse({
        'ok': True,
        'sustento': {
            'numero': row[0] or '',
            'fecha': fecha,
            'identificacion': row[2] or '',
            'razon_social': row[3] or '',
            'autorizacion': row[4] or '',
        },
    })




@login_required
def retencion_emitir(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return redirect('portal')
    return render(request, 'retencion-emitir.html', {
        'cliente': cliente,
        'establecimientos': _factura_contexto(cliente),
        'tipos_identificacion': FACTURA_TIPOS_IDENTIFICACION,
        'fecha_emision': datetime.now().strftime('%Y-%m-%d'),
    })


@login_required
def liquidacion_compra_emitir(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return redirect('portal')
    return render(request, 'liquidacion-compra-emitir.html', {
        'cliente': cliente,
        'establecimientos': _factura_contexto(cliente),
        'tipos_identificacion': FACTURA_TIPOS_IDENTIFICACION,
        'formas_pago': FACTURA_FORMAS_PAGO,
        'fecha_emision': datetime.now().strftime('%Y-%m-%d'),
    })

@login_required
def guia_remision_emitir(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return redirect('portal')

    return render(
        request,
        'guia-remision-emitir.html',
        {
            'cliente': cliente,
            'establecimientos': _factura_contexto(cliente),
            'tipos_identificacion': FACTURA_TIPOS_IDENTIFICACION,
            'fecha_emision': datetime.now().strftime('%Y-%m-%d'),
        },
    )

@login_required
def factura_emitir(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return redirect('portal')

    return render(
        request,
        'factura-emitir.html',
        {
            'cliente': cliente,
            'establecimientos': _factura_contexto(cliente),
            'tipos_identificacion': FACTURA_TIPOS_IDENTIFICACION,
            'formas_pago': FACTURA_FORMAS_PAGO,
            'fecha_emision': datetime.now().strftime('%Y-%m-%d'),
        },
    )


@login_required
def factura_buscar_cliente(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return JsonResponse({'ok': False, 'error': 'No autorizado.'}, status=403)

    identificacion = request.GET.get('identificacion', '').strip()
    if not identificacion:
        return JsonResponse({'ok': False, 'error': 'Ingrese la identificación.'}, status=400)

    try:
        datos = _factura_buscar_cliente_datos(cliente, identificacion)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': f'No se pudo consultar el cliente: {exc}'}, status=500)

    if datos is None:
        return JsonResponse({'ok': False, 'error': 'No se encontró el cliente en la base de datos.'}, status=404)

    return JsonResponse({'ok': True, 'cliente': datos})


@login_required
def factura_buscar_productos(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return JsonResponse({'ok': False, 'error': 'No autorizado.'}, status=403)

    termino = request.GET.get('q', '').strip()
    if len(termino) < 1:
        return JsonResponse({'ok': True, 'productos': []})

    try:
        productos = _factura_buscar_productos_datos(cliente, termino)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': f'No se pudo consultar productos: {exc}'}, status=500)

    return JsonResponse({'ok': True, 'productos': productos})

def about(request):
    return render(request, 'about.html')


def contactanos(request):
    return render(request, 'contactanos.html')


def avisos_legales(request):
    return render(request, 'avisos-legales.html')


def servicios(request):
    raise Http404


def blog(request):
    raise Http404


def error_404(request, exception):
    return render(request, '404.html', status=404)


@staff_member_required
def template_catalog(request):
    """Catálogo interno para revisar las plantillas del tema antes de reutilizarlas."""
    return render(request, 'template-catalog.html', {'templates': TEMPLATE_PREVIEWS})


@staff_member_required
def template_preview(request, slug):
    """Renderiza una plantilla del catálogo usando el mismo sistema de templates de Django."""
    template_name = TEMPLATE_PREVIEWS.get(slug)
    if template_name is None:
        raise Http404
    return render(request, template_name, {'preview_mode': True, 'preview_slug': slug})
