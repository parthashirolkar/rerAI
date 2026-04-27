from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True, slots=True)
class ConvexUser:
    user_id: str
    token_identifier: str | None = None


class ConvexAuthClient(Protocol):
    async def get_viewer(self, token: str) -> ConvexUser | None: ...

    async def owns_langgraph_thread(self, token: str, thread_id: str) -> bool: ...


def _trim_trailing_slash(value: str) -> str:
    return value.rstrip("/")


def _default_convex_url() -> str:
    return (
        os.getenv("CONVEX_URL", "").strip()
        or os.getenv("CONVEX_SITE_URL", "").strip()
        or os.getenv("VITE_CONVEX_URL", "").strip()
    )


class ConvexHttpClient:
    def __init__(self, convex_url: str | None = None) -> None:
        self.convex_url = _trim_trailing_slash(convex_url or _default_convex_url())

    async def _call(
        self, endpoint: str, token: str, path: str, args: dict[str, Any] | None = None
    ) -> Any:
        if not self.convex_url:
            raise RuntimeError("Missing CONVEX_URL")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.convex_url}/api/{endpoint}",
                headers={"Authorization": f"Bearer {token}"},
                json={"path": path, "args": args or {}, "format": "json"},
            )
        if response.status_code in {401, 403}:
            return None
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "value" in payload:
            return payload["value"]
        return payload

    async def query(
        self, token: str, path: str, args: dict[str, Any] | None = None
    ) -> Any:
        return await self._call("query", token, path, args)

    async def mutation(
        self, token: str, path: str, args: dict[str, Any] | None = None
    ) -> Any:
        return await self._call("mutation", token, path, args)

    async def get_viewer(self, token: str) -> ConvexUser | None:
        payload = await self.query(token, "backend:viewer")
        if not isinstance(payload, dict):
            return None
        user_id = payload.get("userId")
        if not isinstance(user_id, str) or not user_id:
            return None
        token_identifier = payload.get("tokenIdentifier")
        return ConvexUser(
            user_id=user_id,
            token_identifier=token_identifier if isinstance(token_identifier, str) else None,
        )

    async def owns_langgraph_thread(self, token: str, thread_id: str) -> bool:
        payload = await self.query(
            token,
            "backend:getThreadByLangGraphThreadId",
            {"langgraphThreadId": thread_id},
        )
        return isinstance(payload, dict) and payload.get("langgraphThreadId") == thread_id
