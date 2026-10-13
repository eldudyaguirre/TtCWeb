from django import forms
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils.html import escape, strip_tags
import mimetypes

from .admin_views import admin_required
from .models.cliente import Cliente
from .models.comunicacion_cliente import ComunicacionCliente
from .blog_utils import sanitize_blog_html


class ComunicacionClienteForm(forms.ModelForm):
    destinatario_email = forms.ChoiceField(
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "com-input", "id": "id_destinatario_email"}),
    )

    class Meta:
        model = ComunicacionCliente
        fields = ("asunto", "titulo", "mensaje", "destinatario_tipo", "destinatario_email", "imagen_adjunto")
        widgets = {
            "asunto": forms.TextInput(attrs={"class": "com-input", "maxlength": 220}),
            "titulo": forms.TextInput(attrs={"class": "com-input", "maxlength": 220}),
            "mensaje": forms.HiddenInput(),
            "destinatario_tipo": forms.Select(attrs={"class": "com-input", "id": "id_destinatario_tipo"}),
            "imagen_adjunto": forms.ClearableFileInput(attrs={"class": "com-input", "accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destinatario_tipo"].choices = ComunicacionCliente.TipoDestinatario.choices
        self.fields["destinatario_email"].choices = [("", "Selecciona un cliente")] + _opciones_destinatario()
        self.fields["imagen_adjunto"].required = False

    def clean_mensaje(self):
        contenido = sanitize_blog_html((self.cleaned_data.get("mensaje") or "").strip())
        if not strip_tags(contenido).strip():
            raise forms.ValidationError("Escribe el contenido de la comunicación.")
        return contenido

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("destinatario_tipo") == ComunicacionCliente.TipoDestinatario.INDIVIDUAL:
            correo = (cleaned.get("destinatario_email") or "").strip().lower()
            if not correo:
                self.add_error("destinatario_email", "Selecciona el cliente que recibirá la comunicación.")
            else:
                try:
                    validate_email(correo)
                except ValidationError:
                    self.add_error("destinatario_email", "El correo seleccionado no es válido.")
                else:
                    cleaned["destinatario_email"] = correo
        else:
            cleaned["destinatario_email"] = ""

        imagen = cleaned.get("imagen_adjunto")
        if imagen:
            if not (getattr(imagen, "content_type", "") or "").startswith("image/"):
                self.add_error("imagen_adjunto", "El archivo adjunto debe ser una imagen.")
            elif imagen.size > 8 * 1024 * 1024:
                self.add_error("imagen_adjunto", "La imagen no puede superar 8 MB.")
        return cleaned


def _opciones_destinatario():
    clientes = Cliente.objects.filter(activo=True).exclude(corelectr__isnull=True).exclude(corelectr__exact="").order_by("nomclient", "ruccedcli")
    opciones = {}
    for cliente in clientes:
        correo = (cliente.corelectr or "").strip().lower()
        try:
            validate_email(correo)
        except ValidationError:
            continue
        etiqueta = f"{cliente.nomclient or 'Cliente'} · {cliente.ruccedcli} · {correo}"
        opciones.setdefault(correo, etiqueta)
    return [(correo, etiqueta) for correo, etiqueta in sorted(opciones.items(), key=lambda item: item[1].lower())]


def _destinatarios():
    return [correo for correo, _ in _opciones_destinatario()]


def _lista_para_comunicacion(c):
    if c.estado == ComunicacionCliente.Estado.ERROR and c.correos_pendientes:
        return [e.strip() for e in c.correos_pendientes.splitlines() if e.strip()]
    if c.destinatario_tipo == ComunicacionCliente.TipoDestinatario.INDIVIDUAL:
        correo = (c.destinatario_email or "").strip().lower()
        try:
            validate_email(correo)
        except ValidationError:
            return []
        return [correo]
    return _destinatarios()


def _html(c):
    contenido = sanitize_blog_html(c.mensaje or "")
    return (
        '<div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#263238;background:#fff">'
        '<div style="padding:25px;text-align:center"><img src="https://www.totalcounts.com.ec/static/images/logosvg.svg" '
        'alt="TotalCounts" width="190" style="max-width:100%;height:auto"></div>'
        '<div style="padding:30px"><div style="color:#bd1020;font-weight:bold">COMUNICACIÓN A CLIENTES</div>'
        f'<h1 style="font-size:26px;line-height:1.3">{escape(c.titulo or c.asunto)}</h1>'
        f'<div style="font-size:15px;line-height:1.75">{contenido}</div></div>'
        '<div style="padding:18px;text-align:center;color:#718096">TotalCounts · Cuentas con nosotros</div></div>'
    )


def _adjuntar_imagen(mensaje, comunicacion):
    imagen = comunicacion.imagen_adjunto
    if imagen and imagen.name:
        nombre = imagen.name.rsplit("/", 1)[-1].rsplit("\\\\", 1)[-1]
        tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
        imagen.open("rb")
        try:
            contenido = imagen.read()
        finally:
            imagen.close()
        mensaje.attach(nombre, contenido, tipo)


def _encolar(c, lista):
    reintento = c.estado == ComunicacionCliente.Estado.ERROR and bool(c.correos_pendientes)
    c.estado = ComunicacionCliente.Estado.PENDIENTE
    if not reintento:
        c.destinatarios = len(lista)
        c.enviados = 0
        c.fallidos = 0
    c.correos_pendientes = "\\n".join(lista)
    c.error_detalle = ""
    c.enviado_en = None
    c.save(update_fields=["estado", "destinatarios", "correos_pendientes", "error_detalle", "enviado_en", "enviados", "fallidos"])


@admin_required
def admin_comunicaciones(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion in ("guardar", "prueba"):
            form = ComunicacionClienteForm(request.POST, request.FILES)
            if form.is_valid():
                if accion == "prueba":
                    destino = request.POST.get("correo_prueba", "").strip().lower()
                    try:
                        validate_email(destino)
                    except ValidationError:
                        messages.error(request, "Ingresa un correo válido para la prueba.")
                    else:
                        c = form.save(commit=False)
                        try:
                            texto = strip_tags(c.mensaje).replace("\\n", "\n")
                            m = EmailMultiAlternatives(c.asunto, texto, settings.DEFAULT_FROM_EMAIL, [destino])
                            m.attach_alternative(_html(c), "text/html")
                            _adjuntar_imagen(m, c)
                            m.send(fail_silently=False)
                            messages.success(request, "Correo de prueba enviado.")
                        except Exception as exc:
                            messages.error(request, f"No se pudo enviar la prueba: {exc}")
                else:
                    c = form.save(commit=False)
                    c.creado_por = request.session.get("admin_name") or request.session.get("admin_username", "")
                    c.save()
                    messages.success(request, "Comunicación guardada como borrador.")
                    return redirect("admin_comunicaciones")
        elif accion == "enviar":
            c = get_object_or_404(ComunicacionCliente, pk=request.POST.get("comunicacion_id"))
            if c.estado not in (ComunicacionCliente.Estado.BORRADOR, ComunicacionCliente.Estado.ERROR):
                messages.error(request, "Esta comunicación ya está en proceso o fue enviada.")
            else:
                lista = _lista_para_comunicacion(c)
                if not lista:
                    messages.error(request, "No existen destinatarios válidos para esta comunicación.")
                else:
                    _encolar(c, lista)
                    messages.success(request, f"Comunicación puesta en cola para {len(lista)} destinatario(s).")
            return redirect("admin_comunicaciones")
    else:
        form = ComunicacionClienteForm()
    return render(request, "admin/comunicaciones.html", {
        "form": form,
        "comunicaciones": ComunicacionCliente.objects.all()[:50],
        "total_activos": Cliente.objects.filter(activo=True).count(),
        "con_correo": len(_destinatarios()),
    })


@admin_required
def admin_comunicacion_eliminar(request, comunicacion_id):
    if request.method != "POST":
        return redirect("admin_comunicaciones")

    c = get_object_or_404(ComunicacionCliente, pk=comunicacion_id)
    if c.estado != ComunicacionCliente.Estado.BORRADOR:
        messages.error(request, "Solo se pueden eliminar comunicaciones que sigan en estado Borrador.")
        return redirect("admin_comunicaciones")

    if c.imagen_adjunto:
        c.imagen_adjunto.delete(save=False)
    c.delete()
    messages.success(request, "Borrador eliminado correctamente.")
    return redirect("admin_comunicaciones")


@admin_required
def admin_comunicacion_enviar(request, comunicacion_id):
    if request.method != "POST":
        return redirect("admin_comunicaciones")
    return _encolar_desde_id(request, comunicacion_id)


def _encolar_desde_id(request, comunicacion_id):
    c = get_object_or_404(ComunicacionCliente, pk=comunicacion_id)
    if c.estado not in (ComunicacionCliente.Estado.BORRADOR, ComunicacionCliente.Estado.ERROR):
        messages.error(request, "Esta comunicación ya está en proceso o fue enviada.")
        return redirect("admin_comunicaciones")
    lista = _lista_para_comunicacion(c)
    if not lista:
        messages.error(request, "No existen destinatarios válidos para esta comunicación.")
        return redirect("admin_comunicaciones")
    _encolar(c, lista)
    messages.success(request, f"Comunicación puesta en cola para {len(lista)} destinatario(s).")
    return redirect("admin_comunicaciones")
