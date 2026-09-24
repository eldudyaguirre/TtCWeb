import hashlib
import secrets

from django.conf import settings

from .models import VisitaWeb


VISITOR_COOKIE = 'tc_visitor'
EXCLUDED_PREFIXES = (
    '/static/',
    '/media/',
    '/portal/',
    '/totalcounts/',
    '/admin/',
)
EXCLUDED_PATHS = {
    '/signin/',
    '/logout/',
    '/favicon.ico',
    '/robots.txt',
}


class WebVisitTrackingMiddleware:
    """
    Registra visitas de las páginas públicas del sitio.

    Se usa una cookie anónima para identificar visitantes recurrentes y no
    almacena la IP en texto plano. Las rutas internas, estáticas y de medios
    quedan fuera del contador público.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        path = request.path or '/'
        if request.method != 'GET' or self._excluir(path):
            return response

        user_agent = request.META.get('HTTP_USER_AGENT', '')
        if self._es_bot(user_agent):
            return response

        visitor_id = request.COOKIES.get(VISITOR_COOKIE)
        if not visitor_id or len(visitor_id) > 64:
            visitor_id = secrets.token_hex(16)

        ip = (
            request.META.get('HTTP_CF_CONNECTING_IP')
            or request.META.get('REMOTE_ADDR')
            or ''
        ).strip()

        salt = getattr(settings, 'VISITAS_IP_SALT', settings.SECRET_KEY)
        ip_hash = hashlib.sha256(f'{salt}:{ip}'.encode('utf-8')).hexdigest()

        try:
            VisitaWeb.objects.create(
                pagina=path[:500],
                visitor_id=visitor_id[:64],
                ip_hash=ip_hash,
                user_agent=user_agent[:5000],
                referencia=request.META.get('HTTP_REFERER', '')[:1000],
            )
            if not request.COOKIES.get(VISITOR_COOKIE):
                response.set_cookie(
                    VISITOR_COOKIE,
                    visitor_id,
                    max_age=60 * 60 * 24 * 365,
                    secure=not settings.DEBUG,
                    httponly=True,
                    samesite='Lax',
                )
        except Exception:
            # Las estadísticas nunca deben impedir que la página cargue.
            pass

        return response

    @staticmethod
    def _excluir(path):
        return path in EXCLUDED_PATHS or any(
            path.startswith(prefix) for prefix in EXCLUDED_PREFIXES
        )

    @staticmethod
    def _es_bot(user_agent):
        ua = user_agent.lower()
        bots = (
            'bot', 'crawler', 'spider', 'slurp', 'bingpreview',
            'facebookexternalhit', 'linkedinbot', 'whatsapp',
        )
        return any(token in ua for token in bots)
