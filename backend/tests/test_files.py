import uuid
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from fastapi import UploadFile
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.api.errors import ApiError
from app.api.files import (
    DemandFileCover,
    DemandFileDelete,
    can_delete_file,
    delete_file,
    normalize_upload,
    preview_image,
    read_upload,
    set_file_cover,
    sign_file_download,
    upload_file,
)
from app.auth.service import Principal
from app.core.config import get_settings
from app.models import (
    AppSession,
    AuditEvent,
    Demand,
    DemandFile,
    DemandUpdate,
    Membership,
    MembershipStatus,
    PermissionRole,
    UserProfile,
    utc_now,
)


class FakeStorage:
    bucket = "demand-files"

    def __init__(self) -> None:
        self.uploaded: tuple[str, bytes, str, str] | None = None
        self.signed: tuple[str, str, int, str] | None = None
        self.downloaded: tuple[str, str] | None = None
        self.download_contents = b""

    async def upload(
        self, path: str, data: bytes, content_type: str, access_token: str
    ) -> None:
        self.uploaded = (path, data, content_type, access_token)

    async def remove(self, path: str, access_token: str) -> None:
        return None

    async def download(self, path: str, access_token: str) -> bytes:
        self.downloaded = (path, access_token)
        return self.download_contents

    async def create_signed_url(
        self,
        path: str,
        access_token: str,
        expires_in: int,
        download_name: str | None,
    ) -> str:
        self.signed = (path, access_token, expires_in, download_name)
        return "https://example.supabase.co/storage/v1/object/sign/demand-files/file?token=test"


def _principal(*, code: str = "collaborator", profile_id: uuid.UUID | None = None) -> Principal:
    organization_id = uuid.uuid4()
    profile = UserProfile(
        id=profile_id or uuid.uuid4(),
        auth_user_id=uuid.uuid4(),
        email=f"{code}@example.com",
        full_name=code.title(),
    )
    membership = Membership(
        id=uuid.uuid4(),
        organization_id=organization_id,
        user_profile_id=profile.id,
        status=MembershipStatus.ACTIVE,
    )
    permissions = (
        ["demands:read", "demands:write"]
        if code == "coordinator"
        else ["demands:read", "demands:work"]
    )
    role = PermissionRole(
        id=uuid.uuid4(),
        organization_id=organization_id,
        code=code,
        name=code.title(),
        permissions=permissions,
    )
    return Principal(MagicMock(spec=AppSession), profile, membership, role)


def _demand(principal: Principal) -> Demand:
    return Demand(
        id=uuid.uuid4(),
        organization_id=principal.membership.organization_id,
        public_id="DMD-2026-000201",
        title="Campanha de lançamento",
        status="WAITING_EXECUTION",
        priority="NORMAL",
        source="interface",
        revision=1,
        created_by=principal.profile.id,
    )


def _file(principal: Principal, demand: Demand) -> DemandFile:
    return DemandFile(
        id=uuid.uuid4(),
        organization_id=demand.organization_id,
        demand_id=demand.id,
        uploaded_by=principal.profile.id,
        original_name="briefing.pdf",
        storage_bucket="demand-files",
        storage_path=f"{demand.organization_id}/{demand.id}/file/briefing.pdf",
        content_type="application/pdf",
        size_bytes=12,
        sha256="a" * 64,
        is_cover=False,
        revision=1,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def test_upload_validation_normalizes_name_and_rejects_disguised_extension() -> None:
    name, content_type, safe_name = normalize_upload(
        "  Planejamento Mídia 2026.PDF ", "application/pdf; charset=binary"
    )
    assert name == "Planejamento Mídia 2026.PDF"
    assert content_type == "application/pdf"
    assert safe_name == "planejamento-midia-2026.pdf"

    tiff_name, tiff_type, tiff_safe_name = normalize_upload("Retrato.TIFF", "image/x-tiff")
    assert (tiff_name, tiff_type, tiff_safe_name) == (
        "Retrato.TIFF",
        "image/tiff",
        "retrato.tiff",
    )

    with pytest.raises(ApiError) as caught:
        normalize_upload("script.exe", "application/pdf")
    assert caught.value.code == "file_type_not_allowed"


@pytest.mark.asyncio
async def test_read_upload_rejects_files_larger_than_limit() -> None:
    upload = UploadFile(
        BytesIO(b"12345"),
        filename="briefing.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    with pytest.raises(ApiError) as caught:
        await read_upload(upload, 4)
    assert caught.value.status_code == 413


@pytest.mark.asyncio
async def test_upload_file_persists_hash_event_and_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    principal = _principal()
    demand = _demand(principal)
    db = MagicMock(spec=Session)
    db.scalar.return_value = demand
    storage = FakeStorage()
    upload = UploadFile(
        BytesIO(b"%PDF-test"),
        filename="Briefing Final.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )

    async def with_token(operation, principal_arg, settings_arg, db_arg):
        return await operation("user-token")

    monkeypatch.setattr("app.api.files._with_storage_token", with_token)

    def assign_database_values() -> None:
        item = next(
            value for value in (call.args[0] for call in db.add.call_args_list) if isinstance(value, DemandFile)
        )
        item.id = uuid.uuid4()
        item.revision = 1
        item.created_at = utc_now()
        item.updated_at = item.created_at

    db.flush.side_effect = assign_database_values

    result = await upload_file(
        demand.id,
        upload,
        principal,
        db,
        get_settings(),
        storage,  # type: ignore[arg-type]
    )

    assert result.name == "Briefing Final.pdf"
    assert result.sha256 == "3c87d37f1dbea6909f917ce437c390fb8e655a774387d9e69301c0b2283d5b63"
    assert result.can_delete
    assert result.is_cover is False
    assert result.can_set_cover is False
    assert storage.uploaded is not None
    assert storage.uploaded[0].startswith(f"{demand.organization_id}/{demand.id}/")
    assert storage.uploaded[2:] == ("application/pdf", "user-token")
    added = [call.args[0] for call in db.add.call_args_list]
    assert any(isinstance(value, DemandUpdate) and value.kind == "FILE_ATTACHED" for value in added)
    assert any(
        isinstance(value, AuditEvent) and value.event_type == "DEMAND_FILE_UPLOADED"
        for value in added
    )
    db.commit.assert_called_once()


def test_set_file_cover_replaces_previous_cover_and_records_history() -> None:
    principal = _principal()
    demand = _demand(principal)
    item = _file(principal, demand)
    item.original_name = "nova-capa.png"
    item.content_type = "image/png"
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [demand, item]
    db.get.return_value = principal.profile

    result = set_file_cover(
        demand.id,
        item.id,
        DemandFileCover(expectedRevision=1),
        principal,
        db,
    )

    assert result.is_cover is True
    assert result.can_set_cover is True
    assert item.revision == 2
    db.execute.assert_called_once()
    added = [call.args[0] for call in db.add.call_args_list]
    assert any(isinstance(value, DemandUpdate) and value.kind == "FILE_COVER_SET" for value in added)
    assert any(
        isinstance(value, AuditEvent) and value.event_type == "DEMAND_FILE_COVER_SET"
        for value in added
    )
    db.commit.assert_called_once()


def test_file_delete_is_soft_and_respects_author_or_coordinator() -> None:
    author = _principal()
    demand = _demand(author)
    item = _file(author, demand)
    colleague = _principal()
    coordinator = _principal(code="coordinator")
    assert can_delete_file(author, item)
    assert not can_delete_file(colleague, item)
    assert can_delete_file(coordinator, item)

    db = MagicMock(spec=Session)
    db.scalar.side_effect = [demand, item]
    delete_file(
        demand.id,
        item.id,
        DemandFileDelete(expectedRevision=1),
        author,
        db,
    )

    assert item.deleted_at is not None
    assert item.revision == 2
    added = [call.args[0] for call in db.add.call_args_list]
    assert any(isinstance(value, DemandUpdate) and value.kind == "FILE_REMOVED" for value in added)
    assert any(
        isinstance(value, AuditEvent) and value.event_type == "DEMAND_FILE_REMOVED"
        for value in added
    )
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_signed_download_uses_private_object_path(monkeypatch: pytest.MonkeyPatch) -> None:
    principal = _principal()
    demand = _demand(principal)
    item = _file(principal, demand)
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [demand, item]
    storage = FakeStorage()

    async def with_token(operation, principal_arg, settings_arg, db_arg):
        return await operation("user-token")

    monkeypatch.setattr("app.api.files._with_storage_token", with_token)
    result = await sign_file_download(
        demand.id,
        item.id,
        principal,
        db,
        get_settings(),
        storage,  # type: ignore[arg-type]
    )

    assert "token=test" in result.url
    assert storage.signed == (item.storage_path, "user-token", 120, item.original_name)


@pytest.mark.asyncio
async def test_image_preview_redirects_to_private_signed_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = _principal()
    demand = _demand(principal)
    item = _file(principal, demand)
    item.original_name = "capa.png"
    item.content_type = "image/png"
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [demand, item]
    storage = FakeStorage()

    async def with_token(operation, principal_arg, settings_arg, db_arg):
        return await operation("user-token")

    monkeypatch.setattr("app.api.files._with_storage_token", with_token)
    result = await preview_image(
        demand.id,
        item.id,
        principal,
        db,
        get_settings(),
        storage,  # type: ignore[arg-type]
    )

    assert result.status_code == 307
    assert result.headers["location"].startswith("https://example.supabase.co/")
    assert result.headers["cache-control"] == "private, max-age=60"
    assert storage.signed == (item.storage_path, "user-token", 120, None)


@pytest.mark.asyncio
async def test_tiff_preview_is_converted_to_png(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image

    principal = _principal()
    demand = _demand(principal)
    item = _file(principal, demand)
    item.original_name = "capa.tiff"
    item.content_type = "image/tiff"
    source = BytesIO()
    Image.new("RGB", (30, 60), "#008f82").save(source, format="TIFF")
    storage = FakeStorage()
    storage.download_contents = source.getvalue()
    db = MagicMock(spec=Session)
    db.scalar.side_effect = [demand, item]

    async def with_token(operation, principal_arg, settings_arg, db_arg):
        return await operation("user-token")

    monkeypatch.setattr("app.api.files._with_storage_token", with_token)
    result = await preview_image(
        demand.id,
        item.id,
        principal,
        db,
        get_settings(),
        storage,  # type: ignore[arg-type]
    )

    assert result.status_code == 200
    assert result.media_type == "image/png"
    assert bytes(result.body).startswith(b"\x89PNG")
    assert storage.downloaded == (item.storage_path, "user-token")
