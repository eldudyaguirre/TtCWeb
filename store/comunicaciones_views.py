from django import forms
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import escape
from .admin_views import admin_required
from .models.cliente import Cliente
from .models.comunicacion_cliente import ComunicacionCliente

class ComunicacionClienteForm(forms.ModelForm):
    class Meta:
        model=ComunicacionCliente; fields=("asunto","titulo","mensaje")
        widgets={"asunto":forms.TextInput(attrs={"class":"com-input","maxlength":220}),"titulo":forms.TextInput(attrs={"class":"com-input","maxlength":220}),"mensaje":forms.Textarea(attrs={"class":"com-input","rows":12})}

def _destinatarios():
    valores=Cliente.objects.filter(activo=True).exclude(corelectr__isnull=True).exclude(corelectr__exact="").values_list("corelectr",flat=True)
    return sorted({e.strip().lower() for e in valores if e and "@" in e})

def _html(c):
    return f'<div style="font-family:Arial,sans-serif;max-width:680px;margin:auto"><div style="padding:25px;text-align:center"><img src="https://www.totalcounts.com.ec/static/images/logosvg.svg" alt="TotalCounts" width="190"></div><div style="padding:30px"><div style="color:#bd1020;font-weight:bold">COMUNICACIÓN A CLIENTES</div><h1>{escape(c.titulo or c.asunto)}</h1><div style="font-size:15px;line-height:1.75">{escape(c.mensaje).replace(chr(10),"<br>")}</div></div><div style="padding:18px;text-align:center;color:#718096">TotalCounts · Cuentas con nosotros</div></div>'

def _enviar(c,lista):
    enviados=fallidos=0; errores=[]
    for i in range(0,len(lista),40):
        grupo=lista[i:i+40]
        try:
            m=EmailMultiAlternatives(c.asunto,c.mensaje,settings.DEFAULT_FROM_EMAIL,[settings.DEFAULT_FROM_EMAIL],bcc=grupo); m.attach_alternative(_html(c),"text/html"); m.send(fail_silently=False); enviados+=len(grupo)
        except Exception as exc: fallidos+=len(grupo); errores.append(str(exc)[:500])
    return enviados,fallidos,errores

@admin_required
def admin_comunicaciones(request):
    if request.method=="POST":
        accion=request.POST.get("accion")
        if accion in ("guardar","prueba"):
            form=ComunicacionClienteForm(request.POST)
            if form.is_valid():
                if accion=="prueba":
                    destino=request.POST.get("correo_prueba","").strip().lower()
                    if destino and "@" in destino:
                        c=form.save(commit=False)
                        try:
                            m=EmailMultiAlternatives(c.asunto,c.mensaje,settings.DEFAULT_FROM_EMAIL,[destino]); m.attach_alternative(_html(c),"text/html"); m.send(fail_silently=False); messages.success(request,"Correo de prueba enviado.")
                        except Exception as exc: messages.error(request,f"No se pudo enviar la prueba: {exc}")
                    else: messages.error(request,"Ingresa un correo válido para la prueba.")
                else:
                    c=form.save(commit=False); c.creado_por=request.session.get("admin_name") or request.session.get("admin_username",""); c.save(); messages.success(request,"Comunicación guardada como borrador."); return redirect("admin_comunicaciones")
        elif accion=="enviar":
            c=get_object_or_404(ComunicacionCliente,pk=request.POST.get("comunicacion_id")); lista=_destinatarios()
            if not lista: messages.error(request,"No existen clientes activos con correo válido.")
            else:
                c.estado=ComunicacionCliente.Estado.ENVIANDO; c.destinatarios=len(lista); c.save(); enviados,fallidos,errores=_enviar(c,lista); c.enviados=enviados; c.fallidos=fallidos; c.estado=ComunicacionCliente.Estado.ENVIADO if not fallidos else ComunicacionCliente.Estado.ERROR; c.enviado_en=timezone.now(); c.error_detalle="\n".join(errores); c.save(); messages.success(request,f"Envío terminado: {enviados} enviados, {fallidos} con error."); return redirect("admin_comunicaciones")
    else: form=ComunicacionClienteForm()
    return render(request,"admin/comunicaciones.html",{"form":form,"comunicaciones":ComunicacionCliente.objects.all()[:50],"total_activos":Cliente.objects.filter(activo=True).count(),"con_correo":len(_destinatarios())})

@admin_required
def admin_comunicacion_enviar(request,comunicacion_id):
    if request.method!="POST": return redirect("admin_comunicaciones")
    data=request.POST.copy(); data["accion"]="enviar"; data["comunicacion_id"]=str(comunicacion_id); request.POST=data; return admin_comunicaciones(request)
