"""Prévia Windows isolada; restaura backups somente em bancos locais novos.

Executar com .venv/Scripts/python.exe scripts/local_preview.py --help.
Nenhum comando conecta ao servidor de produção ou remove um banco existente.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".preview"
CONFIG = STATE / "settings.json"
PG = STATE / "runtime" / "pgsql" / "bin"
CLUSTER = STATE / "postgres"
URL = "http://127.0.0.1:18000"
PORT = 15432
USER = "fm_preview_admin"


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def config() -> dict:
    if not CONFIG.is_file():
        raise RuntimeError("Execute primeiro o comando init.")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def pg_env(settings: dict) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("APP_") and not k.startswith("PG")
    }
    env.update(
        PGHOST="127.0.0.1",
        PGPORT=str(PORT),
        PGUSER=USER,
        PGPASSWORD=settings["databasePassword"],
        PGCONNECT_TIMEOUT="10",
    )
    return env


def validate_database(name: str) -> str:
    if not re.fullmatch(r"fm_preview_(?:structure|[0-9]{14}_[a-f0-9]{8})", name):
        raise ValueError("Nome fora do conjunto de bancos exclusivos da prévia.")
    return name


def storage_path(relative: str) -> Path:
    target = (STATE / relative).resolve()
    if not target.is_relative_to(STATE.resolve()) or target == STATE.resolve():
        raise ValueError("Armazenamento precisa estar dentro de .preview.")
    return target


def app_env(settings: dict, database: str, storage: Path) -> dict[str, str]:
    validate_database(database)
    if not storage.resolve().is_relative_to(STATE.resolve()):
        raise ValueError("Armazenamento fora da prévia.")
    env = pg_env(settings)
    password = quote(settings["databasePassword"], safe="")
    env.update(
        APP_ENV="development",
        APP_NAME="Fluxo Marketing — Prévia local",
        APP_PUBLIC_URL=URL,
        APP_DATABASE_URL=f"postgresql+psycopg://{USER}:{password}@127.0.0.1:{PORT}/{database}?sslmode=disable",
        APP_SESSION_SECRET=settings["sessionSecret"],
        APP_TOKEN_ENCRYPTION_KEY=settings["encryptionKey"],
        APP_STORAGE_DIR=str(storage.resolve()),
        APP_COOKIE_SECURE="false",
        APP_ALLOWED_ORIGINS=json.dumps([URL]),
        APP_RETENTION_SCHEDULER_ENABLED="false",
        PYTHONPATH=str(ROOT / "backend"),
    )
    return env


def run_pg(
    tool: str, args: list[str], settings: dict, *, check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess:
    if not capture:
        # O postgres herda os handles do pg_ctl no Windows. Um PIPE de captura
        # ficaria aberto no processo do banco mesmo depois da saída do pg_ctl.
        with (STATE / "postgres-control.log").open("a", encoding="utf-8") as output:
            return subprocess.run(
                [str(PG / f"{tool}.exe"), *args], cwd=ROOT, env=pg_env(settings),
                check=check, stdout=output, stderr=subprocess.STDOUT, text=True,
            )
    return subprocess.run(
        [str(PG / f"{tool}.exe"), *args],
        cwd=ROOT,
        env=pg_env(settings),
        check=check,
        capture_output=True,
        text=True,
    )


def start_database(settings: dict) -> None:
    if (
        run_pg(
            "pg_ctl", ["-D", str(CLUSTER), "status"], settings, check=False
        ).returncode
        == 0
    ):
        return
    run_pg(
        "pg_ctl",
        [
            "-D",
            str(CLUSTER),
            "-l",
            str(STATE / "postgres.log"),
            "-o",
            f"-h 127.0.0.1 -p {PORT}",
            "-w",
            "-t",
            "30",
            "start",
        ],
        settings,
        capture=False,
    )


def create_database(settings: dict, name: str) -> None:
    validate_database(name)
    run_pg(
        "createdb",
        ["--maintenance-db=postgres", "--encoding=UTF8", "--template=template0", name],
        settings,
    )


def migrate(settings: dict, name: str, storage: Path) -> None:
    log = STATE / "migration.log"
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "backend/alembic.ini",
                "upgrade",
                "head",
            ],
            cwd=ROOT,
            env=app_env(settings, name, storage),
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"Migração local falhou. Consulte {log}.")


def initialize() -> None:
    STATE.mkdir(exist_ok=True)
    if not CONFIG.exists():
        save_json(
            CONFIG,
            {
                "databasePassword": secrets.token_urlsafe(36),
                "sessionSecret": secrets.token_urlsafe(48),
                "encryptionKey": base64.urlsafe_b64encode(
                    secrets.token_bytes(32)
                ).decode(),
                "instance": secrets.token_hex(16),
                "snapshot": None,
                "pid": None,
            },
        )
    settings = config()
    if not (CLUSTER / "PG_VERSION").exists():
        password_file = STATE / "init-password.tmp"
        password_file.write_text(settings["databasePassword"], encoding="utf-8")
        try:
            run_pg(
                "initdb",
                [
                    "-D",
                    str(CLUSTER),
                    "-U",
                    USER,
                    "--auth=scram-sha-256",
                    "--encoding=UTF8",
                    "--locale=C",
                    "--pwfile",
                    str(password_file),
                ],
                settings,
            )
        finally:
            password_file.unlink(missing_ok=True)
    start_database(settings)
    import psycopg

    with psycopg.connect(
        host="127.0.0.1",
        port=PORT,
        user=USER,
        password=settings["databasePassword"],
        dbname="postgres",
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", ("fm_preview_structure",)
        ).fetchone()
    if not exists:
        create_database(settings, "fm_preview_structure")
    migrate(settings, "fm_preview_structure", STATE / "structure-storage")
    print(
        "Código e estrutura local preparados. Dados atuais aguardam backup do banco e dos anexos."
    )


def archive_target(root: Path, name: str) -> Path:
    posix = PurePosixPath(name)
    if (
        posix.is_absolute()
        or PureWindowsPath(name).drive
        or "\\" in name
        or any(part in {".."} or ":" in part for part in posix.parts)
    ):
        raise ValueError(f"Caminho inválido no arquivo de anexos: {name!r}")
    target = (root / Path(*posix.parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Arquivo fora do diretório de restauração.")
    return target


def extract_storage(archive: Path, root: Path) -> None:
    # Não permite links, devices ou paths arbitrários vindos do tar.
    root.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            target = archive_target(root, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile() and target != root.resolve():
                target.parent.mkdir(parents=True, exist_ok=True)
                reader = source.extractfile(member)
                if reader is None:
                    raise ValueError("Anexo ilegível no backup.")
                with reader, target.open("xb") as output:
                    shutil.copyfileobj(reader, output)
            else:
                raise ValueError(f"Tipo de entrada não permitido: {member.name!r}")


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def inspect_database(settings: dict, name: str, storage: Path) -> dict:
    import psycopg
    from psycopg import sql

    validate_database(name)
    counts = {}
    with psycopg.connect(
        host="127.0.0.1",
        port=PORT,
        user=USER,
        password=settings["databasePassword"],
        dbname=name,
    ) as connection:
        for (table,) in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'app' ORDER BY tablename"
        ):
            counts[table] = connection.execute(
                sql.SQL("SELECT count(*) FROM app.{}").format(sql.Identifier(table))
            ).fetchone()[0]
        for table in (
            "organizations",
            "auth_users",
            "user_profiles",
            "workflows",
            "demands",
        ):
            if table not in counts:
                raise ValueError(f"Backup não contém a tabela obrigatória app.{table}.")
        revision = connection.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchone()[0]
        missing = 0
        for bucket, path in connection.execute(
            "SELECT storage_bucket, storage_path FROM app.demand_files WHERE storage_path IS NOT NULL AND deleted_at IS NULL"
        ):
            target = archive_target(storage, f"{bucket}/{path}")
            missing += not target.is_file()
    files = [item for item in storage.rglob("*") if item.is_file()]
    if missing:
        raise ValueError(
            f"Backup de anexos incompleto: {missing} arquivos ativos não encontrados. A cópia anterior foi preservada."
        )
    return {
        "tableCounts": counts,
        "migration": revision,
        "fileCount": len(files),
        "fileBytes": sum(item.stat().st_size for item in files),
        "missingActiveFiles": missing,
    }


def preview_info() -> dict | None:
    try:
        with urlopen(f"{URL}/__local-preview/status", timeout=2) as response:
            return json.load(response)
    except (URLError, TimeoutError, ValueError):
        return None


def restore(dump: Path, files: Path) -> None:
    settings = config()
    if preview_info():
        raise RuntimeError("Pare a prévia antes de restaurar outra cópia.")
    with dump.open("rb") as source:
        if source.read(5) != b"PGDMP":
            raise ValueError(
                "Use o backup PostgreSQL custom (.dump) do servidor atual."
            )
    suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(4)
    name = "fm_preview_" + suffix
    folder = STATE / "snapshots" / suffix
    folder.mkdir(parents=True)
    copied_dump = folder / "database.dump"
    copied_files = folder / "storage.tar.gz"
    shutil.copy2(dump, copied_dump)
    shutil.copy2(files, copied_files)
    storage = folder / "storage"
    extract_storage(copied_files, storage)
    start_database(settings)
    create_database(settings, name)
    result = run_pg(
        "pg_restore",
        [
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            "--single-transaction",
            "--dbname",
            name,
            str(copied_dump),
        ],
        settings,
        check=False,
    )
    (folder / "restore.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(
            f"Restauração falhou. Consulte {folder / 'restore.log'}. A cópia anterior foi preservada."
        )
    migrate(settings, name, storage)
    details = inspect_database(settings, name, storage)
    manifest = {
        "restoredAt": datetime.now(UTC).isoformat(),
        "database": name,
        "storage": str(storage.relative_to(STATE)),
        "sourceDump": dump.name,
        "sourceFiles": files.name,
        "dumpSha256": sha256(copied_dump),
        "filesSha256": sha256(copied_files),
        **details,
    }
    save_json(folder / "manifest.json", manifest)
    settings["snapshot"] = manifest
    settings["pid"] = None
    save_json(CONFIG, settings)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def serve() -> None:
    settings = config()
    snapshot = settings.get("snapshot")
    if not snapshot:
        raise RuntimeError(
            "Ainda falta restaurar o backup atual. Uma base vazia não será apresentada como réplica."
        )
    storage = storage_path(snapshot["storage"])
    start_database(settings)
    migrate(settings, snapshot["database"], storage)
    current = preview_info()
    if current:
        if current.get("instance") != settings["instance"]:
            raise RuntimeError("A porta da prévia está ocupada por outra instalação.")
        print(f"Prévia já está em {URL}")
        return
    env = app_env(settings, snapshot["database"], storage)
    with (STATE / "app.log").open("a", encoding="utf-8") as output:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_worker"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    settings["pid"] = child.pid
    save_json(CONFIG, settings)
    for _ in range(40):
        current = preview_info()
        if current and current.get("instance") == settings["instance"]:
            print(
                f"Prévia disponível em {URL}; dados do backup {snapshot['sourceDump']}."
            )
            return
        if child.poll() is not None:
            break
        time.sleep(0.5)
    raise RuntimeError(f"A prévia não iniciou. Consulte {STATE / 'app.log'}.")


def worker() -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    import uvicorn
    from app.main import app
    from fastapi.routing import APIRoute

    settings = config()

    def local_status() -> dict:
        snapshot = settings["snapshot"]
        return {
            "environment": "local-preview",
            "instance": settings["instance"],
            "sourceDump": snapshot["sourceDump"],
            "restoredAt": snapshot["restoredAt"],
        }

    # Precisa preceder o fallback de rotas do frontend.
    app.router.routes.insert(
        0, APIRoute("/__local-preview/status", local_status, methods=["GET"], include_in_schema=False)
    )

    uvicorn.run(app, host="127.0.0.1", port=18000)


def stop() -> None:
    settings = config()
    current = preview_info()
    if current and current.get("instance") != settings["instance"]:
        raise RuntimeError(
            "A porta pertence a outra instalação. Nenhum processo será encerrado."
        )
    if current and settings.get("pid"):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(int(settings["pid"])), "/T", "/F"],
                check=True,
                capture_output=True,
            )
        else:
            import signal

            os.kill(int(settings["pid"]), signal.SIGTERM)
        time.sleep(1)
    run_pg(
        "pg_ctl", ["-D", str(CLUSTER), "-w", "-t", "30", "stop"], settings, check=False
    )
    settings["pid"] = None
    save_json(CONFIG, settings)
    print("Prévia local parada. Dados preservados.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "start", "stop", "status", "_worker"):
        sub.add_parser(command)
    command = sub.add_parser("restore")
    command.add_argument("--database", required=True, type=Path)
    command.add_argument("--files", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "init":
        initialize()
    elif args.command == "restore":
        restore(args.database.resolve(), args.files.resolve())
    elif args.command == "start":
        serve()
    elif args.command == "stop":
        stop()
    elif args.command == "_worker":
        worker()
    else:
        settings = config()
        print(
            json.dumps(
                {
                    "url": URL,
                    "running": preview_info() is not None,
                    "snapshot": settings.get("snapshot"),
                    "folder": str(ROOT),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        # Não imprimir argumentos/ambiente: podem incluir credenciais locais.
        print(
            f"Falha em ferramenta local (código {error.returncode}). {error.stderr or ''}",
            file=sys.stderr,
        )
        sys.exit(1)
    except (RuntimeError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
