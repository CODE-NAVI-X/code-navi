"""Pydantic schemas for auth API request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: str
    displayName: str
    email: str
    emailVerified: bool
    status: str


class SessionInfo(BaseModel):
    id: str
    createdAt: str
    expiresAt: str
    remembered: bool


class ClaimResult(BaseModel):
    claimed: bool
    workspaceCount: int = 0
    taskCount: int = 0
    activityCount: int = 0


class SessionResponse(BaseModel):
    mode: str
    user: UserOut | None
    session: SessionInfo
    csrfToken: str
    claimResult: ClaimResult | None


class RegisterRequest(BaseModel):
    email: str
    password: str
    displayName: str = Field(min_length=1, max_length=100)
    claimGuestData: bool = True


class LoginRequest(BaseModel):
    email: str
    password: str
    rememberMe: bool = False
    claimGuestData: bool = True


class LogoutAllRequest(BaseModel):
    currentPassword: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    newPassword: str


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str


class EmailVerificationRequest(BaseModel):
    email: str | None = None


class EmailVerificationConfirmRequest(BaseModel):
    token: str


class EmailChangeRequest(BaseModel):
    newEmail: str
    currentPassword: str


class EmailChangeConfirmRequest(BaseModel):
    token: str


class UpdateProfileRequest(BaseModel):
    displayName: str = Field(min_length=1, max_length=100)


class DeleteAccountRequest(BaseModel):
    currentPassword: str
    confirmation: str


class UserResponse(BaseModel):
    id: str
    displayName: str
    email: str
    emailVerified: bool
    status: str


class SessionItem(BaseModel):
    id: str
    createdAt: str
    lastSeenAt: str
    expiresAt: str
    userAgentLabel: str | None
    current: bool


class SessionListResponse(BaseModel):
    items: list[SessionItem]
