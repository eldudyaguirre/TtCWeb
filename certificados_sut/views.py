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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

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
    """Genera el certificado acuarela usando las fuentes Bobby Jones y Ruthie."""
    buffer = io.BytesIO()
    pagina = landscape(A4)
    ancho, alto = pagina
    pdf = canvas.Canvas(buffer, pagesize=pagina)
    pdf.setTitle(f"Certificado - {trabajador['nombre']}")

    # Cargar y registrar las fuentes TrueType para incrustarlas en el PDF.
    def _registrar_fuente(nombre_registro, ruta_relativa):
        if nombre_registro in pdfmetrics.getRegisteredFontNames():
            return nombre_registro
        ruta = finders.find(ruta_relativa)
        if not ruta:
            candidata = settings.BASE_DIR / "static" / ruta_relativa
            ruta = str(candidata) if candidata.exists() else None
        if ruta:
            pdfmetrics.registerFont(TTFont(nombre_registro, ruta))
            return nombre_registro
        return None

    fuente_bobby = _registrar_fuente("BobbyJonesCondensed", "fonts/bobby-jones-condensed.ttf")
    fuente_ruthie = _registrar_fuente("RuthieScript", "fonts/Ruthie.ttf")
    fuente_titulo = fuente_bobby or "Helvetica-Bold"
    fuente_nombre = fuente_ruthie or "Times-Italic"

    # Plantilla gráfica de fondo, sin datos variables.
    fondo = finders.find("images/Fondo-certificado.png")
    if not fondo:
        candidata = settings.BASE_DIR / "static" / "images" / "Fondo-certificado.png"
        fondo = str(candidata) if candidata.exists() else None
    if fondo:
        pdf.drawImage(fondo, 0, 0, width=ancho, height=alto, preserveAspectRatio=False, mask="auto")
    else:
        # Fondo de respaldo decorativo: nunca dejar el certificado completamente blanco.
        pdf.setFillColor(colors.HexColor("#FBFDFE"))
        pdf.rect(0, 0, ancho, alto, stroke=0, fill=1)
        pdf.saveState()
        try:
            pdf.setFillAlpha(0.28)
        except Exception:
            pass
        pdf.setFillColor(colors.HexColor("#E8BFCB"))
        pdf.ellipse(-45, alto - 95, 105, alto + 35, stroke=0, fill=1)
        pdf.setFillColor(colors.HexColor("#BFE3E9"))
        pdf.ellipse(15, alto - 68, 145, alto + 35, stroke=0, fill=1)
        pdf.setFillColor(colors.HexColor("#E8BFCB"))
        pdf.ellipse(ancho - 95, -38, ancho + 45, 92, stroke=0, fill=1)
        pdf.setFillColor(colors.HexColor("#BFE3E9"))
        pdf.ellipse(ancho - 145, -25, ancho - 5, 95, stroke=0, fill=1)
        pdf.restoreState()
        # Esquinas triangulares doradas y líneas geométricas finas.
        pdf.setFillColor(colors.HexColor("#F3DE98"))
        p = pdf.beginPath()
        p.moveTo(ancho - 105, alto)
        p.lineTo(ancho, alto)
        p.lineTo(ancho, alto - 105)
        p.close()
        pdf.drawPath(p, stroke=0, fill=1)
        p = pdf.beginPath()
        p.moveTo(0, 0)
        p.lineTo(105, 0)
        p.lineTo(0, 105)
        p.close()
        pdf.drawPath(p, stroke=0, fill=1)
        pdf.setStrokeColor(colors.HexColor("#202020"))
        pdf.setLineWidth(0.7)
        pdf.line(ancho - 210, alto - 18, ancho - 28, alto - 18)
        pdf.line(ancho - 28, alto - 18, ancho - 28, alto - 155)
        pdf.line(18, 155, 18, 18)
        pdf.line(18, 18, 165, 18)
        # Sello dorado inferior derecho.
        pdf.setFillColor(colors.HexColor("#B78B2F"))
        pdf.circle(ancho - 58, 62, 27, stroke=0, fill=1)
        pdf.setFillColor(colors.HexColor("#F4D77C"))
        pdf.circle(ancho - 58, 62, 22, stroke=0, fill=1)
        pdf.setFillColor(colors.HexColor("#D6AD45"))
        pdf.circle(ancho - 58, 62, 16, stroke=0, fill=1)

    tinta = colors.HexColor("#101820")
    gris = colors.HexColor("#46515B")
    centro = ancho / 2

    # Composición ampliada: proporciones más cercanas al arte original de Canva.
    # El título y los textos condensados usan Bobby Jones; el nombre usa Ruthie.
    pdf.setFillColor(tinta)

    def _centrar_ajustado(texto, fuente, tam, y, max_ancho, minimo=9):
        actual = tam
        while actual > minimo and pdfmetrics.stringWidth(texto, fuente, actual) > max_ancho:
            actual -= 1
        pdf.setFont(fuente, actual)
        pdf.drawCentredString(centro, y, texto)

    # Canva: Bobby Jones Condensed, tamaño 64.5, interlineado 1.4 e interletrado 302.
    # En PDF se representa el interletrado 302 como 3.02 pt de separación entre caracteres.
    def _centrar_con_interletrado(texto, fuente, tam, tracking, y, escala_x=100):
        # Aislar el estado tipográfico: Tc/Tz de PDF persisten entre objetos
        # de texto si no se restaura el estado gráfico.
        pdf.saveState()
        try:
            objeto = pdf.beginText()
            objeto.setFont(fuente, tam)
            objeto.setCharSpace(tracking)
            objeto.setHorizScale(escala_x)
            ancho_base = pdfmetrics.stringWidth(texto, fuente, tam) + max(0, len(texto) - 1) * tracking
            ancho_texto = ancho_base * escala_x / 100
            objeto.setTextOrigin((ancho - ancho_texto) / 2, y)
            objeto.textOut(texto)
            pdf.drawText(objeto)
        finally:
            pdf.restoreState()

    # Solo CERTIFICADO lleva el interletrado de Canva. El estado de texto
    # se restaura inmediatamente para que los demás textos no hereden Tc/Tz.
    _centrar_con_interletrado("CERTIFICADO", fuente_titulo, 64.5, 3.02, alto - 112, escala_x=155)
    # Distancia vertical basada en el interlineado 1.4 del diseño original.
    _centrar_ajustado("DE CAPACITACIÓN", fuente_titulo, 31, alto - 174, ancho - 220, 22)
    _centrar_ajustado("ESTE CERTIFICADO SE OTORGA A", fuente_titulo, 16, alto - 235, ancho - 250, 11)

    # Nombre protagonista, como en la plantilla de referencia.
    nombre = trabajador.get("nombre", "").strip().title()
    tam_nombre = 43
    while tam_nombre > 27 and pdfmetrics.stringWidth(nombre, fuente_nombre, tam_nombre) > ancho - 180:
        tam_nombre -= 1
    pdf.setFillColor(colors.HexColor("#111111"))
    pdf.setFont(fuente_nombre, tam_nombre)
    pdf.drawCentredString(centro, alto - 292, nombre)

    pdf.setFillColor(gris)
    _centrar_ajustado(f"CÉDULA: {trabajador['cedula']}", fuente_titulo, 12, alto - 318, ancho - 240, 9)

    empresa = datos.get("empresa", "").strip()
    frase = f"EN RECONOCIMIENTO POR SU PARTICIPACIÓN EN LA CAPACITACIÓN ORGANIZADA POR {empresa}"
    # Limitar el ancho real del texto y dividirlo en líneas antes de centrar.
    # Se deja margen generoso para que ninguna razón social quede cortada.
    lineas_frase = _lineas(pdf, frase, fuente_titulo, 12, ancho - 260)
    pdf.setFillColor(tinta)
    y = alto - 365
    for linea in lineas_frase[:3]:
        _centrar_ajustado(linea, fuente_titulo, 12, y, ancho - 260, 9)
        y -= 17

    tema = tema.strip()
    lineas_tema = _lineas(pdf, tema, fuente_titulo, 16, ancho - 240)
    y = alto - 430
    for linea in lineas_tema[:2]:
        _centrar_ajustado(linea, fuente_titulo, 16, y, ancho - 240, 10)
        y -= 19

    pdf.setFillColor(gris)
    _centrar_ajustado(f"DURACIÓN ACREDITADA: {horas} HORAS", fuente_titulo, 15, alto - 472, ancho - 230, 10)

    # Dos espacios de firma y sus responsables.
    y_firma = 66
    pdf.setStrokeColor(colors.HexColor("#333333"))
    pdf.setLineWidth(0.7)
    pdf.line(145, y_firma, 335, y_firma)
    pdf.line(ancho - 335, y_firma, ancho - 145, y_firma)
    pdf.setFillColor(tinta)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(240, 49, "Psi.Cli Hester Palacio Segovia")
    pdf.drawCentredString(ancho - 240, 49, "Dudy Aguirre")
    pdf.setFillColor(gris)
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
