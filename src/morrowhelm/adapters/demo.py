from __future__ import annotations

from uuid import uuid4

from .base import RuntimeAdapter, RuntimeEvent, RuntimeEventType


class DemoRuntime(RuntimeAdapter):
    """Synthetic local runtime used for demos and offline development."""

    name = "demo"

    def receive(self, payload: dict[str, object]) -> RuntimeEvent:
        return RuntimeEvent(
            event_type=RuntimeEventType.MESSAGE,
            source=self.name,
            payload=payload,
            event_id=str(uuid4()),
        )
