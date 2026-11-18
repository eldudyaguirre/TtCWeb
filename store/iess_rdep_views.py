from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import Cliente
from .models.iess_rdep_job import IessRdepJob


@require_POST
def iniciar_consulta(request, ruc):
    if not request.session.get("admin_portal"):
        return redirect("admin_login")

    # La consulta documental también puede ejecutarse para clientes inactivos.
    # La disponibilidad del acceso se valida por las credenciales IESS configuradas.
    cliente = get_object_or_404(Cliente, pk=ruc)
    if not str(cliente.cediess or "").strip() or not str(cliente.claveiess or "").strip():
        messages.error(request, "El cliente no tiene las credenciales IESS completas en su ficha.")
        return redirect("admin_anexo_archivos", ruc=ruc, modulo="rdep")

    try:
        anio = int(request.POST.get("anio", ""))
    except (TypeError, ValueError):
        anio = 0

    from django.utils import timezone
    anio_actual = timezone.localdate().year
    if not anio_actual - 7 <= anio <= anio_actual:
        messages.error(request, "Selecciona un periodo fiscal válido.")
        return redirect("admin_anexo_archivos", ruc=ruc, modulo="rdep")

    activo = IessRdepJob.objects.filter(
        cliente=cliente, anio=anio,
        estado__in=[IessRdepJob.Estado.PENDIENTE, IessRdepJob.Estado.PROCESANDO],
    ).exists()
    if activo:
        messages.warning(request, f"Ya existe una consulta IESS pendiente o en proceso para {anio}.")
        return redirect("admin_anexo_archivos", ruc=ruc, modulo="rdep")

    IessRdepJob.objects.create(
        cliente=cliente,
        anio=anio,
        estado=IessRdepJob.Estado.PENDIENTE,
        mensaje="Consulta encolada; esperando al IESS RDEP Worker.",
        worker_id="",
    )
    messages.success(request, f"Consulta consolidada del IESS para {anio} agregada a la cola.")
    return redirect("admin_anexo_archivos", ruc=ruc, modulo="rdep")
