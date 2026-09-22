from django.conf import settings

from ..models import AceptacionLegal


TIPOS_LEGALES = (
    AceptacionLegal.Tipo.POLITICA_DATOS,
    AceptacionLegal.Tipo.TERMINOS_USO,
)


def versiones_legales_vigentes():
    return {
        AceptacionLegal.Tipo.POLITICA_DATOS: getattr(
            settings, 'POLITICA_DATOS_VERSION', '1.0'
        ),
        AceptacionLegal.Tipo.TERMINOS_USO: getattr(
            settings, 'TERMINOS_USO_VERSION', '1.0'
        ),
    }


def obtener_aceptaciones_pendientes(usuario):
    vigentes = versiones_legales_vigentes()
    aceptadas = set(
        AceptacionLegal.objects.filter(
            usuario=usuario,
            tipo__in=TIPOS_LEGALES,
        ).values_list('tipo', 'version')
    )

    return [
        tipo for tipo in TIPOS_LEGALES
        if (tipo, vigentes[tipo]) not in aceptadas
    ]
