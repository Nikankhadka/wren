"""T-004: Supabase JWT verification and the tenant/platform-admin auth dependencies.

Supabase issues HS256 access tokens signed with the project's JWT secret
(``settings.supabase_jwt_secret``), audience ``authenticated``, ``sub`` set to the
Supabase ``auth.users.id``. This module verifies that token and turns it into one
of two authenticated-principal dataclasses, each backed by a pre-context lookup
that runs through the resolver functions from migration 0009 (``resolve_user_tenant``,
``resolve_platform_admin``) - the one legitimate way to read `users` /
`platform_admins` before any ``tenant_context`` exists, mirroring
``resolve_tenant_slug`` (0003). See database.md sections 2 and 3.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import db
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Supabase access tokens always carry this audience; verifying it is part of
# validating the token, not an optional extra.
SUPABASE_AUDIENCE = "authenticated"

_bearer_scheme = HTTPBearer(auto_error=False)


class AuthConfigError(RuntimeError):
    """Raised when SUPABASE_JWT_SECRET is unset or empty.

    Deliberately distinct from an auth failure: an empty secret must never fall
    back to unsigned/"none" verification, and the caller (a misconfigured
    deployment) should see a 500, not a misleading 401.
    """


@dataclass(frozen=True)
class AuthedTenantAdmin:
    user_id: UUID
    tenant_id: UUID


@dataclass(frozen=True)
class AuthedPlatformAdmin:
    user_id: UUID


def verify_token(token: str) -> UUID:
    """Verify a Supabase access token and return the user id (`sub` claim).

    Raises ``AuthConfigError`` if the JWT secret is not configured, and
    ``HTTPException(401)`` for any invalid/expired/wrong-audience token.
    """
    settings = get_settings()
    secret = settings.supabase_jwt_secret
    if not secret:
        raise AuthConfigError("SUPABASE_JWT_SECRET is not configured")

    try:
        # ``exp`` is only validated by PyJWT when present; require it so a token
        # minted without one can never be accepted as a forever-valid credential.
        # ``aud`` is effectively required by passing ``audience=`` (this is also
        # what rejects the public anon / service_role API keys, which are signed
        # with the same secret but carry no ``aud`` claim).
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=SUPABASE_AUDIENCE,
            options={"require": ["exp"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        ) from exc

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing sub")
    try:
        return UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token sub is not a valid user id"
        ) from exc


async def authenticate(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UUID:
    """Bare authentication: verify the bearer token, return the user id.

    Used directly by routes (e.g. signup) that need an authenticated caller but
    resolve tenant/platform membership themselves rather than through one of the
    dependencies below.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        return verify_token(credentials.credentials)
    except AuthConfigError as exc:
        logger.error("auth config error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="auth misconfigured"
        ) from exc


async def require_tenant_admin(
    user_id: Annotated[UUID, Depends(authenticate)],
) -> AuthedTenantAdmin:
    """Authenticate, then resolve the caller's ``users`` row -> tenant membership.

    403 when the token is valid but the user has no ``users`` row (never signed
    up / not a member of any tenant).
    """
    pool = db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("select tenant_id, role from resolve_user_tenant($1)", user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="no tenant membership for this user"
        )
    return AuthedTenantAdmin(user_id=user_id, tenant_id=row["tenant_id"])


async def require_platform_admin(
    user_id: Annotated[UUID, Depends(authenticate)],
) -> AuthedPlatformAdmin:
    """Authenticate, then check ``platform_admins`` membership.

    403 when the token is valid but the user has no ``platform_admins`` row.
    """
    pool = db.get_pool()
    async with pool.acquire() as conn:
        is_admin = await conn.fetchval("select resolve_platform_admin($1)", user_id)
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not a platform admin")
    return AuthedPlatformAdmin(user_id=user_id)
