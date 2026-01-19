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
        description="Authentication provider (local|ad|keycloak|dev). Optional.",
    )


class LoginResponse(BaseModel):
    """
    Returned for compatibility / debug.
    ⚠️ Session cookie is the real auth mechanism.
    """
    session: str = Field(..., description="Session identifier")
    user: "UserInfo"


# ------------------------------------------------------------------
# User
# ------------------------------------------------------------------

class UserInfo(BaseModel):
    """
    Canonical user object shared across:
    - auth-service
    - gateway
    - frontend
    """

    # Internal stable identifier (DAL / KC / AD)
    user_id: str = Field(..., description="Internal user identifier")

    # Login / username
    username: str = Field(..., description="Login name")

    # Optional identity attributes
    display_name: Optional[str] = Field(
        default=None,
        description="Human-readable display name",
    )
    email: Optional[str] = Field(
        default=None,
        description="User email address",
    )

    # Authorization
    roles: List[str] = Field(
        default_factory=list,
        description="Assigned roles",
    )
    permissions: List[str] = Field(
        default_factory=list,
        description="Computed permissions",
    )

    # Raw external groups as returned by identity sources.
    # - AD: distinguishedName strings from memberOf
    # - OIDC/Keycloak: group paths or names
    # Used by governance to map to BornToShare roles.
    groups: List[str] = Field(
        default_factory=list,
        description="External groups (raw) used for governance mapping",
    )

    # Optional stable external identifier (DN, subject, etc.)
    external_id: Optional[str] = Field(
        default=None,
        description="External stable id (DN/sub/etc.)",
    )

    # Source of authentication
    auth_source: str = Field(
        ...,
        description="Authentication source (local|ad|keycloak|dev)",
    )


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


# ------------------------------------------------------------------
# Keycloak
# ------------------------------------------------------------------

class KeycloakCallbackResponse(BaseModel):
    """
    Returned after successful Keycloak login.
    Cookie remains the source of truth.
    """
    session: str = Field(..., description="Session identifier")
    user: UserInfo
