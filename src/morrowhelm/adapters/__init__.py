"""Runtime adapter contracts and reference adapters for MorrowHelm."""

from .a2a import A2AAdapter
from .base import RuntimeEvent, RuntimeEventType
from .crewai import CrewAIAdapter
from .demo import DemoRuntime
from .openai_compatible import OpenAICompatibleAdapter
from .webhook import WebhookAdapter

__all__ = [
    "A2AAdapter",
    "CrewAIAdapter",
    "DemoRuntime",
    "OpenAICompatibleAdapter",
    "RuntimeEvent",
    "RuntimeEventType",
    "WebhookAdapter",
]
