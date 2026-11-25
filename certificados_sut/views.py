import io
import re
import unicodedata
import uuid
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.conf import settings
from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from .excel import leer_nomina

CACHE_TTL = 60 * 60 * 2
SESSION_KEY = "certificados_sut_token"
TEMAS = 5
TEMAS_INICIALES = [
    "DERECHOS LABORALES DE MUJERES Y HOMBRES",
    "IGUALDAD DE GÉNERO",
    "ERRADICACIÓN DE VIOLENCIA Y NO DISCRIMINACIÓN EN UNA EMPRESA O CENTRO DE TRABAJO",
    "OTROS RELACIONADOS PARA ESTABLECER EL TRABAJO DE IGUAL VALOR",
    "EL VALOR DE LOS TRABAJOS DESDE UNA PERSPECTIVA DE IGUALDAD DE GÉNERO Y SIN DISCRIMINACIÓN"
]
PROFESIONAL_INICIAL = "Psi.Cli Hester Palacio Segovia"
HORAS_INICIALES = ["10", "10", "10", "10", "2"]


def _es_sa(request):
    """El módulo utiliza exclusivamente la sesión administrativa SA de TtCWeb."""
    return (
        request.session.get("admin_portal") is True
        and str(request.session.get("admin_username", "")).strip().upper() == "SA"
    )


def _proteger(request):
    if not _es_sa(request):
        raise Http404("No encontrado")


def _obtener_datos(request):
    token = request.session.get(SESSION_KEY)
    return cache.get(f"certificados_sut:{token}") if token else None


def inicio(request):
    _proteger(request)
    datos = _obtener_datos(request) or {}
    return render(request, "certificados_sut/index.html", {
        "datos": datos,
        "trabajadores": datos.get("trabajadores", []),
        "temas": datos.get("temas", TEMAS_INICIALES.copy()),
        "empresa": datos.get("empresa", ""),
        "telefono": datos.get("telefono", ""),
        "email": datos.get("email", ""),
        "profesional": datos.get("profesional", PROFESIONAL_INICIAL),
        "responsable_uath": datos.get("responsable_uath", ""),
        "areas_text": datos.get("areas_text", ""),
        "fecha_inicio": datos.get("fecha_inicio", ""),
        "fecha_fin": datos.get("fecha_fin", ""),
        "error": request.GET.get("error", ""),
    })


@require_POST
def cargar_excel(request):
    _proteger(request)
    archivo = request.FILES.get("archivo_iess")
    if not archivo:
        return redirect("/totalcounts/certificados-sut/?error=Selecciona+un+archivo+Excel")
    try:
        trabajadores, periodos = leer_nomina(archivo.name, archivo.read())
    except ValueError as exc:
        return redirect(f"/totalcounts/certificados-sut/?error={str(exc)}")

    token = uuid.uuid4().hex
    datos = {
        "trabajadores": trabajadores,
        "periodos": periodos,
        "temas": TEMAS_INICIALES.copy(),
        "empresa": "",
        "telefono": "",
        "email": "",
        "profesional": PROFESIONAL_INICIAL,
        "responsable_uath": "",
        "areas_text": "",
        "fecha_inicio": "",
        "fecha_fin": "",
    }
    cache.set(f"certificados_sut:{token}", datos, CACHE_TTL)
    request.session[SESSION_KEY] = token
    return redirect("certificados_sut:inicio")


def _guardar_formulario(request, datos):
    datos["empresa"] = request.POST.get("empresa", "").strip()
    datos["telefono"] = request.POST.get("telefono", "").strip()
    datos["email"] = request.POST.get("email", "").strip()
    datos["profesional"] = request.POST.get("profesional", "").strip()
    datos["responsable_uath"] = request.POST.get("responsable_uath", "").strip()
    datos["areas_text"] = request.POST.get("areas_text", "").strip()
    datos["fecha_inicio"] = request.POST.get("fecha_inicio", "").strip()
    datos["fecha_fin"] = request.POST.get("fecha_fin", "").strip()
    try:
        inicio = date.fromisoformat(datos["fecha_inicio"])
        fin = date.fromisoformat(datos["fecha_fin"])
        if fin < inicio:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Ingresa fechas válidas y verifica que la fecha final no sea anterior a la inicial.")
    areas_validas = [a.strip() for a in re.split(r"[\n,;]+", datos["areas_text"]) if a.strip()]
    datos["temas"] = [request.POST.get(f"tema_{i}", "").strip() for i in range(1, TEMAS + 1)]

    trabajadores = datos.get("trabajadores", [])
    for indice, trabajador in enumerate(trabajadores):
        area = request.POST.get(f"area_{indice}", "").strip()
        if area and area not in areas_validas:
            raise ValueError(f"El área de {trabajador['nombre']} no está en la lista de áreas.")
        trabajador["area"] = area
        horas = []
        for tema in range(1, TEMAS + 1):
            valor = request.POST.get(f"horas_{indice}_{tema}", "0").strip().replace(",", ".")
            try:
                numero = Decimal(valor or "0")
                if numero < 0 or numero > 999:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                raise ValueError(f"Las horas del trabajador {trabajador['nombre']} deben ser números entre 0 y 999.")
            horas.append(str(numero))
        trabajador["horas"] = horas


def _nombre_archivo(texto):
    limpio = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^A-Za-z0-9_-]+", "_", limpio).strip("_")
    return limpio[:80] or "documento"


def _ruta_logo_mdt():
    """Obtiene el logo del Ministerio desde static/images."""
    ruta = finders.find("images/LOGO_MDT.png")
    if ruta:
        return ruta
    candidata = settings.BASE_DIR / "static" / "images" / "LOGO_MDT.png"
    return str(candidata) if candidata.exists() else None


def _crear_certificado(datos, trabajador, tema, horas):
    buffer = io.BytesIO()
    pagina = landscape(A4)
    ancho, alto = pagina
    pdf = canvas.Canvas(buffer, pagesize=pagina)
    pdf.setTitle(f"Certificado - {trabajador['nombre']}")

    azul = colors.HexColor("#253B55")
    tinta = colors.HexColor("#18212B")
    rosa = colors.HexColor("#E8BFCB")
    celeste = colors.HexColor("#BFE3E9")
    dorado = colors.HexColor("#D9B85B")
    dorado_claro = colors.HexColor("#F4E3A0")

    # Fondo blanco y marco fino de esquinas redondeadas.
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, ancho, alto, stroke=0, fill=1)
    pdf.setStrokeColor(colors.HexColor("#252525"))
    pdf.setLineWidth(0.8)
    pdf.roundRect(8, 8, ancho - 16, alto - 16, 15, stroke=1, fill=0)

    # Manchas suaves de acuarela en las esquinas (formas vectoriales originales).
    def mancha(cx, cy, rx, ry, color, alpha):
        try:
            pdf.saveState()
            pdf.setFillAlpha(alpha)
        except Exception:
            pdf.saveState()
        pdf.setFillColor(color)
        p = pdf.beginPath()
        p.moveTo(cx - rx, cy)
        p.curveTo(cx - rx * 1.2, cy + ry * 0.65, cx - rx * 0.45, cy + ry * 1.15, cx, cy + ry)
        p.curveTo(cx + rx * 0.85, cy + ry * 1.1, cx + rx * 1.15, cy + ry * 0.35, cx + rx, cy)
        p.curveTo(cx + rx * 1.1, cy - ry * 0.8, cx + rx * 0.35, cy - ry * 1.1, cx, cy - ry)
        p.curveTo(cx - rx * 0.8, cy - ry * 1.05, cx - rx * 1.1, cy - ry * 0.35, cx - rx, cy)
        p.close()
        pdf.drawPath(p, stroke=0, fill=1)
        pdf.restoreState()

    for cx, cy, rx, ry, color, alpha in [
        (22, alto - 30, 62, 42, rosa, 0.28),
        (70, alto - 10, 45, 28, celeste, 0.30),
        (ancho - 28, alto - 26, 55, 38, celeste, 0.25),
        (ancho - 14, 38, 62, 42, rosa, 0.23),
        (36, 24, 55, 34, celeste, 0.24),
        (ancho - 72, alto - 5, 35, 24, rosa, 0.20),
    ]:
        mancha(cx, cy, rx, ry, color, alpha)

    # Pequeñas salpicaduras alrededor de las manchas.
    for x, y, r, color in [
        (22, alto - 78, 3, rosa), (48, alto - 52, 2, celeste),
        (82, alto - 28, 2.5, rosa), (ancho - 54, alto - 76, 2.5, rosa),
        (ancho - 28, alto - 48, 2, celeste), (ancho - 78, 30, 2.5, rosa),
        (ancho - 42, 66, 2, celeste), (48, 52, 2.5, rosa),
        (25, 85, 2, celeste)
    ]:
        pdf.setFillColor(color)
        pdf.circle(x, y, r, stroke=0, fill=1)

    # Esquinas geométricas doradas y líneas finas, inspiradas en el modelo.
    pdf.setFillColor(dorado_claro)
    p = pdf.beginPath()
    p.moveTo(ancho - 125, alto)
    p.lineTo(ancho, alto)
    p.lineTo(ancho, alto - 125)
    p.close()
    pdf.drawPath(p, stroke=0, fill=1)
    p = pdf.beginPath()
    p.moveTo(0, 0)
    p.lineTo(115, 0)
    p.lineTo(0, 115)
    p.close()
    pdf.drawPath(p, stroke=0, fill=1)

    pdf.setStrokeColor(colors.HexColor("#222222"))
    pdf.setLineWidth(0.8)
    # Geometría superior derecha.
    pdf.line(ancho - 215, alto - 18, ancho - 42, alto - 18)
    pdf.line(ancho - 42, alto - 18, ancho - 42, alto - 145)
    pdf.line(ancho - 195, alto - 28, ancho - 52, alto - 28)
    pdf.line(ancho - 52, alto - 28, ancho - 52, alto - 128)
    pdf.line(ancho - 145, alto - 18, ancho - 95, alto - 48)
    # Geometría inferior izquierda.
    pdf.line(18, 155, 18, 35)
    pdf.line(28, 145, 28, 28)
    pdf.line(28, 28, 170, 28)
    pdf.line(38, 18, 190, 18)
    pdf.line(18, 82, 48, 82)
    pdf.line(48, 82, 48, 18)

    # Encabezado y jerarquía tipográfica.
    pdf.setFillColor(tinta)
    pdf.setFont("Helvetica-Bold", 27)
    pdf.drawCentredString(ancho / 2, alto - 82, "CERTIFICADO")
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(ancho / 2, alto - 111, "DE CAPACITACIÓN")
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(ancho / 2, alto - 151, "ESTE CERTIFICADO SE OTORGA A")

    # Nombre destacado con una serif itálica elegante.
    nombre = trabajador.get("nombre", "").strip()
    fuente_nombre = "Times-Italic"
    tam_nombre = 28
    while tam_nombre > 17 and pdf.stringWidth(nombre, fuente_nombre, tam_nombre) > ancho - 190:
        tam_nombre -= 1
    pdf.setFillColor(colors.HexColor("#17202A"))
    pdf.setFont(fuente_nombre, tam_nombre)
    pdf.drawCentredString(ancho / 2, alto - 198, nombre.title())
    pdf.setFillColor(colors.HexColor("#5D6873"))
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(ancho / 2, alto - 220, f"CÉDULA: {trabajador['cedula']}")

    # Reconocimiento y tema con ajuste de línea.
    frase = f"EN RECONOCIMIENTO POR SU PARTICIPACIÓN EN LA CAPACITACIÓN ORGANIZADA POR {datos.get('empresa', '').strip()}"
    pdf.setFillColor(tinta)
    pdf.setFont("Helvetica-Bold", 8.5)
    lineas_frase = _lineas(pdf, frase, "Helvetica-Bold", 8.5, ancho - 210)
    y = alto - 254
    for linea in lineas_frase[:2]:
        pdf.drawCentredString(ancho / 2, y, linea)
        y -= 13

    tema = tema.strip()
    pdf.setFillColor(azul)
    pdf.setFont("Helvetica-Bold", 10)
    lineas_tema = _lineas(pdf, tema, "Helvetica-Bold", 10, ancho - 230)
    y_tema = alto - 294
    for linea in lineas_tema[:2]:
        pdf.drawCentredString(ancho / 2, y_tema, linea)
        y_tema -= 14

    pdf.setFillColor(colors.HexColor("#4D5965"))
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(ancho / 2, alto - 333, f"DURACIÓN ACREDITADA: {horas} HORAS")

    # Sello dorado decorativo, sin texto ni logotipos institucionales.
    sello_x, sello_y = ancho - 78, 66
    pdf.setFillColor(colors.HexColor("#B78B2F"))
    pdf.circle(sello_x, sello_y, 25, stroke=0, fill=1)
    pdf.setFillColor(dorado_claro)
    pdf.circle(sello_x, sello_y, 21, stroke=0, fill=1)
    pdf.setFillColor(dorado)
    pdf.circle(sello_x, sello_y, 16, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#F7E6A6"))
    pdf.circle(sello_x - 5, sello_y + 6, 5, stroke=0, fill=1)

    # Firmas conservadas en dos columnas, con nombres y cargos debajo.
    y_firma = 66
    pdf.setStrokeColor(colors.HexColor("#333333"))
    pdf.setLineWidth(0.7)
    pdf.line(145, y_firma, 335, y_firma)
    pdf.line(ancho - 335, y_firma, ancho - 145, y_firma)
    pdf.setFillColor(tinta)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(240, 49, "Psi.Cli Hester Palacio Segovia")
    pdf.drawCentredString(ancho - 240, 49, "Dudy Aguirre")
    pdf.setFillColor(colors.HexColor("#58636F"))
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(240, 37, "Profesional encargado")
    pdf.drawCentredString(ancho - 240, 37, "Responsable UATH")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()

def _lineas(pdf, texto, fuente, tam, ancho):
    palabras = str(texto or "").split()
    lineas, actual = [], ""
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        if pdf.stringWidth(prueba, fuente, tam) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _celda_texto(pdf, texto, x, y_centro, ancho, fuente="Helvetica", tam=7, color=colors.black):
    lineas = _lineas(pdf, texto, fuente, tam, ancho - 8)
    pdf.setFillColor(color)
    pdf.setFont(fuente, tam)
    alto_linea = tam + 2
    y = y_centro + ((len(lineas) - 1) * alto_linea / 2) - tam * 0.35
    for linea in lineas:
        pdf.drawString(x + 4, y, linea)
        y -= alto_linea
    return len(lineas)


def _encabezado_pdf(pdf, ancho, alto, titulo, datos, tema):
    azul = colors.HexColor("#173B63")
    pdf.setFillColor(azul)
    pdf.rect(0, alto - 10, ancho, 10, stroke=0, fill=1)
    logo = _ruta_logo_mdt()
    if logo:
        try:
            pdf.drawImage(logo, 32, alto - 88, width=175, height=55, preserveAspectRatio=True, mask="auto", anchor="c")
        except Exception:
            pass
    pdf.setFillColor(azul)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(ancho - 32, alto - 43, "MINISTERIO DEL TRABAJO")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(ancho - 32, alto - 61, titulo.upper())

    y = alto - 105
    campos = [
        ("EMPRESA", datos.get("empresa", "")),
        ("TEMA", tema),
        ("PERÍODO", f"{datos.get('fecha_inicio','')}  AL  {datos.get('fecha_fin','')}"),
        ("PROFESIONAL / FACILITADOR", datos.get("profesional", "")),
        ("TELÉFONO", datos.get("telefono", "")),
        ("CORREO", datos.get("email", "")),
        ("RESPONSABLE UATH", datos.get("responsable_uath", "")),
    ]
    for etiqueta, valor in campos:
        pdf.setFillColor(azul)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawString(34, y, etiqueta + ":")
        lineas = _lineas(pdf, valor, "Helvetica", 7.5, ancho - 190)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 7.5)
        for j, linea in enumerate(lineas):
            pdf.drawString(165, y - j * 9, linea)
        y -= max(14, len(lineas) * 9 + 3)
    return y - 8


def _crear_planificacion(datos, tema, participantes):
    buffer = io.BytesIO()
    ancho, alto = A4
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"Planificación - {tema}")
    y = _encabezado_pdf(pdf, ancho, alto, "Planificación de capacitación con facilitadores internos", datos, tema)
    azul = colors.HexColor("#173B63")
    pdf.setFillColor(azul)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(34, y, "PLANIFICACIÓN DE LA CAPACITACIÓN")
    y -= 20
    campos = [
        ("OBJETIVO", "Fortalecer los conocimientos y promover prácticas laborales con igualdad y sin discriminación, de acuerdo con la temática establecida."),
        ("MODALIDAD / LUGAR", "_______________________________________________"),
        ("FECHA(S) DE EJECUCIÓN", f"{datos['fecha_inicio']} al {datos['fecha_fin']}"),
        ("FACILITADOR INTERNO", datos["profesional"]),
        ("DURACIÓN PLANIFICADA", "Según las horas registradas para los participantes en esta temática."),
        ("METODOLOGÍA", "Exposición, diálogo participativo y revisión de situaciones relacionadas con la temática."),
        ("RECURSOS", "Material de apoyo, presentación y registro de asistencia."),
        ("EVALUACIÓN", "Verificación de participación y comprensión de los contenidos tratados."),
    ]
    for etiqueta, valor in campos:
        pdf.setFillColor(azul)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(38, y, etiqueta + ":")
        lineas = _lineas(pdf, valor, "Helvetica", 7, ancho - 190)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 7)
        for j, linea in enumerate(lineas):
            pdf.drawString(165, y - j * 9, linea)
        y -= max(17, len(lineas) * 9 + 7)

    y -= 4
    pdf.setFillColor(azul)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(34, y, "PARTICIPANTES Y HORAS REGISTRADAS")
    y -= 15
    # Tabla con anchos definidos; el texto largo se ajusta dentro de cada celda.
    xs = [34, 58, 290, 420, 510]
    ws = [24, 232, 130, 90, 51]
    headers = ["N°", "NOMBRE", "ÁREA", "HORAS", ""]
    h = 20
    pdf.setFillColor(azul)
    pdf.rect(34, y - h + 4, ancho - 68, h, stroke=0, fill=1)
    for x, w, titulo in zip(xs, ws, headers):
        _celda_texto(pdf, titulo, x, y - 6, w, "Helvetica-Bold", 7, colors.white)
    y -= h
    for i, t in enumerate(participantes, 1):
        n1 = len(_lineas(pdf, t.get("nombre", ""), "Helvetica", 6.7, ws[1] - 8))
        n2 = len(_lineas(pdf, t.get("area", ""), "Helvetica", 6.7, ws[2] - 8))
        rh = max(20, max(n1, n2) * 9 + 8)
        if y - rh < 72:
            pdf.showPage()
            y = alto - 45
        pdf.setStrokeColor(colors.HexColor("#B9C5D2"))
        pdf.rect(34, y - rh + 4, ancho - 68, rh, stroke=1, fill=0)
        vals = [str(i), t["nombre"], t["area"], str(t["_horas"])]
        for x, w, val in zip(xs, ws, vals):
            _celda_texto(pdf, val, x, y - rh / 2 + 2, w, "Helvetica", 6.7)
        for x in xs[1:]:
            pdf.line(x, y - rh + 4, x, y + 4)
        y -= rh
    pdf.setStrokeColor(colors.HexColor("#555555"))
    pdf.line(55, 48, 245, 48)
    pdf.line(ancho - 245, 48, ancho - 55, 48)
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(150, 37, "Firma del facilitador interno")
    pdf.drawCentredString(ancho - 150, 37, "Firma Responsable UATH")
    pdf.save()
    return buffer.getvalue()


def _crear_asistencia(datos, tema, participantes):
    buffer = io.BytesIO()
    ancho, alto = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    pdf.setTitle(f"Registro de asistencia - {tema}")
    y = _encabezado_pdf(pdf, ancho, alto, "Registro de asistencia", datos, tema)
    azul = colors.HexColor("#173B63")
    pdf.setFillColor(azul)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(30, y, "REGISTRO DE PARTICIPANTES")
    y -= 18

    # Columnas proporcionales al ancho real de A4 horizontal (842 pt).
    xs = [30, 55, 145, 365, 490, 555, 625, 785]
    ws = [25, 90, 220, 125, 65, 70, 160, 27]
    headers = ["N°", "CÉDULA", "NOMBRES Y APELLIDOS", "ÁREA", "HORAS", "CORREO", "FIRMA", ""]
    hh = 23
    pdf.setFillColor(azul)
    pdf.rect(30, y - hh + 4, ancho - 60, hh, stroke=0, fill=1)
    for x, w, titulo in zip(xs, ws, headers):
        _celda_texto(pdf, titulo, x, y - hh / 2 + 2, w, "Helvetica-Bold", 6.5, colors.white)
    y -= hh
    for i, t in enumerate(participantes, 1):
        nombre_lines = _lineas(pdf, t.get("nombre", ""), "Helvetica", 6.5, ws[2] - 8)
        area_lines = _lineas(pdf, t.get("area", ""), "Helvetica", 6.5, ws[3] - 8)
        rh = max(34, max(len(nombre_lines), len(area_lines)) * 9 + 12)
        if y - rh < 48:
            pdf.showPage()
            y = alto - 42
        pdf.setStrokeColor(colors.HexColor("#AEBBC9"))
        pdf.rect(30, y - rh + 4, ancho - 60, rh, stroke=1, fill=0)
        vals = [str(i), t["cedula"], t["nombre"], t["area"], str(t["_horas"]), "SN", ""]
        for x, w, val in zip(xs, ws, vals):
            _celda_texto(pdf, val, x, y - rh / 2 + 2, w, "Helvetica", 6.5)
        for x in xs[1:-1]:
            pdf.line(x, y - rh + 4, x, y + 4)
        y -= rh
    pdf.setFont("Helvetica", 7)
    pdf.drawString(30, 27, f"Facilitador: {datos['profesional'][:90]}")
    pdf.drawRightString(ancho - 30, 27, f"Responsable UATH: {datos['responsable_uath'][:90]}")
    pdf.save()
    return buffer.getvalue()


@require_POST
def generar_zip(request):
    _proteger(request)
    datos = _obtener_datos(request)
    if not datos or not datos.get("trabajadores"):
        return redirect("/totalcounts/certificados-sut/?error=Primero+carga+la+nómina")
    try:
        _guardar_formulario(request, datos)
    except ValueError as exc:
        return redirect(f"/totalcounts/certificados-sut/?error={str(exc)}")

    if not datos["empresa"] or not datos["responsable_uath"]:
        return redirect("/totalcounts/certificados-sut/?error=Completa+la+empresa+y+el+responsable+UATH")
    if any(not t.get("area") for t in datos["trabajadores"]):
        return redirect("/totalcounts/certificados-sut/?error=Asigna+un+área+de+trabajo+a+cada+trabajador")
    if not any(datos["temas"]):
        return redirect("/totalcounts/certificados-sut/?error=Ingresa+al+menos+una+temática")

    token = request.session.get(SESSION_KEY)
    cache.set(f"certificados_sut:{token}", datos, CACHE_TTL)
    salida = io.BytesIO()
    total_certificados = 0
    total_formatos = 0
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as archivo_zip:
        for indice_tema, tema in enumerate(datos["temas"]):
            if not tema:
                continue
            carpeta = _nombre_archivo(tema)
            participantes = []
            for trabajador in datos["trabajadores"]:
                horas = Decimal(trabajador.get("horas", ["0"] * TEMAS)[indice_tema])
                if horas <= 0:
                    continue
                participante = dict(trabajador)
                participante["_horas"] = str(horas)
                participantes.append(participante)
                nombre = _nombre_archivo(trabajador["nombre"])
                pdf_certificado = _crear_certificado(datos, trabajador, tema, horas)
                archivo_zip.writestr(f"{carpeta}/Certificados/{nombre}_{trabajador['cedula']}.pdf", pdf_certificado)
                total_certificados += 1
            archivo_zip.writestr(f"{carpeta}/01_Planificacion.pdf", _crear_planificacion(datos, tema, participantes))
            archivo_zip.writestr(f"{carpeta}/02_Registro_Asistencia.pdf", _crear_asistencia(datos, tema, participantes))
            total_formatos += 2

    if not total_certificados and not total_formatos:
        return redirect("/totalcounts/certificados-sut/?error=No+hay+temáticas+para+generar+documentos")
    respuesta = HttpResponse(salida.getvalue(), content_type="application/zip")
    respuesta["Content-Disposition"] = 'attachment; filename="certificados_sut.zip"'
    respuesta["X-Certificados-Generados"] = str(total_certificados)
    respuesta["X-Formatos-Generados"] = str(total_formatos)
    return respuesta


def limpiar(request):
    _proteger(request)
    token = request.session.pop(SESSION_KEY, None)
    if token:
        cache.delete(f"certificados_sut:{token}")
    return redirect("certificados_sut:inicio")
