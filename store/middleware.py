from django.shortcuts import redirect

from .services.legales import obtener_aceptaciones_pendientes


class LegalAcceptanceMiddleware:
    """
    Impide utilizar rutas internas del portal hasta aceptar
    las versiones vigentes de los documentos legales.
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
            if obtener_aceptaciones_pendientes(request.user):
                return redirect('portal')

        return self.get_response(request)
