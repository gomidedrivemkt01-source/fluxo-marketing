from pathlib import Path

import pytest

from app.api.errors import ApiError
from app.storage import LocalStorageGateway

SIGNING_KEY = "storage-signing-secret-with-more-than-32-characters"


def gateway(tmp_path: Path) -> LocalStorageGateway:
    return LocalStorageGateway(tmp_path, "demand-files", SIGNING_KEY)


@pytest.mark.asyncio
async def test_upload_download_and_remove_round_trip(tmp_path: Path) -> None:
    storage = gateway(tmp_path)
    await storage.upload("org/demand/abc/briefing.pdf", b"%PDF-test", "application/pdf")
    assert (tmp_path / "demand-files/org/demand/abc/briefing.pdf").read_bytes() == b"%PDF-test"
    assert await storage.download("org/demand/abc/briefing.pdf") == b"%PDF-test"
    await storage.remove("org/demand/abc/briefing.pdf")
    with pytest.raises(ApiError) as caught:
        await storage.download("org/demand/abc/briefing.pdf")
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_upload_never_overwrites_existing_object(tmp_path: Path) -> None:
    storage = gateway(tmp_path)
    await storage.upload("org/demand/abc/a.txt", b"first", "text/plain")
    with pytest.raises(ApiError) as caught:
        await storage.upload("org/demand/abc/a.txt", b"second", "text/plain")
    assert caught.value.status_code == 409
    assert await storage.download("org/demand/abc/a.txt") == b"first"


@pytest.mark.parametrize("path", ["../outside.txt", "org/../../outside.txt", "/etc/passwd", ""])
def test_paths_cannot_escape_bucket(tmp_path: Path, path: str) -> None:
    with pytest.raises(ApiError) as caught:
        gateway(tmp_path).create_signed_url(path, "text/plain", None)
    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_signed_url_resolves_until_it_expires(tmp_path: Path) -> None:
    storage = gateway(tmp_path)
    await storage.upload("org/demand/abc/capa.png", b"png", "image/png")
    url = storage.create_signed_url("org/demand/abc/capa.png", "image/png", "Capa.png")
    token = url.rsplit("/", 1)[1]
    signed = storage.resolve_signed(token, 120)
    assert signed.path.read_bytes() == b"png"
    assert (signed.content_type, signed.download_name) == ("image/png", "Capa.png")


def test_tampered_or_foreign_token_is_rejected(tmp_path: Path) -> None:
    foreign = LocalStorageGateway(tmp_path, "demand-files", "another-secret-with-more-than-32-chars!")
    token = foreign.create_signed_url("org/a.txt", "text/plain", None).rsplit("/", 1)[1]
    with pytest.raises(ApiError) as caught:
        gateway(tmp_path).resolve_signed(token, 120)
    assert caught.value.status_code == 403
