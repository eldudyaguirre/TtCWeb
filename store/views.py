from django.shortcuts import render, redirect
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


def about(request):
    return render(request, 'about.html')

