from pathlib import Path
from types import SimpleNamespace

from cryptography.fernet import Fernet

from app.core import cookie_vault


def test_encrypt_decrypt_and_upgrade_legacy_cookie(tmp_path: Path, monkeypatch) -> None:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        cookie_vault,
        "get_settings",
        lambda: SimpleNamespace(cookie_encryption_key=key),
    )
    contents = b"# Netscape HTTP Cookie File\nsecret=value\n"

    encrypted = cookie_vault.encrypt_cookie(contents)
    assert encrypted != contents
    assert Fernet(key.encode("ascii")).decrypt(encrypted) == contents

    stored = tmp_path / "cookie.txt"
    stored.write_bytes(encrypted)
    plaintext_path = Path(cookie_vault.decrypt_cookie_file(stored))
    try:
        assert plaintext_path.read_bytes() == contents
        assert stored.read_bytes() == encrypted
    finally:
        plaintext_path.unlink(missing_ok=True)

    stored.write_bytes(contents)
    plaintext_path = Path(cookie_vault.decrypt_cookie_file(stored))
    try:
        assert plaintext_path.read_bytes() == contents
        assert stored.read_bytes() != contents
        assert Fernet(key.encode("ascii")).decrypt(stored.read_bytes()) == contents
    finally:
        plaintext_path.unlink(missing_ok=True)
