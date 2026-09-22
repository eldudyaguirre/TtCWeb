from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import redirect, render

from .models import (
    Establecimiento,
    ParametrosCliente,
    PuntoEmision,
    SecuencialDocumento,
    UsuarioCliente,
)
from .services.acceso import obtener_resumen_cliente, validar_acceso_cliente


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
        return redirect('home')

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

                        archivo_anterior = parametros_cliente.certificado_p12.name
                        parametros_cliente.certificado_p12 = archivo
                        parametros_cliente.certificado_nombre = archivo.name
                        parametros_cliente.save()
                        if archivo_anterior and archivo_anterior != parametros_cliente.certificado_p12.name:
                            parametros_cliente.certificado_p12.storage.delete(archivo_anterior)
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

    return render(
        request,
        'cambiar-contrasena.html',
        {'form': form},
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
                },
            )

    logout(request)
    messages.error(
        request,
        'El acceso al portal está restringido. Verifica el estado de tu cuenta.',
    )
    return redirect('signin')


def about(request):
    return render(request, 'about.html')


def contactanos(request):
    return render(request, 'contactanos.html')


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
