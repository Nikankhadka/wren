"""Mint Supabase-style anon / service_role API keys from the project's JWT secret.

Supabase's anon and service_role keys are just HS256 JWTs signed with the
project's JWT secret, carrying ``{"role": "anon"|"service_role", "iss":
"supabase"}`` and a far-future ``exp`` - they are NOT user access tokens.
This helper mints them locally so the demo bootstrap
(``scripts/demo.sh``) can write a real anon key into ``frontend/.env.local``
and ``seeds/seed_demo`` can mint its own service_role token in-process for
the GoTrue Admin API, without committing a demo secret or passing anything
secret between processes.

Deliberately carries NO ``aud`` claim. Backend ``verify_token``
(app/core/auth.py) requires ``aud=authenticated`` and rejects any token
without it - so these role keys can never be used as an API bearer (same
property as hosted Supabase's keys, already regression-tested by
``test_signup_wrong_audience_token_is_unauthorized``). The role keys are
only ever presented to GoTrue (Admin API) or handed to supabase-js
(client init), never to the Wren backend.

Usage: ``uv run python -m seeds.supabase_keys anon`` (or ``service_role``)
prints the key for the caller's ``settings.supabase_jwt_secret``.
"""

from __future__ import annotations

import sys
import time

import jwt

from app.core.config import get_settings

_ROLES = ("anon", "service_role")
# 10 years - matches Supabase's own far-future key expiry. These are
# long-lived config keys, not user sessions.
_DEFAULT_EXPIS_IN = 10 * 365 * 24 * 60 * 60


def mint_key(role: str, secret: str, *, expires_in: int = _DEFAULT_EXPIS_IN) -> str:
    """Mint a Supabase role key (HS256) signed with ``secret``.

    ``role`` must be ``anon`` or ``service_role``. The payload is
    ``{"role", "iss": "supabase", "iat", "exp"}`` with no ``aud`` (see the
    module docstring for why).
    """
    if role not in _ROLES:
        raise ValueError(f"invalid role {role!r}; must be one of {_ROLES}")
    if not secret:
        raise ValueError("JWT secret must be non-empty")
    now = int(time.time())
    payload = {"role": role, "iss": "supabase", "iat": now, "exp": now + expires_in}
    return jwt.encode(payload, secret, algorithm="HS256")


def _main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in _ROLES:
        print(f"usage: python -m seeds.supabase_keys <{'|'.join(_ROLES)}>", file=sys.stderr)
        return 2
    secret = get_settings().supabase_jwt_secret
    if not secret:
        print("SUPABASE_JWT_SECRET is not set in backend/.env", file=sys.stderr)
        return 1
    print(mint_key(sys.argv[1], secret))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
