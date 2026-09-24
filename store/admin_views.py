from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.db import connections
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings

from .models import Cliente, UsuarioCliente


def _admin_required(request):
    if not request.user.is_authenticated:
        return None
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied
    return request.user


def admin_login(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('admin_dashboard')
        messages.error(request, 'Este acceso es exclusivo para administración de TotalCounts.')
        return redirect('signin')

    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )

            if user is not None and (user.is_staff or user.is_superuser):
                login(request, user)
                request.session['admin_portal'] = True
                return redirect('admin_dashboard')

            messages.error(
                request,
                'El usuario o la contraseña no son válidos para el portal administrativo.',
            )
        else:
            messages.error(request, 'Usuario o contraseña inválidos.')

    return render(request, 'admin/login.html', {'login_form': form})


@login_required
def admin_dashboard(request):
    _admin_required(request)

    clientes_qs = Cliente.objects.all()
    clientes = clientes_qs.order_by('nomclient')[:12]

    context = {
        'clientes_total': clientes_qs.count(),
        'clientes_activos': clientes_qs.filter(activo=True).count(),
        'clientes_inactivos': clientes_qs.filter(activo=False).count(),
        'usuarios_clientes': UsuarioCliente.objects.filter(activo=True).count(),
        'clientes': clientes,
    }
    return render(request, 'admin/dashboard.html', context)


@login_required
def admin_clientes(request):
    _admin_required(request)

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


@login_required
def admin_cliente(request, ruc):
    _admin_required(request)

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
        connection = connections[alias]
        connection.ensure_connection()
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
