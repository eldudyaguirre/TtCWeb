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

    logo = _ruta_logo_mdt()
    if logo:
        pdf.drawImage(logo, 28, alto - 78, width=190, height=48, preserveAspectRatio=True, mask="auto")

    pdf.setStrokeColor(colors.HexColor("#173B63"))
    pdf.setLineWidth(5)
    pdf.rect(22, 22, ancho - 44, alto - 44, stroke=1, fill=0)
    pdf.setStrokeColor(colors.HexColor("#C5A24A"))
    pdf.setLineWidth(1.4)
    pdf.rect(30, 30, ancho - 60, alto - 60, stroke=1, fill=0)

    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawCentredString(ancho / 2, alto - 82, "CERTIFICADO DE CAPACITACIÓN")
    pdf.setFillColor(colors.HexColor("#333333"))
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(ancho / 2, alto - 125, "Se certifica que")

    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawCentredString(ancho / 2, alto - 165, trabajador["nombre"][:90])
    pdf.setFillColor(colors.HexColor("#333333"))
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(ancho / 2, alto - 190, f"Cédula: {trabajador['cedula']}")
    pdf.drawCentredString(ancho / 2, alto - 220, f"Ha participado en la capacitación organizada por {datos['empresa'][:100]}")

    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.setFont("Helvetica-Bold", 15)
    texto_tema = tema[:150]
    pdf.drawCentredString(ancho / 2, alto - 260, texto_tema)
    pdf.setFillColor(colors.HexColor("#333333"))
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(ancho / 2, alto - 290, f"Con una duración acreditada de {horas} horas.")

    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(ancho / 2, 105, f"Profesional encargado: {datos['profesional'][:100]}")
    pdf.drawCentredString(ancho / 2, 88, f"Responsable UATH: {datos['responsable_uath'][:100]}")
    pdf.setStrokeColor(colors.HexColor("#555555"))
    pdf.line(145, 72, 335, 72)
    pdf.line(ancho - 335, 72, ancho - 145, 72)
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(240, 57, "Firma del profesional encargado")
    pdf.drawCentredString(ancho - 240, 57, "Firma del responsable UATH")
    pdf.setFillColor(colors.HexColor("#666666"))
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(ancho - 48, 42, f"Emitido el {date.today().strftime('%d/%m/%Y')}")
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()



def _texto(canvas_pdf, texto, x, y, max_ancho, fuente="Helvetica", tam=8, interlineado=11):
    """Dibuja texto con ajuste de línea y devuelve la siguiente coordenada Y."""
    palabras = str(texto or "").split()
    lineas, actual = [], ""
    canvas_pdf.setFont(fuente, tam)
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        if canvas_pdf.stringWidth(prueba, fuente, tam) <= max_ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    for linea in lineas:
        canvas_pdf.drawString(x, y, linea)
        y -= interlineado
    return y


def _encabezado_pdf(pdf, ancho, alto, titulo, datos, tema):
    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.rect(0, alto - 12, ancho, 12, stroke=0, fill=1)
    logo = _ruta_logo_mdt()
    if logo:
        try:
            pdf.drawImage(logo, 32, alto - 92, width=205, height=62, preserveAspectRatio=True, mask="auto", anchor="c")
        except Exception:
            pass
    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawRightString(ancho - 35, alto - 48, "MINISTERIO DEL TRABAJO")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(ancho - 35, alto - 67, titulo.upper())
    y = alto - 112
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(36, y, "EMPRESA:")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(105, y, datos["empresa"][:100])
    y -= 17
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(36, y, "TEMA:")
    y = _texto(pdf, tema, 105, y, ancho - 145, "Helvetica", 9, 12) - 5
    pdf.setFont("Helvetica", 8)
    pdf.drawString(36, y, f"PERÍODO: {datos['fecha_inicio']}  AL  {datos['fecha_fin']}")
    y -= 14
    pdf.drawString(36, y, f"PROFESIONAL / FACILITADOR: {datos['profesional'][:95]}")
    y -= 14
    pdf.drawString(36, y, f"TELÉFONO: {datos['telefono'][:35]}    CORREO: {datos['email'][:75]}")
    y -= 14
    pdf.drawString(36, y, f"RESPONSABLE UATH: {datos['responsable_uath'][:100]}")
    return y - 20


def _crear_planificacion(datos, tema, participantes):
    buffer = io.BytesIO()
    pagina = A4
    ancho, alto = pagina
    pdf = canvas.Canvas(buffer, pagesize=pagina)
    pdf.setTitle(f"Planificación - {tema}")
    y = _encabezado_pdf(pdf, ancho, alto, "Planificación de capacitación con facilitadores internos", datos, tema)
    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(36, y, "PLANIFICACIÓN DE LA CAPACITACIÓN")
    y -= 24
    campos = [
        ("Objetivo", "Fortalecer los conocimientos y promover prácticas laborales con igualdad y sin discriminación, de acuerdo con la temática establecida."),
        ("Modalidad / lugar", "_______________________________________________"),
        ("Fecha(s) de ejecución", f"{datos['fecha_inicio']} al {datos['fecha_fin']}"),
        ("Facilitador interno", datos["profesional"]),
        ("Duración planificada", "Según las horas registradas para los participantes en esta temática."),
        ("Metodología", "Exposición, diálogo participativo y revisión de situaciones relacionadas con la temática."),
        ("Recursos", "Material de apoyo, presentación y registro de asistencia."),
        ("Evaluación", "Verificación de participación y comprensión de los contenidos tratados."),
    ]
    for etiqueta, valor in campos:
        pdf.setFillColor(colors.HexColor("#173B63"))
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(38, y, etiqueta.upper() + ":")
        y = _texto(pdf, valor, 155, y, ancho - 190, "Helvetica", 8, 11) - 13
    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(38, y, "PARTICIPANTES CON HORAS REGISTRADAS")
    y -= 18
    pdf.setFillColor(colors.HexColor("#E8EEF5"))
    pdf.rect(36, y - 4, ancho - 72, 18, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(42, y + 2, "N°")
    pdf.drawString(66, y + 2, "NOMBRE")
    pdf.drawString(300, y + 2, "ÁREA")
    pdf.drawRightString(ancho - 42, y + 2, "HORAS")
    y -= 16
    for i, t in enumerate(participantes, 1):
        if y < 95:
            pdf.showPage()
            y = alto - 55
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 7)
        pdf.drawString(42, y, str(i))
        pdf.drawString(66, y, t["nombre"][:43])
        pdf.drawString(300, y, t["area"][:28])
        pdf.drawRightString(ancho - 42, y, str(t["_horas"]))
        pdf.setStrokeColor(colors.HexColor("#D5DDE6"))
        pdf.line(36, y - 5, ancho - 36, y - 5)
        y -= 17
    y = min(y - 12, 85)
    pdf.setStrokeColor(colors.HexColor("#555555"))
    pdf.line(55, 55, 245, 55)
    pdf.line(ancho - 245, 55, ancho - 55, 55)
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(150, 43, "Firma del facilitador interno")
    pdf.drawCentredString(ancho - 150, 43, "Firma Responsable UATH")
    pdf.save()
    return buffer.getvalue()


def _crear_asistencia(datos, tema, participantes):
    buffer = io.BytesIO()
    pagina = landscape(A4)
    ancho, alto = pagina
    pdf = canvas.Canvas(buffer, pagesize=pagina)
    pdf.setTitle(f"Registro de asistencia - {tema}")
    y = _encabezado_pdf(pdf, ancho, alto, "Registro de asistencia", datos, tema)
    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(36, y, "REGISTRO DE PARTICIPANTES")
    y -= 22
    xcols = [38, 65, 275, 405, 475, 590, 735]
    headers = ["N°", "CÉDULA", "NOMBRES Y APELLIDOS", "ÁREA", "HORAS", "CORREO", "FIRMA"]
    widths = [27, 210, 130, 68, 115, 145]
    pdf.setFillColor(colors.HexColor("#173B63"))
    pdf.rect(36, y - 5, ancho - 72, 22, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 7)
    for x, h in zip(xcols, headers):
        pdf.drawString(x, y + 3, h)
    y -= 23
    for i, t in enumerate(participantes, 1):
        if y < 55:
            pdf.showPage()
            y = alto - 45
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 7)
        vals = [str(i), t["cedula"], t["nombre"][:35], t["area"][:22], str(t["_horas"]), "SN", ""]
        for x, val in zip(xcols, vals):
            pdf.drawString(x, y, val)
        pdf.setStrokeColor(colors.HexColor("#B8C4D1"))
        pdf.line(36, y - 8, ancho - 36, y - 8)
        y -= 30
    pdf.setFont("Helvetica", 8)
    pdf.drawString(38, 35, f"Facilitador: {datos['profesional'][:90]}")
    pdf.drawRightString(ancho - 38, 35, f"Responsable UATH: {datos['responsable_uath'][:90]}")
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
            if participantes:
                archivo_zip.writestr(f"{carpeta}/01_Planificacion.pdf", _crear_planificacion(datos, tema, participantes))
                archivo_zip.writestr(f"{carpeta}/02_Registro_Asistencia.pdf", _crear_asistencia(datos, tema, participantes))
                total_formatos += 2

    if not total_certificados:
        return redirect("/totalcounts/certificados-sut/?error=No+hay+horas+mayores+a+cero+para+generar+documentos")
    respuesta = HttpResponse(salida.getvalue(), content_type="application/zip")
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
