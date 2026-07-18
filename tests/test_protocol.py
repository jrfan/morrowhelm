from morrowhelm.protocol import action_hash, approval_manifest
from morrowhelm.codex_runtime import build_agent_prompt


def test_action_hash_is_stable_for_same_action() -> None:
    kwargs = {
        "tool": "send_email",
        "arguments": {"to": "founder@example.com", "subject": "Hello"},
        "requested_scopes": ["email:send"],
        "side_effects": ["Sends one email"],
        "expires_at": "2030-01-01T00:00:00Z",
    }
    assert action_hash(**kwargs) == action_hash(**kwargs)


def test_manifest_exposes_real_impact_and_hash() -> None:
    manifest = approval_manifest(
        tool="publish",
        arguments={"channel": "newsletter"},
        summary="Publish a newsletter",
        side_effects=["Sends to opted-in contacts"],
        requested_scopes=["newsletter:send"],
        amount=10,
        currency="EUR",
    )
    assert manifest["amount"] == 10
    assert manifest["currency"] == "EUR"
    assert len(manifest["action_hash"]) == 64


def test_codex_employee_prompt_is_workspace_scoped() -> None:
    prompt = build_agent_prompt(
        {"name": "Mira Vale", "role": "Research Lead", "focus": "Customer evidence"},
        {"name": "LumenDesk Studio"},
        "Prepare a synthetic customer brief.",
        "/tmp/agent-workspace",
    )
    assert "Do not read or write any parent directory" in prompt
    assert "approval_request" in prompt
