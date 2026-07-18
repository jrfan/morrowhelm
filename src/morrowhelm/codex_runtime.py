from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .store import Store, now_iso


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    employee: dict[str, Any]
    prompt: str
    task_id: str | None = None
    sprint_id: str | None = None
    stage: str = "direct"
    depends_on: tuple[str, ...] = ()
    mode: str = "live"


def build_agent_prompt(employee: dict[str, Any], company: dict[str, Any], prompt: str, workspace: Path) -> str:
    return f"""You are {employee['name']}, the {employee['role']} at {company['name']}.

Your focus: {employee['focus']}
Your workspace is: {workspace}

You are one employee inside a small one-person company. Work only inside the
workspace above. Do not read or write any parent directory, private user data,
credentials, or network services. You may create useful local artifacts such
as Markdown briefs, JSON plans, CSV checklists, or small code samples.

Founder request:
{prompt}

Do the work in the workspace and finish with a concise JSON object (no markdown
fence) using exactly this shape:
{{
  "summary": "what you completed",
  "artifacts": [{{"path": "relative/path", "kind": "brief|plan|checklist|code|other"}}],
  "next_step": "the clearest next step",
  "approval_request": null
}}

If the next step would send something externally, spend money, delete data,
publish content, or contact a real person, do not perform it. Instead return an
approval_request object with title, summary, tool, arguments, side_effects,
requested_scopes, risk, amount, currency, recipient, and reversible fields.
Never reveal chain-of-thought; provide only the concise result and artifacts.
"""


def _parse_result(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {"summary": "The agent returned no final message.", "artifacts": [], "next_step": "Retry the task."}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"summary": text, "artifacts": []}
    except json.JSONDecodeError:
        start = text.rfind("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                if isinstance(parsed, dict):
                    parsed.setdefault("summary", text[:start].strip())
                    return parsed
            except json.JSONDecodeError:
                pass
    return {"summary": text[-4000:], "artifacts": [], "next_step": "Review the agent output."}


class CodexAgentManager:
    """Run one isolated Codex CLI workspace per virtual employee."""

    def __init__(
        self,
        *,
        store: Store,
        data_dir: Path,
        executable: str = "codex",
        model: str = "gpt-5.6-sol",
        timeout_seconds: int = 240,
        max_workers: int = 6,
    ):
        self.store = store
        self.data_dir = data_dir
        self.executable = shutil.which(executable) or executable
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="morrowhelm-codex")
        self.on_complete: Callable[[dict[str, Any], dict[str, Any]], None] | None = None

    @property
    def available(self) -> bool:
        return shutil.which(self.executable) is not None or Path(self.executable).exists()

    def dispatch(self, request: AgentRunRequest) -> dict[str, Any]:
        run_id = f"run-{uuid4().hex[:12]}"
        workspace = self.data_dir / "agents" / request.employee["id"] / run_id
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "AGENTS.md").write_text(
            "# MorrowHelm employee workspace\n\n"
            "Work only in this directory. Do not access parent directories, credentials, or external services.\n",
            encoding="utf-8",
        )
        prompt = build_agent_prompt(request.employee, self.store.profile(), request.prompt, workspace)
        run = self.store.create_agent_run(
            run_id=run_id,
            employee_id=request.employee["id"],
            task_id=request.task_id,
            prompt=request.prompt,
            workspace=str(workspace),
            model=self.model,
            sprint_id=request.sprint_id,
            stage=request.stage,
            depends_on=list(request.depends_on),
            mode=request.mode,
        )
        self.executor.submit(self._run, run, request.employee, prompt, workspace)
        return run

    def _run(self, run: dict[str, Any], employee: dict[str, Any], prompt: str, workspace: Path) -> None:
        if not self.available:
            self.store.finish_agent_run(run["id"], status="failed", output="Codex CLI is not available on PATH.", result={})
            return
        output_path = workspace / "agent-final.txt"
        command = [
            self.executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--json",
            "--color",
            "never",
            "-c",
            'approval_policy="never"',
            "-C",
            str(workspace),
            "-s",
            "workspace-write",
            "-m",
            self.model,
            "-o",
            str(output_path),
            prompt,
        ]
        self.store.start_agent_run(run["id"], pid=None)
        env = os.environ.copy()
        env.update({"MORROWHELM_AGENT_ID": employee["id"], "MORROWHELM_AGENT_RUN_ID": run["id"]})
        output_chunks: list[str] = []
        try:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.store.start_agent_run(run["id"], pid=process.pid)
            stdout, _ = process.communicate(timeout=self.timeout_seconds)
            output_chunks.append(stdout or "")
            final_text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else stdout or ""
            result = _parse_result(final_text)
            status = "succeeded" if process.returncode == 0 else "failed"
            if process.returncode != 0:
                result.setdefault("error", f"Codex exited with code {process.returncode}")
            self.store.finish_agent_run(run["id"], status=status, output=final_text[-12000:], result=result)
            if self.on_complete:
                self.on_complete({**run, "status": status, "employee_id": employee["id"]}, result)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout, _ = process.communicate()
            output_chunks.append(stdout or "")
            message = f"Codex timed out after {self.timeout_seconds} seconds."
            self.store.finish_agent_run(run["id"], status="timeout", output=message, result={"summary": message, "artifacts": []})
        except OSError as exc:
            LOGGER.exception("Codex agent failed to start")
            message = f"Could not start Codex: {exc}"
            self.store.finish_agent_run(run["id"], status="failed", output=message, result={"summary": message, "artifacts": []})
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            LOGGER.exception("Codex agent run failed")
            message = f"Agent run failed: {exc}"
            self.store.finish_agent_run(run["id"], status="failed", output=message, result={"summary": message, "artifacts": []})

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
