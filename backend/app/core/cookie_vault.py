"""Encrypt cookie files at rest and materialize temporary plaintext for downloaders."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().cookie_encryption_key
    if not key:
        raise HTTPException(status_code=503, detail="Cookie encryption key is not configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise HTTPException(status_code=503, detail="Cookie encryption key is invalid")


def encrypt_cookie(contents: bytes) -> bytes:
    return _fernet().encrypt(contents)


def decrypt_cookie_file(path: Path) -> str:
    fernet = _fernet()
    # Wrap the read so a transient FS error (file moved, perm denied)
    # surfaces as RuntimeError instead of leaking the OSError + a
    # half-decrypted tempfile.
    try:
        stored = path.read_bytes()
    except OSError as e:
        raise RuntimeError(f"Cannot read cookie file {path.name}: {e}") from e
    try:
        contents = fernet.decrypt(stored)
    except InvalidToken:
        # Upgrade cookies created by earlier versions on first use.
        if not stored.startswith((b"# Netscape HTTP Cookie File", b"# HTTP Cookie File")):
            raise RuntimeError(f"Cookie file cannot be decrypted with the configured key: {path.name}")
        contents = stored
        path.write_bytes(fernet.encrypt(contents))
    fd, temp_path = tempfile.mkstemp(prefix="dnload_cookie_", suffix=".txt")
    try:
        os.chmod(temp_path, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(contents)
        return temp_path
    except Exception:
        os.close(fd)
        Path(temp_path).unlink(missing_ok=True)
        raise
