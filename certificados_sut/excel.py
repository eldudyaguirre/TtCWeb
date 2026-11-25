import io
import re
import unicodedata


def normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def _buscar_columnas(encabezados):
    normalizados = [normalizar(x) for x in encabezados]

    def buscar(*opciones):
        for indice, nombre in enumerate(normalizados):
            if any(opcion in nombre for opcion in opciones):
                return indice
        return None

    cedula = buscar("cedula", "identificacion")
    nombre = buscar("nombre", "trabajador", "afiliado")
    periodo = buscar("periodo", "mes")
    if cedula is None or nombre is None:
        raise ValueError("No se encontraron las columnas Cédula y Nombre en el Excel.")
    return cedula, nombre, periodo


def leer_nomina(nombre_archivo, contenido):
    extension = nombre_archivo.lower().rsplit(".", 1)[-1]
    filas = []
    try:
        if extension == "xlsx":
            from openpyxl import load_workbook
            libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
            hoja = libro.active
            filas = list(hoja.iter_rows(values_only=True))
            libro.close()
        elif extension == "xls":
            import xlrd
            libro = xlrd.open_workbook(file_contents=contenido)
            hoja = libro.sheet_by_index(0)
            filas = [hoja.row_values(i) for i in range(hoja.nrows)]
        else:
            raise ValueError("El archivo debe tener formato .xls o .xlsx.")
    except ImportError:
        raise ValueError("Falta instalar xlrd para leer archivos .xls. Ejecuta: poetry add xlrd")
    except Exception as exc:
        raise ValueError(f"No se pudo leer el Excel: {exc}")

    encabezado_idx = None
    columnas = None
    for indice, fila in enumerate(filas[:20]):
        try:
            columnas = _buscar_columnas(fila)
            encabezado_idx = indice
            break
        except ValueError:
            continue
    if encabezado_idx is None:
        raise ValueError("No se encontró una fila de encabezados con Cédula y Nombre.")

    idx_cedula, idx_nombre, idx_periodo = columnas
    trabajadores = {}
    periodos = set()
    for fila in filas[encabezado_idx + 1:]:
        if len(fila) <= max(idx_cedula, idx_nombre):
            continue
        cedula = str(fila[idx_cedula] or "").strip()
        if cedula.endswith(".0"):
            cedula = cedula[:-2]
        nombre = str(fila[idx_nombre] or "").strip()
        if not cedula or not nombre or cedula.lower() == "none":
            continue
        trabajador = trabajadores.setdefault(cedula, {
            "cedula": cedula,
            "nombre": nombre.upper(),
            "horas": ["0", "0", "0", "0"],
        })
        if len(nombre) > len(trabajador["nombre"]):
            trabajador["nombre"] = nombre.upper()
        if idx_periodo is not None and idx_periodo < len(fila) and fila[idx_periodo]:
            periodos.add(str(fila[idx_periodo]).strip())

    if not trabajadores:
        raise ValueError("El Excel no contiene trabajadores identificables.")
    return sorted(trabajadores.values(), key=lambda x: x["nombre"]), sorted(periodos)
