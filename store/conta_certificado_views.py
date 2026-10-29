import hashlib
import json
import re
import tempfile
from pathlib import Path
from urllib import error, request

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Cliente
from .admin_views import ADMIN_USERNAME_KEY, _conta_certificado_ruc_request, admin_required
from .services.archivos.storage import data_root


@admin_required
def admin_cliente_obtener_ruc_sri(request, ruc):
    if request.method != "POST":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido."}, status=405)
    ruc = "".join(c for c in str(ruc) if c.isdigit())
    cliente = Cliente.objects.filter(ruccedcli=ruc, activo=True).first()
    if not cliente:
        return JsonResponse({"ok": False, "mensaje": "Cliente no encontrado o inactivo."}, status=404)
    if not str(cliente.clavesri or "").strip():
        return JsonResponse({"ok": False, "mensaje": "El cliente no tiene clave SRI registrada."}, status=400)
    try:
        result = _conta_certificado_ruc_request(ruc, request.session.get(ADMIN_USERNAME_KEY, "ADMIN"))
        return JsonResponse({"ok": True, "estado": result.get("estado", "iniciando"), "mensaje": result.get("mensaje", "Solicitud recibida por Conta.")})
    except RuntimeError as exc:
        return JsonResponse({"ok": False, "mensaje": str(exc)}, status=502)


@admin_required
def admin_cliente_estado_ruc_sri(request, ruc):
    if request.method != "GET":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido."}, status=405)
    ruc = "".join(c for c in str(ruc) if c.isdigit())
    if not Cliente.objects.filter(ruccedcli=ruc, activo=True).exists():
        return JsonResponse({"ok": False, "mensaje": "Cliente no encontrado o inactivo."}, status=404)
    try:
        result = _conta_certificado_ruc_request(ruc, request.session.get(ADMIN_USERNAME_KEY, "ADMIN"), estado=True)
        return JsonResponse({"ok": True, **result})
    except RuntimeError as exc:
        return JsonResponse({"ok": False, "mensaje": str(exc)}, status=502)



def _conta_declaraciones_sri_request(ruc, usuario, anio, estado=False):
    """Llama a Conta para iniciar o consultar la sincronización de declaraciones."""
    base_url = str(__import__('os').getenv('CONTA_URL', 'http://127.0.0.1:2408')).rstrip('/')
    token = str(__import__('os').getenv('CONTA_INTERNAL_TOKEN', '')).strip()
    if not token:
        raise RuntimeError('CONTA_INTERNAL_TOKEN no está configurado en TotalCounts.')

    url = f'{base_url}/api/v1/admin/sri/declaraciones/{ruc}/estado?anio={int(anio)}'
    method, payload = 'GET', None
    if not estado:
        url = f'{base_url}/api/v1/admin/sri/declaraciones/{ruc}/sincronizar'
        payload = json.dumps({'anio': int(anio)}).encode('utf-8')
        method = 'POST'

    req = request.Request(url, data=payload, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-TotalCounts-Internal': token,
        'X-TotalCounts-User': str(usuario or 'ADMIN'),
    }, method=method)
    try:
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))
    except error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        try:
            detail = json.loads(body).get('detail', body)
        except json.JSONDecodeError:
            detail = body
        raise RuntimeError(f'Conta respondió HTTP {exc.code}: {detail}') from exc
    except error.URLError as exc:
        raise RuntimeError(f'No se pudo conectar con Conta: {exc.reason}') from exc


@admin_required
def admin_cliente_sincronizar_declaraciones_sri(request, ruc):
    """Inicia la descarga de declaraciones ya presentadas, sin presentar nuevas."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'mensaje': 'Método no permitido.'}, status=405)

    ruc = ''.join(char for char in str(ruc) if char.isdigit())
    cliente = Cliente.objects.filter(ruccedcli=ruc, activo=True).first()
    if cliente is None:
        return JsonResponse({'ok': False, 'mensaje': 'Cliente no encontrado o inactivo.'}, status=404)
    if not str(cliente.clavesri or '').strip():
        return JsonResponse({'ok': False, 'mensaje': 'El cliente no tiene clave SRI registrada.'}, status=400)

    try:
        payload = json.loads((request.body or b'{}').decode('utf-8'))
        anio = int(payload.get('anio'))
        if anio < 2000 or anio > 2100:
            raise ValueError
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        return JsonResponse({'ok': False, 'mensaje': 'El año fiscal no es válido.'}, status=400)

    try:
        resultado = _conta_declaraciones_sri_request(
            ruc, request.session.get(ADMIN_USERNAME_KEY, 'ADMIN'), anio,
        )
        return JsonResponse({'ok': True, **resultado})
    except RuntimeError as exc:
        return JsonResponse({'ok': False, 'mensaje': str(exc)}, status=502)


@admin_required
def admin_cliente_estado_declaraciones_sri(request, ruc):
    """Consulta el avance y los resultados de una sincronización de declaraciones."""
    if request.method != 'GET':
        return JsonResponse({'ok': False, 'mensaje': 'Método no permitido.'}, status=405)

    ruc = ''.join(char for char in str(ruc) if char.isdigit())
    if not Cliente.objects.filter(ruccedcli=ruc, activo=True).exists():
        return JsonResponse({'ok': False, 'mensaje': 'Cliente no encontrado o inactivo.'}, status=404)
    try:
        anio = int(request.GET.get('anio', ''))
        if anio < 2000 or anio > 2100:
            raise ValueError
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'mensaje': 'El año fiscal no es válido.'}, status=400)

    try:
        resultado = _conta_declaraciones_sri_request(
            ruc, request.session.get(ADMIN_USERNAME_KEY, 'ADMIN'), anio, estado=True,
        )
        return JsonResponse({'ok': True, **resultado})
    except RuntimeError as exc:
        return JsonResponse({'ok': False, 'mensaje': str(exc)}, status=502)


@csrf_exempt
def conta_declaraciones_sri(request, ruc):
    """API interna: compara documentos existentes y recibe PDFs descargados por Conta."""
    if request.method not in {'GET', 'POST'}:
        return JsonResponse({'ok': False, 'mensaje': 'Método no permitido.'}, status=405)

    token = request.headers.get('X-TotalCounts-Internal', '').strip()
    esperado = str(getattr(settings, 'CONTA_INTERNAL_TOKEN', '') or '').strip()
    if not token or not esperado or token != esperado:
        return JsonResponse({'ok': False, 'mensaje': 'No autorizado.'}, status=401)

    ruc = ''.join(char for char in str(ruc) if char.isdigit())
    if len(ruc) != 13:
        return JsonResponse({'ok': False, 'mensaje': 'RUC inválido.'}, status=400)
    cliente = Cliente.objects.filter(ruccedcli=ruc, activo=True).first()
    if cliente is None:
        return JsonResponse({'ok': False, 'mensaje': 'El RUC no existe o el cliente no está activo.'}, status=404)

    raiz_cliente = data_root() / ruc
    raiz = raiz_cliente / 'anexos'
    raiz.mkdir(parents=True, exist_ok=True)

    if request.method == 'GET':
        # Listamos todos los PDF del cliente, no solo los del nuevo módulo,
        # para poder reconocer una declaración que ya se guardó anteriormente
        # bajo otra carpeta o con el nombre original descargado del SRI.
        archivos = []
        for archivo in raiz_cliente.rglob('*'):
            if not archivo.is_file() or archivo.suffix.lower() != '.pdf':
                continue
            if any(parte.startswith('.') for parte in archivo.relative_to(raiz_cliente).parts):
                continue
            try:
                clave = archivo.relative_to(raiz_cliente).as_posix()
            except ValueError:
                continue
            archivos.append({
                'key': clave,
                'nombre': archivo.name,
                'tamano': archivo.stat().st_size,
            })
        archivos.sort(key=lambda item: item['key'])
        return JsonResponse({'ok': True, 'ruc': ruc, 'files': archivos, 'total': len(archivos)})

    tipo = str(request.POST.get('tipo', '')).strip().lower()
    anio_txt = str(request.POST.get('anio_fiscal', '')).strip()
    mes = str(request.POST.get('mes', '')).strip().zfill(2)
    nombre = Path(str(request.POST.get('nombre_archivo', '')).strip()).name
    if tipo not in {'iva', 'renta'}:
        return JsonResponse({'ok': False, 'mensaje': 'Tipo de declaración no válido.'}, status=400)
    if not re.fullmatch(r'20\d{2}', anio_txt):
        return JsonResponse({'ok': False, 'mensaje': 'Año fiscal no válido.'}, status=400)
    if mes not in {'00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'}:
        return JsonResponse({'ok': False, 'mensaje': 'Periodo mensual no válido.'}, status=400)
    if tipo == 'iva' and mes == '00':
        return JsonResponse({'ok': False, 'mensaje': 'La declaración de IVA debe tener un mes válido.'}, status=400)
    if tipo == 'renta':
        mes = '00'
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,180}\.pdf', nombre, flags=re.IGNORECASE):
        return JsonResponse({'ok': False, 'mensaje': 'Nombre de PDF no válido.'}, status=400)

    archivo = request.FILES.get('archivo')
    if archivo is None:
        return JsonResponse({'ok': False, 'mensaje': 'No se recibió el PDF de la declaración.'}, status=400)
    contenido = archivo.read()
    if not contenido.startswith(b'%PDF'):
        return JsonResponse({'ok': False, 'mensaje': 'El contenido recibido no es un PDF válido.'}, status=400)

    carpeta_tipo = 'declaraciones_iva' if tipo == 'iva' else 'declaraciones_renta'
    carpeta_destino = raiz / carpeta_tipo / anio_txt / mes
    carpeta_destino.mkdir(parents=True, exist_ok=True)
    destino = carpeta_destino / nombre
    clave = destino.relative_to(raiz_cliente).as_posix()

    if destino.is_file():
        try:
            with destino.open('rb') as existente:
                if existente.read(5).startswith(b'%PDF'):
                    return JsonResponse({
                        'ok': True, 'existia': True, 'key': clave,
                        'mensaje': 'La declaración ya estaba guardada.',
                        'tamano': destino.stat().st_size,
                    })
        except OSError:
            pass

    temporal = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.declaracion_', suffix='.tmp', dir=carpeta_destino, delete=False) as salida:
            temporal = Path(salida.name)
            salida.write(contenido)
        temporal.replace(destino)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)

    return JsonResponse({
        'ok': True, 'existia': False, 'key': clave,
        'mensaje': 'Declaración archivada correctamente.',
        'tamano': len(contenido),
        'sha256': hashlib.sha256(contenido).hexdigest(),
    })
