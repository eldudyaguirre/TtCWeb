from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .admin_views import admin_required
from .models.noticia import CategoriaNoticia, Noticia


@admin_required
def admin_blog(request):
    """Panel del blog: crear publicaciones y administrar su estado."""
    if request.method == "POST":
        accion = request.POST.get("accion", "crear")

        if accion == "estado":
            noticia = get_object_or_404(Noticia, pk=request.POST.get("noticia_id"))
            if noticia.estado == Noticia.Estado.PUBLICADO:
                noticia.estado = Noticia.Estado.BORRADOR
                noticia.save(update_fields=["estado", "actualizado_en"])
                messages.success(request, f'“{noticia.titulo}” pasó a borrador.')
            else:
                noticia.estado = Noticia.Estado.PUBLICADO
                if noticia.fecha_publicacion is None or noticia.fecha_publicacion > timezone.now():
                    noticia.fecha_publicacion = timezone.now()
                noticia.save(update_fields=["estado", "fecha_publicacion", "actualizado_en"])
                messages.success(request, f'“{noticia.titulo}” fue publicada.')
            return redirect("admin_blog")

        titulo = request.POST.get("titulo", "").strip()
        resumen = request.POST.get("resumen", "").strip()
        contenido = request.POST.get("contenido", "").strip()
        categoria_nombre = request.POST.get("categoria", "").strip()
        publicar = request.POST.get("publicar") == "on"

        if not titulo or not resumen or not contenido:
            messages.error(request, "Completa el título, el resumen y el contenido.")
        elif len(titulo) > 220 or len(resumen) > 320:
            messages.error(request, "El título o el resumen supera la longitud permitida.")
        else:
            categoria = None
            if categoria_nombre:
                categoria, _ = CategoriaNoticia.objects.get_or_create(nombre=categoria_nombre[:100])
            noticia = Noticia(
                titulo=titulo,
                resumen=resumen,
                contenido=contenido,
                categoria=categoria,
                autor=None,
                estado=Noticia.Estado.PUBLICADO if publicar else Noticia.Estado.BORRADOR,
                fecha_publicacion=timezone.now() if publicar else None,
                imagen_destacada=request.FILES.get("imagen_destacada"),
                texto_alternativo_imagen=request.POST.get("texto_alternativo_imagen", "").strip()[:220],
            )
            noticia.save()
            messages.success(
                request,
                f'La publicación “{noticia.titulo}” fue creada ' +
                ("y publicada." if publicar else "como borrador.")
            )
            return redirect("admin_blog")

    query = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "").strip()
    noticias = Noticia.objects.select_related("categoria", "autor").order_by("-creado_en")
    if query:
        noticias = noticias.filter(Q(titulo__icontains=query) | Q(resumen__icontains=query))
    if estado in (Noticia.Estado.BORRADOR, Noticia.Estado.PUBLICADO):
        noticias = noticias.filter(estado=estado)

    context = {
        "noticias": noticias[:100],
        "noticias_total": Noticia.objects.count(),
        "noticias_publicadas": Noticia.objects.filter(estado=Noticia.Estado.PUBLICADO).count(),
        "noticias_borrador": Noticia.objects.filter(estado=Noticia.Estado.BORRADOR).count(),
        "categorias": CategoriaNoticia.objects.filter(activa=True),
        "query": query,
        "estado": estado,
        "admin_usuario": request.session.get("admin_username", ""),
        "admin_nombre": request.session.get("admin_name", ""),
    }
    return render(request, "admin/blog.html", context)
