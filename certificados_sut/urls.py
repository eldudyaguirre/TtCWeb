from django.urls import path

from . import views

app_name = "certificados_sut"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("cargar/", views.cargar_excel, name="cargar"),
    path("generar/", views.generar_zip, name="generar"),
    path("limpiar/", views.limpiar, name="limpiar"),
]
