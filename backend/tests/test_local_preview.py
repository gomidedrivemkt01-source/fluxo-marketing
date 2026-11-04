"""Confere as barreiras que impedem restauração fora do ambiente local."""

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "local_preview", Path(__file__).resolve().parents[2] / "scripts" / "local_preview.py"
)
assert spec is not None and spec.loader is not None
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


@pytest.mark.parametrize("name", ["marketing", "postgres", "marketing_preview", "fm_preview_bad"])
def test_rejects_non_preview_database(name: str) -> None:
    with pytest.raises(ValueError):
        preview.validate_database(name)


@pytest.mark.parametrize(
    "name", ["../../outside", "/outside", "C:/outside", "a\\..\\outside", "file:stream"]
)
def test_rejects_archive_path_escape(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        preview.archive_target(tmp_path, name)


def test_rejects_archive_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "files.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        info = tarfile.TarInfo("shortcut")
        info.type = tarfile.SYMTYPE
        info.linkname = "../outside"
        output.addfile(info)
    with pytest.raises(ValueError, match="Tipo de entrada"):
        preview.extract_storage(archive, tmp_path / "restored")


def test_restores_nested_files_without_overwriting_existing_files(tmp_path: Path) -> None:
    archive = tmp_path / "files.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        info = tarfile.TarInfo("./demand-files/org/card/image.png")
        info.size = 3
        output.addfile(info, io.BytesIO(b"png"))
    destination = tmp_path / "restored"
    preview.extract_storage(archive, destination)
    assert (destination / "demand-files/org/card/image.png").read_bytes() == b"png"
    with pytest.raises(FileExistsError):
        preview.extract_storage(archive, destination)


def test_local_environment_does_not_inherit_production_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql://production/db")
    monkeypatch.setenv("PGHOST", "192.168.0.160")
    settings = {
        "databasePassword": "test-password",
        "sessionSecret": "s" * 48,
        "encryptionKey": "k" * 44,
    }
    env = preview.app_env(settings, "fm_preview_structure", preview.STATE / "test-storage")
    assert "@127.0.0.1:15432/fm_preview_structure?" in env["APP_DATABASE_URL"]
    assert env["PGHOST"] == "127.0.0.1"
    assert env["APP_RETENTION_SCHEDULER_ENABLED"] == "false"


@pytest.mark.asyncio
async def test_preview_does_not_run_automatic_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    monkeypatch.setattr(main.settings, "retention_scheduler_enabled", False)

    def unexpected_scheduler() -> None:
        pytest.fail("A prévia não pode iniciar a retenção automática.")

    monkeypatch.setattr(main, "retention_loop", unexpected_scheduler)
    async with main.lifespan(main.app):
        pass
