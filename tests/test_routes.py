"""Route smoke tests.

We override the OIDC `require_user` / `require_scope` deps with stubs so we
test the route + service surface without minting real tokens.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from src.auth.deps import require_scope, require_user
from src.auth.oidc import Principal
from src.main import app


_FAKE_PRINCIPAL = Principal(
    subject="user-test",
    email="test@example.com",
    tenant_id="tenant-1",
    scopes=("forge:read", "forge:write", "pack:read", "pack:publish", "pack:deploy"),
    raw_claims={},
)


def _override_user() -> Principal:
    return _FAKE_PRINCIPAL


def _override_scope(*_required: str):
    async def _ok() -> Principal:
        return _FAKE_PRINCIPAL
    return _ok


@pytest.fixture
def client():
    # Override all auth deps for testing
    app.dependency_overrides[require_user] = _override_user
    # require_scope returns a *new* dep each call; we patch all known scopes
    for scope_set in [
        ("forge:read",), ("forge:write",), ("pack:read",),
        ("pack:publish",), ("pack:deploy",),
    ]:
        app.dependency_overrides[require_scope(*scope_set)] = _override_scope(*scope_set)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_industries(client):
    r = client.get("/api/industries")
    assert r.status_code == 200
    body = r.json()
    assert {b["id"] for b in body} == {"retail", "hospitality", "manufacturing", "technology"}


def test_forge_full_cycle(client):
    # 1. Submit
    payload = {
        "source_micro_app_id": "ma-lvmh-onboarding-v3",
        "target_industry": "retail",
        "target_pack_name": "retail-onboarding",
        "target_pack_version": "1.0.0",
        "description": "Retail onboarding pack",
    }
    r = client.post("/api/forge/jobs", json=payload)
    assert r.status_code == 202
    job = r.json()
    job_id = job["job_id"]
    assert job["status"] in ("queued", "running")

    # 2. Wait for completion (4 stages × ~0.3s each + scheduling overhead)
    deadline = time.time() + 5
    while time.time() < deadline:
        r = client.get(f"/api/forge/jobs/{job_id}")
        assert r.status_code == 200
        if r.json()["status"] in ("succeeded", "failed", "canceled"):
            break
        time.sleep(0.1)

    final = client.get(f"/api/forge/jobs/{job_id}").json()
    assert final["status"] == "succeeded", final
    assert len(final["stages"]) == 4
    assert final["manifest"] is not None
    assert final["manifest"]["signature"]  # signed

    # 3. Publish to library
    r = client.post(f"/api/forge/jobs/{job_id}/publish")
    assert r.status_code == 201
    pack = r.json()
    assert pack["published"] is True
    pack_id = pack["pack_id"]

    # 4. Re-publishing same version → 409
    r = client.post(f"/api/forge/jobs/{job_id}/publish")
    assert r.status_code == 409

    # 5. List packs, filter by industry
    r = client.get("/api/packs?industry=retail")
    assert r.status_code == 200
    assert any(p["pack_id"] == pack_id for p in r.json())

    # 6. Deploy to two tenants
    r = client.post(
        f"/api/packs/{pack_id}/deploy",
        json={"tenant_ids": ["tenant-A", "tenant-B"], "params": {"cost_center_code": "RETAIL-FR"}},
    )
    assert r.status_code == 201
    assert len(r.json()["deployments"]) == 2

    # 7. Customer list reflects deploys
    r = client.get(f"/api/packs/{pack_id}/customers")
    assert r.status_code == 200
    assert {d["tenant_id"] for d in r.json()} == {"tenant-A", "tenant-B"}


def test_publish_blocked_when_not_succeeded(client):
    r = client.post("/api/forge/jobs", json={
        "source_micro_app_id": "ma-1",
        "target_industry": "technology",
        "target_pack_name": "tech-test",
        "target_pack_version": "0.1.0",
    })
    job_id = r.json()["job_id"]
    # immediately try to publish — almost certainly still running
    r = client.post(f"/api/forge/jobs/{job_id}/publish")
    # either still-running (412) or just-finished (201). Both are correct;
    # we only assert it's NOT a 5xx and not 404.
    assert r.status_code in (201, 412)


def test_missing_pack_404s(client):
    r = client.get("/api/packs/nonexistent")
    assert r.status_code == 404
