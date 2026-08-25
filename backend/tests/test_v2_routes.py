import pytest
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_config_still_reports_v1_keys():
    """/config moved to its own router; its response shape must not change."""
    body = client.get("/config").json()
    for key in ("llm_available", "llm_provider", "llm_model", "pdf_available"):
        assert key in body


def test_sources_lists_registered_sources_with_ui_fields():
    body = client.get("/sources").json()
    assert isinstance(body["sources"], list)
    for s in body["sources"]:
        assert {"key", "label", "kind", "regions", "requires_login", "enabled",
                "warning"} <= set(s)


def test_put_unknown_source_is_404():
    """Toggling a source that isn't registered must not silently write config."""
    r = client.put("/sources/does-not-exist", json={"enabled": False})
    assert r.status_code == 404
    assert "unknown source" in r.json()["detail"]


def test_connections_returns_a_list():
    assert isinstance(client.get("/connections").json()["connections"], list)


def test_connection_actions_are_not_implemented_yet():
    """501, not fake success — a stub that lies can ship unnoticed."""
    r = client.post("/connections/naukri/login")
    assert r.status_code == 501
    assert "Track C" in r.json()["detail"]


def test_schedule_read_works_and_write_is_not_implemented():
    body = client.get("/schedule").json()
    assert {"enabled", "interval_minutes", "quiet_hours"} <= set(body)
    assert client.put("/schedule", json={"interval_minutes": 60}).status_code == 501


def test_runs_returns_a_list():
    assert isinstance(client.get("/runs").json()["runs"], list)


def test_queue_read_works_and_actions_are_not_implemented():
    assert isinstance(client.get("/queue").json()["queue"], list)
    assert client.post("/queue/abc/prepare").status_code == 501


def test_v1_routes_are_all_still_mounted():
    # NOTE: walking `app.routes` directly and reading `.path` (as the task-6
    # brief's verbatim test does) breaks under fastapi==0.141.1: routes added
    # via `include_router` are now wrapped in a private `_IncludedRouter` node
    # with no `.path` attribute, rather than being flattened into `app.routes`
    # as older fastapi versions did. `app.openapi()["paths"]` is the public,
    # documented way to enumerate every mounted path regardless of how deeply
    # it's nested behind included routers, so it stays correct across fastapi
    # versions. See task-6-report.md for the investigation.
    paths = set(app.openapi()["paths"].keys())
    for p in ("/health", "/profile", "/jobs", "/scan", "/evaluate", "/config",
              "/tailor/{job_id}", "/apply/{job_id}"):
        assert p in paths
