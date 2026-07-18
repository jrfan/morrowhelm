from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "MorrowHelm"
    host: str = "127.0.0.1"
    port: int = 8787
    data_dir: Path = REPO_ROOT / ".data"
    password: str = "change-me-now"
    cookie_secure: bool = False
    session_max_age: int = 60 * 60 * 24 * 30
    agent_base_url: str | None = None
    codex_command: str = "codex"
    codex_model: str = "gpt-5.6-sol"
    codex_timeout_seconds: int = 240
    demo_mode: str = "auto"

    @classmethod
    def from_env(cls) -> "Settings":
        raw_data_dir = os.getenv("MORROWHELM_DATA_DIR", ".data")
        data_dir = Path(raw_data_dir).expanduser()
        if not data_dir.is_absolute():
            data_dir = REPO_ROOT / data_dir
        return cls(
            host=os.getenv("MORROWHELM_HOST", "127.0.0.1"),
            port=int(os.getenv("MORROWHELM_PORT", "8787")),
            data_dir=data_dir,
            password=os.getenv("MORROWHELM_PASSWORD", "change-me-now"),
            cookie_secure=_bool(os.getenv("MORROWHELM_COOKIE_SECURE")),
            agent_base_url=os.getenv("MORROWHELM_AGENT_BASE_URL") or None,
            codex_command=os.getenv("MORROWHELM_CODEX_COMMAND", "codex"),
            codex_model=os.getenv("MORROWHELM_CODEX_MODEL", "gpt-5.6-sol"),
            codex_timeout_seconds=int(os.getenv("MORROWHELM_CODEX_TIMEOUT_SECONDS", "240")),
            demo_mode=os.getenv("MORROWHELM_DEMO_MODE", "auto").strip().lower(),
        )

    def ensure_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir
