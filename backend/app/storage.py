"""Armazenamento dos anexos em disco local (volume Docker).

A autorização acontece na API antes de qualquer operação; o download usa um link
assinado e de curta duração servido pela própria aplicação.
"""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import anyio

from app.api.errors import ApiError
from app.core.security import TokenCipher

SIGNED_FILES_PATH = "/api/v1/files/signed"


@dataclass(frozen=True, slots=True)
class SignedObject:
    path: Path
    content_type: str
    download_name: str | None


class LocalStorageGateway:
    def __init__(self, root: Path, bucket: str, signing_key: str) -> None:
        self._root = (root / bucket).resolve()
        self._cipher = TokenCipher(signing_key)
        self.bucket = bucket

    def _object_path(self, path: str) -> Path:
        target = (self._root / path).resolve()
        if not path or not target.is_relative_to(self._root) or target == self._root:
            raise ApiError(400, "file_path_invalid", "Caminho de arquivo inválido.")
        return target

    @staticmethod
    def _write_new(target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ApiError(409, "file_object_conflict", "Já existe um arquivo neste caminho.")
        descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, target)
        except FileExistsError as exc:
            raise ApiError(
                409, "file_object_conflict", "Já existe um arquivo neste caminho."
            ) from exc
        finally:
            os.unlink(temporary)

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        target = self._object_path(path)
        try:
            await anyio.to_thread.run_sync(self._write_new, target, data)
        except OSError as exc:
            raise ApiError(
                503, "file_storage_unavailable", "O serviço de arquivos está indisponível."
            ) from exc

    async def remove(self, path: str) -> None:
        target = self._object_path(path)
        await anyio.to_thread.run_sync(lambda: target.unlink(missing_ok=True))

    async def download(self, path: str) -> bytes:
        target = self._object_path(path)
        try:
            return await anyio.to_thread.run_sync(target.read_bytes)
        except FileNotFoundError as exc:
            raise ApiError(404, "file_object_not_found", "O arquivo não está disponível.") from exc

    def create_signed_url(
        self,
        path: str,
        content_type: str,
        download_name: str | None,
    ) -> str:
        self._object_path(path)
        token = self._cipher.encrypt(
            json.dumps({"path": path, "type": content_type, "name": download_name})
        )
        return f"{SIGNED_FILES_PATH}/{token}"

    def resolve_signed(self, token: str, expires_in: int) -> SignedObject:
        try:
            payload = json.loads(self._cipher.decrypt(token, ttl=expires_in))
        except ValueError as exc:
            raise ApiError(
                403, "file_link_expired", "O link do arquivo expirou. Abra-o novamente."
            ) from exc
        target = self._object_path(str(payload["path"]))
        if not target.is_file():
            raise ApiError(404, "file_object_not_found", "O arquivo não está disponível.")
        return SignedObject(target, str(payload["type"]), payload.get("name"))
