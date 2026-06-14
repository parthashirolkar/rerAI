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

    async def ensure_turn(
        self,
        token: str,
        *,
        ui_thread_id: str,
        turn_id: str,
        human_message_id: str,
        content: str,
    ) -> dict[str, Any]: ...

    async def mark_turn_running(
        self,
        token: str,
        *,
        turn_id: str,
        langgraph_thread_id: str,
        langgraph_run_id: str,
    ) -> dict[str, Any]: ...

    async def finalize_turn(self, payload: dict[str, Any]) -> None: ...

    async def project_turn(self, payload: dict[str, Any]) -> None: ...

    async def list_stale_pending_turns(self, *, cutoff_timestamp: int) -> list[dict[str, Any]]: ...

    async def list_invalid_running_turns(self) -> list[dict[str, Any]]: ...


def _trim_trailing_slash(value: str) -> str:
    return value.rstrip("/")


def _default_convex_url() -> str:
    return (
        os.getenv("CONVEX_URL", "").strip()
        or os.getenv("CONVEX_SITE_URL", "").strip()
        or os.getenv("VITE_CONVEX_URL", "").strip()
    )


class ConvexHttpClient:
    def __init__(
        self,
        convex_url: str | None = None,
        *,
        site_url: str | None = None,
        service_token: str | None = None,
    ) -> None:
        self.convex_url = _trim_trailing_slash(convex_url or _default_convex_url())
        self.site_url = _trim_trailing_slash(
            site_url or os.getenv("CONVEX_SITE_URL", "").strip()
        )
        self.service_token = (
            service_token or os.getenv("CONVEX_SERVICE_TOKEN", "").strip()
        )

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

    async def ensure_turn(
        self,
        token: str,
        *,
        ui_thread_id: str,
        turn_id: str,
        human_message_id: str,
        content: str,
    ) -> dict[str, Any]:
        payload = await self.mutation(
            token,
            "backend:ensureTurn",
            {
                "uiThreadId": ui_thread_id,
                "turnId": turn_id,
                "humanMessageId": human_message_id,
                "content": content,
            },
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Convex did not return a Conversation Turn")
        return payload

    async def mark_turn_running(
        self,
        token: str,
        *,
        turn_id: str,
        langgraph_thread_id: str,
        langgraph_run_id: str,
    ) -> dict[str, Any]:
        payload = await self.mutation(
            token,
            "backend:markTurnRunning",
            {
                "turnId": turn_id,
                "langgraphThreadId": langgraph_thread_id,
                "langgraphRunId": langgraph_run_id,
            },
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Convex did not return a running Conversation Turn")
        return payload

    async def finalize_turn(self, payload: dict[str, Any]) -> None:
        if not self.site_url or not self.service_token:
            raise RuntimeError("Convex service finalization is not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.site_url}/service/turns/finalize",
                headers={"x-rerai-service-token": self.service_token},
                json=payload,
            )
        response.raise_for_status()

    async def project_turn(self, payload: dict[str, Any]) -> None:
        if not self.site_url or not self.service_token:
            raise RuntimeError("Convex service projection is not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.site_url}/service/turns/project",
                headers={"x-rerai-service-token": self.service_token},
                json=payload,
            )
        response.raise_for_status()

    async def list_stale_pending_turns(self, *, cutoff_timestamp: int) -> list[dict[str, Any]]:
        if not self.site_url or not self.service_token:
            raise RuntimeError("Convex service list stale pending is not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.site_url}/service/turns/listStalePending",
                headers={"x-rerai-service-token": self.service_token},
                json={"cutoffTimestamp": cutoff_timestamp},
            )
        response.raise_for_status()
        return response.json()

    async def list_invalid_running_turns(self) -> list[dict[str, Any]]:
        if not self.site_url or not self.service_token:
            raise RuntimeError("Convex service list invalid running is not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.site_url}/service/turns/listInvalidRunning",
                headers={"x-rerai-service-token": self.service_token},
            )
        response.raise_for_status()
        return response.json()
