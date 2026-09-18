from django.urls import path, include
from . import views
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('', views.home, name='home'),
    path('signin/', views.do_signin, name='signin'),
    path('logout/', views.do_logout, name='logout'),
    path('signup/', views.do_signup, name='signup'),
    path('success-signup/', views.success_signup, name='success_signup'),
    path('categorias/<int:categoria_id>/productos/', views.get_productos_by_categoria, name='productos_by_categoria'),
    path('add-to-cart/', views.add_to_cart, name='add_to_cart'),
    path('remove-from-cart/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/', views.get_shopping_cart, name='cart'),
    path('pedidos/', views.crear_pedido, name='crear_pedido'),
    path('about/', views.about, name='about'),
    #path('sign-in/', views.signinnow, name='sign-in'),
    #path('sign-up/', views.signupnow, name='sign-up'),

]

