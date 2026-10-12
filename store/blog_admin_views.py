from django import forms
from django.contrib import messages
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .admin_views import admin_required
from .models.noticia import CategoriaNoticia, EtiquetaNoticia, Noticia
from .blog_utils import sanitize_blog_html


class NoticiaAdminForm(forms.ModelForm):
    """Formulario editorial inspirado en el editor de H-Escapa, adaptado a Noticia."""
    class Meta:
        model = Noticia
        fields = (
            "titulo", "resumen", "contenido", "imagen_destacada",
            "texto_alternativo_imagen", "categoria", "etiquetas",
            "estado", "fecha_publicacion", "destacada",
            "meta_titulo", "meta_descripcion",
        )
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "blog-input", "maxlength": 220, "placeholder": "Título de la publicación"}),
            "resumen": forms.Textarea(attrs={"class": "blog-input", "rows": 3, "maxlength": 320, "placeholder": "Resumen que aparecerá en tarjetas y buscadores"}),
            "contenido": forms.HiddenInput(),
            "texto_alternativo_imagen": forms.TextInput(attrs={"class": "blog-input", "maxlength": 220, "placeholder": "Describe la imagen para accesibilidad"}),
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


def _save_noticia_form(request, form, noticia=None):
    if not form.is_valid():
        return None
    noticia = form.save(commit=False)
    noticia.autor = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    if noticia.estado == Noticia.Estado.PUBLICADO and (
        noticia.fecha_publicacion is None or noticia.fecha_publicacion > timezone.now()
    ):
        noticia.fecha_publicacion = timezone.now()
    noticia.save()
    form.save_m2m()
    return noticia


@admin_required
def admin_blog(request):
    if request.method == "POST":
        form = NoticiaAdminForm(request.POST, request.FILES)
        noticia = _save_noticia_form(request, form)
        if noticia:
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
    estado = request.POST.get("estado", "").strip()
    if estado not in {Noticia.Estado.BORRADOR, Noticia.Estado.PUBLICADO}:
        messages.error(request, "Estado de publicación no válido.")
        return redirect("admin_blog")
    noticia.estado = estado
    if estado == Noticia.Estado.PUBLICADO and (
        noticia.fecha_publicacion is None or noticia.fecha_publicacion > timezone.now()
    ):
        noticia.fecha_publicacion = timezone.now()
    noticia.save(update_fields=["estado", "fecha_publicacion", "actualizado_en"])
    messages.success(request, f'“{noticia.titulo}” ahora está {noticia.get_estado_display().lower()}.')
    return redirect("admin_blog")


@admin_required
def admin_blog_etiquetas(request):
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        if not nombre or len(nombre) > 60:
            messages.error(request, "El nombre de etiqueta es obligatorio y debe tener hasta 60 caracteres.")
        else:
            _, creada = EtiquetaNoticia.objects.get_or_create(nombre=nombre)
            messages.success(request, "Etiqueta creada." if creada else "La etiqueta ya existía.")
            return redirect("admin_blog_etiquetas")
    etiquetas = EtiquetaNoticia.objects.annotate(total= models.Count("noticias")).order_by("nombre")
    return render(request, "admin/blog_etiquetas.html", {
        "etiquetas": etiquetas,
        "admin_usuario": request.session.get("admin_username", ""),
        "admin_nombre": request.session.get("admin_name", ""),
    })


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
    if estado in {Noticia.Estado.BORRADOR, Noticia.Estado.PUBLICADO}:
        noticias = noticias.filter(estado=estado)
    return render(request, "admin/blog.html", {
        "form": form,
        "editar": editar,
        "noticia_actual": noticia,
        "noticias": noticias[:100],
        "noticias_total": Noticia.objects.count(),
        "noticias_publicadas": Noticia.objects.filter(estado=Noticia.Estado.PUBLICADO).count(),
        "noticias_borrador": Noticia.objects.filter(estado=Noticia.Estado.BORRADOR).count(),
        "categorias": CategoriaNoticia.objects.filter(activa=True),
        "etiquetas": EtiquetaNoticia.objects.order_by("nombre"),
        "query": query,
        "estado": estado,
        "admin_usuario": request.session.get("admin_username", ""),
        "admin_nombre": request.session.get("admin_name", ""),
    })
