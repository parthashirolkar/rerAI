from __future__ import annotations

from typing import Any


def _message_type(message: dict[str, Any]) -> str:
    return str(message.get("type") or message.get("role") or "").lower()


def _text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(part for part in parts if part)


def canonical_assistant_messages(
    state: dict[str, Any], *, human_message_id: str
) -> list[dict[str, Any]]:
    raw_messages = state.get("values", {}).get("messages", [])
    if not isinstance(raw_messages, list):
        return []

    inside_turn = False
    result: list[dict[str, Any]] = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        message_type = _message_type(raw)
        message_id = raw.get("id")
        if message_type in {"human", "user"}:
            if inside_turn:
                break
            inside_turn = message_id == human_message_id
            continue
        if not inside_turn or message_type not in {"ai", "assistant"}:
            continue
        content = _text_content(raw.get("content")).strip()
        if not content:
            continue
        stable_id = str(message_id or f"assistant-{len(result)}")
        projected = {
            "messageId": stable_id,
            "messagePosition": len(result),
            "canonicalContent": content,
        }
        if message_id:
            projected["langgraphMessageId"] = str(message_id)
        result.append(projected)
    return result


def streamed_assistant_messages(events: list[Any]) -> list[dict[str, Any]]:
    messages_by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        if getattr(event, "event", None) != "messages":
            continue
        data = getattr(event, "data", None)
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            continue
        raw = data[0]
        message_type = _message_type(raw)
        if message_type not in {
            "ai",
            "assistant",
            "aimessage",
            "aimessagechunk",
        }:
            continue
        content = _text_content(raw.get("content"))
        if not content:
            continue
        message_id = str(raw.get("id") or f"stream-{len(messages_by_id)}")
        existing = messages_by_id.get(message_id)
        if existing is None:
            projected = {
                "messageId": message_id,
                "messagePosition": len(messages_by_id),
                "content": content,
            }
            if raw.get("id"):
                projected["langgraphMessageId"] = str(raw["id"])
            messages_by_id[message_id] = projected
            continue
        previous = existing["content"]
        existing["content"] = (
            content if content.startswith(previous) else f"{previous}{content}"
        )
    return list(messages_by_id.values())


def reconcile_assistant_messages(
    canonical: list[dict[str, Any]],
    streamed: list[dict[str, Any]],
    *,
    preserve_display_only: bool,
) -> list[dict[str, Any]]:
    stream_by_id = {message["messageId"]: message for message in streamed}
    canonical_ids = {message["messageId"] for message in canonical}
    next_position = len(streamed)
    result: list[dict[str, Any]] = []

    for message in canonical:
        streamed_message = stream_by_id.get(message["messageId"])
        projected = dict(message)
        if streamed_message is not None:
            projected["messagePosition"] = streamed_message["messagePosition"]
            streamed_content = streamed_message["content"]
            canonical_content = message["canonicalContent"]
            if (
                preserve_display_only
                and streamed_content.startswith(canonical_content)
                and streamed_content != canonical_content
            ):
                projected["displayOnlyContent"] = streamed_content[
                    len(canonical_content) :
                ]
        else:
            projected["messagePosition"] = next_position
            next_position += 1
        result.append(projected)

    if preserve_display_only:
        for message in streamed:
            if message["messageId"] in canonical_ids:
                continue
            projected = {
                "messageId": message["messageId"],
                "messagePosition": message["messagePosition"],
                "canonicalContent": "",
                "displayOnlyContent": message["content"],
            }
            if message.get("langgraphMessageId"):
                projected["langgraphMessageId"] = message["langgraphMessageId"]
            result.append(projected)

    return sorted(result, key=lambda message: message["messagePosition"])
