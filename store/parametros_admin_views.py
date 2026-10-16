from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4
import re

from django.conf import settings
from django.contrib import messages
from django.db import connections, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .admin_views import admin_required


DB_ALIAS = 'bdtotal_parametros'


def _parametros_db():
    if DB_ALIAS not in connections.databases:
        config = settings.DATABASES['default'].copy()
        config['NAME'] = 'BdTotal'
        connections.databases[DB_ALIAS] = config
    return connections[DB_ALIAS]


def _leer_parametros():
    with _parametros_db().cursor() as cursor:
        cursor.execute("""
            SELECT id, numserfac, numfactur, poriva, basico, ubifirelec, passp12
            FROM public.parametros
            ORDER BY id
            LIMIT 1
        """)
        row = cursor.fetchone()

    if row is None:
        raise RuntimeError('La tabla public.parametros no contiene registros.')
    return {
        'id': row[0],
        'numserfac': str(row[1] or '').strip(),
        'numfactur': row[2],
        'poriva': row[3] if row[3] is not None else 15,
        'basico': row[4] if row[4] is not None else 482,
        'ubifirelec': str(row[5] or '').strip(),
        'passp12_configurada': bool(row[6]),
    }


def _separar_serie(serie):
    coincidencia = re.fullmatch(r'\s*(\d{1,3})\s*-\s*(\d{1,3})\s*', serie or '')
    if not coincidencia:
        return '', ''
    return coincidencia.group(1).zfill(3), coincidencia.group(2).zfill(3)


@admin_required
@require_http_methods(["GET", "POST"])
def admin_parametros(request):
    error = ''
    try:
        parametros = _leer_parametros()
    except Exception:
        messages.error(
            request,
            'No se pudieron consultar los parámetros en BdTotal. Verifica la conexión y la tabla public.parametros.',
        )
        return redirect('admin_dashboard')

    establecimiento, punto_emision = _separar_serie(parametros['numserfac'])
    initial = {
        'establecimiento': establecimiento,
        'punto_emision': punto_emision,
        'numfactur': parametros['numfactur'] if parametros['numfactur'] is not None else '',
        'poriva': parametros['poriva'] if parametros['poriva'] not in (None, '') else 15,
        'basico': parametros['basico'] if parametros['basico'] not in (None, '') else 482,
        'ubifirelec': parametros['ubifirelec'],
        'firma_nombre': Path(parametros['ubifirelec']).name if parametros['ubifirelec'] else '',
        'passp12_configurada': parametros['passp12_configurada'],
    }

    if request.method == 'POST':
        establecimiento = request.POST.get('establecimiento', '').strip()
        punto_emision = request.POST.get('punto_emision', '').strip()
        serie_raw = request.POST.get('serie_actual', '').strip()
        if serie_raw:
            serie_match = re.fullmatch(r'(\d{1,3})\s*-\s*(\d{1,3})', serie_raw)
            if serie_match:
                establecimiento = serie_match.group(1)
                punto_emision = serie_match.group(2)
        numfactur_raw = request.POST.get('numfactur', '').strip()
        poriva_raw = request.POST.get('poriva', '').strip().replace(',', '.') or str(parametros['poriva'])
        basico_raw = request.POST.get('basico', '').strip().replace(',', '.') or str(parametros['basico'])
        certificado_subido = request.FILES.get('certificado_p12')
        passp12 = request.POST.get('passp12', '')
        ubifirelec = parametros['ubifirelec']

        errors = []
        if not re.fullmatch(r'\d{1,3}', establecimiento):
            errors.append('El número de establecimiento debe contener de 1 a 3 dígitos.')
        if not re.fullmatch(r'\d{1,3}', punto_emision):
            errors.append('El punto de emisión debe contener de 1 a 3 dígitos.')

        try:
            numfactur = int(numfactur_raw)
            if numfactur < 0:
                raise ValueError
        except (ValueError, TypeError):
            numfactur = None
            errors.append('El secuencial debe ser un número entero igual o mayor que cero.')

        try:
            poriva = Decimal(poriva_raw)
            if not poriva.is_finite() or poriva < 0 or poriva > 100:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            poriva = None
            errors.append('Ingresa un porcentaje de IVA válido entre 0 y 100.')

        try:
            basico = Decimal(basico_raw)
            if not basico.is_finite() or basico <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            basico = None
            errors.append('Ingresa un salario básico unificado mayor que cero.')

        if certificado_subido:
            if not certificado_subido.name.lower().endswith('.p12'):
                errors.append('El certificado debe ser un archivo con extensión .p12.')
            if certificado_subido.size > 10 * 1024 * 1024:
                errors.append('El certificado no puede superar los 10 MB.')

        initial = {
            'establecimiento': establecimiento,
            'punto_emision': punto_emision,
            'serie_actual': serie_raw,
            'numfactur': numfactur_raw,
            'poriva': poriva_raw or parametros['poriva'],
            'basico': basico_raw or parametros['basico'],
            'ubifirelec': parametros['ubifirelec'],
            'firma_nombre': Path(parametros['ubifirelec']).name if parametros['ubifirelec'] else '',
            'passp12_configurada': parametros['passp12_configurada'] or bool(passp12),
        }

        if errors:
            for item in errors:
                messages.error(request, item)
        else:
            serie = f'{establecimiento.zfill(3)}-{punto_emision.zfill(3)}'
            ruta_nuevo_certificado = None
            try:
                # El certificado se almacena fuera de MEDIA_ROOT, en una carpeta privada del servidor.
                if certificado_subido:
                    carpeta_firmas = Path(settings.TOTALCOUNTS_DATA_ROOT) / 'configuracion' / 'firma_electronica'
                    carpeta_firmas.mkdir(parents=True, exist_ok=True)
                    ruta_nuevo_certificado = carpeta_firmas / f'{uuid4().hex}.p12'
                    with ruta_nuevo_certificado.open('wb') as destino:
                        for bloque in certificado_subido.chunks():
                            destino.write(bloque)
                    ubifirelec = str(ruta_nuevo_certificado.resolve())

                with transaction.atomic(using=DB_ALIAS):
                    with _parametros_db().cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE public.parametros
                            SET numserfac = %s, numfactur = %s, poriva = %s, basico = %s,
                                ubifirelec = %s,
                                passp12 = CASE WHEN %s <> '' THEN %s ELSE passp12 END
                            WHERE id = %s
                            """,
                            [serie, numfactur, float(poriva), float(basico), ubifirelec,
                             passp12, passp12, parametros['id']],
                        )
                        if cursor.rowcount != 1:
                            raise RuntimeError('No se actualizó un único registro de parámetros.')

                messages.success(
                    request,
                    'Parámetros actualizados correctamente.'
                    if not certificado_subido
                    else 'Parámetros actualizados y certificado electrónico guardado en el servidor.',
                )
                return redirect('admin_parametros')
            except Exception:
                if ruta_nuevo_certificado:
                    ruta_nuevo_certificado.unlink(missing_ok=True)
                messages.error(
                    request,
                    'No se pudieron guardar los parámetros. Verifica la base de datos y los permisos de la carpeta de firmas.',
                )

    return render(request, 'admin/parametros.html', {
        'parametros': initial,
        'serie_actual': initial.get('serie_actual') or parametros['numserfac'],
    })
