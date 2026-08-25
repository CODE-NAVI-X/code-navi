"""Cryptographic helpers: hashing, token generation, and password verification."""

from __future__ import annotations

import hashlib
import re
import secrets

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# -- Password hashing --------------------------------------------------------

_password_hash = PasswordHash([Argon2Hasher()])

# Common weak passwords (minimal inline blocklist)
_WEAK_PASSWORDS: frozenset[str] = frozenset(
    [
        "password",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty123",
        "password1",
        "iloveyou",
        "admin123",
        "letmein1",
        "welcome1",
        "monkey12",
        "dragon12",
        "master12",
        "sunshine",
        "princess",
        "football",
        "baseball",
        "superman",
        "trustno1",
        "passw0rd",
        "abc12345",
        "abcdefgh",
    ]
)


def hash_password(plain: str) -> str:
    """Return Argon2id hash of the plain-text password."""
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches hashed."""
    try:
        return _password_hash.verify(plain, hashed)
    except Exception:
        return False


def validate_password_strength(plain: str, email: str | None = None) -> str | None:
    """Return an error message if the password is too weak, else None."""
    if len(plain) < 8:
        return "密码至少需要 8 个字符"
    if len(plain) > 64:
        return "密码不能超过 64 个字符"
    if plain.lower() in _WEAK_PASSWORDS:
        return "密码过于常见，请选择更安全的密码"
    # Reject if password is clearly a repetition of email local part
    if email:
        local = email.split("@")[0].lower()
        if len(local) >= 4 and local in plain.lower():
            return "密码不能包含邮箱地址的主要部分"
    return None


# -- Token generation --------------------------------------------------------


def generate_session_token() -> str:
    """Generate a cryptographically secure opaque session token."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def generate_one_time_token() -> str:
    """Generate a random one-time token (for email verification etc.)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return SHA-256 hex digest of the token. Only hashes are stored in DB."""
    return hashlib.sha256(token.encode()).hexdigest()


# -- Email normalisation ------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    """Lowercase and strip whitespace for storage/lookup."""
    return email.strip().lower()


def validate_email_format(email: str) -> bool:
    """Return True if the email looks syntactically valid."""
    return bool(_EMAIL_RE.match(email.strip())) and len(email.strip()) <= 320