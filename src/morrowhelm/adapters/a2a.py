from __future__ import annotations

from typing import Any

from .base import RuntimeAdapter, RuntimeEvent, RuntimeEventType


class A2AAdapter(RuntimeAdapter):
    """Translate A2A task/message/artifact payloads into MorrowHelm events."""

    name = "a2a"

    def receive(self, payload: dict[str, Any]) -> RuntimeEvent:
        kind = str(payload.get("kind") or payload.get("type") or "message").lower()
        event_type = {
            "task": RuntimeEventType.TASK,
            "task.status": RuntimeEventType.TASK_UPDATE,
            "status": RuntimeEventType.TASK_UPDATE,
            "artifact": RuntimeEventType.ARTIFACT,
            "approval_request": RuntimeEventType.APPROVAL_REQUEST,
            "input_required": RuntimeEventType.APPROVAL_REQUEST,
        }.get(kind, RuntimeEventType.MESSAGE)
        return RuntimeEvent(
            event_type=event_type,
            source=self.name,
            payload=payload,
            event_id=str(payload.get("id") or payload.get("taskId") or ""),
            metadata={"protocol": "a2a", "version": "1.0"},
        )

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "protocol": "A2A", "version": "1.0", "capabilities": ["tasks", "messages", "artifacts", "approvals"]}
