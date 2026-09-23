from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
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
                # Los usuarios administrativos de Django mantienen acceso al portal.
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
    ('fecha', 'Fecha'),
    ('ruc', 'RUC proveedor'),
    ('proveedor', 'Proveedor'),
    ('comprobante', 'Comprobante'),
    ('autorizacion', 'Autorización'),
    ('subtotal0', 'Subtotal 0%'),
    ('subtotal5', 'Subtotal 5%'),
    ('subtotal8', 'Subtotal 8%'),
    ('subtotal12', 'Subtotal 12%'),
    ('subtotal14', 'Subtotal 14%'),
    ('subtotal15', 'Subtotal 15%'),
    ('iva5', 'IVA 5%'),
    ('iva8', 'IVA 8%'),
    ('iva12', 'IVA 12%'),
    ('iva14', 'IVA 14%'),
    ('iva15', 'IVA 15%'),
    ('total', 'Total'),
]

COMPRAS_NUMERIC = [
    'subtotal0', 'subtotal5', 'subtotal8', 'subtotal12', 'subtotal14',
    'subtotal15', 'iva5', 'iva8', 'iva12', 'iva14', 'iva15', 'total',
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


def _compras_where(request):
    cliente = _cliente_portal(request)
    if cliente is None:
        return None, [], None

    where = [
        "tipcom IN ('01', '02')",
        "ruccedprovee IS NOT NULL",
        "TRIM(ruccedprovee) <> ''",
    ]
    params = []

    # La fecha almacenada en la base histórica se maneja como DD/MM/YYYY.
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    proveedor = request.GET.get('proveedor', '').strip()

    if fecha_desde:
        try:
            datetime.strptime(fecha_desde, '%Y-%m-%d')
            where.append("CASE WHEN NULLIF(TRIM(fecemi::text), '') ~ '^\\d{4}-\\d{2}-\\d{2}' THEN fecemi::date ELSE to_date(NULLIF(TRIM(fecemi::text), ''), 'DD/MM/YYYY') END >= %s::date")
            params.append(fecha_desde)
        except ValueError:
            fecha_desde = ''

    if fecha_hasta:
        try:
            datetime.strptime(fecha_hasta, '%Y-%m-%d')
            where.append("CASE WHEN NULLIF(TRIM(fecemi::text), '') ~ '^\\d{4}-\\d{2}-\\d{2}' THEN fecemi::date ELSE to_date(NULLIF(TRIM(fecemi::text), ''), 'DD/MM/YYYY') END <= %s::date")
            params.append(fecha_hasta)
        except ValueError:
            fecha_hasta = ''

    if proveedor:
        where.append("(ruccedprovee ILIKE %s OR nomprovee ILIKE %s)")
        params.extend([f'%{proveedor}%', f'%{proveedor}%'])

    # El cliente se identifica por RUC del proveedor/comprobante en la tabla.
    # Si la tabla está separada por base de datos, no se requiere filtro adicional.
    return " AND ".join(where), params, {
        'cliente': cliente,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'proveedor': proveedor,
    }


def _compras_query(where, params, limit=None, offset=None):
    sql = f"""
        SELECT
            fecemi,
            ruccedprovee,
            nomprovee,
            CONCAT_WS('-', NULLIF(TRIM(numest::text), ''), NULLIF(TRIM(numptoemi::text), ''), NULLIF(TRIM(numsec::text), '')) AS comprobante,
            numaut,
            COALESCE(baseimpiva0, 0),
            COALESCE(baseimpiva5, 0),
            COALESCE(baseimpiva8, 0),
            COALESCE(baseimpiva12, 0),
            COALESCE(baseimpiva14, 0),
            COALESCE(baseimpiva15, 0),
            COALESCE(montoiva5, 0),
            COALESCE(montoiva8, 0),
            COALESCE(montoiva12, 0),
            COALESCE(montoiva14, 0),
            COALESCE(montoiva15, 0),
            COALESCE(totbases, 0)
                + COALESCE(montoiva5, 0)
                + COALESCE(montoiva8, 0)
                + COALESCE(montoiva12, 0)
                + COALESCE(montoiva14, 0)
                + COALESCE(montoiva15, 0)
        FROM compras
        WHERE {where}
        ORDER BY CASE WHEN NULLIF(TRIM(fecemi::text), '') ~ '^\\d{4}-\\d{2}-\\d{2}' THEN fecemi::date ELSE to_date(NULLIF(TRIM(fecemi::text), ''), 'DD/MM/YYYY') END DESC
    """
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params = [*params, limit, offset or 0]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _compras_resumen(where, params):
    sql = f"""
        SELECT
            COALESCE(SUM(baseimpiva0), 0),
            COALESCE(SUM(baseimpiva5), 0),
            COALESCE(SUM(baseimpiva8), 0),
            COALESCE(SUM(baseimpiva12), 0),
            COALESCE(SUM(baseimpiva14), 0),
            COALESCE(SUM(baseimpiva15), 0),
            COALESCE(SUM(montoiva5), 0),
            COALESCE(SUM(montoiva8), 0),
            COALESCE(SUM(montoiva12), 0),
            COALESCE(SUM(montoiva14), 0),
            COALESCE(SUM(montoiva15), 0),
            COALESCE(SUM(totbases), 0)
                + COALESCE(SUM(montoiva5), 0)
                + COALESCE(SUM(montoiva8), 0)
                + COALESCE(SUM(montoiva12), 0)
                + COALESCE(SUM(montoiva14), 0)
                + COALESCE(SUM(montoiva15), 0)
        FROM compras
        WHERE {where}
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return dict(zip(
        ['subtotal0','subtotal5','subtotal8','subtotal12','subtotal14','subtotal15',
         'iva5','iva8','iva12','iva14','iva15','total'],
        [float(value or 0) for value in row],
    ))


def _compras_datos_exportacion(request):
    where, params, filtros = _compras_where(request)
    if where is None:
        return None, [], None, None
    filas = _compras_query(where, params)
    resumen = _compras_resumen(where, params)
    return filtros, filas, resumen, where


@login_required
def compras(request):
    filtros, filas, resumen, _ = _compras_datos_exportacion(request)
    if filtros is None:
        return redirect('portal')

    # Mostrar 50 registros por página.
    try:
        pagina = max(1, int(request.GET.get('pagina', '1')))
    except ValueError:
        pagina = 1
    por_pagina = 50
    total_registros = 0

    where, params, _ = _compras_where(request)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM compras WHERE {where}", params)
        total_registros = cursor.fetchone()[0]

    offset = (pagina - 1) * por_pagina
    filas = _compras_query(where, params, por_pagina, offset)
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
    elements = [
        Paragraph('Reporte de Compras', styles['Title']),
        Paragraph(f"Proveedor: {filtros['proveedor'] or 'Todos'} | Desde: {filtros['fecha_desde'] or '—'} | Hasta: {filtros['fecha_hasta'] or '—'}", styles['Normal']),
        Spacer(1, 10),
    ]

    headers = [label for _, label in COMPRAS_COLUMNS]
    data = [headers]
    for row in filas:
        values = list(row[:5]) + [float(x or 0) for x in row[5:]]
        data.append(values)

    data.append(['', '', '', '', 'RESUMEN'] + [
        resumen[k] for k in ['subtotal0','subtotal5','subtotal8','subtotal12','subtotal14','subtotal15','iva5','iva8','iva12','iva14','iva15','total']
    ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#21333e')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), .25, colors.HexColor('#d8e0e3')),
        ('ALIGN', (5,1), (-1,-1), 'RIGHT'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#eef5f5')),
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
        values = list(row[:5]) + [float(x or 0) for x in row[5:]]
        ws.append(values)

    ws.append([])
    ws.append(['', '', '', '', 'RESUMEN'])
    for key, label in COMPRAS_COLUMNS[5:]:
        if key in resumen:
            ws.cell(ws.max_row, COMPRAS_COLUMNS.index((key, label)) + 1, resumen[key])
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    widths = [13, 16, 42, 18, 28, 14, 14, 14, 14, 14, 14, 12, 12, 12, 12, 12, 14]
    for i, width in enumerate(widths, 1):
        ws.column_dimensions[chr(64+i) if i <= 26 else 'A'].width = width

    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="reporte_compras.xlsx"'
    return response


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
