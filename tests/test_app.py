from pathlib import Path

from fastapi.testclient import TestClient

from morrowhelm.app import create_app
from morrowhelm.config import Settings


def client_for(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path, password="test-password", codex_command="__missing_codex__")
    return TestClient(create_app(settings))


def signed_client(tmp_path: Path) -> TestClient:
    client = client_for(tmp_path)
    response = client.post("/api/session", json={"password": "test-password"})
    assert response.status_code == 200
    return client


def test_health_is_public_and_bootstrap_requires_auth(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    assert client.get("/api/health").json()["mode"] == "local-first"
    assert client.get("/api/bootstrap").status_code == 401


def test_chat_creates_a_task_for_external_request(tmp_path: Path) -> None:
    client = signed_client(tmp_path)
    response = client.post("/api/chat", json={"message": "Please publish the launch note", "employee_id": "ceo"})
    assert response.status_code == 200
    assert response.json()["task"]["trigger"] == "chat"


def test_approval_is_version_checked_and_decision_updates_task(tmp_path: Path) -> None:
    client = signed_client(tmp_path)
    approval = client.get("/api/approvals").json()[0]
    response = client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "approved", "expected_version": approval["version"]},
    )
    assert response.status_code == 200
    assert response.json()["approval"]["status"] == "approved"
    assert client.get("/api/approvals").json()[0]["status"] == "approved"


def test_connection_key_is_not_returned_by_api(tmp_path: Path) -> None:
    client = signed_client(tmp_path)
    response = client.post(
        "/api/connections",
        json={"provider": "openai-compatible", "label": "Local gateway", "api_key": "sk-secret-value"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_api_key"] is True
    assert "sk-secret-value" not in response.text
    assert client.get("/api/connections").json()[0]["has_api_key"] is True


def test_connection_can_be_updated_validated_and_deleted(tmp_path: Path) -> None:
    client = signed_client(tmp_path)
    created = client.post(
        "/api/connections",
        json={"provider": "openai-compatible", "label": "Draft gateway", "api_key": "sk-local-secret"},
    ).json()

    updated = client.put(
        f"/api/connections/{created['id']}",
        json={"provider": "a2a", "label": "Local A2A", "base_url": None, "model": "agent-v1"},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "Local A2A"
    assert updated.json()["has_api_key"] is True

    validation = client.post(f"/api/connections/{created['id']}/test")
    assert validation.status_code == 200
    assert validation.json()["ok"] is False

    deleted = client.delete(f"/api/connections/{created['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/api/connections").json() == []


def test_replay_launch_builds_synthesis_artifact_and_founder_gate(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        password="test-password",
        codex_command="__missing_codex__",
        demo_mode="replay",
    )
    client = TestClient(create_app(settings))
    assert client.post("/api/session", json={"password": "test-password"}).status_code == 200

    response = client.post("/api/demo/launch", json={"prompt": "Prepare the LumenDesk pilot."})
    assert response.status_code == 200
    assert response.json()["sprint"]["mode"] == "replay"

    bootstrap = client.get("/api/bootstrap").json()
    assert bootstrap["sprint"]["status"] == "complete"
    assert bootstrap["sprint"]["specialist_count"] == 5
    assert bootstrap["sprint"]["synthesis"]["stage"] == "synthesis"
    assert len(bootstrap["artifacts"]) >= 6
    assert sum(item["status"] == "pending" for item in bootstrap["approvals"]) == 1


def test_replay_chat_returns_an_inspectable_run(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        password="test-password",
        codex_command="__missing_codex__",
        demo_mode="replay",
    )
    client = TestClient(create_app(settings))
    assert client.post("/api/session", json={"password": "test-password"}).status_code == 200

    response = client.post("/api/chat", json={"message": "Turn my notes into a small next step.", "employee_id": "product"})
    assert response.status_code == 200
    assert response.json()["mode"] == "replay"
    assert response.json()["run"]["result_json"]["artifacts"][0]["path"] == "artifacts/chat-response.md"


def test_artifact_content_and_download_stay_inside_the_run_workspace(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        password="test-password",
        codex_command="__missing_codex__",
        demo_mode="replay",
    )
    client = TestClient(create_app(settings))
    assert client.post("/api/session", json={"password": "test-password"}).status_code == 200
    client.post("/api/chat", json={"message": "Draft a focused product note.", "employee_id": "product"})

    artifact = next(item for item in client.get("/api/artifacts").json() if item["path"] == "artifacts/chat-response.md")
    content = client.get(
        f"/api/artifacts/{artifact['run_id']}/content",
        params={"path": artifact["path"]},
    )
    assert content.status_code == 200
    assert "Draft a focused product note" in content.json()["content"]

    download = client.get(
        f"/api/artifacts/{artifact['run_id']}/download",
        params={"path": artifact["path"]},
    )
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]

    traversal = client.get(
        f"/api/artifacts/{artifact['run_id']}/content",
        params={"path": "../master.key"},
    )
    assert traversal.status_code == 404
