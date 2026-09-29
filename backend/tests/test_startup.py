from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from app import startup


def test_skips_alembic_when_database_is_already_at_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup, "migration_head", lambda: "0009")
    monkeypatch.setattr(startup, "database_revision", lambda: "0009")

    def unexpected_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("alembic nao deveria ser executado")

    monkeypatch.setattr(startup.subprocess, "run", unexpected_run)

    startup.ensure_database_at_head()


def test_accepts_timeout_only_after_database_reaches_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revisions = iter(["0008", "0009"])
    monkeypatch.setattr(startup, "migration_head", lambda: "0009")
    monkeypatch.setattr(startup, "database_revision", lambda: next(revisions))
    monkeypatch.setattr(startup, "migration_timeout_seconds", lambda: 30)

    def timed_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="alembic", timeout=30)

    monkeypatch.setattr(startup.subprocess, "run", timed_out)

    startup.ensure_database_at_head()


def test_rejects_timeout_when_database_did_not_reach_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revisions = iter(["0008", "0008"])
    monkeypatch.setattr(startup, "migration_head", lambda: "0009")
    monkeypatch.setattr(startup, "database_revision", lambda: next(revisions))
    monkeypatch.setattr(startup, "migration_timeout_seconds", lambda: 30)

    def timed_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="alembic", timeout=30)

    monkeypatch.setattr(startup.subprocess, "run", timed_out)

    with pytest.raises(RuntimeError, match="permaneceu"):
        startup.ensure_database_at_head()


def test_rejects_successful_command_without_expected_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revisions = iter(["0008", "0008"])
    monkeypatch.setattr(startup, "migration_head", lambda: "0009")
    monkeypatch.setattr(startup, "database_revision", lambda: next(revisions))
    monkeypatch.setattr(startup, "migration_timeout_seconds", lambda: 30)
    monkeypatch.setattr(
        startup.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )

    with pytest.raises(RuntimeError, match="Migration terminou"):
        startup.ensure_database_at_head()
