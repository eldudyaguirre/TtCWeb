from django.db import connection
from django.contrib import messages
from django.shortcuts import redirect, render
from .admin_views import admin_required, ADMIN_NAME_KEY, ADMIN_USERNAME_KEY


def _ensure_worker_column():
    with connection.cursor() as cursor:
        cursor.execute("""
            ALTER TABLE seguridad
            ADD COLUMN IF NOT EXISTS worker BOOLEAN NOT NULL DEFAULT FALSE
        """)


@admin_required
def admin_workers(request):
    _ensure_worker_column()

    if request.method == 'POST':
        usuario = request.POST.get('usuario', '').strip()
        accion = request.POST.get('accion', '').strip()

        if usuario and accion in ('activar', 'desactivar'):
            valor = accion == 'activar'
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE seguridad
                    SET worker = %s
                    WHERE UPPER(TRIM(usrname::text)) = UPPER(TRIM(%s))
                """, [valor, usuario])
            messages.success(
                request,
                f'Worker {"activado" if valor else "desactivado"} para {usuario}.'
            )

        return redirect('admin_workers')

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                TRIM(usrname::text) AS usuario,
                COALESCE(TRIM(nomusuari::text), '') AS nombre,
                COALESCE(worker, FALSE) AS worker
            FROM seguridad
            ORDER BY worker DESC, nomusuari, usrname
        """)
        trabajadores = [
            {'usuario': row[0], 'nombre': row[1], 'worker': bool(row[2])}
            for row in cursor.fetchall()
        ]

    return render(
        request,
        'admin/workers.html',
        {
            'trabajadores': trabajadores,
            'admin_nombre': request.session.get(ADMIN_NAME_KEY, ''),
            'admin_usuario': request.session.get(ADMIN_USERNAME_KEY, ''),
        },
    )
