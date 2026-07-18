from __future__ import annotations

import hashlib
import json
from typing import Any


def action_hash(
    *,
    tool: str,
    arguments: dict[str, Any],
    requested_scopes: list[str],
    side_effects: list[str],
    expires_at: str | None,
) -> str:
    """Return a stable hash for the exact action a founder is approving."""

    payload = {
        "arguments": arguments,
        "expires_at": expires_at,
        "requested_scopes": requested_scopes,
        "side_effects": side_effects,
        "tool": tool,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def approval_manifest(
    *,
    tool: str,
    arguments: dict[str, Any],
    summary: str,
    side_effects: list[str],
    requested_scopes: list[str],
    risk: str = "medium",
    amount: float | None = None,
    currency: str | None = None,
    recipient: str | None = None,
    reversible: bool = True,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Build the framework-neutral approval contract used by adapters."""

    return {
        "tool": tool,
        "arguments": arguments,
        "summary": summary,
        "side_effects": side_effects,
        "requested_scopes": requested_scopes,
        "risk": risk,
        "amount": amount,
        "currency": currency,
        "recipient": recipient,
        "reversible": reversible,
        "expires_at": expires_at,
        "action_hash": action_hash(
            tool=tool,
            arguments=arguments,
            requested_scopes=requested_scopes,
            side_effects=side_effects,
            expires_at=expires_at,
        ),
    }
