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
    datos["temas"] = [request.POST.get(f"tema_{i}", "").strip() for i in range(1, TEMAS + 1)]

    trabajadores = datos.get("trabajadores", [])
    for indice, trabajador in enumerate(trabajadores):
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


def _crear_certificado(datos, trabajador, tema, horas):
    buffer = io.BytesIO()
    pagina = landscape(A4)
    ancho, alto = pagina
    pdf = canvas.Canvas(buffer, pagesize=pagina)
    pdf.setTitle(f"Certificado - {trabajador['nombre']}")

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
    if not any(datos["temas"]):
        return redirect("/totalcounts/certificados-sut/?error=Ingresa+al+menos+una+temática")

    token = request.session.get(SESSION_KEY)
    cache.set(f"certificados_sut:{token}", datos, CACHE_TTL)
    salida = io.BytesIO()
    total = 0
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as archivo_zip:
        for indice_tema, tema in enumerate(datos["temas"]):
            if not tema:
                continue
            carpeta = _nombre_archivo(tema)
            for trabajador in datos["trabajadores"]:
                horas = Decimal(trabajador.get("horas", ["0"] * TEMAS)[indice_tema])
                if horas <= 0:
                    continue
                nombre = _nombre_archivo(trabajador["nombre"])
                pdf = _crear_certificado(datos, trabajador, tema, horas)
                archivo_zip.writestr(f"{carpeta}/{nombre}_{trabajador['cedula']}.pdf", pdf)
                total += 1

    if not total:
        return redirect("/totalcounts/certificados-sut/?error=No+hay+horas+mayores+a+cero+para+generar+certificados")
    respuesta = HttpResponse(salida.getvalue(), content_type="application/zip")
    respuesta["Content-Disposition"] = 'attachment; filename="certificados_sut.zip"'
    respuesta["X-Certificados-Generados"] = str(total)
    return respuesta


def limpiar(request):
    _proteger(request)
    token = request.session.pop(SESSION_KEY, None)
    if token:
        cache.delete(f"certificados_sut:{token}")
    return redirect("certificados_sut:inicio")
