from django.urls import path

from . import views


urlpatterns = [
    path('', views.home, name='home'),
    path('signin/', views.do_signin, name='signin'),
    path('logout/', views.do_logout, name='logout'),
    path('portal/mi-empresa/', views.mi_empresa, name='mi_empresa'),
    path('portal/parametros/', views.parametros, name='parametros'),
    path('portal/cambiar-contrasena/', views.cambiar_contrasena, name='cambiar_contrasena'),
    path('portal/aceptar-documento-legal/', views.aceptar_documento_legal, name='aceptar_documento_legal'),
    path('portal/', views.portal, name='portal'),
    path('about/', views.about, name='about'),
    path('contactanos/', views.contactanos, name='contactanos'),
    path('servicios/', views.servicios, name='servicios'),
    path('blog/', views.blog, name='blog'),
    path('plantillas/', views.template_catalog, name='template_catalog'),
    path('plantillas/<slug:slug>/', views.template_preview, name='template_preview'),
]
