"""Email sender protocol and dev-mode logging implementation."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    """Protocol for sending auth-related emails."""

    def send_verification_email(self, email: str, token: str) -> None: ...

    def send_password_reset_email(self, email: str, token: str) -> None: ...

    def send_email_change_email(self, new_email: str, token: str) -> None: ...


class LoggingEmailSender:
    """Dev-mode sender: logs token/link instead of delivering real email.

    Tokens are written to the server log only; they NEVER appear in API
    responses. Replace this with a real SMTP implementation for production.
    """

    def send_verification_email(self, email: str, token: str) -> None:
        logger.info(
            "[DEV EMAIL] Email verification for %s -- token: %s",
            email,
            token,
        )

    def send_password_reset_email(self, email: str, token: str) -> None:
        logger.info(
            "[DEV EMAIL] Password reset for %s -- token: %s",
            email,
            token,
        )

    def send_email_change_email(self, new_email: str, token: str) -> None:
        logger.info(
            "[DEV EMAIL] Email change confirmation for %s -- token: %s",
            new_email,
            token,
        )


# Default singleton used by the router.
_default_sender: EmailSender = LoggingEmailSender()


def get_email_sender() -> EmailSender:
    """FastAPI dependency: returns the configured email sender."""
    return _default_sender