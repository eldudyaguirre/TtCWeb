from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from .admin_views import admin_required
from .models.noticia import CategoriaNoticia, EtiquetaNoticia, Noticia
from .models.suscriptor import Suscriptor
from .models.cliente import Cliente
from .blog_utils import sanitize_blog_html


class NoticiaAdminForm(forms.ModelForm):
    """Formulario editorial inspirado en el editor de H-Escapa, adaptado a Noticia."""
    class Meta:
        model = Noticia
        fields = (
            "titulo", "resumen", "contenido", "imagen_destacada",
            "texto_alternativo_imagen", "autor_nombre", "categoria", "etiquetas",
            "estado", "fecha_publicacion", "destacada",
            "meta_titulo", "meta_descripcion",
        )
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "blog-input", "maxlength": 220, "placeholder": "Título de la publicación"}),
            "resumen": forms.Textarea(attrs={"class": "blog-input", "rows": 3, "maxlength": 320, "placeholder": "Resumen que aparecerá en tarjetas y buscadores"}),
            "contenido": forms.HiddenInput(),
            "texto_alternativo_imagen": forms.TextInput(attrs={"class": "blog-input", "maxlength": 220, "placeholder": "Describe la imagen para accesibilidad"}),
            "autor_nombre": forms.TextInput(attrs={"class": "blog-input", "maxlength": 150, "placeholder": "Nombre que aparecerá como autor"}),
            "categoria": forms.Select(attrs={"class": "blog-input"}),
            "etiquetas": forms.SelectMultiple(attrs={"class": "blog-input", "size": 5}),
            "estado": forms.Select(attrs={"class": "blog-input"}),
            "fecha_publicacion": forms.DateTimeInput(attrs={"class": "blog-input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "meta_titulo": forms.TextInput(attrs={"class": "blog-input", "maxlength": 220, "placeholder": "Título para buscadores"}),
            "meta_descripcion": forms.Textarea(attrs={"class": "blog-input", "rows": 3, "maxlength": 320, "placeholder": "Descripción para buscadores"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = CategoriaNoticia.objects.filter(activa=True).order_by("nombre")
        self.fields["categoria"].required = False
        self.fields["etiquetas"].queryset = EtiquetaNoticia.objects.order_by("nombre")
        self.fields["etiquetas"].required = False
        self.fields["imagen_destacada"].required = False
        self.fields["fecha_publicacion"].required = False
        self.fields["destacada"].required = False
        self.fields["fecha_publicacion"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean_contenido(self):
        contenido = (self.cleaned_data.get("contenido") or "").strip()
        if not contenido:
            raise forms.ValidationError("Escribe el contenido de la publicación.")
        contenido = sanitize_blog_html(contenido)
        if not contenido.strip():
            raise forms.ValidationError("El contenido no incluye texto o formato permitido.")
        return contenido

    def clean_imagen_destacada(self):
        imagen = self.cleaned_data.get("imagen_destacada")
        if imagen and getattr(imagen, "size", 0) > 8 * 1024 * 1024:
            raise forms.ValidationError("La imagen no puede superar 8 MB.")
        return imagen

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("estado") == Noticia.Estado.PUBLICADO:
            fecha = cleaned.get("fecha_publicacion")
            if not fecha or fecha > timezone.now():
                cleaned["fecha_publicacion"] = timezone.now()
        return cleaned


def _enviar_aviso_publicacion(request, noticia):
    """Envía el anuncio una sola vez al publicar, sin exponer direcciones entre destinatarios."""
    suscriptores = Suscriptor.objects.filter(
        activo=True, consentimiento_marketing=True
    ).values_list("email", flat=True)
    clientes = Cliente.objects.filter(
        activo=True
    ).exclude(corelectr__isnull=True).exclude(corelectr__exact="").values_list("corelectr", flat=True)

    destinatarios = set()
    for email in list(suscriptores) + list(clientes):
        email = (email or "").strip().lower()
        if email and "@" in email:
            destinatarios.add(email)

    if not destinatarios:
        return 0, 0

    url = request.build_absolute_uri(reverse("blog_detalle", kwargs={"slug": noticia.slug}))
    titulo = escape(noticia.titulo)
    resumen = escape(noticia.resumen)
    asunto = f"Nuevo artículo de TotalCounts: {noticia.titulo}"
    texto = (
        f"Se ha publicado una nueva entrada en el Blog de TotalCounts.\n\n"
        f"{noticia.titulo}\n{noticia.resumen}\n\n"
        f"Lee la publicación completa: {url}\n\n"
        "Si ya no deseas recibir comunicaciones, utiliza las opciones de gestión disponibles en TotalCounts."
    )
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;color:#263238">'
        '<div style="background:#12343b;padding:24px;color:#fff"><h2 style="margin:0">TotalCounts | Blog</h2></div>'
        f'<div style="padding:24px"><p>Se ha publicado una nueva entrada:</p>'
        f'<h1 style="font-size:24px">{titulo}</h1><p>{resumen}</p>'
        f'<p><a href="{escape(url)}" style="display:inline-block;background:#00a6a6;color:#fff;padding:12px 18px;text-decoration:none;border-radius:6px">Leer artículo completo</a></p>'
        '<p style="font-size:12px;color:#718096">TotalCounts · Información tributaria y empresarial.</p></div></div>'
    )

    enviados = 0
    fallidos = 0
    lista = sorted(destinatarios)
    # BCC en grupos pequeños para proteger la privacidad y no exponer los correos.
    for inicio in range(0, len(lista), 40):
        grupo = lista[inicio:inicio + 40]
        try:
            mensaje = EmailMultiAlternatives(
                subject=asunto,
                body=texto,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.DEFAULT_FROM_EMAIL],
                bcc=grupo,
            )
            mensaje.attach_alternative(html, "text/html")
            mensaje.send(fail_silently=False)
            enviados += len(grupo)
        except Exception:
            fallidos += len(grupo)
    return enviados, fallidos


def _notificar_si_se_publico(request, noticia, ya_estaba_publicada):
    if noticia.estado != Noticia.Estado.PUBLICADO or ya_estaba_publicada:
        return
    enviados, fallidos = _enviar_aviso_publicacion(request, noticia)
    if fallidos:
        messages.warning(
            request,
            f'La publicación se guardó, pero no se pudo enviar el aviso a {fallidos} destinatarios. '
            f'Envíos completados: {enviados}. Revisa la configuración SMTP.',
        )
    else:
        messages.success(request, f'Aviso de publicación enviado a {enviados} destinatarios.')


def _save_noticia_form(request, form, noticia=None):
    # Leer el estado persistido antes de validar el ModelForm, porque la validación
    # puede actualizar form.instance con el estado enviado desde el formulario.
    pk_existente = getattr(form.instance, "pk", None)
    estado_anterior = (
        Noticia.objects.filter(pk=pk_existente).values_list("estado", flat=True).first()
        if pk_existente else None
    )
    if not form.is_valid():
        return None
    ya_estaba_publicada = estado_anterior == Noticia.Estado.PUBLICADO
    noticia = form.save(commit=False)
    noticia._ya_estaba_publicada = ya_estaba_publicada
    usuario = getattr(request, "user", None)
    if usuario is not None and usuario.is_authenticated:
        noticia.autor = usuario
    elif noticia.pk is None:
        noticia.autor = None
    if noticia.estado == Noticia.Estado.PUBLICADO and (
        noticia.fecha_publicacion is None or noticia.fecha_publicacion > timezone.now()
    ):
        noticia.fecha_publicacion = timezone.now()
    noticia.save()
    form.save_m2m()
    return noticia


@admin_required
def admin_blog(request):
    if request.method == "POST" and request.POST.get("accion") == "categoria":
        nombre = request.POST.get("nombre_categoria", "").strip()
        descripcion = request.POST.get("descripcion_categoria", "").strip()
        if not nombre or len(nombre) > 100:
            messages.error(request, "El nombre de la categoría es obligatorio y admite hasta 100 caracteres.")
        else:
            _, creada = CategoriaNoticia.objects.get_or_create(
                nombre=nombre,
                defaults={"descripcion": descripcion[:255]},
            )
            messages.success(request, "Categoría creada." if creada else "La categoría ya existía.")
            return redirect("admin_blog")
    if request.method == "POST" and request.POST.get("accion") != "categoria":
        form = NoticiaAdminForm(request.POST, request.FILES)
        noticia = _save_noticia_form(request, form)
        if noticia:
            _notificar_si_se_publico(request, noticia, getattr(noticia, "_ya_estaba_publicada", False))
            messages.success(request, f'La publicación “{noticia.titulo}” fue guardada.')
            return redirect("admin_blog")
        messages.error(request, "Revisa los campos señalados y vuelve a intentarlo.")
    else:
        form = NoticiaAdminForm(initial={"estado": Noticia.Estado.BORRADOR})

    return _blog_context_render(request, form, editar=False)


@admin_required
def admin_blog_editar(request, noticia_id):
    noticia = get_object_or_404(Noticia.objects.prefetch_related("etiquetas"), pk=noticia_id)
    if request.method == "POST":
        form = NoticiaAdminForm(request.POST, request.FILES, instance=noticia)
        guardada = _save_noticia_form(request, form, noticia)
        if guardada:
            _notificar_si_se_publico(request, guardada, getattr(guardada, "_ya_estaba_publicada", False))
            messages.success(request, f'La publicación “{guardada.titulo}” fue actualizada.')
            return redirect("admin_blog")
        messages.error(request, "Revisa los campos señalados y vuelve a intentarlo.")
    else:
        form = NoticiaAdminForm(instance=noticia)
    return _blog_context_render(request, form, editar=True, noticia=noticia)


@admin_required
def admin_blog_eliminar(request, noticia_id):
    if request.method != "POST":
        return redirect("admin_blog")
    noticia = get_object_or_404(Noticia, pk=noticia_id)
    titulo = noticia.titulo
    noticia.delete()
    messages.success(request, f'La publicación “{titulo}” fue eliminada.')
    return redirect("admin_blog")


@admin_required
def admin_blog_estado(request, noticia_id):
    if request.method != "POST":
        return redirect("admin_blog")
    noticia = get_object_or_404(Noticia, pk=noticia_id)
    ya_estaba_publicada = noticia.estado == Noticia.Estado.PUBLICADO
    estado = request.POST.get("estado", "").strip()
    if estado not in {Noticia.Estado.BORRADOR, Noticia.Estado.PUBLICADO, Noticia.Estado.ARCHIVADO}:
        messages.error(request, "Estado de publicación no válido.")
        return redirect("admin_blog")
    noticia.estado = estado
    if estado == Noticia.Estado.PUBLICADO and (
        noticia.fecha_publicacion is None or noticia.fecha_publicacion > timezone.now()
    ):
        noticia.fecha_publicacion = timezone.now()
    noticia.save(update_fields=["estado", "fecha_publicacion", "actualizado_en"])
    _notificar_si_se_publico(request, noticia, ya_estaba_publicada)
    messages.success(request, f'“{noticia.titulo}” ahora está {noticia.get_estado_display().lower()}.')
    return redirect("admin_blog")


@admin_required
def admin_blog_etiquetas(request):
    if request.method != "POST":
        return redirect("admin_blog")
    nombre = request.POST.get("nombre", "").strip()
    if not nombre or len(nombre) > 60:
        messages.error(request, "El nombre de etiqueta es obligatorio y debe tener hasta 60 caracteres.")
    else:
        _, creada = EtiquetaNoticia.objects.get_or_create(nombre=nombre)
        messages.success(request, "Etiqueta creada." if creada else "La etiqueta ya existía.")
    return redirect("admin_blog")


def _blog_context_render(request, form, editar=False, noticia=None):
    query = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "").strip()
    noticias = Noticia.objects.select_related("categoria", "autor").prefetch_related("etiquetas").order_by("-creado_en")
    if query:
        noticias = noticias.filter(
            models.Q(titulo__icontains=query) |
            models.Q(resumen__icontains=query) |
            models.Q(contenido__icontains=query)
        )
    if estado in {Noticia.Estado.BORRADOR, Noticia.Estado.PUBLICADO, Noticia.Estado.ARCHIVADO}:
        noticias = noticias.filter(estado=estado)
    return render(request, "admin/blog.html", {
        "form": form,
        "editar": editar,
        "noticia_actual": noticia,
        "noticias": noticias[:100],
        "noticias_total": Noticia.objects.count(),
        "noticias_publicadas": Noticia.objects.filter(estado=Noticia.Estado.PUBLICADO).count(),
        "noticias_borrador": Noticia.objects.filter(estado=Noticia.Estado.BORRADOR).count(),
        "noticias_archivadas": Noticia.objects.filter(estado=Noticia.Estado.ARCHIVADO).count(),
        "categorias": CategoriaNoticia.objects.filter(activa=True),
        "etiquetas": EtiquetaNoticia.objects.annotate(total=models.Count("noticias")).order_by("nombre"),
        "query": query,
        "estado": estado,
        "admin_usuario": request.session.get("admin_username", ""),
        "admin_nombre": request.session.get("admin_name", ""),
    })
