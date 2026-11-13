"""Column-level encryption for sensitive data (national IDs, license keys)."""
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from .config import get_settings

_fernet = Fernet(get_settings().encryption_key.encode())


class EncryptedString(TypeDecorator):
    """Transparently encrypts on write and decrypts on read (AES-128-CBC + HMAC via Fernet)."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return None
        return _fernet.encrypt(str(value).encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            return "<decryption-failed>"
