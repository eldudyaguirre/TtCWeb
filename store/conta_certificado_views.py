from django.http import JsonResponse
from .models import Cliente
from .admin_views import ADMIN_USERNAME_KEY, _conta_certificado_ruc_request, admin_required


@admin_required
def admin_cliente_obtener_ruc_sri(request, ruc):
    if request.method != "POST":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido."}, status=405)
    ruc = "".join(c for c in str(ruc) if c.isdigit())
    cliente = Cliente.objects.filter(ruccedcli=ruc, activo=True).first()
    if not cliente:
        return JsonResponse({"ok": False, "mensaje": "Cliente no encontrado o inactivo."}, status=404)
    if not str(cliente.clavesri or "").strip():
        return JsonResponse({"ok": False, "mensaje": "El cliente no tiene clave SRI registrada."}, status=400)
    try:
        result = _conta_certificado_ruc_request(ruc, request.session.get(ADMIN_USERNAME_KEY, "ADMIN"))
        return JsonResponse({"ok": True, "estado": result.get("estado", "iniciando"), "mensaje": result.get("mensaje", "Solicitud recibida por Conta.")})
    except RuntimeError as exc:
        return JsonResponse({"ok": False, "mensaje": str(exc)}, status=502)


@admin_required
def admin_cliente_estado_ruc_sri(request, ruc):
    if request.method != "GET":
        return JsonResponse({"ok": False, "mensaje": "Método no permitido."}, status=405)
    ruc = "".join(c for c in str(ruc) if c.isdigit())
    if not Cliente.objects.filter(ruccedcli=ruc, activo=True).exists():
        return JsonResponse({"ok": False, "mensaje": "Cliente no encontrado o inactivo."}, status=404)
    try:
        result = _conta_certificado_ruc_request(ruc, request.session.get(ADMIN_USERNAME_KEY, "ADMIN"), estado=True)
        return JsonResponse({"ok": True, **result})
    except RuntimeError as exc:
        return JsonResponse({"ok": False, "mensaje": str(exc)}, status=502)
