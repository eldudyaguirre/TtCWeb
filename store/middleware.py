from django.shortcuts import redirect

from .models import AceptacionLegal
from .services.legales import versiones_legales_vigentes


class LegalAcceptanceMiddleware:
    """
    Obliga a aceptar la versión vigente de los Términos y Condiciones
    antes de utilizar las funcionalidades internas del portal.
    La Política de Protección de Datos no bloquea el acceso por su falta
    de aceptación; su comunicación y eventual registro son independientes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and not request.user.is_staff
            and not request.user.is_superuser
            and request.path.startswith('/portal/')
            and request.path.rstrip('/') != '/portal'
            and request.path != '/portal/aceptar-documento-legal/'
        ):
            version = versiones_legales_vigentes()[AceptacionLegal.Tipo.TERMINOS_USO]
            aceptado = AceptacionLegal.objects.filter(
                usuario=request.user,
                tipo=AceptacionLegal.Tipo.TERMINOS_USO,
                version=version,
            ).exists()

            if not aceptado:
                return redirect('portal')

        return self.get_response(request)
