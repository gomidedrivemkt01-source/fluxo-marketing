"""Inicializa o servico somente depois de confirmar as migrations."""

from __future__ import annotations

import os
import subprocess
from typing import NoReturn

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import get_settings

ALEMBIC_CONFIG_PATH = "backend/alembic.ini"
DEFAULT_MIGRATION_TIMEOUT_SECONDS = 180


def _database_dsn() -> str:
    return get_settings().database_dsn().replace(
        "postgresql+psycopg://",
        "postgresql://",
        1,
    )


def migration_head() -> str:
    config = Config(ALEMBIC_CONFIG_PATH)
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("Nenhuma revisao Alembic foi encontrada.")
    return head


def database_revision() -> str | None:
    with psycopg.connect(_database_dsn(), connect_timeout=15) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.alembic_version')")
            relation_row = cursor.fetchone()
            if relation_row is None or relation_row[0] is None:
                return None
            cursor.execute("SELECT version_num FROM public.alembic_version")
            row = cursor.fetchone()
            return None if row is None else str(row[0])


def migration_timeout_seconds() -> int:
    raw_value = os.environ.get(
        "APP_MIGRATION_TIMEOUT_SECONDS",
        str(DEFAULT_MIGRATION_TIMEOUT_SECONDS),
    )
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError("APP_MIGRATION_TIMEOUT_SECONDS deve ser um inteiro.") from error
    if value < 30:
        raise RuntimeError("APP_MIGRATION_TIMEOUT_SECONDS deve ser pelo menos 30.")
    return value


def ensure_database_at_head() -> None:
    head = migration_head()
    current = database_revision()
    if current == head:
        print(f"Banco ja esta na revisao {head}; migration dispensada.", flush=True)
        return

    timeout = migration_timeout_seconds()
    print(
        f"Atualizando banco de {current or 'sem revisao'} para {head} "
        f"(limite de {timeout}s).",
        flush=True,
    )
    try:
        subprocess.run(
            ["alembic", "-c", ALEMBIC_CONFIG_PATH, "upgrade", "head"],
            check=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        current = database_revision()
        if current != head:
            raise RuntimeError(
                f"Migration excedeu {timeout}s e o banco permaneceu em {current!r}; esperado {head!r}."
            ) from None
        print(
            f"Migration confirmou {head}, mas nao encerrou em {timeout}s; continuando com seguranca.",
            flush=True,
        )
        return

    current = database_revision()
    if current != head:
        raise RuntimeError(
            f"Migration terminou, mas o banco esta em {current!r}; esperado {head!r}."
        )
    print(f"Banco atualizado e confirmado na revisao {head}.", flush=True)


def main() -> NoReturn:
    ensure_database_at_head()
    port = os.environ.get("PORT", "8000")
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.main:app",
            "--app-dir",
            "backend",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ],
    )


if __name__ == "__main__":
    main()
