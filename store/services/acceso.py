from django.db import connection


def validar_acceso_cliente(cliente):
    """Valida las condiciones de acceso web de un cliente.

    Reglas:
    - El cliente debe estar activo.
    - El acceso web debe estar habilitado.
    - No debe tener saldo pendiente en salcuenta.
    - No puede tener más de 3 registros pendientes en prefactura.

    Retorna una tupla (permitido, motivo, detalle).
    """
    if not cliente.activo:
        return False, 'inactivo', 'El cliente no se encuentra activo.'

    if not cliente.acceso_ttcweb:
        return False, 'web_desactivada', 'El acceso al portal web no está habilitado para este cliente.'

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT salcuenta
            FROM clientes
            WHERE ruccedcli = %s
            """,
            [cliente.ruccedcli],
        )
        row = cursor.fetchone()

    if row is None:
        return False, 'cliente_no_encontrado', 'No se encontró la información del cliente.'

    salcuenta = row[0] or 0

    if salcuenta > 0:
        return False, 'saldo_pendiente', (
            'El acceso al portal está restringido porque existen valores '
            'pendientes de pago.'
        )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM prefactura
            WHERE ruc = %s
            """,
            [cliente.ruccedcli],
        )
        prefacturas_pendientes = cursor.fetchone()[0]

    if prefacturas_pendientes > 3:
        return False, 'prefacturas_pendientes', (
            'El acceso al portal está restringido porque existen más de '
            '3 servicios pendientes de facturación.'
        )

    return True, 'ok', 'Acceso permitido.'
