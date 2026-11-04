"""Importa exportação de leitura do Supabase em um NOVO banco da prévia local.

O CSV aceita snapshot JSON ou compressed_snapshot (pgcrypto, formato de transporte).
Nunca conecta ao Supabase nem altera um banco preexistente. Os anexos em cache
só são reaproveitados após conferir tamanho e checksum contra a exportação atual.
O arquivo CSV contém informações confidenciais e deve ficar fora do Git.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import re
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

import local_preview as preview
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

PROJECT = "xtsbravvqeibkiuybhty"
TRANSPORT_FORMAT = "fluxo-local-transfer-format-v1"


def connect(settings: dict, database: str) -> psycopg.Connection:
    preview.validate_database(database)
    return psycopg.connect(
        host="127.0.0.1",
        port=preview.PORT,
        user=preview.USER,
        password=settings["databasePassword"],
        dbname=database,
    )


def read_snapshot(path: Path, connection: psycopg.Connection) -> dict:
    csv.field_size_limit(2**31 - 1)
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != 1:
        raise ValueError("O CSV precisa conter exatamente um snapshot completo.")
    if "compressed_snapshot" in rows[0]:
        # pgcrypto é criado apenas no banco NOVO local para descompactar o transporte.
        connection.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        payload = base64.b64decode(rows[0]["compressed_snapshot"])
        text = connection.execute(
            "SELECT public.pgp_sym_decrypt(%s, %s)", (payload, TRANSPORT_FORMAT)
        ).fetchone()[0]
    else:
        text = rows[0]["snapshot"]
    snapshot = json.loads(text)
    if snapshot.get("sourceProject") != PROJECT or snapshot.get("formatVersion") != 1:
        raise ValueError("Projeto ou versão do snapshot incorretos.")
    required = {
        "app.demands",
        "app.user_profiles",
        "app.workflows",
        "auth.users",
        "storage.objects",
    }
    if not required.issubset(snapshot.get("tables", {})):
        raise ValueError("Snapshot incompleto: faltam tabelas obrigatórias.")
    return snapshot


def copy_files(snapshot: dict, cache: Path, storage: Path) -> list[dict]:
    storage.mkdir(parents=True, exist_ok=False)
    references = {
        (row.get("storage_bucket"), row.get("storage_path")): row
        for row in snapshot["tables"].get("app.demand_files", [])
    }
    manifest = []
    for obj in snapshot["tables"]["storage.objects"]:
        if obj["bucket_id"] != "demand-files":
            raise ValueError("Bucket inesperado no snapshot.")
        source = preview.archive_target(cache, obj["name"])
        target = preview.archive_target(storage, f"demand-files/{obj['name']}")
        if not source.is_file():
            raise ValueError(f"Anexo ausente no cache: {obj['name']}")
        metadata = obj.get("metadata") or {}
        ref = references.get(("demand-files", obj["name"]), {})
        expected_size = metadata.get("size", ref.get("size_bytes"))
        if expected_size is None or source.stat().st_size != int(expected_size):
            raise ValueError(f"Tamanho diferente no anexo: {obj['name']}")
        digest = preview.sha256(source)
        expected_sha = ref.get("sha256", "").lower()
        etag = str(metadata.get("eTag", metadata.get("etag", ""))).strip('"').lower()
        if re.fullmatch(r"[a-f0-9]{64}", expected_sha):
            if digest != expected_sha:
                raise ValueError(f"SHA-256 diferente no anexo: {obj['name']}")
        elif re.fullmatch(r"[a-f0-9]{32}", etag):
            with source.open("rb") as handle:
                actual_md5 = hashlib.file_digest(
                    handle, lambda: hashlib.md5(usedforsecurity=False)
                ).hexdigest()
            if actual_md5 != etag:
                raise ValueError(f"Checksum diferente no anexo: {obj['name']}")
        else:
            raise ValueError(f"Snapshot sem checksum para validar o cache: {obj['name']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest.append(
            {
                "path": f"demand-files/{obj['name']}",
                "sha256": digest,
                "bytes": source.stat().st_size,
                "origin": "verified-local-cache",
            }
        )
    return manifest


def load_application(snapshot: dict, connection: psycopg.Connection) -> dict:
    source_columns: dict[str, list[str]] = {}
    for column in snapshot["columns"]:
        source_columns.setdefault(column["table"], []).append(column["column"])
    local_columns: dict[str, list[str]] = {}
    for table, column in connection.execute(
        "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='app' ORDER BY table_name,ordinal_position"
    ):
        local_columns.setdefault(table, []).append(column)
    tables = snapshot["tables"]
    for qualified in tables:
        if qualified.startswith("app."):
            table = qualified.removeprefix("app.")
            if table not in local_columns or set(source_columns.get(table, [])) - set(
                local_columns[table]
            ):
                raise ValueError(f"Estrutura incompatível na tabela {qualified}.")
    # O alvo acabou de ser criado por este script. Nenhum dado preexistente é tocado.
    connection.execute("SET LOCAL session_replication_role = replica")
    connection.execute(
        sql.SQL("TRUNCATE {} CASCADE").format(
            sql.SQL(",").join(sql.Identifier("app", table) for table in local_columns)
        )
    )
    expected_counts = {}
    for qualified, rows in tables.items():
        if not qualified.startswith("app.") or qualified == "app.app_sessions":
            continue
        table = qualified.removeprefix("app.")
        columns = sql.SQL(",").join(map(sql.Identifier, source_columns[table]))
        if rows:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {} ({}) SELECT {} FROM jsonb_populate_recordset(NULL::{}, %s)"
                ).format(
                    sql.Identifier("app", table), columns, columns, sql.Identifier("app", table)
                ),
                (Jsonb(rows),),
            )
        expected_counts[table] = len(rows)
    accounts = [
        row
        for row in tables["auth.users"]
        if not row.get("deleted_at")
        and row.get("email_confirmed_at")
        and row.get("email")
        and row.get("encrypted_password")
    ]
    for row in accounts:
        connection.execute(
            "INSERT INTO app.auth_users (id,email,password_hash,user_metadata,must_change_password,failed_attempts,password_changed_at,created_at,updated_at) VALUES (%s,%s,%s,%s,false,0,%s,%s,%s)",
            (
                row["id"],
                row["email"].lower(),
                row["encrypted_password"],
                Jsonb(row.get("raw_user_meta_data") or {}),
                row["updated_at"],
                row["created_at"],
                row["updated_at"],
            ),
        )
    expected_counts["auth_users"] = len(accounts)
    # Verifica referências após a carga; triggers ficam desativadas só nesta transação.
    foreign_keys = connection.execute("""SELECT c.conname, n.nspname, t.relname, pn.nspname, pt.relname,
        ARRAY(SELECT attname FROM pg_attribute WHERE attrelid=c.conrelid AND attnum=ANY(c.conkey) ORDER BY array_position(c.conkey,attnum)),
        ARRAY(SELECT attname FROM pg_attribute WHERE attrelid=c.confrelid AND attnum=ANY(c.confkey) ORDER BY array_position(c.confkey,attnum))
        FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_class pt ON pt.oid=c.confrelid JOIN pg_namespace pn ON pn.oid=pt.relnamespace
        WHERE c.contype='f' AND n.nspname='app'""").fetchall()
    for name, schema, table, parent_schema, parent, children, parents in foreign_keys:
        joins = sql.SQL(" AND ").join(
            sql.SQL("c.{} = p.{}").format(sql.Identifier(child), sql.Identifier(target))
            for child, target in zip(children, parents, strict=True)
        )
        nonnull = sql.SQL(" AND ").join(
            sql.SQL("c.{} IS NOT NULL").format(sql.Identifier(column)) for column in children
        )
        statement = sql.SQL(
            "SELECT count(*) FROM {} c WHERE {} AND NOT EXISTS (SELECT 1 FROM {} p WHERE {})"
        ).format(
            sql.Identifier(schema, table), nonnull, sql.Identifier(parent_schema, parent), joins
        )
        if connection.execute(statement).fetchone()[0]:
            raise ValueError(f"Referências ausentes em {name}; importação cancelada.")
    for table, expected in expected_counts.items():
        actual = connection.execute(
            sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("app", table))
        ).fetchone()[0]
        if actual != expected:
            raise ValueError(f"Contagem divergente na tabela {table}.")
    connection.execute("SET LOCAL session_replication_role = origin")
    return expected_counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--files-cache", type=Path, required=True)
    args = parser.parse_args()
    settings = preview.config()
    if preview.preview_info():
        raise RuntimeError("Pare a prévia antes de trocar a cópia ativa.")
    preview.start_database(settings)
    suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(4)
    database = f"fm_preview_{suffix}"
    folder = preview.STATE / "snapshots" / suffix
    folder.mkdir(parents=True)
    copied = folder / "supabase-snapshot.csv"
    shutil.copy2(args.csv, copied)
    preview.create_database(settings, database)
    with connect(settings, database) as connection:
        snapshot = read_snapshot(copied, connection)
    storage = folder / "storage"
    files = copy_files(snapshot, args.files_cache.resolve(), storage)
    preview.migrate(settings, database, storage)
    with connect(settings, database) as connection:
        counts = load_application(snapshot, connection)
    details = preview.inspect_database(settings, database, storage)
    if any(details["tableCounts"][table] != count for table, count in counts.items()):
        raise ValueError("A conferência final dos registros falhou.")
    manifest = {
        "sourceType": "supabase",
        "sourceProject": PROJECT,
        "sourceCapturedAt": snapshot["capturedAt"],
        "restoredAt": datetime.now(UTC).isoformat(),
        "database": database,
        "storage": str(storage.relative_to(preview.STATE)),
        "sourceDump": "Supabase — " + snapshot["capturedAt"],
        "sourceFiles": "cache validado por checksum da origem atual",
        "snapshotSha256": preview.sha256(copied),
        "files": files,
        **details,
        "serverReplica": False,
        "omittedTables": ["app.app_sessions"],
    }
    preview.save_json(folder / "manifest.json", manifest)
    settings["snapshot"] = manifest
    settings["pid"] = None
    preview.save_json(preview.CONFIG, settings)
    print(
        json.dumps(
            {
                "imported": True,
                "source": "supabase",
                "capturedAt": snapshot["capturedAt"],
                "counts": counts,
                "files": len(files),
                "migration": details["migration"],
                "serverReplica": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
