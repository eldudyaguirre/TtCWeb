from django.shortcuts import render, redirect
from store.models import Producto, Pedido, ItemPedido
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import SignUpForm
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from datetime import datetime
from .cart_session import ShoppingCartSession
import json
from django.http import JsonResponse
from django.db import transaction
import string
import random

def error_404(request, exception):
    return render(request, '404.html',{})


def home(request):
    return render(request, 'index.html')

def do_signin(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('home')
            else:
                messages.error(request, 'Usuario o contraseña inválidos.')
        else:
            messages.error(request, 'Usuario o contraseña inválidos.')        
    
    form = AuthenticationForm()
    return render(request, 'sign-in.html', {'signin_form': form})


def do_logout(request):
    logout(request)
    return redirect('home')


def do_signup(request):
    if request.method == "POST":        
        sign_up_form = SignUpForm(request.POST)
        if sign_up_form.is_valid():
            username = sign_up_form.cleaned_data.get('username')
            password = sign_up_form.cleaned_data.get('password1')
            nombre = sign_up_form.cleaned_data.get('nombre')
            apellido = sign_up_form.cleaned_data.get('apellido')
            email = sign_up_form.cleaned_data.get('email')
            
            if User.objects.filter(username=username).exists():
                messages.error(request, "El username ingresado ya está siendo utilizado!")
            else:            
                new_user = User(
                    username=username,
                    password=make_password(password),
                    is_superuser=False,
                    first_name=nombre,
                    last_name=apellido,
                    email=email,
                    is_staff=False,
                    is_active=True,
                    date_joined=datetime.now()
                )
                new_user.save()
                                
                return redirect('success_signup')
    else:
        sign_up_form = SignUpForm()        
    
    return render(request, 'sign-up.html', {'sign_up_form': sign_up_form})
            


def success_signup(request):
    return render(request, 'success_signup.html')


def get_productos_by_categoria(request, categoria_id):
    productos = Producto.objects.filter(categorias__in=[categoria_id])
    return render(request, 'catalog.html', {'productos': productos})


def add_to_cart(request):
    cart = ShoppingCartSession(request)
    
    payload = json.loads(request.body)
    
    producto_id = int(payload.get('producto_id'))
    cantidad = int(payload.get('cantidad'))
    
    try:    
        producto_existente = Producto.objects.get(pk=producto_id)
        cart.add(producto_existente.id, cantidad)
        return JsonResponse(status=200, data={'result': True, 'message': 'OK', 'count_cart_items': cart.__len__()})
    except Producto.DoesNotExist:
        return JsonResponse(status=404, data={'result': False, 'message': 'El producto no existe'})    
    

def remove_from_cart(request):
    cart = ShoppingCartSession(request)
    
    payload = json.loads(request.body)    
    producto_id = int(payload.get('producto_id'))    
    cart.delete(producto_id)    
    return JsonResponse(status=200, data={'result': True, 'message': 'OK', 'count_cart_items': cart.__len__()})   


def get_shopping_cart(request):
    cart = ShoppingCartSession(request)
    return render(request, 'cart.html', {'cart': cart.get_cart_detail(), 'count_cart_items': cart.__len__(), 'cart_total': cart.get_total()})


@transaction.atomic
def crear_pedido(request):
    cart = ShoppingCartSession(request)
    
    try:
        pedido = Pedido(usuario=request.user,
                        codigo=generar_codigo_pedido(),
                        total=cart.get_total()
        )
        
        pedido.save()
        
        for item in cart.get_cart_detail():
            item_pedido = ItemPedido(
                pedido=pedido,
                producto=item.get('product'),
                cantidad=item.get('cantidad')
            )
            
            item_pedido.save()
        
        cart.clear()
        return JsonResponse(status=200, data={'codigo_pedido': pedido.codigo})
        
    except Exception as error:
        return JsonResponse(status=500, data={'error_msg': f'Ops, no se pudo registrar el pedido. Error: {error}'})
    
    
def generar_codigo_pedido():
    caracteres = string.ascii_letters + string.digits
    codigo_pedido = 'PED-' + ''.join(random.choice(caracteres) for _ in range(5))
    return codigo_pedido


def about(request):
    return render(request, 'about.html')

