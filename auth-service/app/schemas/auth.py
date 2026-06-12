from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., description="Username / login")
    password: str = Field(..., description="User password")
    provider: Optional[str] = Field(
        default=None,
        description="Authentication provider (local|ad). Optional.",
    )


class LoginResponse(BaseModel):
    """
    Login response payload.
    Session is cookie-based and is not exposed in body.
    """
    user: "UserInfo"


# ------------------------------------------------------------------
# User
# ------------------------------------------------------------------

class UserInfo(BaseModel):
    identity_id: Optional[str] = None
    identity_source_id: Optional[int] = None
    username: str

    display_name: Optional[str] = None
    email: Optional[str] = None

    external_id: Optional[str] = None
    auth_source: str

    is_admin: bool = False

    # Convenience projection derived from roles at session build time.
    roles: List[str] = Field(default_factory=list)


class IntrospectRequest(BaseModel):
    session: str = Field(..., description="Session identifier")


class IntrospectResponse(BaseModel):
    active: bool
    authenticated: bool = False
    session_status: str = "inactive"
    identity_id: Optional[str] = None
    user: Optional["UserInfo"] = None
    auth_source: Optional[str] = None
    expires_at: Optional[str] = None
    roles: List[str] = Field(default_factory=list)



# ------------------------------------------------------------------
# Password management
# ------------------------------------------------------------------

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., description="New password")


class ChangePasswordResponse(BaseModel):
    detail: str = Field(
        default="Password changed",
        description="Operation status",
    )


# ------------------------------------------------------------------
# Logout
# ------------------------------------------------------------------

class LogoutResponse(BaseModel):
    detail: str = Field(
        default="Logged out",
        description="Operation status",
    )
