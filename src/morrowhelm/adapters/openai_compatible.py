from __future__ import annotations

from typing import Any

from .base import RuntimeAdapter, RuntimeEvent, RuntimeEventType


class OpenAICompatibleAdapter(RuntimeAdapter):
    """Normalize chat-completions-shaped responses without owning the client."""

    name = "openai-compatible"

    def __init__(self, base_url: str, model: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def receive(self, payload: dict[str, Any]) -> RuntimeEvent:
        choices = payload.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        event_type = RuntimeEventType.APPROVAL_REQUEST if message.get("tool_calls") else RuntimeEventType.MESSAGE
        return RuntimeEvent(
            event_type=event_type,
            source=self.name,
            payload=payload,
            event_id=str(payload.get("id") or ""),
            metadata={"base_url": self.base_url, "model": self.model or payload.get("model")},
        )

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "base_url": self.base_url, "model": self.model, "capabilities": ["messages", "tool_approval"]}
