from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render



# Plantillas de demostración reutilizables.
TEMPLATE_PREVIEWS = {
    'page-404-1': 'page-404-1.html',
    'page-about-1': 'page-about-1.html',
    'page-blog-1': 'page-blog-1.html',
    'page-blog-2': 'page-blog-2.html',
    'page-contact-1': 'page-contact-1.html',
    'page-contact-2': 'page-contact-2.html',
    'page-our-people-1': 'page-our-people-1.html',
    'page-partners-1': 'page-partners-1.html',
    'page-pricing-table-1': 'page-pricing-table-1.html',
    'page-pricing-table-2': 'page-pricing-table-2.html',
    'page-projects-1': 'page-projects-1.html',
    'page-search-1': 'page-search-1.html',
    'page-services-1': 'page-services-1.html',
    'page-single-post-1': 'page-single-post-1.html',
    'page-single-project-1': 'page-single-project-1.html',
    'page-single-service-1': 'page-single-service-1.html',
    'page-single-service-2': 'page-single-service-2.html',
    'page-testimonials-1': 'page-testimonials-1.html',
    'quienes': 'quienes.html',
    'signup': 'signup.html',
}


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


def template_catalog(request):
    """Catálogo interno para revisar las plantillas del tema antes de reutilizarlas."""
    return render(request, 'template-catalog.html', {'templates': TEMPLATE_PREVIEWS})


def template_preview(request, slug):
    """Renderiza una plantilla del catálogo usando el mismo sistema de templates de Django."""
    template_name = TEMPLATE_PREVIEWS.get(slug)
    if template_name is None:
        from django.http import Http404
        raise Http404
    return render(request, template_name, {'preview_mode': True, 'preview_slug': slug})
