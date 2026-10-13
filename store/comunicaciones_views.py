from django import forms
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils.html import escape
from .admin_views import admin_required
from .models.cliente import Cliente
from .models.comunicacion_cliente import ComunicacionCliente


class ComunicacionClienteForm(forms.ModelForm):
    class Meta:
        model = ComunicacionCliente
        fields = ("asunto", "titulo", "mensaje")
        widgets = {
            "asunto": forms.TextInput(attrs={"class": "com-input", "maxlength": 220}),
            "titulo": forms.TextInput(attrs={"class": "com-input", "maxlength": 220}),
            "mensaje": forms.Textarea(attrs={"class": "com-input", "rows": 12}),
        }


def _destinatarios():
    valores = Cliente.objects.filter(activo=True).exclude(corelectr__isnull=True).exclude(corelectr__exact="").values_list("corelectr", flat=True)
    resultado = set()
    for valor in valores:
        correo = (valor or "").strip().lower()
        if not correo:
            continue
        try:
            validate_email(correo)
        except ValidationError:
            continue
        resultado.add(correo)
    return sorted(resultado)


def _html(c):
    return f'<div style="font-family:Arial,sans-serif;max-width:680px;margin:auto"><div style="padding:25px;text-align:center"><img src="https://www.totalcounts.com.ec/static/images/logosvg.svg" alt="TotalCounts" width="190"></div><div style="padding:30px"><div style="color:#bd1020;font-weight:bold">COMUNICACIÓN A CLIENTES</div><h1>{escape(c.titulo or c.asunto)}</h1><div style="font-size:15px;line-height:1.75">{escape(c.mensaje).replace(chr(10), "<br>")}</div></div><div style="padding:18px;text-align:center;color:#718096">TotalCounts · Cuentas con nosotros</div></div>'


@admin_required
def admin_comunicaciones(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion in ("guardar", "prueba"):
            form = ComunicacionClienteForm(request.POST)
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
                            m = EmailMultiAlternatives(c.asunto, c.mensaje, settings.DEFAULT_FROM_EMAIL, [destino])
                            m.attach_alternative(_html(c), "text/html")
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
                lista = _destinatarios()
                if not lista:
                    messages.error(request, "No existen clientes activos con correo válido.")
                else:
                    c.estado = ComunicacionCliente.Estado.PENDIENTE
                    c.destinatarios = len(lista)
                    c.enviados = 0
                    c.fallidos = 0
                    c.error_detalle = ""
                    c.enviado_en = None
                    c.save(update_fields=["estado", "destinatarios", "enviados", "fallidos", "error_detalle", "enviado_en"])
                    messages.success(request, f"Comunicación puesta en cola para {len(lista)} clientes.")
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
def admin_comunicacion_enviar(request, comunicacion_id):
    if request.method != "POST":
        return redirect("admin_comunicaciones")
    return _encolar_comunicacion(request, comunicacion_id)


def _encolar_comunicacion(request, comunicacion_id):
    c = get_object_or_404(ComunicacionCliente, pk=comunicacion_id)
    if c.estado not in (ComunicacionCliente.Estado.BORRADOR, ComunicacionCliente.Estado.ERROR):
        messages.error(request, "Esta comunicación ya está en proceso o fue enviada.")
        return redirect("admin_comunicaciones")
    lista = _destinatarios()
    if not lista:
        messages.error(request, "No existen clientes activos con correo válido.")
        return redirect("admin_comunicaciones")
    c.estado = ComunicacionCliente.Estado.PENDIENTE
    c.destinatarios = len(lista)
    c.enviados = 0
    c.fallidos = 0
    c.error_detalle = ""
    c.enviado_en = None
    c.save(update_fields=["estado", "destinatarios", "enviados", "fallidos", "error_detalle", "enviado_en"])
    messages.success(request, f"Comunicación puesta en cola para {len(lista)} clientes.")
    return redirect("admin_comunicaciones")
