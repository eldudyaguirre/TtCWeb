from functools import wraps
import mimetypes

from django.contrib import messages
from django.db import connection, connections
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from urllib.parse import urlencode
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.http import FileResponse, Http404
from django.contrib.auth.hashers import check_password, make_password

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
def admin_cambiar_contrasena(request):
    """Permite cambiar la contraseña del usuario administrativo en la tabla legacy seguridad."""
    usuario_sesion = request.session.get(ADMIN_USERNAME_KEY, '').strip()
    error = ''

    if request.method == 'POST':
        actual = request.POST.get('old_password', '')
        nueva = request.POST.get('new_password1', '')
        confirmacion = request.POST.get('new_password2', '')

        if not actual or not nueva or not confirmacion:
            error = 'Completa todos los campos.'
        elif len(nueva) < 8:
            error = 'La nueva contraseña debe tener al menos 8 caracteres.'
        elif nueva != confirmacion:
            error = 'La confirmación de la nueva contraseña no coincide.'
        else:
            with connection.cursor() as cursor:
                cursor.execute(
                    '''
                    SELECT conusuari
                    FROM seguridad
                    WHERE UPPER(TRIM(usrname::text)) = UPPER(TRIM(%s))
                    LIMIT 1
                    ''',
                    [usuario_sesion],
                )
                fila = cursor.fetchone()

            if not fila:
                error = 'No se encontró el usuario administrativo.'
            else:
                clave_actual = '' if fila[0] is None else str(fila[0])
                es_hash = clave_actual.startswith(
                    ('pbkdf2_', 'argon2', 'bcrypt', 'scrypt')
                )

                if es_hash:
                    try:
                        valido = check_password(actual, clave_actual)
                    except Exception:
                        valido = False
                else:
                    valido = actual == clave_actual

                if not valido:
                    error = 'La contraseña actual no es correcta.'
                elif nueva == actual:
                    error = 'La nueva contraseña debe ser diferente a la actual.'
                else:
                    nueva_guardada = make_password(nueva) if es_hash else nueva

                    with connection.cursor() as cursor:
                        cursor.execute(
                            '''
                            UPDATE seguridad
                            SET conusuari = %s
                            WHERE UPPER(TRIM(usrname::text)) = UPPER(TRIM(%s))
                            ''',
                            [nueva_guardada, usuario_sesion],
                        )

                    messages.success(
                        request,
                        'Tu contraseña fue actualizada correctamente.',
                    )
                    return redirect('admin_cambiar_contrasena')


    return render(
        request,
        'admin/cambiar_contrasena.html',
        {
            'admin_usuario': usuario_sesion,
            'admin_nombre': request.session.get(ADMIN_NAME_KEY, ''),
            'password_error': error,
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
def _admin_dashboard_saldos():
    """Obtiene los saldos globales que se muestran en el panel administrativo."""
    cuentas_por_cobrar = Cliente.objects.aggregate(total=__import__('django.db.models', fromlist=['Sum']).Sum('salcuenta'))['total'] or 0

    # Prefactura pertenece a la base maestra BDatos. Como su estructura legacy
    # puede variar, detectamos una columna monetaria conocida antes de sumar.
    saldo_prefacturas = 0
    try:
        candidatos = (
            'salprefactura', 'saldoprefactura', 'valprefactura',
            'valpre', 'valpref', 'valor', 'valtotal', 'total', 'saldo'
        )
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'prefactura'
                  AND data_type IN ('smallint','integer','bigint','numeric','decimal','real','double precision')
                ORDER BY ordinal_position
            """)
            columnas = {str(row[0]).lower(): str(row[0]) for row in cursor.fetchall()}

            columna = next((columnas[nombre] for nombre in candidatos if nombre in columnas), None)
            if columna:
                cursor.execute(
                    f'SELECT COALESCE(SUM("{columna}"), 0) FROM prefactura'
                )
                saldo_prefacturas = cursor.fetchone()[0] or 0
    except Exception:
        saldo_prefacturas = 0

    return {
        'cuentas_por_cobrar': cuentas_por_cobrar,
        'saldo_por_facturar': saldo_prefacturas,
    }


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

    # Solo mostramos páginas públicas reales del sitio. Las rutas técnicas,
    # administrativas, del portal y solicitudes de scanners quedan fuera.
    paginas_publicas = (
        '/',
        '/about/',
        '/contactanos/',
        '/avisos-legales/',
        '/servicios/',
        '/blog/',
    )
    paginas_mas_visitadas = (
        visitas_mes_qs
        .filter(pagina__in=paginas_publicas)
        .values('pagina')
        .annotate(total=Count('id'))
        .order_by('-total')[:8]
    )

    saldos = _admin_dashboard_saldos()

    context = {
        'clientes_total': clientes_qs.count(),
        'clientes_activos': clientes_qs.filter(activo=True).count(),
        'clientes_inactivos': clientes_qs.filter(activo=False).count(),
        'usuarios_clientes': UsuarioCliente.objects.filter(activo=True).count(),
        'cuentas_por_cobrar': saldos['cuentas_por_cobrar'],
        'saldo_por_facturar': saldos['saldo_por_facturar'],
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
def admin_contrasenas_editar(request, ruc):
    """Edita únicamente las credenciales del cliente desde el módulo Contraseñas."""
    cliente = get_object_or_404(Cliente, pk=ruc)

    if request.method != 'POST':
        return redirect('admin_contrasenas')

    campos = (
        'clavesri',
        'cediess',
        'claveiess',
        'mrlcon',
        'mrlsal',
        'clavesuper',
        'iessdomestica',
    )

    for campo in campos:
        setattr(cliente, campo, request.POST.get(campo, '').strip())

    tipdec = request.POST.get('tipdec', '').strip().upper()
    if tipdec in ('MENSUAL', 'SEMESTRAL', 'ANUAL'):
        # El campo existente en el modelo es semensual (TipDec).
        cliente.semensual = tipdec

    campos_guardar = list(campos)
    if tipdec in ('MENSUAL', 'SEMESTRAL', 'ANUAL'):
        campos_guardar.append('semensual')

    cliente.save(update_fields=campos_guardar)

    messages.success(
        request,
        f'Las contraseñas de {cliente.nomclient} fueron actualizadas correctamente.',
    )

    query = request.POST.get('q', '').strip()
    url = redirect('admin_contrasenas')
    if query:
        url['Location'] += '?' + urlencode({'q': query})
    return url


@admin_required
def admin_contrasenas_toggle_activo(request, ruc):
    """Activa o desactiva un cliente desde el módulo Contraseñas."""
    cliente = get_object_or_404(Cliente, pk=ruc)

    if request.method != 'POST':
        return redirect('admin_contrasenas')

    cliente.activo = not bool(cliente.activo)
    cliente.save(update_fields=['activo'])

    estado = 'activado' if cliente.activo else 'desactivado'
    messages.success(request, f'El cliente {cliente.nomclient} fue {estado} correctamente.')

    query = request.POST.get('q', '').strip()
    url = redirect('admin_contrasenas')
    if query:
        url['Location'] += f'?q={query}'
    return url


@admin_required
def admin_clientes(request):
    query = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()
    dia = request.GET.get('dia', 'todos').strip() or 'todos'
    tipdec = request.GET.get('tipdec', '').strip()

    clientes = Cliente.objects.all().order_by('nomclient')

    if query:
        from django.db.models import Q
        clientes = clientes.filter(
            Q(nomclient__icontains=query) |
            Q(ruccedcli__icontains=query)
        )

    if estado == 'activos':
        clientes = clientes.filter(activo=True)
    elif estado == 'inactivos':
        clientes = clientes.filter(activo=False)

    if dia != 'todos':
        clientes = clientes.filter(diadeclaracion=dia)

    if tipdec:
        clientes = clientes.filter(tipdec__iexact=tipdec)

    dias = (10, 12, 14, 16, 18, 20, 22, 24, 26, 28)
    tipos_dec = ('MENSUAL', 'SEMESTRAL', 'ANUAL')

    return render(
        request,
        'admin/clientes.html',
        {
            'clientes': clientes,
            'query': query,
            'estado': estado,
            'dia': dia,
            'tipdec': tipdec,
            'dias': dias,
            'tipos_dec': tipos_dec,
        },
    )


@admin_required
def admin_contrasenas(request):
    """Listado administrativo de clientes activos y sus credenciales tributarias/laborales."""
    query = request.GET.get('q', '').strip()
    dia = request.GET.get('dia', 'todos').strip() or 'todos'
    tipdec = request.GET.get('tipdec', '').strip()

    # Al entrar se muestran únicamente clientes activos.
    # Cuando se realiza una búsqueda, se consulta toda la base de datos,
    # incluyendo clientes inactivos.
    clientes_qs = Cliente.objects.filter(activo=True)

    if query:
        from django.db.models import Q
        clientes_qs = Cliente.objects.all().filter(
            Q(nomclient__icontains=query) |
            Q(ruccedcli__icontains=query)
        )

    if dia != 'todos':
        clientes_qs = clientes_qs.filter(diadeclaracion=str(dia))

    if tipdec:
        clientes_qs = clientes_qs.filter(semensual__iexact=tipdec)

    clientes_qs = clientes_qs.order_by('nomclient')

    dias = (10, 12, 14, 16, 18, 20, 22, 24, 26, 28)
    tipos_dec = ('MENSUAL', 'SEMESTRAL', 'ANUAL')

    return render(
        request,
        'admin/contrasenas.html',
        {
            'clientes': clientes_qs,
            'pestanas': [
                {
                    'dia': dia_item,
                    'clientes': clientes_qs.filter(diadeclaracion=str(dia_item)),
                }
                for dia_item in dias
            ],
            'clientes_busqueda': clientes_qs if query else Cliente.objects.none(),
            'query': query,
            'dia': dia,
            'tipdec': tipdec,
            'dias': dias,
            'tipos_dec': tipos_dec,
            'admin_nombre': request.session.get(ADMIN_NAME_KEY, ''),
            'admin_usuario': request.session.get(ADMIN_USERNAME_KEY, ''),
        },
    )


def _admin_conciliacion_cliente(cliente, anio=None):
    """Obtiene la conciliación mensual de ventas, compras y retenciones del cliente."""
    db_name = str(cliente.ruccedcli).strip()
    alias = f'cliente_{db_name}'
    if alias not in connections.databases:
        base = settings.DATABASES['default'].copy()
        base['NAME'] = db_name
        connections.databases[alias] = base

    db = connections[alias]

    with db.cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT anio FROM (
                SELECT EXTRACT(YEAR FROM (
                    CASE
                        WHEN TRIM(fecfactur::text) ~ '^\\d{1,2}/\\d{1,2}/\\d{4}'
                            THEN CASE WHEN SPLIT_PART(TRIM(fecfactur::text), '/', 1)::integer > 12 THEN TO_DATE(SUBSTRING(TRIM(fecfactur::text) FROM 1 FOR 10), 'DD/MM/YYYY') ELSE TO_DATE(SUBSTRING(TRIM(fecfactur::text) FROM 1 FOR 10), 'MM/DD/YYYY') END
                        WHEN TRIM(fecfactur::text) ~ '^\\d{4}-\\d{1,2}-\\d{1,2}'
                            THEN TO_DATE(SUBSTRING(TRIM(fecfactur::text) FROM 1 FOR 10), 'YYYY-MM-DD')
                        ELSE NULL
                    END
                ))::integer AS anio FROM ventas
                UNION
                SELECT EXTRACT(YEAR FROM (
                    CASE
                        WHEN TRIM(fecemi::text) ~ '^\\d{1,2}/\\d{1,2}/\\d{4}'
                            THEN CASE WHEN SPLIT_PART(TRIM(fecemi::text), '/', 1)::integer > 12 THEN TO_DATE(SUBSTRING(TRIM(fecemi::text) FROM 1 FOR 10), 'DD/MM/YYYY') ELSE TO_DATE(SUBSTRING(TRIM(fecemi::text) FROM 1 FOR 10), 'MM/DD/YYYY') END
                        WHEN TRIM(fecemi::text) ~ '^\\d{4}-\\d{1,2}-\\d{1,2}'
                            THEN TO_DATE(SUBSTRING(TRIM(fecemi::text) FROM 1 FOR 10), 'YYYY-MM-DD')
                        ELSE NULL
                    END
                ))::integer AS anio FROM comprasnue
            ) periodos
            WHERE anio IS NOT NULL
            ORDER BY anio DESC
        """)
        anios = [int(row[0]) for row in cursor.fetchall()]

    if not anios:
        return {'anio': anio or 0, 'anios': [], 'meses': [], 'totales': {'ventas': 0, 'compras': 0, 'retrenta': 0, 'retiva': 0}}

    try:
        anio = int(anio)
    except (TypeError, ValueError):
        anio = anios[0]
    if anio not in anios:
        anio = anios[0]

    with db.cursor() as cursor:
        cursor.execute("""
            WITH meses AS (
                SELECT generate_series(1, 12) AS mes
            ),
            ventas_mes AS (
                SELECT EXTRACT(MONTH FROM (CASE WHEN TRIM(fecfactur::text) ~ '^\\d{1,2}/\\d{1,2}/\\d{4}' THEN CASE WHEN SPLIT_PART(TRIM(fecfactur::text), '/', 1)::integer > 12 THEN TO_DATE(SUBSTRING(TRIM(fecfactur::text) FROM 1 FOR 10), 'DD/MM/YYYY') ELSE TO_DATE(SUBSTRING(TRIM(fecfactur::text) FROM 1 FOR 10), 'MM/DD/YYYY') END WHEN TRIM(fecfactur::text) ~ '^\\d{4}-\\d{1,2}-\\d{1,2}' THEN TO_DATE(SUBSTRING(TRIM(fecfactur::text) FROM 1 FOR 10), 'YYYY-MM-DD') ELSE NULL END))::integer AS mes,
                       COALESCE(SUM(
                           COALESCE(NULLIF(basenoobj::text, ''), '0')::numeric +
                           COALESCE(NULLIF(baseiva0::text, ''), '0')::numeric +
                           COALESCE(NULLIF(baseiva12::text, ''), '0')::numeric
                       ), 0) AS ventas,
                       COALESCE(SUM(COALESCE(NULLIF(retrenta::text, ''), '0')::numeric), 0) AS retrenta,
                       COALESCE(SUM(COALESCE(NULLIF(retiva::text, ''), '0')::numeric), 0) AS retiva
                FROM ventas
                WHERE EXTRACT(YEAR FROM (CASE WHEN TRIM(fecfactur::text) ~ '^\\d{1,2}/\\d{1,2}/\\d{4}' THEN CASE WHEN SPLIT_PART(TRIM(fecfactur::text), '/', 1)::integer > 12 THEN TO_DATE(SUBSTRING(TRIM(fecfactur::text) FROM 1 FOR 10), 'DD/MM/YYYY') ELSE TO_DATE(SUBSTRING(TRIM(fecfactur::text) FROM 1 FOR 10), 'MM/DD/YYYY') END WHEN TRIM(fecfactur::text) ~ '^\\d{4}-\\d{1,2}-\\d{1,2}' THEN TO_DATE(SUBSTRING(TRIM(fecfactur::text) FROM 1 FOR 10), 'YYYY-MM-DD') ELSE NULL END))::integer = %s
                GROUP BY 1
            ),
            compras_mes AS (
                SELECT EXTRACT(MONTH FROM (CASE WHEN TRIM(fecemi::text) ~ '^\\d{1,2}/\\d{1,2}/\\d{4}' THEN CASE WHEN SPLIT_PART(TRIM(fecemi::text), '/', 1)::integer > 12 THEN TO_DATE(SUBSTRING(TRIM(fecemi::text) FROM 1 FOR 10), 'DD/MM/YYYY') ELSE TO_DATE(SUBSTRING(TRIM(fecemi::text) FROM 1 FOR 10), 'MM/DD/YYYY') END WHEN TRIM(fecemi::text) ~ '^\\d{4}-\\d{1,2}-\\d{1,2}' THEN TO_DATE(SUBSTRING(TRIM(fecemi::text) FROM 1 FOR 10), 'YYYY-MM-DD') ELSE NULL END))::integer AS mes,
                       COALESCE(SUM(
                           COALESCE(NULLIF(baseimpnoobj::text, ''), '0')::numeric +
                           COALESCE(NULLIF(baseimpiva0::text, ''), '0')::numeric +
                           COALESCE(NULLIF(baseexenta::text, ''), '0')::numeric +
                           COALESCE(NULLIF(baseimpiva5::text, ''), '0')::numeric +
                           COALESCE(NULLIF(baseimpiva8::text, ''), '0')::numeric +
                           COALESCE(NULLIF(baseimpiva12::text, ''), '0')::numeric +
                           COALESCE(NULLIF(baseimpiva14::text, ''), '0')::numeric +
                           COALESCE(NULLIF(baseimpiva15::text, ''), '0')::numeric +
                           COALESCE(NULLIF(montoiva8::text, ''), '0')::numeric +
                           COALESCE(NULLIF(montoiva12::text, ''), '0')::numeric +
                           COALESCE(NULLIF(montoiva14::text, ''), '0')::numeric +
                           COALESCE(NULLIF(montoiva15::text, ''), '0')::numeric
                       ), 0) AS compras
                FROM comprasnue
                WHERE TRIM(tipcom::text) IN ('01', '02')
                  AND EXTRACT(YEAR FROM (CASE WHEN TRIM(fecemi::text) ~ '^\\d{1,2}/\\d{1,2}/\\d{4}' THEN CASE WHEN SPLIT_PART(TRIM(fecemi::text), '/', 1)::integer > 12 THEN TO_DATE(SUBSTRING(TRIM(fecemi::text) FROM 1 FOR 10), 'DD/MM/YYYY') ELSE TO_DATE(SUBSTRING(TRIM(fecemi::text) FROM 1 FOR 10), 'MM/DD/YYYY') END WHEN TRIM(fecemi::text) ~ '^\\d{4}-\\d{1,2}-\\d{1,2}' THEN TO_DATE(SUBSTRING(TRIM(fecemi::text) FROM 1 FOR 10), 'YYYY-MM-DD') ELSE NULL END))::integer = %s
                GROUP BY 1
            )
            SELECT m.mes,
                   COALESCE(v.ventas, 0),
                   COALESCE(c.compras, 0),
                   COALESCE(v.retrenta, 0),
                   COALESCE(v.retiva, 0)
            FROM meses m
            LEFT JOIN ventas_mes v ON v.mes = m.mes
            LEFT JOIN compras_mes c ON c.mes = m.mes
            ORDER BY m.mes
        """, [anio, anio])
        rows = cursor.fetchall()

    nombres = ['ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO','JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE']
    meses = []
    for mes, ventas, compras, retrenta, retiva in rows:
        meses.append({
            'nombre': nombres[int(mes) - 1],
            'ventas': ventas or 0,
            'compras': compras or 0,
            'retrenta': retrenta or 0,
            'retiva': retiva or 0,
        })

    totales = {campo: sum((m[campo] for m in meses), 0) for campo in ('ventas','compras','retrenta','retiva')}
    totales['resultado'] = totales['ventas'] - totales['compras']
    totales['retenciones'] = totales['retrenta'] + totales['retiva']
    return {'anio': anio, 'anios': anios, 'meses': meses, 'totales': totales}


def admin_cliente(request, ruc):
    cliente = get_object_or_404(Cliente, pk=ruc)

    if request.method == 'POST' and request.POST.get('accion') == 'guardar_datos_cliente':
        cliente.dirclient = request.POST.get('dirclient', '').strip()
        cliente.teldomcli = request.POST.get('teldomcli', '').strip()
        cliente.teloficli = request.POST.get('teloficli', '').strip()
        cliente.telcelcli = request.POST.get('telcelcli', '').strip()
        cliente.corelectr = request.POST.get('corelectr', '').strip()
        cliente.ocuclient = request.POST.get('ocuclient', '').strip()
        cliente.save(update_fields=[
            'dirclient', 'teldomcli', 'teloficli',
            'telcelcli', 'corelectr', 'ocuclient',
        ])
        messages.success(request, 'Datos básicos del cliente actualizados correctamente.')
        return redirect('admin_cliente', ruc=cliente.ruccedcli)

    usuarios = (
        UsuarioCliente.objects
        .filter(cliente=cliente)
        .select_related('usuario')
        .order_by('usuario__username')
    )

    db_name = str(cliente.ruccedcli).strip()
    db_status = 'No verificada'
    db_error = ''
    conciliacion = {
        'anio': 0,
        'anios': [],
        'meses': [],
        'totales': {
            'ventas': 0,
            'compras': 0,
            'retrenta': 0,
            'retiva': 0,
            'resultado': 0,
            'retenciones': 0,
        },
    }

    # La conexión y la consulta de conciliación se manejan por separado.
    # Un error en una consulta no debe hacer aparecer la base como desconectada.
    try:
        alias = f'cliente_{db_name}'
        if alias not in connections.databases:
            base = settings.DATABASES['default'].copy()
            base['NAME'] = db_name
            connections.databases[alias] = base
        client_connection = connections[alias]
        client_connection.ensure_connection()
        db_status = 'Conectada'
    except Exception as exc:
        db_status = 'No disponible'
        db_error = str(exc)

    if db_status == 'Conectada':
        try:
            conciliacion = _admin_conciliacion_cliente(cliente, request.GET.get('anio'))
        except Exception as exc:
            db_error = f'Error consultando datos: {exc}'

    return render(
        request,
        'admin/cliente.html',
        {
            'cliente': cliente,
            'usuarios': usuarios,
            'db_name': db_name,
            'db_status': db_status,
            'db_error': db_error,
            'conciliacion': conciliacion,
        },
    )
