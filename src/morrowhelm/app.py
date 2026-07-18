from __future__ import annotations

import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as URLRequest, urlopen
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import create_session, valid_session
from .codex_runtime import AgentRunRequest, CodexAgentManager
from .config import Settings
from .protocol import approval_manifest
from .store import Store
from .vault import SecretsVault, VaultError


LOGGER = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BASE_DIR / "static"
SESSION_COOKIE = "morrowhelm_session"


class LoginPayload(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    employee_id: str = Field(default="ceo", min_length=1, max_length=80)


class TaskPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    owner_id: str = Field(default="ceo", max_length=80)
    priority: str = Field(default="medium", max_length=20)


class DecisionPayload(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str = Field(default="", max_length=2000)
    expected_version: int | None = None


class ConnectionPayload(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=160)
    api_key: str | None = Field(default=None, max_length=1000)


class AgentRunPayload(BaseModel):
    prompt: str = Field(min_length=1, max_length=6000)
    task_id: str | None = Field(default=None, max_length=100)


class DemoLaunchPayload(BaseModel):
    prompt: str = Field(
        default="Prepare a two-week launch sprint for LumenDesk, a calm planning tool for solo consultants.",
        min_length=1,
        max_length=4000,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_data_dir()
    store = Store(settings.data_dir)
    vault = SecretsVault(settings.data_dir)
    codex = CodexAgentManager(
        store=store,
        data_dir=settings.data_dir,
        executable=settings.codex_command,
        model=settings.codex_model,
        timeout_seconds=settings.codex_timeout_seconds,
    )
    app = FastAPI(title="MorrowHelm", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    def require_founder(request: Request) -> None:
        if not valid_session(request.cookies.get(SESSION_COOKIE), settings.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")

    def employee_for(employee_id: str) -> dict[str, object]:
        employee = next((item for item in store.employees() if item["id"] == employee_id), None)
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        return employee

    def artifact_index(limit: int = 18) -> list[dict[str, object]]:
        """Return safe, small previews of agent-created files for the founder UI."""

        artifacts: list[dict[str, object]] = []
        for run in store.agent_runs(limit=80):
            result = run.get("result_json") or {}
            for item in result.get("artifacts", []) if isinstance(result, dict) else []:
                if not isinstance(item, dict) or not item.get("path"):
                    continue
                relative = Path(str(item["path"]))
                workspace = Path(str(run["workspace"])).resolve()
                target = (workspace / relative).resolve()
                try:
                    target.relative_to(workspace)
                except ValueError:
                    continue
                preview = ""
                if target.is_file():
                    try:
                        preview = target.read_text(encoding="utf-8", errors="replace")[:640]
                    except OSError:
                        preview = ""
                artifacts.append(
                    {
                        "run_id": run["id"],
                        "employee_id": run["employee_id"],
                        "employee_name": run.get("employee_name"),
                        "employee_role": run.get("employee_role"),
                        "path": str(relative),
                        "kind": item.get("kind", "other"),
                        "preview": preview,
                        "status": run["status"],
                        "mode": run.get("mode", "live"),
                        "model": run["model"],
                        "created_at": run["created_at"],
                    }
                )
                if len(artifacts) >= limit:
                    return artifacts
        return artifacts

    def artifact_file(run_id: str, artifact_path: str) -> Path:
        run = next((item for item in store.agent_runs(limit=200) if item["id"] == run_id), None)
        if not run:
            raise HTTPException(status_code=404, detail="Artifact run not found")
        result = run.get("result_json") or {}
        declared = {
            str(item.get("path"))
            for item in result.get("artifacts", [])
            if isinstance(item, dict) and item.get("path")
        } if isinstance(result, dict) else set()
        if artifact_path not in declared:
            raise HTTPException(status_code=404, detail="Artifact not found")
        workspace = Path(str(run["workspace"])).resolve()
        target = (workspace / artifact_path).resolve()
        try:
            target.relative_to(workspace)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid artifact path") from exc
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Artifact file is unavailable")
        return target

    def sprint_payload() -> dict[str, object] | None:
        sprint = store.latest_sprint()
        if not sprint:
            return None
        runs = store.sprint_runs(str(sprint["id"]))
        by_stage = {str(run["stage"]): run for run in runs if run["stage"] == "synthesis"}
        specialists = [run for run in runs if run["stage"] == "work"]
        return {
            **sprint,
            "runs": runs,
            "specialist_count": len(specialists),
            "specialists_complete": sum(run["status"] in {"succeeded", "failed", "timeout"} for run in specialists),
            "synthesis": by_stage.get("synthesis"),
        }

    def handle_agent_complete(run: dict[str, object], result: dict[str, object]) -> None:
        employee_id = str(run["employee_id"])
        summary = str(result.get("summary") or "The agent finished its run.")
        artifacts = result.get("artifacts") or []
        artifact_names = ", ".join(str(item.get("path", "artifact")) for item in artifacts if isinstance(item, dict))
        message = summary + (f"\nArtifacts: {artifact_names}" if artifact_names else "")
        store.add_message(employee_id, "assistant", message[:4000])
        task_id = run.get("task_id")
        approval_request = result.get("approval_request")
        if task_id and isinstance(approval_request, dict):
            manifest = dict(approval_request)
            normalized = approval_manifest(
                tool=str(manifest.get("tool", "agent_action")),
                arguments=manifest.get("arguments", {}) if isinstance(manifest.get("arguments", {}), dict) else {},
                summary=str(manifest.get("summary", "An agent requested permission for an external action.")),
                side_effects=[str(item) for item in manifest.get("side_effects", [])],
                requested_scopes=[str(item) for item in manifest.get("requested_scopes", [])],
                risk=str(manifest.get("risk", "medium")),
                amount=manifest.get("amount"),
                currency=manifest.get("currency"),
                recipient=manifest.get("recipient"),
                reversible=bool(manifest.get("reversible", True)),
                expires_at=manifest.get("expires_at"),
            )
            normalized["title"] = manifest.get("title") or normalized["tool"]
            store.create_approval_from_manifest(task_id=str(task_id), requested_by=employee_id, manifest=normalized)
        elif task_id and run.get("status") == "succeeded":
            store.update_task_status(str(task_id), "completed")
        elif task_id:
            store.update_task_status(str(task_id), "blocked")

        sprint_id = run.get("sprint_id")
        if not sprint_id:
            return
        sprint_runs = store.sprint_runs(str(sprint_id))
        worker_runs = [item for item in sprint_runs if item.get("stage") == "work"]
        synthesis_runs = [item for item in sprint_runs if item.get("stage") == "synthesis"]
        if synthesis_runs:
            if all(item["status"] in {"succeeded", "failed", "timeout"} for item in synthesis_runs):
                store.complete_sprint(str(sprint_id), status="complete" if synthesis_runs[-1]["status"] == "succeeded" else "needs_attention")
            return
        if len(worker_runs) < 5 or not all(item["status"] in {"succeeded", "failed", "timeout"} for item in worker_runs):
            return
        if not store.claim_synthesis_slot(str(sprint_id)):
            return
        ceo = employee_for("ceo")
        dependencies = tuple(str(item["id"]) for item in worker_runs)
        summaries = "\n".join(
            f"- {item['employee_role']}: {(item.get('result_json') or {}).get('summary', 'No summary')}"
            for item in worker_runs
        )
        synthesis_prompt = (
            f"Synthesize the LumenDesk launch sprint for the founder. The specialist outputs are:\n{summaries}\n\n"
            "Create a one-page decision brief with the single clearest next move, evidence, risks, and an approval boundary. "
            "Do not publish, spend, or contact anyone."
        )
        if run.get("mode") == "replay":
            create_replay_synthesis(str(sprint_id), synthesis_prompt, dependencies)
            return
        task = store.create_task(
            title="Chief of Staff: synthesize the launch sprint",
            description=synthesis_prompt,
            owner_id="ceo",
            trigger="sprint_synthesis",
            priority="high",
        )
        synthesis_run = codex.dispatch(
            AgentRunRequest(
                employee=ceo,
                prompt=synthesis_prompt,
                task_id=task["id"],
                sprint_id=str(sprint_id),
                stage="synthesis",
                depends_on=dependencies,
                mode="live",
            )
        )
        store.attach_synthesis_run(str(sprint_id), str(synthesis_run["id"]))

    def replay_result(employee_id: str) -> dict[str, object]:
        results: dict[str, dict[str, object]] = {
            "research": {
                "summary": "Mapped three recurring pains for solo consultants: scattered follow-ups, unclear priorities, and launch anxiety.",
                "next_step": "Run five short customer interviews.",
                "artifacts": [{"path": "artifacts/customer-signal-brief.md", "kind": "brief"}],
            },
            "product": {
                "summary": "Defined a smallest useful MVP: daily focus, one decision queue, and a lightweight weekly review.",
                "next_step": "Prototype the daily focus flow.",
                "artifacts": [{"path": "artifacts/mvp-brief.md", "kind": "plan"}],
            },
            "growth": {
                "summary": "Created a calm launch angle for independent consultants and a three-message early-access sequence.",
                "next_step": "Review the audience and budget before sending.",
                "artifacts": [{"path": "artifacts/launch-positioning.md", "kind": "brief"}],
                "approval_request": {
                    "title": "Send the LumenDesk early-access sequence",
                    "summary": "Send three emails to the opted-in early-access audience.",
                    "tool": "publish_experiment",
                    "arguments": {"channel": "newsletter", "audience": "early_access", "budget": 120},
                    "side_effects": ["Sends three emails to 180 opted-in contacts", "Spends up to €120 on the test"],
                    "requested_scopes": ["newsletter:send", "billing:spend"],
                    "risk": "medium",
                    "amount": 120,
                    "currency": "EUR",
                    "recipient": "180 opted-in contacts",
                    "reversible": False,
                },
            },
            "finance": {
                "summary": "Built a €120 launch budget with a clear stop rule and a founder-controlled spend boundary.",
                "next_step": "Approve only after the audience and message are confirmed.",
                "artifacts": [{"path": "artifacts/lean-budget.md", "kind": "plan"}],
            },
            "ops": {
                "summary": "Prepared a two-week checklist for launch readiness, support, and feedback capture.",
                "next_step": "Assign the first customer feedback review.",
                "artifacts": [{"path": "artifacts/two-week-ops-checklist.md", "kind": "checklist"}],
            },
        }
        return results[employee_id]

    def create_replay_synthesis(sprint_id: str, prompt: str, dependencies: tuple[str, ...]) -> None:
        ceo = employee_for("ceo")
        task = store.create_task(
            title="Chief of Staff: synthesize the launch sprint",
            description=prompt,
            owner_id="ceo",
            trigger="sprint_synthesis",
            priority="high",
        )
        run_id = f"run-{uuid4().hex[:12]}"
        workspace = settings.data_dir / "agents" / "ceo" / run_id
        workspace.mkdir(parents=True, exist_ok=True)
        artifact_path = workspace / "artifacts" / "founder-decision-brief.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "# LumenDesk founder decision brief\n\n"
            "## Clearest next move\nRun a five-person early-access pilot with the daily focus flow.\n\n"
            "## Evidence\nResearch found scattered follow-ups and unclear priorities as the strongest repeated pains.\n\n"
            "## Guardrail\nKeep the €120 newsletter experiment behind the Founder Gate until the message and audience are approved.\n",
            encoding="utf-8",
        )
        run = store.create_agent_run(
            run_id=run_id,
            employee_id="ceo",
            task_id=task["id"],
            prompt=prompt,
            workspace=str(workspace),
            model=settings.codex_model,
            sprint_id=sprint_id,
            stage="synthesis",
            depends_on=list(dependencies),
            mode="replay",
        )
        store.attach_synthesis_run(sprint_id, run_id)
        store.start_agent_run(run_id, pid=None)
        result = {
            "summary": "Synthesized one clear pilot decision from five specialist outputs and kept external action behind founder approval.",
            "next_step": "Review the Founder Gate before any audience contact or spend.",
            "artifacts": [{"path": "artifacts/founder-decision-brief.md", "kind": "brief"}],
        }
        finished = store.finish_agent_run(run_id, status="succeeded", output=result["summary"], result=result)
        handle_agent_complete(finished or run, result)

    def launch_replay(prompt: str) -> dict[str, object]:
        sprint_id = f"sprint-{uuid4().hex[:10]}"
        sprint = store.create_sprint(sprint_id=sprint_id, prompt=prompt, mode="replay")
        worker_ids: list[str] = []
        for employee in store.employees():
            if employee["id"] == "ceo":
                continue
            employee_id = str(employee["id"])
            task = store.create_task(
                title=f"{employee['role']}: LumenDesk launch sprint",
                description=prompt,
                owner_id=employee_id,
                trigger="demo_replay",
                priority="medium",
            )
            run_id = f"run-{uuid4().hex[:12]}"
            workspace = settings.data_dir / "agents" / employee_id / run_id
            workspace.mkdir(parents=True, exist_ok=True)
            result = replay_result(employee_id)
            if employee_id == "growth" and any(item["status"] == "pending" for item in store.approvals()):
                # The seeded Founder Gate already represents this exact synthetic
                # launch action; avoid stacking duplicate approvals on every demo run.
                result = {key: value for key, value in result.items() if key != "approval_request"}
            for artifact in result["artifacts"]:
                target = workspace / str(artifact["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    f"# {employee['role']}\n\n{result['summary']}\n\nNext step: {result['next_step']}\n",
                    encoding="utf-8",
                )
            run = store.create_agent_run(
                run_id=run_id,
                employee_id=employee_id,
                task_id=task["id"],
                prompt=prompt,
                workspace=str(workspace),
                model=settings.codex_model,
                sprint_id=sprint_id,
                stage="work",
                mode="replay",
            )
            worker_ids.append(run_id)
            store.start_agent_run(run_id, pid=None)
            finished = store.finish_agent_run(run_id, status="succeeded", output=result["summary"], result=result)
            handle_agent_complete(finished or run, result)
        return {"company": store.profile(), "sprint": store.sprint(sprint_id), "runs": store.sprint_runs(sprint_id), "message": "Replay sprint completed with five synthetic Codex employee outputs."}

    def create_replay_chat(employee: dict[str, object], task: dict[str, object], prompt: str) -> dict[str, object]:
        run_id = f"run-{uuid4().hex[:12]}"
        employee_id = str(employee["id"])
        workspace = settings.data_dir / "agents" / employee_id / run_id
        workspace.mkdir(parents=True, exist_ok=True)
        result = {
            "summary": f"I turned your request into a concrete next step for {employee['role']}: {prompt[:140]}",
            "next_step": "Review the task and decide whether it should become part of the next sprint.",
            "artifacts": [{"path": "artifacts/chat-response.md", "kind": "brief"}],
        }
        target = workspace / "artifacts" / "chat-response.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {employee['role']} response\n\n{result['summary']}\n\nNext step: {result['next_step']}\n", encoding="utf-8")
        run = store.create_agent_run(
            run_id=run_id,
            employee_id=employee_id,
            task_id=task["id"],
            prompt=prompt,
            workspace=str(workspace),
            model=settings.codex_model,
            mode="replay",
        )
        store.start_agent_run(run_id, pid=None)
        finished = store.finish_agent_run(run_id, status="succeeded", output=result["summary"], result=result)
        handle_agent_complete(finished or run, result)
        response_run = finished or run
        response_run["result_json"] = result
        return response_run

    codex.on_complete = handle_agent_complete

    @app.on_event("shutdown")
    def shutdown_codex_agents() -> None:
        codex.shutdown()

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/login", include_in_schema=False)
    def login_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "login.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "product": "MorrowHelm", "mode": "local-first", "demo_mode": settings.demo_mode}

    @app.get("/api/session")
    def session(request: Request) -> dict[str, bool]:
        return {"authenticated": valid_session(request.cookies.get(SESSION_COOKIE), settings.password)}

    @app.post("/api/session")
    def login(payload: LoginPayload, response: Response) -> dict[str, bool]:
        if payload.password != settings.password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
        response.set_cookie(
            SESSION_COOKIE,
            create_session(settings.password, settings.session_max_age),
            max_age=settings.session_max_age,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
        )
        return {"authenticated": True}

    @app.delete("/api/session")
    def logout(response: Response) -> dict[str, bool]:
        response.delete_cookie(SESSION_COOKIE)
        return {"authenticated": False}

    @app.get("/api/bootstrap")
    def bootstrap(_: None = Depends(require_founder)) -> dict[str, object]:
        approvals = store.approvals()
        tasks = store.tasks()
        return {
            "company": store.profile(),
            "employees": store.employees(),
            "conversation": store.conversations(),
            "tasks": tasks,
            "approvals": approvals,
            "activity": store.activity(),
            "agent_runs": store.agent_runs(),
            "artifacts": artifact_index(),
            "sprint": sprint_payload(),
            "runtime": {
                "codex_available": codex.available,
                "codex_model": codex.model,
                "demo_mode": settings.demo_mode,
                "effective_demo_mode": "replay" if settings.demo_mode == "replay" or (settings.demo_mode == "auto" and not codex.available) else "live",
            },
            "connections": [
                {**connection, "has_api_key": vault.has(connection["id"]), "key_hint": connection.get("key_hint")}
                for connection in store.connections()
            ],
            "metrics": {
                "active_tasks": sum(task["status"] in {"queued", "in_progress"} for task in tasks),
                "pending_approvals": sum(approval["status"] == "pending" for approval in approvals),
                "team_online": sum(employee["status"] == "available" for employee in store.employees()),
            },
        }

    @app.post("/api/chat")
    def chat(payload: ChatPayload, _: None = Depends(require_founder)) -> dict[str, object]:
        employee = employee_for(payload.employee_id if payload.employee_id else "ceo")
        employee_id = str(employee["id"])
        store.add_message(employee_id, "founder", payload.message.strip())
        created_task = store.create_task(
            title=f"{employee['role']}: {payload.message.strip()[:80]}",
            description=payload.message.strip(),
            owner_id=employee_id,
            trigger="chat",
            priority="high",
        )
        if not codex.available and settings.demo_mode == "live":
            reply = "Codex CLI is not available. I saved this as a task so you can connect a local Codex runtime."
            store.add_message(employee_id, "assistant", reply)
            return {"reply": reply, "task": created_task, "run": None}
        if settings.demo_mode == "replay" or (settings.demo_mode == "auto" and not codex.available):
            run = create_replay_chat(employee, created_task, payload.message.strip())
            reply = str((run.get("result_json") or {}).get("summary") or f"{employee['name']} completed the task in replay mode.")
            return {"reply": reply, "task": created_task, "run": run, "mode": "replay"}
        run = codex.dispatch(AgentRunRequest(employee=employee, prompt=payload.message.strip(), task_id=created_task["id"], mode="live"))
        reply = f"{employee['name']} is working on it in an isolated Codex workspace. I’ll bring back the result here."
        store.add_message(employee_id, "assistant", reply)
        return {"reply": reply, "task": created_task, "run": run}

    @app.get("/api/agents")
    def agents(_: None = Depends(require_founder)) -> list[dict[str, object]]:
        return store.agent_runs()

    @app.get("/api/artifacts")
    def artifacts(limit: int = 100, _: None = Depends(require_founder)) -> list[dict[str, object]]:
        return artifact_index(limit=max(1, min(limit, 100)))

    @app.get("/api/artifacts/{run_id}/content")
    def artifact_content(run_id: str, path: str, _: None = Depends(require_founder)) -> dict[str, str]:
        target = artifact_file(run_id, path)
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Artifact could not be read") from exc
        return {"path": path, "content": content[:100_000]}

    @app.get("/api/artifacts/{run_id}/download")
    def artifact_download(run_id: str, path: str, _: None = Depends(require_founder)) -> FileResponse:
        target = artifact_file(run_id, path)
        return FileResponse(target, filename=target.name, media_type="text/plain; charset=utf-8")

    @app.get("/api/sprints/latest")
    def latest_sprint(_: None = Depends(require_founder)) -> dict[str, object] | None:
        return sprint_payload()

    @app.post("/api/agents/{employee_id}/run")
    def run_agent(employee_id: str, payload: AgentRunPayload, _: None = Depends(require_founder)) -> dict[str, object]:
        employee = employee_for(employee_id)
        if not codex.available:
            raise HTTPException(status_code=503, detail="Codex CLI is not available on PATH")
        run = codex.dispatch(AgentRunRequest(employee=employee, prompt=payload.prompt, task_id=payload.task_id))
        return {"run": run}

    @app.post("/api/demo/launch")
    def launch_demo(payload: DemoLaunchPayload, _: None = Depends(require_founder)) -> dict[str, object]:
        if settings.demo_mode == "replay" or (settings.demo_mode == "auto" and not codex.available):
            return launch_replay(payload.prompt)
        team = store.employees()
        sprint_id = f"sprint-{uuid4().hex[:10]}"
        sprint = store.create_sprint(sprint_id=sprint_id, prompt=payload.prompt, mode="live")
        prompts = {
            "research": f"{payload.prompt} Create a synthetic customer research brief: target user, pain, alternatives, and three interview questions.",
            "product": f"{payload.prompt} Create a small product brief with the smallest useful MVP, key user flow, and acceptance criteria.",
            "growth": f"{payload.prompt} Create launch positioning, a landing-page outline, and three short pieces of launch copy. Do not publish anything.",
            "finance": f"{payload.prompt} Create a lean launch budget and identify one spend or external action that should wait for founder approval.",
            "ops": f"{payload.prompt} Create a two-week operating checklist covering launch readiness, support, and feedback capture.",
        }
        runs = []
        for employee in team:
            if employee["id"] == "ceo":
                continue
            task = store.create_task(
                title=f"{employee['role']}: LumenDesk launch sprint",
                description=prompts.get(str(employee["id"]), payload.prompt),
                owner_id=str(employee["id"]),
                trigger="demo_launch",
                priority="high" if employee["id"] in {"ceo", "finance"} else "medium",
            )
            runs.append(codex.dispatch(AgentRunRequest(employee=employee, prompt=prompts.get(str(employee["id"]), payload.prompt), task_id=task["id"], sprint_id=sprint_id, stage="work", mode="live")))
        return {"company": store.profile(), "sprint": sprint, "runs": runs, "message": f"Dispatched {len(runs)} Codex employees in parallel. The Chief of Staff will synthesize their outputs next."}

    @app.get("/api/tasks")
    def tasks(_: None = Depends(require_founder)) -> list[dict[str, object]]:
        return store.tasks()

    @app.post("/api/tasks")
    def create_task(payload: TaskPayload, _: None = Depends(require_founder)) -> dict[str, object]:
        return store.create_task(
            title=payload.title,
            description=payload.description,
            owner_id=payload.owner_id,
            priority=payload.priority,
        )

    @app.get("/api/approvals")
    def approvals(_: None = Depends(require_founder)) -> list[dict[str, object]]:
        return store.approvals()

    @app.get("/api/approvals/{approval_id}")
    def approval(approval_id: str, _: None = Depends(require_founder)) -> dict[str, object]:
        item = store.approval(approval_id)
        if not item:
            raise HTTPException(status_code=404, detail="Approval not found")
        return item

    @app.post("/api/approvals/{approval_id}/decision")
    def decide(approval_id: str, payload: DecisionPayload, _: None = Depends(require_founder)) -> dict[str, object]:
        current = store.approval(approval_id)
        if not current:
            raise HTTPException(status_code=404, detail="Approval not found")
        if payload.expected_version is not None and payload.expected_version != current["version"]:
            raise HTTPException(status_code=409, detail="Approval changed; refresh before deciding")
        decided = store.decide_approval(approval_id, payload.decision, payload.note)
        if not decided:
            raise HTTPException(status_code=409, detail="Approval is no longer pending")
        return {"approval": decided, "receipt": {"status": "queued", "action_hash": decided["action_hash"]}}

    @app.get("/api/activity")
    def activity(_: None = Depends(require_founder)) -> list[dict[str, object]]:
        return store.activity()

    @app.get("/api/connections")
    def connections(_: None = Depends(require_founder)) -> list[dict[str, object]]:
        return [
            {**connection, "has_api_key": vault.has(connection["id"])}
            for connection in store.connections()
        ]

    @app.post("/api/connections")
    def save_connection(payload: ConnectionPayload, _: None = Depends(require_founder)) -> dict[str, object]:
        connection = store.save_connection(
            provider=payload.provider,
            label=payload.label,
            base_url=payload.base_url,
            model=payload.model,
            key_hint=(f"…{payload.api_key[-4:]}" if payload.api_key else None),
        )
        if payload.api_key:
            try:
                vault.set(connection["id"], payload.api_key)
            except VaultError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {**connection, "has_api_key": bool(payload.api_key)}

    @app.put("/api/connections/{connection_id}")
    def update_connection(connection_id: str, payload: ConnectionPayload, _: None = Depends(require_founder)) -> dict[str, object]:
        current = store.connection(connection_id)
        if not current:
            raise HTTPException(status_code=404, detail="Connection not found")
        connection = store.update_connection(
            connection_id,
            provider=payload.provider,
            label=payload.label,
            base_url=payload.base_url,
            model=payload.model,
            key_hint=(f"…{payload.api_key[-4:]}" if payload.api_key else None),
        )
        if payload.api_key:
            try:
                vault.set(connection_id, payload.api_key)
            except VaultError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {**(connection or current), "has_api_key": vault.has(connection_id)}

    @app.post("/api/connections/{connection_id}/test")
    def test_connection(connection_id: str, _: None = Depends(require_founder)) -> dict[str, object]:
        connection = store.connection(connection_id)
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")
        base_url = str(connection.get("base_url") or "").strip().rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return {"ok": False, "message": "Add a valid HTTP or HTTPS base URL before testing."}
        target = f"{base_url}/models" if connection["provider"] == "openai-compatible" else base_url
        headers = {"Accept": "application/json", "User-Agent": "MorrowHelm/0.1"}
        api_key = vault.get(connection_id)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = URLRequest(target, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=4) as response:
                status_code = int(response.status)
            return {"ok": status_code < 400, "status_code": status_code, "message": f"Endpoint responded with HTTP {status_code}."}
        except HTTPError as exc:
            message = "Authentication was rejected." if exc.code in {401, 403} else f"Endpoint responded with HTTP {exc.code}."
            return {"ok": False, "status_code": exc.code, "message": message}
        except (URLError, TimeoutError, OSError):
            return {"ok": False, "message": "MorrowHelm could not reach this endpoint within four seconds."}

    @app.delete("/api/connections/{connection_id}")
    def delete_connection(connection_id: str, _: None = Depends(require_founder)) -> dict[str, bool]:
        if not store.connection(connection_id):
            raise HTTPException(status_code=404, detail="Connection not found")
        try:
            vault.delete(connection_id)
        except VaultError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        store.delete_connection(connection_id)
        return {"deleted": True}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run("morrowhelm.app:app", host=settings.host, port=settings.port, reload=False)
