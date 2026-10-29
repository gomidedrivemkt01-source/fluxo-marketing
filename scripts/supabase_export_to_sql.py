"""Converte o data.sql exportado do Supabase em uma carga para o PostgreSQL próprio.

Uso: python3 -I scripts/supabase_export_to_sql.py migracao/supabase-export/database/data.sql \
        | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U marketing -d marketing

- Copia todas as tabelas do schema "app", exceto as sessões (que guardavam tokens do Supabase).
- Converte os usuários confirmados de auth.users em app.auth_users, preservando id e hash bcrypt.
- Ignora os demais schemas internos do Supabase (auth, storage, realtime, vault).
- Roda em uma transação única: ou tudo entra, ou nada muda.
"""

import re
import sys
from collections.abc import Iterator

COPY_HEADER = re.compile(r'^COPY "(?P<schema>\w+)"\."(?P<table>\w+)" \((?P<columns>[^)]*)\) FROM stdin;$')
SKIPPED_APP_TABLES = {"app_sessions"}


def copy_blocks(path: str) -> Iterator[tuple[str, str, list[str], list[str]]]:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            match = COPY_HEADER.match(line.rstrip("\n"))
            if not match:
                continue
            rows: list[str] = []
            for row in handle:
                if row == "\\.\n":
                    break
                rows.append(row)
            else:
                raise SystemExit(f"Bloco COPY sem terminador: {match['schema']}.{match['table']}")
            columns = [column.strip().strip('"') for column in match["columns"].split(",")]
            yield match["schema"], match["table"], columns, rows


def main() -> None:
    out = sys.stdout
    out.write("SET client_encoding = 'UTF8';\nSET standard_conforming_strings = on;\n")
    out.write("BEGIN;\n")
    # Replica desliga triggers e checagem de FK durante a carga; a ordem do dump não importa.
    out.write("SET LOCAL session_replication_role = replica;\n")
    out.write(
        "DO $$ DECLARE t record; BEGIN\n"
        "  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'app' LOOP\n"
        "    EXECUTE format('TRUNCATE app.%I CASCADE', t.tablename);\n"
        "  END LOOP;\n"
        "END $$;\n"
    )
    loaded: list[str] = []
    auth_users = False
    for schema, table, columns, rows in copy_blocks(sys.argv[1]):
        if schema == "app" and table not in SKIPPED_APP_TABLES:
            column_list = ", ".join(f'"{column}"' for column in columns)
            out.write(f'COPY "app"."{table}" ({column_list}) FROM stdin;\n')
            out.writelines(rows)
            out.write("\\.\n")
            loaded.append(f"{table}={len(rows)}")
        elif schema == "auth" and table == "users":
            definitions = ", ".join(f'"{column}" text' for column in columns)
            column_list = ", ".join(f'"{column}"' for column in columns)
            out.write(f"CREATE TEMP TABLE supabase_users ({definitions}) ON COMMIT DROP;\n")
            out.write(f"COPY supabase_users ({column_list}) FROM stdin;\n")
            out.writelines(rows)
            out.write("\\.\n")
            auth_users = True
    if not auth_users:
        raise SystemExit("auth.users não encontrado no export.")
    out.write(
        "INSERT INTO app.auth_users (id, email, password_hash, user_metadata, "
        "must_change_password, failed_attempts, password_changed_at, created_at, updated_at)\n"
        "SELECT id::uuid, lower(email), encrypted_password, "
        "COALESCE(raw_user_meta_data::jsonb, '{}'::jsonb), false, 0, "
        "updated_at::timestamptz, created_at::timestamptz, updated_at::timestamptz\n"
        "FROM supabase_users\n"
        "WHERE deleted_at IS NULL AND email IS NOT NULL\n"
        "  AND COALESCE(encrypted_password, '') <> '' AND email_confirmed_at IS NOT NULL;\n"
    )
    # Recalcula sequências que pertençam a colunas do schema app.
    out.write(
        "DO $$ DECLARE s record; maximo bigint; BEGIN\n"
        "  FOR s IN SELECT seq.relname AS seq, tab.relname AS tab, att.attname AS col\n"
        "    FROM pg_depend d\n"
        "    JOIN pg_class seq ON seq.oid = d.objid AND seq.relkind = 'S'\n"
        "    JOIN pg_class tab ON tab.oid = d.refobjid\n"
        "    JOIN pg_namespace n ON n.oid = tab.relnamespace AND n.nspname = 'app'\n"
        "    JOIN pg_attribute att ON att.attrelid = tab.oid AND att.attnum = d.refobjsubid\n"
        "  LOOP\n"
        "    EXECUTE format('SELECT max(%I) FROM app.%I', s.col, s.tab) INTO maximo;\n"
        "    IF maximo IS NOT NULL THEN\n"
        "      PERFORM setval(format('app.%I', s.seq), maximo);\n"
        "    END IF;\n"
        "  END LOOP;\n"
        "END $$;\n"
    )
    out.write("COMMIT;\n")
    print(f"Tabelas app carregadas: {len(loaded)}", file=sys.stderr)
    print(" ".join(loaded), file=sys.stderr)


if __name__ == "__main__":
    main()
