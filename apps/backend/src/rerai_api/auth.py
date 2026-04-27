from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from .convex import ConvexAuthClient, ConvexUser


@dataclass(frozen=True, slots=True)
class AuthContext:
    token: str
    user: ConvexUser


def parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Missing authorization token")
    return token.strip()


async def authenticate_request(
    authorization: str | None,
    convex_client: ConvexAuthClient,
) -> AuthContext:
    token = parse_bearer_token(authorization)
    try:
        user = await convex_client.get_viewer(token)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authorization token") from exc
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid authorization token")
    return AuthContext(token=token, user=user)


async def require_thread_owner(
    auth: AuthContext,
    convex_client: ConvexAuthClient,
    thread_id: str,
) -> None:
    try:
        owns_thread = await convex_client.owns_langgraph_thread(auth.token, thread_id)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Unauthorized thread access") from exc
    if not owns_thread:
        raise HTTPException(status_code=403, detail="Unauthorized thread access")
