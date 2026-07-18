import json
import hmac
import hashlib

from morrowhelm.adapters import A2AAdapter, CrewAIAdapter, OpenAICompatibleAdapter, RuntimeEventType, WebhookAdapter


def test_a2a_task_and_artifact_events_are_normalized() -> None:
    adapter = A2AAdapter()
    assert adapter.receive({"kind": "task", "id": "a1"}).event_type == RuntimeEventType.TASK
    assert adapter.receive({"kind": "artifact", "id": "a2"}).event_type == RuntimeEventType.ARTIFACT


def test_crewai_approval_event_is_normalized() -> None:
    event = CrewAIAdapter().receive({"event": "approval_requested", "task_id": "t1"})
    assert event.event_type == RuntimeEventType.APPROVAL_REQUEST
    assert event.metadata["framework"] == "CrewAI"


def test_openai_tool_calls_become_approval_events() -> None:
    event = OpenAICompatibleAdapter("http://gateway", "demo").receive({"id": "x", "choices": [{"message": {"tool_calls": [{"id": "tool-1"}]}}]})
    assert event.event_type == RuntimeEventType.APPROVAL_REQUEST


def test_webhook_signature_and_payload() -> None:
    body = json.dumps({"event": "approval.requested", "data": {"id": "a1"}}, separators=(",", ":")).encode()
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    adapter = WebhookAdapter("secret")
    assert adapter.verify(body, f"sha256={signature}")
    assert adapter.receive(json.loads(body)).event_type == RuntimeEventType.APPROVAL_REQUEST
