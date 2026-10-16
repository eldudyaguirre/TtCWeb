from django.contrib import messages
from django.conf import settings
from django.db import connections, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .admin_views import admin_required


TABLE = 'items'
KEY_FIELD = 'coditem'
DB_ALIAS = 'bdtotal_items_catalog'


def _items_db():
    if DB_ALIAS not in connections.databases:
        config = settings.DATABASES['default'].copy()
        config['NAME'] = 'BdTotal'
        connections.databases[DB_ALIAS] = config
    return connections[DB_ALIAS]


def _items_columns():
    db = _items_db()
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default,
                   character_maximum_length, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, [TABLE])
        return [
            {
                'name': row[0],
                'type': row[1],
                'nullable': row[2] == 'YES',
                'default': row[3],
                'max_length': row[4],
                'position': row[5],
            }
            for row in cursor.fetchall()
        ]


def _items_table():
    columns = _items_columns()
    if not columns:
        raise RuntimeError("No existe la tabla public.items en la base de datos configurada.")
    names = {column['name'] for column in columns}
    if KEY_FIELD not in names:
        raise RuntimeError("La tabla public.items no contiene el campo coditem.")
    return columns


def _quote(name):
    return _items_db().ops.quote_name(name)


def _input_value(column, value):
    if value == '' and column['type'] not in (
        'character varying', 'character', 'text', 'varchar', 'char'
    ):
        return None
    return value


@admin_required
def admin_servicios_venta(request):
    try:
        columns = _items_table()
        search = request.GET.get('q', '').strip()
        quoted_columns = ', '.join(_quote(column['name']) for column in columns)
        sql = f"SELECT {quoted_columns} FROM public.{_quote(TABLE)}"
        params = []
        if search:
            sql += f" WHERE CAST({_quote(KEY_FIELD)} AS text) ILIKE %s"
            params.append(f'%{search}%')
            name_fields = [
                column['name'] for column in columns
                if any(term in column['name'].lower() for term in ('nombre', 'descripcion', 'detalle', 'item'))
                and column['name'] != KEY_FIELD
            ]
            for field in name_fields:
                sql += f" OR CAST({_quote(field)} AS text) ILIKE %s"
                params.append(f'%{search}%')
        sql += f" ORDER BY {_quote(KEY_FIELD)}"
        with _items_db().cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        items = [
            {'values': row, 'key': row[next(i for i, c in enumerate(columns) if c['name'] == KEY_FIELD)]}
            for row in rows
        ]
        return render(request, 'admin/servicios_venta.html', {
            'columns': columns,
            'items': items,
            'search': search,
            'total': len(items),
        })
    except Exception as exc:
        messages.error(request, f'No se pudo cargar el catálogo de items: {exc}')
        return render(request, 'admin/servicios_venta.html', {
            'columns': [], 'items': [], 'search': request.GET.get('q', '').strip(),
            'total': 0, 'load_error': True,
        })


@admin_required
@require_http_methods(["GET", "POST"])
def admin_servicio_venta_form(request, coditem=None):
    is_new = coditem is None
    try:
        columns = _items_table()
        with _items_db().cursor() as cursor:
            existing = None
            if not is_new:
                cursor.execute(
                    f"SELECT {', '.join(_quote(c['name']) for c in columns)} "
                    f"FROM public.{_quote(TABLE)} WHERE {_quote(KEY_FIELD)}::text = %s",
                    [str(coditem)],
                )
                existing = cursor.fetchone()
                if existing is None:
                    messages.error(request, f'No existe el item {coditem}.')
                    return redirect('admin_servicios_venta')
    except Exception as exc:
        messages.error(request, f'No se pudo consultar el item: {exc}')
        return redirect('admin_servicios_venta')

    initial = {}
    if existing is not None:
        initial = {column['name']: existing[index] for index, column in enumerate(columns)}

    if request.method == 'POST':
        values = {}
        errors = []
        for column in columns:
            name = column['name']
            raw = request.POST.get(name, '')
            if is_new and raw == '' and column['default'] is not None:
                continue
            if not column['nullable'] and column['default'] is None and raw == '':
                if column['type'] in ('character varying', 'character', 'text', 'varchar', 'char'):
                    errors.append(f'El campo {name} es obligatorio.')
                    continue
                if name == KEY_FIELD:
                    errors.append(f'El campo {name} es obligatorio.')
                    continue
            values[name] = _input_value(column, raw)

        if errors:
            for error in errors:
                messages.error(request, error)
            initial = {column['name']: request.POST.get(column['name'], '') for column in columns}
        else:
            try:
                with transaction.atomic(using=DB_ALIAS), _items_db().cursor() as cursor:
                    if is_new:
                        fields = list(values)
                        if not fields:
                            raise ValueError('No se recibieron datos para guardar.')
                        sql = (
                            f"INSERT INTO public.{_quote(TABLE)} "
                            f"({', '.join(_quote(field) for field in fields)}) "
                            f"VALUES ({', '.join(['%s'] * len(fields))})"
                        )
                        cursor.execute(sql, [values[field] for field in fields])
                        saved_key = values.get(KEY_FIELD)
                        messages.success(request, f'Item {saved_key} creado correctamente.')
                    else:
                        fields = [field for field in values if field != KEY_FIELD]
                        if not fields:
                            raise ValueError('No hay campos para actualizar.')
                        sql = (
                            f"UPDATE public.{_quote(TABLE)} SET "
                            + ', '.join(f"{_quote(field)} = %s" for field in fields)
                            + f" WHERE {_quote(KEY_FIELD)}::text = %s"
                        )
                        cursor.execute(sql, [values[field] for field in fields] + [str(coditem)])
                        messages.success(request, f'Item {coditem} actualizado correctamente.')
                return redirect('admin_servicios_venta')
            except Exception as exc:
                messages.error(request, f'No se pudo guardar el item. Verifica los datos ingresados. Detalle: {exc}')
                initial = {column['name']: request.POST.get(column['name'], '') for column in columns}

    fields = []
    for column in columns:
        value = initial.get(column['name'], '')
        if value is None:
            value = ''
        fields.append({
            **column,
            'value': str(value),
            'is_key': column['name'] == KEY_FIELD,
            'readonly': (not is_new and column['name'] == KEY_FIELD),
        })

    return render(request, 'admin/servicio_venta_form.html', {
        'fields': fields,
        'is_new': is_new,
        'coditem': coditem,
    })
