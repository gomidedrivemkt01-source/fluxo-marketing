from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    privacy_notice_version: str = Field(alias="privacyNoticeVersion", min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Informe o nome")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6,8}$")
    purpose: Literal["signup", "recovery"]


class EmailRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    recovery_token: str = Field(alias="recoveryToken", min_length=20, max_length=4096)
    password: str = Field(min_length=12, max_length=128)


class MessageResponse(BaseModel):
    message: str


class SessionResponse(BaseModel):
    state: Literal["pending_approval", "active", "suspended"]
    name: str
    email: EmailStr
    role: str | None


class RecoveryResponse(BaseModel):
    recovery_token: str = Field(alias="recoveryToken")
