from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .protocol import approval_manifest


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "morrowhelm.db"
        self._init_schema()
        self._seed()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS company_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    name TEXT NOT NULL,
                    tagline TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS employees (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    focus TEXT NOT NULL,
                    accent TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
                    agent_provider TEXT NOT NULL DEFAULT 'codex-cli',
                    agent_model TEXT NOT NULL DEFAULT 'gpt-5.6-sol'
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(employee_id) REFERENCES employees(id)
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(owner_id) REFERENCES employees(id)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    side_effects TEXT NOT NULL,
                    requested_scopes TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    amount REAL,
                    currency TEXT,
                    recipient TEXT,
                    reversible INTEGER NOT NULL,
                    action_hash TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    feedback TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    decision_note TEXT,
                    FOREIGN KEY(task_id) REFERENCES tasks(id),
                    FOREIGN KEY(requested_by) REFERENCES employees(id)
                );
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    label TEXT NOT NULL,
                    base_url TEXT,
                    model TEXT,
                    key_hint TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activity (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    task_id TEXT,
                    sprint_id TEXT,
                    stage TEXT NOT NULL DEFAULT 'direct',
                    depends_on TEXT NOT NULL DEFAULT '[]',
                    mode TEXT NOT NULL DEFAULT 'live',
                    status TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    output TEXT,
                    result_json TEXT,
                    workspace TEXT NOT NULL,
                    model TEXT NOT NULL,
                    pid INTEGER,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY(employee_id) REFERENCES employees(id),
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS sprints (
                    id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    synthesis_run_id TEXT
                );
                """
            )
            employee_columns = {row[1] for row in db.execute("PRAGMA table_info(employees)").fetchall()}
            if "agent_provider" not in employee_columns:
                db.execute("ALTER TABLE employees ADD COLUMN agent_provider TEXT NOT NULL DEFAULT 'codex-cli'")
            if "agent_model" not in employee_columns:
                db.execute("ALTER TABLE employees ADD COLUMN agent_model TEXT NOT NULL DEFAULT 'gpt-5.6-sol'")
            run_columns = {row[1] for row in db.execute("PRAGMA table_info(agent_runs)").fetchall()}
            if "sprint_id" not in run_columns:
                db.execute("ALTER TABLE agent_runs ADD COLUMN sprint_id TEXT")
            if "stage" not in run_columns:
                db.execute("ALTER TABLE agent_runs ADD COLUMN stage TEXT NOT NULL DEFAULT 'direct'")
            if "depends_on" not in run_columns:
                db.execute("ALTER TABLE agent_runs ADD COLUMN depends_on TEXT NOT NULL DEFAULT '[]'")
            if "mode" not in run_columns:
                db.execute("ALTER TABLE agent_runs ADD COLUMN mode TEXT NOT NULL DEFAULT 'live'")

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _decode(row: sqlite3.Row, fields: tuple[str, ...]) -> dict[str, Any]:
        item = dict(row)
        for field in fields:
            try:
                item[field] = json.loads(item[field])
            except (TypeError, json.JSONDecodeError):
                item[field] = []
        return item

    def _seed(self) -> None:
        with self._connect() as db:
            if db.execute("SELECT 1 FROM company_profile WHERE id = 1").fetchone():
                return
            timestamp = now_iso()
            db.execute(
                "INSERT INTO company_profile VALUES (1, ?, ?, ?, ?)",
                ("LumenDesk Studio", "A calm launch studio for one-person companies.", "UTC", timestamp),
            )
            role_specs = [
                ("ceo", "Chief of Staff", "Keeps priorities clear and decisions moving.", "violet"),
                ("research", "Customer Research Lead", "Turns customer signals into useful evidence.", "teal"),
                ("product", "Product Builder", "Shapes ideas into useful, testable experiences.", "blue"),
                ("growth", "Growth and Launch Lead", "Turns a clear product story into a focused launch.", "orange"),
                ("finance", "Finance and Risk Lead", "Makes costs, permissions, and trade-offs visible.", "violet"),
                ("ops", "Operations and Support Lead", "Keeps delivery, handoffs, and customer loops tidy.", "teal"),
            ]
            first_names = ["Avery", "Mira", "Theo", "Nia", "Rowan", "Jules", "Sage", "Iris", "Luca", "Mara", "Noa", "Remy"]
            last_names = ["Stone", "Vale", "Park", "Hart", "Mercer", "Kim", "Sol", "Quinn", "Marlow", "Reed", "Voss", "Lane"]
            names = [f"{first} {last}" for first, last in zip(secrets.SystemRandom().sample(first_names, len(role_specs)), secrets.SystemRandom().sample(last_names, len(role_specs)))]
            employees = [
                (employee_id, name, role, focus, accent, "codex-cli", "gpt-5.6-sol")
                for (employee_id, role, focus, accent), name in zip(role_specs, names)
            ]
            db.executemany(
                "INSERT INTO employees(id,name,role,focus,accent,agent_provider,agent_model) VALUES(?,?,?,?,?,?,?)",
                employees,
            )
            task_id = "task-demo-brief"
            db.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    "Shape the LumenDesk launch experiment",
                    "Turn the latest customer notes into a small, measurable launch test for a calm planning tool for solo consultants.",
                    "in_progress",
                    "growth",
                    "chat",
                    "high",
                    timestamp,
                    timestamp,
                ),
            )
            manifest = approval_manifest(
                tool="publish_experiment",
                arguments={"channel": "newsletter", "audience": "early_access", "budget": 120},
                summary="Publish the early-access experiment brief to the newsletter audience.",
                side_effects=["Sends one newsletter to 180 opted-in contacts", "Spends up to €120 on the test"],
                requested_scopes=["newsletter:send", "billing:spend"],
                risk="medium",
                amount=120,
                currency="EUR",
                recipient="180 opted-in contacts",
                reversible=False,
            )
            db.execute(
                """INSERT INTO approvals
                (id,task_id,title,summary,side_effects,requested_scopes,risk,amount,currency,recipient,reversible,action_hash,version,status,requested_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "approval-demo-experiment",
                    task_id,
                    "Launch the early-access experiment",
                    manifest["summary"],
                    self._json(manifest["side_effects"]),
                    self._json(manifest["requested_scopes"]),
                    manifest["risk"],
                    manifest["amount"],
                    manifest["currency"],
                    manifest["recipient"],
                    int(manifest["reversible"]),
                    manifest["action_hash"],
                    1,
                    "pending",
                    "growth",
                    timestamp,
                ),
            )
            db.execute(
                "INSERT INTO conversations VALUES(?,?,?,?,?)",
                (str(uuid4()), "ceo", "assistant", "Good morning. The LumenDesk team is ready to turn one clear idea into a launch.", timestamp),
            )
            db.execute(
                "INSERT INTO activity VALUES(?,?,?,?,?)",
                (str(uuid4()), "approval", "A decision is waiting", "The growth lead prepared a €120 LumenDesk launch test.", timestamp),
            )
            db.execute("INSERT INTO app_settings VALUES('seed_version','1')")

    def profile(self) -> dict[str, Any]:
        with self._connect() as db:
            return dict(db.execute("SELECT * FROM company_profile WHERE id=1").fetchone())

    def employees(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM employees ORDER BY id='ceo' DESC, name")]

    def conversations(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT c.*, e.name, e.role, e.accent FROM conversations c JOIN employees e ON e.id=c.employee_id ORDER BY c.created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def add_message(self, employee_id: str, speaker: str, content: str) -> dict[str, Any]:
        message = {"id": str(uuid4()), "employee_id": employee_id, "speaker": speaker, "content": content, "created_at": now_iso()}
        with self._connect() as db:
            db.execute("INSERT INTO conversations VALUES(?,?,?,?,?)", tuple(message.values()))
        return message

    def tasks(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT t.*, e.name AS owner_name, e.role AS owner_role FROM tasks t JOIN employees e ON e.id=t.owner_id ORDER BY t.updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_task(self, *, title: str, description: str, owner_id: str = "ceo", trigger: str = "manual", priority: str = "medium") -> dict[str, Any]:
        task = {
            "id": f"task-{uuid4().hex[:10]}",
            "title": title,
            "description": description,
            "status": "queued",
            "owner_id": owner_id,
            "trigger": trigger,
            "priority": priority,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        with self._connect() as db:
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)", tuple(task.values()))
        return task

    def update_task_status(self, task_id: str, status: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=?", (status, now_iso(), task_id))

    def create_agent_run(
        self,
        *,
        run_id: str,
        employee_id: str,
        task_id: str | None,
        prompt: str,
        workspace: str,
        model: str,
        sprint_id: str | None = None,
        stage: str = "direct",
        depends_on: list[str] | None = None,
        mode: str = "live",
    ) -> dict[str, Any]:
        run = {
            "id": run_id,
            "employee_id": employee_id,
            "task_id": task_id,
            "sprint_id": sprint_id,
            "stage": stage,
            "depends_on": depends_on or [],
            "mode": mode,
            "status": "queued",
            "prompt": prompt,
            "output": None,
            "result_json": {},
            "workspace": workspace,
            "model": model,
            "pid": None,
            "created_at": now_iso(),
            "started_at": None,
            "completed_at": None,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO agent_runs(id,employee_id,task_id,sprint_id,stage,depends_on,mode,status,prompt,output,result_json,workspace,model,pid,created_at,started_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    employee_id,
                    task_id,
                    sprint_id,
                    stage,
                    self._json(depends_on or []),
                    mode,
                    "queued",
                    prompt,
                    None,
                    self._json({}),
                    workspace,
                    model,
                    None,
                    run["created_at"],
                    None,
                    None,
                ),
            )
        return run

    def start_agent_run(self, run_id: str, pid: int | None) -> None:
        timestamp = now_iso()
        with self._connect() as db:
            db.execute("UPDATE agent_runs SET status='running', pid=?, started_at=? WHERE id=?", (pid, timestamp, run_id))
            row = db.execute("SELECT task_id FROM agent_runs WHERE id=?", (run_id,)).fetchone()
            if row and row[0]:
                db.execute("UPDATE tasks SET status='in_progress', updated_at=? WHERE id=?", (timestamp, row[0]))

    def finish_agent_run(self, run_id: str, *, status: str, output: str, result: dict[str, Any]) -> dict[str, Any] | None:
        timestamp = now_iso()
        with self._connect() as db:
            db.execute(
                "UPDATE agent_runs SET status=?, output=?, result_json=?, completed_at=? WHERE id=?",
                (status, output, self._json(result), timestamp, run_id),
            )
            row = db.execute("SELECT ar.*, e.name AS employee_name, e.role AS employee_role FROM agent_runs ar JOIN employees e ON e.id=ar.employee_id WHERE ar.id=?", (run_id,)).fetchone()
            if not row:
                return None
            db.execute(
                "INSERT INTO activity VALUES(?,?,?,?,?)",
                (str(uuid4()), "agent", f"{row['employee_name']} {status}", (result.get("summary") or output or "Agent run finished")[:300], timestamp),
            )
            return dict(row)

    def agent_runs(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT ar.*, e.name AS employee_name, e.role AS employee_role FROM agent_runs ar JOIN employees e ON e.id=ar.employee_id ORDER BY ar.created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["result_json"] = json.loads(item["result_json"] or "{}")
            except json.JSONDecodeError:
                item["result_json"] = {}
            try:
                item["depends_on"] = json.loads(item["depends_on"] or "[]")
            except json.JSONDecodeError:
                item["depends_on"] = []
            item["prompt"] = item["prompt"][-500:]
            item["output"] = (item["output"] or "")[-1200:]
            result.append(item)
        return result

    def create_sprint(self, *, sprint_id: str, prompt: str, mode: str) -> dict[str, Any]:
        sprint = {
            "id": sprint_id,
            "prompt": prompt,
            "mode": mode,
            "status": "running",
            "created_at": now_iso(),
            "completed_at": None,
            "synthesis_run_id": None,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO sprints(id,prompt,mode,status,created_at,completed_at,synthesis_run_id) VALUES(?,?,?,?,?,?,?)",
                tuple(sprint.values()),
            )
            db.execute(
                "INSERT INTO activity VALUES(?,?,?,?,?)",
                (str(uuid4()), "sprint", "Launch sprint started", "Five specialists are working in parallel before the Chief of Staff synthesis.", sprint["created_at"]),
            )
        return sprint

    def sprint(self, sprint_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sprints WHERE id=?", (sprint_id,)).fetchone()
        return dict(row) if row else None

    def latest_sprint(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sprints ORDER BY created_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def sprint_runs(self, sprint_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT ar.*, e.name AS employee_name, e.role AS employee_role FROM agent_runs ar JOIN employees e ON e.id=ar.employee_id WHERE ar.sprint_id=? ORDER BY ar.created_at",
                (sprint_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["result_json"] = json.loads(item["result_json"] or "{}")
            except json.JSONDecodeError:
                item["result_json"] = {}
            try:
                item["depends_on"] = json.loads(item["depends_on"] or "[]")
            except json.JSONDecodeError:
                item["depends_on"] = []
            item["prompt"] = item["prompt"][-500:]
            item["output"] = (item["output"] or "")[-1200:]
            result.append(item)
        return result

    def claim_synthesis_slot(self, sprint_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE sprints SET synthesis_run_id='pending', status='synthesizing' WHERE id=? AND synthesis_run_id IS NULL",
                (sprint_id,),
            )
        return cursor.rowcount == 1

    def attach_synthesis_run(self, sprint_id: str, run_id: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE sprints SET synthesis_run_id=? WHERE id=?", (run_id, sprint_id))

    def complete_sprint(self, sprint_id: str, *, status: str = "complete") -> None:
        with self._connect() as db:
            db.execute("UPDATE sprints SET status=?, completed_at=? WHERE id=?", (status, now_iso(), sprint_id))

    def create_approval_from_manifest(self, *, task_id: str, requested_by: str, manifest: dict[str, Any]) -> dict[str, Any]:
        timestamp = now_iso()
        approval_id = f"approval-{uuid4().hex[:12]}"
        title = manifest.get("title") or manifest.get("tool") or "Agent action needs approval"
        summary = manifest.get("summary") or "An agent requested permission for an external action."
        with self._connect() as db:
            db.execute(
                """INSERT INTO approvals
                (id,task_id,title,summary,side_effects,requested_scopes,risk,amount,currency,recipient,reversible,action_hash,version,status,requested_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    approval_id,
                    task_id,
                    title,
                    summary,
                    self._json(manifest.get("side_effects", [])),
                    self._json(manifest.get("requested_scopes", [])),
                    manifest.get("risk", "medium"),
                    manifest.get("amount"),
                    manifest.get("currency"),
                    manifest.get("recipient"),
                    int(bool(manifest.get("reversible", True))),
                    manifest.get("action_hash", ""),
                    1,
                    "pending",
                    requested_by,
                    timestamp,
                ),
            )
            db.execute("UPDATE tasks SET status='waiting_approval', updated_at=? WHERE id=?", (timestamp, task_id))
        return self.approval(approval_id) or {}

    def approvals(self, limit: int = 40) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT a.*, e.name AS requester_name, e.role AS requester_role, t.title AS task_title FROM approvals a JOIN employees e ON e.id=a.requested_by JOIN tasks t ON t.id=a.task_id ORDER BY CASE a.status WHEN 'pending' THEN 0 ELSE 1 END, a.created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._decode(row, ("side_effects", "requested_scopes")) for row in rows]

    def approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT a.*, e.name AS requester_name, e.role AS requester_role, t.title AS task_title FROM approvals a JOIN employees e ON e.id=a.requested_by JOIN tasks t ON t.id=a.task_id WHERE a.id=?",
                (approval_id,),
            ).fetchone()
        return self._decode(row, ("side_effects", "requested_scopes")) if row else None

    def decide_approval(self, approval_id: str, decision: str, note: str = "") -> dict[str, Any] | None:
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        timestamp = now_iso()
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE approvals SET status=?, decided_at=?, decision_note=?, version=version+1 WHERE id=? AND status='pending'",
                (decision, timestamp, note.strip() or None, approval_id),
            )
            if cursor.rowcount == 0:
                return None
            row = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            approval = self._decode(row, ("side_effects", "requested_scopes"))
            db.execute(
                "INSERT INTO activity VALUES(?,?,?,?,?)",
                (str(uuid4()), "decision", f"Approval {decision}", approval["title"], timestamp),
            )
            db.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                ("completed" if decision == "approved" else "blocked", timestamp, approval["task_id"]),
            )
        return approval

    def activity(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM activity ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def connections(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM connections ORDER BY provider, label")]

    def connection(self, connection_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM connections WHERE id=?", (connection_id,)).fetchone()
        return dict(row) if row else None

    def save_connection(self, *, provider: str, label: str, base_url: str | None, model: str | None, key_hint: str | None) -> dict[str, Any]:
        timestamp = now_iso()
        connection_id = f"conn-{uuid4().hex[:10]}"
        with self._connect() as db:
            db.execute(
                "INSERT INTO connections VALUES(?,?,?,?,?,?,?,?,?)",
                (connection_id, provider, label, base_url, model, key_hint, 1, timestamp, timestamp),
            )
            return dict(db.execute("SELECT * FROM connections WHERE id=?", (connection_id,)).fetchone())

    def update_connection(
        self,
        connection_id: str,
        *,
        provider: str,
        label: str,
        base_url: str | None,
        model: str | None,
        key_hint: str | None,
    ) -> dict[str, Any] | None:
        timestamp = now_iso()
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE connections
                SET provider=?, label=?, base_url=?, model=?,
                    key_hint=COALESCE(?, key_hint), updated_at=?
                WHERE id=?""",
                (provider, label, base_url, model, key_hint, timestamp, connection_id),
            )
            if cursor.rowcount == 0:
                return None
            row = db.execute("SELECT * FROM connections WHERE id=?", (connection_id,)).fetchone()
        return dict(row) if row else None

    def delete_connection(self, connection_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM connections WHERE id=?", (connection_id,))
        return cursor.rowcount == 1
