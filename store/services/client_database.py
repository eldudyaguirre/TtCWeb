"""Creación segura y conexión de bases de datos de clientes TotalCounts."""
from pathlib import Path
import re

import psycopg2
from psycopg2 import sql
from django.conf import settings


RUC_RE = re.compile(r"^\\d{13}$")
SCHEMA_PATH = Path(settings.BASE_DIR) / "store" / "sql" / "totalcounts_schema.sql"
LOCK_KEY = 728194063


def _connection_params(database):
    cfg = settings.DATABASES["default"]
    return {
        "dbname": database,
        "user": cfg.get("USER") or None,
        "password": cfg.get("PASSWORD") or None,
        "host": cfg.get("HOST") or None,
        "port": cfg.get("PORT") or None,
        "connect_timeout": 10,
    }


def _initialize_table(cursor, table_name):
    """Inserta una fila inicial usando valores compatibles con los tipos de la tabla."""
    cursor.execute(
        """
        SELECT column_name, data_type, udt_name, is_identity, is_generated
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        [table_name],
    )
    columns = cursor.fetchall()
    if not columns:
        raise RuntimeError(f"No existe la tabla public.{table_name} en el esquema instalado.")

    names = []
    expressions = []
    for name, data_type, udt_name, is_identity, is_generated in columns:
        if is_identity == "YES" or is_generated != "NEVER":
            continue
        names.append(sql.Identifier(name))
        if data_type in ("smallint", "integer", "bigint", "numeric", "decimal", "real", "double precision"):
            expressions.append(sql.SQL("0"))
        elif data_type == "boolean":
            expressions.append(sql.SQL("FALSE"))
        elif data_type == "date":
            expressions.append(sql.SQL("CURRENT_DATE"))
        elif data_type in ("timestamp without time zone", "timestamp with time zone", "time without time zone", "time with time zone"):
            expressions.append(sql.SQL("CURRENT_TIMESTAMP"))
        elif data_type == "ARRAY":
            expressions.append(sql.SQL("ARRAY[]::{}[]").format(sql.Identifier(udt_name)))
        else:
            # Campos de texto se inicializan con "0" para conservar el formato
            # esperado por el sistema heredado; las fechas se inicializan aparte.
            expressions.append(sql.Literal("0"))

    if not names:
        cursor.execute(sql.SQL("INSERT INTO public.{} DEFAULT VALUES").format(sql.Identifier(table_name)))
    else:
        cursor.execute(
            sql.SQL("INSERT INTO public.{} ({}) VALUES ({})").format(
                sql.Identifier(table_name),
                sql.SQL(", ").join(names),
                sql.SQL(", ").join(expressions),
            )
        )


def ensure_client_database(ruc):
    """
    Verifica la base por RUC. Si no existe, crea la base, instala el esquema
    y añade las filas iniciales. Devuelve (nombre_bd, creada).
    Nunca modifica una base que ya existía.
    """
    db_name = str(ruc or "").strip()
    if not RUC_RE.fullmatch(db_name):
        raise ValueError("El RUC del cliente debe contener exactamente 13 dígitos.")
    if not SCHEMA_PATH.is_file():
        raise RuntimeError(f"No se encuentra el esquema base: {SCHEMA_PATH}")

    admin_conn = psycopg2.connect(**_connection_params("postgres"))
    created = False
    try:
        admin_conn.autocommit = True
        with admin_conn.cursor() as cursor:
            # Serializa la comprobación/creación para evitar carreras entre solicitudes.
            cursor.execute("SELECT pg_advisory_lock(%s)", [LOCK_KEY])
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db_name])
            exists = cursor.fetchone() is not None
            if not exists:
                cursor.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(db_name)))
                created = True

        if created:
            try:
                schema = SCHEMA_PATH.read_text(encoding="utf-8")
                schema = re.sub(r"(?m)^\\s*\\(?:restrict|unrestrict)\\s+[^\\n]*\\n?", "", schema)
                with psycopg2.connect(**_connection_params(db_name)) as client_conn:
                    with client_conn.cursor() as cursor:
                        cursor.execute(schema)
                        _initialize_table(cursor, "parametros")
                        _initialize_table(cursor, "parametroscontables")
            except Exception:
                # Si la importación falla, no dejar una base nueva a medio construir.
                with admin_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = %s AND pid <> pg_backend_pid()
                        """,
                        [db_name],
                    )
                    cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))
                raise
        return db_name, created
    finally:
        try:
            with admin_conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
        except Exception:
            pass
        admin_conn.close()
