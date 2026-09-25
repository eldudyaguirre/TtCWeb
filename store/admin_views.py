from functools import wraps
import mimetypes

from django.contrib import messages
from django.db import connection, connections
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.http import FileResponse, Http404
from django.contrib.auth.hashers import check_password

from .models import AdminPerfil, Cliente, UsuarioCliente, VisitaWeb


ADMIN_SESSION_KEY = 'admin_portal'
ADMIN_USERNAME_KEY = 'admin_username'
ADMIN_NAME_KEY = 'admin_name'


def admin_required(view_func):
    """Protege las vistas del portal administrativo con la sesión propia de TotalCounts."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.session.get(ADMIN_SESSION_KEY):
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    return wrapped


def _admin_required(request):
    return request.session.get(ADMIN_SESSION_KEY, False)


def admin_login(request):
    if request.session.get(ADMIN_SESSION_KEY):
        return redirect('admin_dashboard')

    error = ''
    username = ''

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            error = 'Ingresa el usuario y la contraseña.'
        else:
            with connection.cursor() as cursor:
                cursor.execute(
                    '''
                    SELECT usrname, nomusuari, conusuari
                    FROM seguridad
                    WHERE UPPER(TRIM(usrname::text)) = UPPER(TRIM(%s))
                    LIMIT 1
                    ''',
                    [username],
                )
                usuario = cursor.fetchone()

            if usuario:
                usuario_db, nombre_db, clave_db = usuario
                clave_db = '' if clave_db is None else str(clave_db)
                valido = False

                # Soporta tanto las claves heredadas almacenadas como texto
                # como hashes Django, si en el futuro se migran.
                if clave_db.startswith(('pbkdf2_', 'argon2$', 'bcrypt$', 'scrypt$')):
                    try:
                        valido = check_password(password, clave_db)
                    except Exception:
                        valido = False
                else:
                    valido = password == clave_db

                if valido:
                    request.session[ADMIN_SESSION_KEY] = True
                    request.session[ADMIN_USERNAME_KEY] = str(usuario_db).strip()
                    request.session[ADMIN_NAME_KEY] = str(nombre_db or usuario_db).strip()
                    request.session.set_expiry(1800)
                    return redirect('admin_dashboard')

            error = 'Usuario o contraseña inválidos.'

    return render(
        request,
        'admin/login.html',
        {
            'error': error,
            'username': username,
        },
    )


def admin_logout(request):
    request.session.pop(ADMIN_SESSION_KEY, None)
    request.session.pop(ADMIN_USERNAME_KEY, None)
    request.session.pop(ADMIN_NAME_KEY, None)
    return redirect('admin_login')


@admin_required
def admin_datos_usuario(request):
    """Muestra y permite editar los datos del usuario administrativo autenticado."""
    usuario = request.session.get(ADMIN_USERNAME_KEY, '').strip()
    nombre_sesion = request.session.get(ADMIN_NAME_KEY, '').strip()

    perfil, _ = AdminPerfil.objects.get_or_create(
        usuario=usuario,
        defaults={'nombres': nombre_sesion},
    )

    if request.method == 'POST':
        perfil.nombres = request.POST.get('nombres', '').strip()
        perfil.direccion = request.POST.get('direccion', '').strip()
        perfil.telefono = request.POST.get('telefono', '').strip()
        perfil.email = request.POST.get('email', '').strip()

        fecha_nacimiento = request.POST.get('fecha_nacimiento', '').strip()
        perfil.fecha_nacimiento = fecha_nacimiento or None

        nueva_foto = request.FILES.get('foto')
        if nueva_foto:
            perfil.foto = nueva_foto

        perfil.save()

        # Mantiene el nombre mostrado en la barra superior sincronizado
        # con el nombre guardado en el perfil.
        request.session[ADMIN_NAME_KEY] = perfil.nombres or usuario

        messages.success(request, 'Datos de usuario actualizados correctamente.')
        return redirect('admin_datos_usuario')

    return render(
        request,
        'admin/datos_usuario.html',
        {
            'admin_usuario': usuario,
            'admin_nombre': perfil.nombres or nombre_sesion,
            'perfil': perfil,
        },
    )


@admin_required
def admin_foto_usuario(request):
    """Entrega la foto del perfil administrativo autenticado."""
    usuario = request.session.get(ADMIN_USERNAME_KEY, '').strip()
    perfil = AdminPerfil.objects.filter(usuario=usuario).first()

    if not perfil or not perfil.foto:
        raise Http404

    try:
        return FileResponse(
            perfil.foto.open('rb'),
            content_type=mimetypes.guess_type(perfil.foto.name)[0] or 'application/octet-stream',
        )
    except FileNotFoundError:
        raise Http404


@admin_required
def admin_dashboard(request):
    clientes_qs = Cliente.objects.all()
    clientes = clientes_qs.order_by('nomclient')[:12]

    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    inicio_mes_anterior = (inicio_mes - timedelta(days=1)).replace(day=1)

    visitas_hoy_qs = VisitaWeb.objects.filter(fecha_hora__date=hoy)
    visitas_mes_qs = VisitaWeb.objects.filter(fecha_hora__date__gte=inicio_mes)
    visitas_mes_anterior_qs = VisitaWeb.objects.filter(
        fecha_hora__date__gte=inicio_mes_anterior,
        fecha_hora__date__lt=inicio_mes,
    )

    inicio_grafica = hoy - timedelta(days=6)
    visitas_grafica = (
        VisitaWeb.objects
        .filter(fecha_hora__date__gte=inicio_grafica, fecha_hora__date__lte=hoy)
        .annotate(dia=TruncDate('fecha_hora'))
        .values('dia')
        .annotate(total=Count('id'))
        .order_by('dia')
    )
    visitas_por_dia = {item['dia']: item['total'] for item in visitas_grafica}

    grafica_visitas = [
        {
            'fecha': inicio_grafica + timedelta(days=i),
            'total': visitas_por_dia.get(inicio_grafica + timedelta(days=i), 0),
        }
        for i in range(7)
    ]

    paginas_mas_visitadas = (
        visitas_mes_qs
        .values('pagina')
        .annotate(total=Count('id'))
        .order_by('-total')[:8]
    )

    context = {
        'clientes_total': clientes_qs.count(),
        'clientes_activos': clientes_qs.filter(activo=True).count(),
        'clientes_inactivos': clientes_qs.filter(activo=False).count(),
        'usuarios_clientes': UsuarioCliente.objects.filter(activo=True).count(),
        'clientes': clientes,
        'admin_nombre': request.session.get(ADMIN_NAME_KEY, ''),
        'admin_usuario': request.session.get(ADMIN_USERNAME_KEY, ''),
        'visitas_hoy': visitas_hoy_qs.count(),
        'visitantes_hoy': visitas_hoy_qs.values('visitor_id').distinct().count(),
        'visitas_mes': visitas_mes_qs.count(),
        'visitas_mes_anterior': visitas_mes_anterior_qs.count(),
        'grafica_visitas': grafica_visitas,
        'paginas_mas_visitadas': paginas_mas_visitadas,
    }
    return render(request, 'admin/dashboard.html', context)


@admin_required
def admin_clientes(request):
    query = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()

    clientes = Cliente.objects.all().order_by('nomclient')

    if query:
        clientes = clientes.filter(
            nomclient__icontains=query
        ) | clientes.filter(
            ruccedcli__icontains=query
        )

    if estado == 'activos':
        clientes = clientes.filter(activo=True)
    elif estado == 'inactivos':
        clientes = clientes.filter(activo=False)

    return render(
        request,
        'admin/clientes.html',
        {
            'clientes': clientes,
            'query': query,
            'estado': estado,
        },
    )


@admin_required
def admin_cliente(request, ruc):
    cliente = get_object_or_404(Cliente, pk=ruc)
    usuarios = (
        UsuarioCliente.objects
        .filter(cliente=cliente)
        .select_related('usuario')
        .order_by('usuario__username')
    )

    db_name = str(cliente.ruccedcli).strip()
    db_status = 'No verificada'

    try:
        alias = f'cliente_{db_name}'
        if alias not in connections.databases:
            base = settings.DATABASES['default'].copy()
            base['NAME'] = db_name
            connections.databases[alias] = base
        client_connection = connections[alias]
        client_connection.ensure_connection()
        db_status = 'Conectada'
    except Exception:
        db_status = 'No disponible'

    return render(
        request,
        'admin/cliente.html',
        {
            'cliente': cliente,
            'usuarios': usuarios,
            'db_name': db_name,
            'db_status': db_status,
        },
    )
