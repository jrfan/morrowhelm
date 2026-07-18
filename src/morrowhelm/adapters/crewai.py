from __future__ import annotations

from typing import Any

from .base import RuntimeAdapter, RuntimeEvent, RuntimeEventType


class CrewAIAdapter(RuntimeAdapter):
    """Normalize callback dictionaries emitted by a CrewAI Flow or crew."""

    name = "crewai"

    def receive(self, payload: dict[str, Any]) -> RuntimeEvent:
        kind = str(payload.get("event") or payload.get("event_type") or "message").lower()
        event_type = {
            "task_started": RuntimeEventType.TASK,
            "task_completed": RuntimeEventType.TASK_UPDATE,
            "approval_requested": RuntimeEventType.APPROVAL_REQUEST,
            "artifact_created": RuntimeEventType.ARTIFACT,
        }.get(kind, RuntimeEventType.MESSAGE)
        return RuntimeEvent(
            event_type=event_type,
            source=self.name,
            payload=payload,
            event_id=str(payload.get("task_id") or payload.get("id") or ""),
            metadata={"framework": "CrewAI"},
        )
