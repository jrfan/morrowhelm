from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .base import RuntimeAdapter, RuntimeEvent, RuntimeEventType


class WebhookAdapter(RuntimeAdapter):
    """Receive a small signed JSON envelope from any agent runtime."""

    name = "webhook"

    def __init__(self, secret: str):
        self.secret = secret.encode()

    def verify(self, body: bytes, signature: str) -> bool:
        expected = hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature.removeprefix("sha256="))

    def receive(self, payload: dict[str, Any]) -> RuntimeEvent:
        kind = str(payload.get("event") or payload.get("type") or "message")
        event_type = {
            "approval.requested": RuntimeEventType.APPROVAL_REQUEST,
            "task.created": RuntimeEventType.TASK,
            "task.updated": RuntimeEventType.TASK_UPDATE,
            "artifact.created": RuntimeEventType.ARTIFACT,
        }.get(kind, RuntimeEventType.MESSAGE)
        return RuntimeEvent(
            event_type=event_type,
            source=self.name,
            payload=payload.get("data", payload),
            event_id=str(payload.get("id") or ""),
            metadata={"signed": True},
        )
