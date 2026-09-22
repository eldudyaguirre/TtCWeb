import hashlib
import re
from pathlib import Path
from uuid import uuid4

from django.conf import settings


def data_root():
    root = Path(settings.TOTALCOUNTS_DATA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(filename):
    name = Path(filename or 'archivo').name
    stem = re.sub(r'[^A-Za-z0-9._-]+', '_', Path(name).stem).strip('._') or 'archivo'
    extension = Path(name).suffix.lower()
    return f'{stem}_{uuid4().hex[:12]}{extension}'


def guardar_archivo(cliente, uploaded_file, tipo, subcarpeta, usuario=None):
    from ...models.archivo import Archivo

    ruc = str(cliente.ruccedcli).strip()
    relative_dir = Path(ruc) / subcarpeta
    target_dir = data_root() / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    nombre_fisico = _safe_name(uploaded_file.name)
    relative_path = relative_dir / nombre_fisico
    target_path = data_root() / relative_path

    sha256 = hashlib.sha256()
    with target_path.open('wb') as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
            sha256.update(chunk)

    return Archivo.objects.create(
        cliente=cliente,
        tipo=tipo,
        nombre_original=Path(uploaded_file.name).name[:255],
        nombre_fisico=nombre_fisico,
        ruta_relativa=relative_path.as_posix(),
        extension=Path(uploaded_file.name).suffix.lower()[:20],
        mime_type=getattr(uploaded_file, 'content_type', '')[:150],
        tamano=target_path.stat().st_size,
        sha256=sha256.hexdigest(),
        creado_por=usuario,
    )


def eliminar_archivo(archivo):
    if not archivo:
        return

    path = data_root() / Path(archivo.ruta_relativa)
    try:
        path.unlink(missing_ok=True)
    finally:
        archivo.delete()
