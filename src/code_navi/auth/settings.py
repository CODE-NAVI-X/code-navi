"""Auth-specific configuration read from environment variables."""

from __future__ import annotations

import os


class SessionSettings:
    """Cookie and session configuration."""

    @property
    def cookie_name(self) -> str:
        name = os.getenv("CODE_NAVI_COOKIE_NAME", "")
        if name:
            return name
        # Use __Host- prefix only when Secure is enabled (production)
        return "__Host-code_navi_session" if self.cookie_secure else "code_navi_session"

    @property
    def cookie_secure(self) -> bool:
        env = os.getenv("CODE_NAVI_COOKIE_SECURE", "")
        if env in ("1", "true", "True"):
            return True
        if env in ("0", "false", "False"):
            return False
        # Default: secure if HTTPS-related env indicates production
        return False  # dev default; override via env for production

    @property
    def cookie_samesite(self) -> str:
        return "lax"

    @property
    def session_ttl_days(self) -> int:
        return int(os.getenv("CODE_NAVI_SESSION_TTL_DAYS", "30"))

    @property
    def session_ttl_seconds(self) -> int:
        """Short session (non-remembered) TTL in seconds - 24h by default."""
        return int(os.getenv("CODE_NAVI_SESSION_SHORT_TTL_SECONDS", str(86400)))

    @property
    def require_email_verification(self) -> bool:
        return os.getenv("CODE_NAVI_REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"

    @property
    def reset_token_ttl_minutes(self) -> int:
        return int(os.getenv("CODE_NAVI_RESET_TOKEN_TTL_MINUTES", "30"))

    @property
    def renew_threshold_fraction(self) -> float:
        """Renew remembered session when remaining life < this fraction of total TTL."""
        return 0.5

    @property
    def cors_origins(self) -> list[str]:
        configured = os.getenv("CODE_NAVI_CORS_ORIGINS")
        if not configured:
            return ["http://127.0.0.1:3000", "http://localhost:3000"]
        return [o.strip().rstrip("/") for o in configured.split(",") if o.strip()]

    @property
    def allow_registration(self) -> bool:
        env = os.getenv("CODE_NAVI_ALLOW_REGISTRATION", "true")
        return env.lower() in ("1", "true", "yes")

    @property
    def environment(self) -> str:
        return os.getenv("CODE_NAVI_ENV", "dev").lower()


session_settings = SessionSettings()