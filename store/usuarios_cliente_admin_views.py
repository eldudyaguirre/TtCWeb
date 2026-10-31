from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .admin_views import admin_required
from .models import Cliente, UsuarioCliente


@admin_required
def admin_usuarios_cliente(request, ruc):
    """Administra los accesos al portal web de un cliente específico."""
    cliente = get_object_or_404(Cliente, pk=ruc)
    User = get_user_model()

    if request.method == 'POST':
        accion = request.POST.get('accion', '').strip()

        if accion == 'crear':
            username = request.POST.get('username', '').strip()
            nombre = request.POST.get('first_name', '').strip()
            apellido = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip().lower()
            password = request.POST.get('password', '')
            password_confirm = request.POST.get('password_confirm', '')
            rol = request.POST.get('rol', UsuarioCliente.Rol.OPERADOR)

            if not username or not password:
                messages.error(request, 'El nombre de usuario y la contraseña son obligatorios.')
            elif rol not in UsuarioCliente.Rol.values:
                messages.error(request, 'Selecciona un rol válido.')
            elif password != password_confirm:
                messages.error(request, 'Las contraseñas no coinciden.')
            elif User.objects.filter(username__iexact=username).exists():
                messages.error(request, 'Ese nombre de usuario ya está registrado. Elige otro.')
            else:
                nuevo_usuario = User(
                    username=username,
                    first_name=nombre,
                    last_name=apellido,
                    email=email,
                )
                try:
                    validate_password(password, user=nuevo_usuario)
                except ValidationError as exc:
                    for error in exc.messages:
                        messages.error(request, error)
                else:
                    try:
                        with transaction.atomic():
                            nuevo_usuario.set_password(password)
                            nuevo_usuario.save()
                            UsuarioCliente.objects.create(
                                usuario=nuevo_usuario,
                                cliente=cliente,
                                rol=rol,
                                activo=True,
                            )
                        messages.success(
                            request,
                            f'El usuario {username} fue creado y asignado al cliente correctamente.',
                        )
                        return redirect('admin_usuarios_cliente', ruc=cliente.ruccedcli)
                    except IntegrityError:
                        messages.error(
                            request,
                            'No se pudo crear el usuario porque ya existe una cuenta o asignación con esos datos.',
                        )

        elif accion == 'cambiar_rol':
            asignacion_id = request.POST.get('asignacion_id', '').strip()
            rol = request.POST.get('rol', '').strip()
            if rol not in UsuarioCliente.Rol.values:
                messages.error(request, 'Selecciona un rol válido.')
            else:
                asignacion = get_object_or_404(
                    UsuarioCliente,
                    pk=asignacion_id,
                    cliente=cliente,
                )
                asignacion.rol = rol
                asignacion.save(update_fields=['rol'])
                messages.success(
                    request,
                    f'Se actualizó el rol de {asignacion.usuario.username}.',
                )
                return redirect('admin_usuarios_cliente', ruc=cliente.ruccedcli)

        elif accion == 'alternar_estado':
            asignacion_id = request.POST.get('asignacion_id', '').strip()
            asignacion = get_object_or_404(
                UsuarioCliente,
                pk=asignacion_id,
                cliente=cliente,
            )
            asignacion.activo = not asignacion.activo
            asignacion.save(update_fields=['activo'])
            estado = 'activado' if asignacion.activo else 'desactivado'
            messages.success(
                request,
                f'El acceso de {asignacion.usuario.username} fue {estado}.',
            )
            return redirect('admin_usuarios_cliente', ruc=cliente.ruccedcli)

        else:
            messages.error(request, 'La acción solicitada no es válida.')

    asignaciones = (
        UsuarioCliente.objects
        .filter(cliente=cliente)
        .select_related('usuario')
        .order_by('usuario__username')
    )
    return render(
        request,
        'admin/usuarios_cliente.html',
        {
            'cliente': cliente,
            'asignaciones': asignaciones,
            'roles': UsuarioCliente.Rol.choices,
            'total_usuarios': asignaciones.count(),
            'usuarios_activos': asignaciones.filter(activo=True, usuario__is_active=True).count(),
        },
    )
