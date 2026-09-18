from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render


def error_404(request, exception):
    return render(request, '404.html')


def home(request):
    return render(request, 'index.html')


def do_signin(request):
    if request.user.is_authenticated:
        return redirect('home')

    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return redirect('home')

        messages.error(request, 'Usuario o contraseña inválidos.')

    return render(request, 'sign-in.html', {'signin_form': form})


def do_logout(request):
    logout(request)
    return redirect('home')


def about(request):
    return render(request, 'about.html')
