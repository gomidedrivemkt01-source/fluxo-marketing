import hashlib
import logging
import mimetypes
import re
import unicodedata
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.access import require_any_permission, require_permission
from app.api.errors import ApiError
from app.auth.dependencies import get_principal, require_csrf
from app.auth.service import Principal
from app.auth.supabase import SupabaseAuthGateway
from app.core.config import Settings, get_settings
from app.core.security import TokenCipher
from app.database import get_db
from app.models import AuditEvent, Demand, DemandFile, DemandUpdate, UserProfile, utc_now
from app.storage import StorageAuthenticationError, SupabaseStorageGateway

router = APIRouter(prefix="/demands", tags=["Arquivos"])
logger = logging.getLogger(__name__)

ALLOWED_FILE_TYPES: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
    "text/plain": {".txt", ".md"},
    "text/csv": {".csv"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {".pptx"},
    "audio/mpeg": {".mp3"},
    "audio/wav": {".wav"},
    "audio/mp4": {".m4a"},
    "video/mp4": {".mp4"},
    "video/webm": {".webm"},
    "video/quicktime": {".mov"},
}


class DemandFileOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    name: str
    content_type: str = Field(alias="contentType")
    size_bytes: int = Field(alias="sizeBytes")
    sha256: str
    uploader_id: uuid.UUID = Field(alias="uploaderId")
    uploader_name: str = Field(alias="uploaderName")
    revision: int
    can_delete: bool = Field(alias="canDelete")
    created_at: datetime = Field(alias="createdAt")


class DemandFileDelete(BaseModel):
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class SignedFileOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    expires_at: datetime = Field(alias="expiresAt")


def get_storage_gateway(settings: Settings = Depends(get_settings)) -> SupabaseStorageGateway:
    return SupabaseStorageGateway(
        str(settings.supabase_url),
        settings.supabase_publishable_key.get_secret_value(),
        settings.storage_bucket,
    )


def _get_demand(db: Session, demand_id: uuid.UUID, principal: Principal) -> Demand:
    demand = db.scalar(
        select(Demand).where(
            Demand.id == demand_id,
            Demand.organization_id == principal.membership.organization_id,
            Demand.deleted_at.is_(None),
        )
    )
    if not demand:
        raise ApiError(404, "demand_not_found", "Demanda não encontrada.")
    return demand


def _get_file(
    db: Session,
    demand: Demand,
    file_id: uuid.UUID,
    *,
    lock: bool = False,
) -> DemandFile:
    query = select(DemandFile).where(
        DemandFile.id == file_id,
        DemandFile.demand_id == demand.id,
        DemandFile.organization_id == demand.organization_id,
        DemandFile.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    item = db.scalar(query)
    if not item:
        raise ApiError(404, "demand_file_not_found", "Arquivo não encontrado.")
    return item


def can_delete_file(principal: Principal, item: DemandFile) -> bool:
    if item.deleted_at:
        return False
    if item.uploaded_by == principal.profile.id:
        return True
    permissions = set(principal.role.permissions if principal.role else [])
    return "*" in permissions or "demands:write" in permissions


def _file_out(item: DemandFile, uploader: UserProfile, principal: Principal) -> DemandFileOut:
    return DemandFileOut(
        id=item.id,
        name=item.original_name,
        contentType=item.content_type,
        sizeBytes=item.size_bytes,
        sha256=item.sha256,
        uploaderId=uploader.id,
        uploaderName=uploader.full_name,
        revision=item.revision,
        canDelete=can_delete_file(principal, item),
        createdAt=item.created_at,
    )


def _audit(principal: Principal, event_type: str, metadata: dict[str, object]) -> AuditEvent:
    return AuditEvent(
        organization_id=principal.membership.organization_id,
        actor_user_id=principal.profile.id,
        event_type=event_type,
        metadata_json=metadata,
    )


def normalize_upload(filename: str | None, content_type: str | None) -> tuple[str, str, str]:
    original_name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    if not original_name:
        raise ApiError(422, "file_name_required", "O arquivo precisa ter um nome.")
    original_name = original_name[:255]
    suffix = Path(original_name).suffix.lower()
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type in {"", "application/octet-stream"}:
        normalized_type = mimetypes.guess_type(original_name)[0] or ""
    allowed_extensions = ALLOWED_FILE_TYPES.get(normalized_type)
    if not allowed_extensions or suffix not in allowed_extensions:
        raise ApiError(
            422,
            "file_type_not_allowed",
            "Este formato de arquivo não é permitido no MVP.",
        )
    normalized_stem = unicodedata.normalize("NFKD", Path(original_name).stem)
    ascii_stem = normalized_stem.encode("ascii", "ignore").decode().lower()
    safe_stem = re.sub(r"[^a-z0-9]+", "-", ascii_stem).strip("-") or "arquivo"
    return original_name, normalized_type, f"{safe_stem[:80]}{suffix}"


async def read_upload(upload: UploadFile, max_size: int) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    digest = hashlib.sha256()
    size = 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        if size > max_size:
            raise ApiError(
                413,
                "file_too_large",
                f"O arquivo deve ter no máximo {max_size // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
        digest.update(chunk)
    if not size:
        raise ApiError(422, "file_empty", "O arquivo está vazio.")
    return b"".join(chunks), digest.hexdigest()


async def _with_storage_token[T](
    operation: Callable[[str], Awaitable[T]],
    principal: Principal,
    settings: Settings,
    db: Session,
) -> T:
    cipher = TokenCipher(settings.token_encryption_key.get_secret_value())
    try:
        access_token = cipher.decrypt(principal.session.access_token_ciphertext)
    except ValueError as exc:
        raise ApiError(401, "session_token_invalid", "Faça login novamente.") from exc
    try:
        return await operation(access_token)
    except StorageAuthenticationError:
        try:
            refresh_token = cipher.decrypt(principal.session.refresh_token_ciphertext)
        except ValueError as exc:
            raise ApiError(401, "session_token_invalid", "Faça login novamente.") from exc
        auth = SupabaseAuthGateway(
            str(settings.supabase_url), settings.supabase_publishable_key.get_secret_value()
        )
        tokens = await auth.refresh(refresh_token)
        if uuid.UUID(tokens.user.id) != principal.profile.auth_user_id:
            raise ApiError(401, "session_identity_changed", "Faça login novamente.") from None
        principal.session.access_token_ciphertext = cipher.encrypt(tokens.access_token)
        principal.session.refresh_token_ciphertext = cipher.encrypt(tokens.refresh_token)
        db.commit()
        try:
            return await operation(tokens.access_token)
        except StorageAuthenticationError as exc:
            raise ApiError(401, "session_token_invalid", "Faça login novamente.") from exc


@router.get("/{demand_id}/files", response_model=list[DemandFileOut])
def list_files(
    demand_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[DemandFileOut]:
    require_permission(principal, "demands:read")
    demand = _get_demand(db, demand_id, principal)
    rows = db.execute(
        select(DemandFile, UserProfile)
        .join(UserProfile, UserProfile.id == DemandFile.uploaded_by)
        .where(DemandFile.demand_id == demand.id, DemandFile.deleted_at.is_(None))
        .order_by(DemandFile.created_at.desc())
    ).all()
    return [_file_out(item, uploader, principal) for item, uploader in rows]


@router.post(
    "/{demand_id}/files",
    response_model=DemandFileOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_file(
    demand_id: uuid.UUID,
    file: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: SupabaseStorageGateway = Depends(get_storage_gateway),
) -> DemandFileOut:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    original_name, content_type, safe_name = normalize_upload(file.filename, file.content_type)
    contents, sha256 = await read_upload(file, settings.storage_max_file_size)
    object_path = (
        f"{demand.organization_id}/{demand.id}/{uuid.uuid4().hex}/{safe_name}"
    )

    await _with_storage_token(
        lambda token: storage.upload(object_path, contents, content_type, token),
        principal,
        settings,
        db,
    )

    item = DemandFile(
        organization_id=demand.organization_id,
        demand_id=demand.id,
        uploaded_by=principal.profile.id,
        original_name=original_name,
        storage_bucket=storage.bucket,
        storage_path=object_path,
        content_type=content_type,
        size_bytes=len(contents),
        sha256=sha256,
    )
    try:
        db.add(item)
        db.flush()
        db.add(
            DemandUpdate(
                demand_id=demand.id,
                created_by=principal.profile.id,
                kind="FILE_ATTACHED",
                summary=f"{original_name} foi anexado à demanda.",
                payload={"fileId": str(item.id), "sizeBytes": len(contents)},
            )
        )
        db.add(
            _audit(
                principal,
                "DEMAND_FILE_UPLOADED",
                {
                    "demandId": str(demand.id),
                    "fileId": str(item.id),
                    "sha256": sha256,
                    "sizeBytes": len(contents),
                },
            )
        )
        db.commit()
        db.refresh(item)
    except SQLAlchemyError:
        db.rollback()
        try:
            await _with_storage_token(
                lambda token: storage.remove(object_path, token), principal, settings, db
            )
        except (ApiError, StorageAuthenticationError):
            logger.exception("Falha ao remover objeto órfão do Storage", extra={"path": object_path})
        raise
    return _file_out(item, principal.profile, principal)


@router.post(
    "/{demand_id}/files/{file_id}/download",
    response_model=SignedFileOut,
    dependencies=[Depends(require_csrf)],
)
async def sign_file_download(
    demand_id: uuid.UUID,
    file_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: SupabaseStorageGateway = Depends(get_storage_gateway),
) -> SignedFileOut:
    require_permission(principal, "demands:read")
    demand = _get_demand(db, demand_id, principal)
    item = _get_file(db, demand, file_id)
    url = await _with_storage_token(
        lambda token: storage.create_signed_url(
            item.storage_path,
            token,
            settings.storage_signed_url_ttl,
            item.original_name,
        ),
        principal,
        settings,
        db,
    )
    return SignedFileOut(url=url, expiresAt=utc_now() + timedelta(seconds=settings.storage_signed_url_ttl))


@router.delete(
    "/{demand_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_file(
    demand_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: DemandFileDelete,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> None:
    require_any_permission(principal, "demands:write", "demands:work")
    demand = _get_demand(db, demand_id, principal)
    item = _get_file(db, demand, file_id, lock=True)
    if not can_delete_file(principal, item):
        raise ApiError(403, "demand_file_delete_denied", "Você não pode remover este arquivo.")
    if item.revision != payload.expected_revision:
        raise ApiError(409, "revision_conflict", "O arquivo foi alterado. Atualize a lista.")
    changed_at = utc_now()
    item.deleted_at = changed_at
    item.updated_at = changed_at
    item.revision += 1
    db.add(
        DemandUpdate(
            demand_id=demand.id,
            created_by=principal.profile.id,
            kind="FILE_REMOVED",
            summary=f"{item.original_name} foi removido da demanda.",
            payload={"fileId": str(item.id)},
        )
    )
    db.add(
        _audit(
            principal,
            "DEMAND_FILE_REMOVED",
            {"demandId": str(demand.id), "fileId": str(item.id)},
        )
    )
    db.commit()
