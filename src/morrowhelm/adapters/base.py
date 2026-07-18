from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RuntimeEventType(StrEnum):
    MESSAGE = "message"
    TASK = "task"
    APPROVAL_REQUEST = "approval_request"
    TASK_UPDATE = "task_update"
    ARTIFACT = "artifact"


@dataclass(slots=True)
class RuntimeEvent:
    """Normalized event shape accepted by the MorrowHelm UI/store."""

    event_type: RuntimeEventType
    source: str
    payload: dict[str, Any]
    event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeAdapter:
    """Minimal adapter protocol implemented by CrewAI, A2A, and webhooks."""

    name = "base"

    def receive(self, payload: dict[str, Any]) -> RuntimeEvent:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "capabilities": ["messages", "tasks", "approvals"]}
