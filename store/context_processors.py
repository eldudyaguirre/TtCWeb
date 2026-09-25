from .services.acceso import validar_acceso_cliente
from django.db import OperationalError

from .models import AdminPerfil, UsuarioCliente


def acceso_cliente(request):
    if not request.user.is_authenticated or request.user.is_staff or request.user.is_superuser:
        return {
            'acceso_restringido': False,
            'motivo_acceso': 'ok',
            'detalle_acceso': '',
        }

    asignacion = (
        UsuarioCliente.objects
        .filter(usuario=request.user, activo=True)
        .select_related('cliente')
        .first()
    )
    if asignacion is None:
        return {
            'acceso_restringido': True,
            'motivo_acceso': 'sin_asignacion',
            'detalle_acceso': 'No tienes una empresa activa asignada a tu usuario.',
        }

    permitido, motivo, detalle = validar_acceso_cliente(asignacion.cliente)
    return {
        'acceso_restringido': not permitido,
        'motivo_acceso': motivo,
        'detalle_acceso': detalle,
    }


def admin_perfil(request):
    usuario = request.session.get('admin_username', '').strip()
    perfil = None
    if usuario:
        try:
            perfil = AdminPerfil.objects.filter(usuario=usuario).first()
        except OperationalError:
            # Permite que el portal siga funcionando mientras la migración
            # de AdminPerfil aún no haya sido aplicada en el servidor.
            perfil = None

    return {
        'admin_usuario': usuario,
        'admin_nombre': (perfil.nombres if perfil and perfil.nombres else request.session.get('admin_name', '')),
        'admin_perfil': perfil,
        'admin_tiene_foto': bool(perfil and perfil.foto),
    }
