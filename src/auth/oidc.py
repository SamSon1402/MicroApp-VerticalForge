"""OIDC bearer-token verifier (JWKS-backed).

Same pattern as a LumApps tenant SSO setup: trust the customer's IdP, verify
against its published JWKS, enforce audience + issuer claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from src.config import get_settings


class TokenError(Exception):
    """Raised when a bearer token fails verification."""


@dataclass(frozen=True)
class Principal:
    subject: str
    email: str | None
    tenant_id: str | None
    scopes: tuple[str, ...]
    raw_claims: dict[str, Any]


class OidcVerifier:
    def __init__(self, issuer: str, jwks_url: str, audience: str) -> None:
        self.issuer = issuer
        self.audience = audience
        self._jwk_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)

    def verify(self, token: str) -> Principal:
        try:
            key = self._jwk_client.get_signing_key_from_jwt(token).key
        except Exception as exc:  # noqa: BLE001
            raise TokenError(f"JWKS lookup failed: {exc}") from exc

        try:
            claims: dict[str, Any] = jwt.decode(
                token, key,
                algorithms=["RS256", "RS384", "RS512"],
                audience=self.audience, issuer=self.issuer,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("token expired") from exc
        except jwt.InvalidTokenError as exc:
            raise TokenError(f"invalid token: {exc}") from exc

        scopes_raw = claims.get("scp") or claims.get("scope") or ""
        scopes = tuple(scopes_raw.split()) if isinstance(scopes_raw, str) else tuple(scopes_raw)
        return Principal(
            subject=claims["sub"],
            email=claims.get("email") or claims.get("preferred_username"),
            tenant_id=claims.get("tid"),
            scopes=scopes,
            raw_claims=claims,
        )


_verifier: OidcVerifier | None = None


def get_verifier() -> OidcVerifier:
    global _verifier
    if _verifier is None:
        s = get_settings()
        _verifier = OidcVerifier(s.oidc_issuer, str(s.oidc_jwks_url), s.oidc_audience)
    return _verifier
