"""FastAPI auth dependencies — `require_user` and `require_scope`."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.oidc import Principal, TokenError, get_verifier

_bearer = HTTPBearer(auto_error=False, description="OIDC bearer token")


async def require_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        principal = get_verifier().verify(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    request.state.principal = principal
    return principal


def require_scope(*required: str):
    async def _checker(principal: Principal = Depends(require_user)) -> Principal:
        missing = [s for s in required if s not in principal.scopes]
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"missing scope: {','.join(missing)}",
            )
        return principal
    return _checker
