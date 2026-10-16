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
        names = {column['name'] for column in columns}
        required = ('coditem', 'desitem', 'cositem', 'iteactivo')
        missing = [name for name in required if name not in names]
        if missing:
            raise RuntimeError(
                "Faltan columnas requeridas en public.items: " + ", ".join(missing)
            )

        # El listado muestra exclusivamente código, descripción y precio unitario.
        list_columns = [
            next(column for column in columns if column['name'] == name)
            for name in ('coditem', 'desitem', 'cositem')
        ]
        search = request.GET.get('q', '').strip()
        selected = ', '.join(_quote(name) for name in ('coditem', 'desitem', 'cositem'))
        sql = (
            f"SELECT {selected} FROM public.{_quote(TABLE)} "
            f"WHERE {_quote('iteactivo')} IS TRUE"
        )
        params = []
        if search:
            sql += (
                f" AND (CAST({_quote('coditem')} AS text) ILIKE %s "
                f"OR CAST({_quote('desitem')} AS text) ILIKE %s)"
            )
            params.extend([f'%{search}%', f'%{search}%'])
        sql += f" ORDER BY {_quote('coditem')}"

        with _items_db().cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        key_index = 0
        items = [
            {'values': row, 'key': row[key_index]}
            for row in rows
        ]
        return render(request, 'admin/servicios_venta.html', {
            'columns': list_columns,
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
    editable_fields = ('cositem', 'desitem', 'aplivaite', 'iteactivo')
    create_fields = ('coditem', 'desitem', 'cositem', 'aplivaite')
    boolean_fields = ('aplivaite', 'iteactivo')

    try:
        all_columns = _items_table()
        columns_by_name = {column['name']: column for column in all_columns}
        if is_new:
            missing = [name for name in create_fields if name not in columns_by_name]
            if missing:
                raise RuntimeError(
                    "Faltan campos para crear el item: " + ", ".join(missing)
                )
            columns = [columns_by_name[name] for name in create_fields]
        else:
            missing = [name for name in editable_fields if name not in columns_by_name]
            if missing:
                raise RuntimeError(
                    "Faltan columnas editables en public.items: " + ", ".join(missing)
                )
            # En edición solo se exponen los cuatro campos autorizados.
            columns = [columns_by_name[name] for name in editable_fields]

        with _items_db().cursor() as cursor:
            existing = None
            if not is_new:
                cursor.execute(
                    f"SELECT {', '.join(_quote(name) for name in editable_fields)} "
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
        initial = {name: existing[index] for index, name in enumerate(editable_fields)}

    if request.method == 'POST':
        values = {}
        errors = []
        for column in columns:
            name = column['name']
            if is_new and name not in create_fields:
                continue
            if not is_new and name not in editable_fields:
                continue

            if name in boolean_fields:
                raw = request.POST.get(name)
                if raw not in ('true', 'false'):
                    errors.append(f'Selecciona un valor válido para {name}.')
                    continue
                values[name] = raw == 'true'
                continue

            raw = request.POST.get(name, '').strip()
            if raw == '' and not column['nullable'] and column['default'] is None:
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
                        # Los items nuevos se crean activos por defecto; ese campo no se muestra en el formulario.
                        values['iteactivo'] = True
                        fields = list(values)
                        if not fields:
                            raise ValueError('No se recibieron datos para guardar.')
                        sql = (
                            f"INSERT INTO public.{_quote(TABLE)} "
                            f"({', '.join(_quote(field) for field in fields)}) "
                            f"VALUES ({', '.join(['%s'] * len(fields))})"
                        )
                        cursor.execute(sql, [values[field] for field in fields])
                        saved_key = values.get(KEY_FIELD, '(código generado)')
                        messages.success(request, f'Item {saved_key} creado correctamente.')
                    else:
                        # Lista blanca: ningún otro campo puede modificarse desde edición.
                        sql = (
                            f"UPDATE public.{_quote(TABLE)} SET "
                            + ', '.join(f"{_quote(field)} = %s" for field in editable_fields)
                            + f" WHERE {_quote(KEY_FIELD)}::text = %s"
                        )
                        cursor.execute(
                            sql,
                            [values[field] for field in editable_fields] + [str(coditem)],
                        )
                        if cursor.rowcount != 1:
                            raise ValueError('No se encontró un único item para actualizar.')
                        messages.success(request, f'Item {coditem} actualizado correctamente.')
                return redirect('admin_servicios_venta')
            except Exception as exc:
                messages.error(request, f'No se pudo guardar el item. Verifica los datos ingresados. Detalle: {exc}')
                initial = {column['name']: request.POST.get(column['name'], '') for column in columns}

    fields = []
    for column in columns:
        name = column['name']
        value = initial.get(name, '')
        if value is None:
            value = ''
        fields.append({
            **column,
            'value': str(value),
            'is_key': name == KEY_FIELD,
            'is_boolean': name in boolean_fields,
            'checked_value': 'true' if value is True or str(value).lower() in ('true', 't', '1', 'yes') else 'false',
            'readonly': (not is_new and name == KEY_FIELD),
        })

    return render(request, 'admin/servicio_venta_form.html', {
        'fields': fields,
        'is_new': is_new,
        'coditem': coditem,
    })
