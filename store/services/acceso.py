from django.db import connection


def validar_acceso_cliente(cliente):
    """Valida las condiciones de acceso web de un cliente.

    Reglas:
    - El cliente debe estar activo.
    - El acceso web debe estar habilitado.
    - Si salcuenta es mayor que cero, solo se permite el acceso cuando
      todos los registros PENDIENTE de cuentascobrar tienen menos de
      45 días de antigüedad, calculados desde fecinicio.
    - No puede tener más de 3 registros pendientes en prefactura.

    Retorna una tupla (permitido, motivo, detalle).
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT activo, acceso_ttcweb, salcuenta
            FROM clientes
            WHERE ruccedcli = %s
            """,
            [cliente.ruccedcli],
        )
        row = cursor.fetchone()

    if row is None:
        return False, 'cliente_no_encontrado', 'No se encontró la información del cliente.'

    activo, acceso_ttcweb, salcuenta = row

    if not activo:
        return False, 'inactivo', 'El cliente no se encuentra activo.'

    if not acceso_ttcweb:
        return False, 'web_desactivada', (
            'El acceso al portal web no está habilitado para este cliente.'
        )

    if (salcuenta or 0) > 0:
        # Con saldo pendiente, revisar únicamente las cuentas PENDIENTE.
        # La antigüedad se calcula desde fecinicio.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM cuentascobrar
                WHERE ruccedcli = %s
                  AND UPPER(TRIM(COALESCE(estpagcue, ''))) = 'PENDIENTE'
                  AND fecinicio IS NOT NULL
                  AND fecinicio <= CURRENT_TIMESTAMP - INTERVAL '45 days'
                """,
                [cliente.ruccedcli],
            )
            saldos_vencidos_45 = cursor.fetchone()[0]

        if saldos_vencidos_45 > 0:
            return False, 'saldo_pendiente', (
                'El acceso al portal está restringido porque existe al menos '
                'un saldo pendiente con 45 días o más de antigüedad.'
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


def obtener_resumen_cliente(cliente):
    """Obtiene los datos que el dashboard necesita mostrar."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                COALESCE(salcuenta, 0),
                (
                    SELECT COUNT(*)
                    FROM prefactura
                    WHERE ruc = clientes.ruccedcli
                )
            FROM clientes
            WHERE ruccedcli = %s
            """,
            [cliente.ruccedcli],
        )
        row = cursor.fetchone()

    if row is None:
        return {
            'salcuenta': 0,
            'prefacturas_pendientes': 0,
        }

    return {
        'salcuenta': row[0] or 0,
        'prefacturas_pendientes': row[1] or 0,
    }
