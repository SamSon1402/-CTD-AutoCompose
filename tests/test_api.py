"""
Smoke tests exercising the full CTD drafting flow against the mock LLM.

Run: `pytest -v`
"""
import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.store import store


@pytest_asyncio.fixture
async def client():
    # Reset in-memory store between tests
    store.submissions.clear()
    store.sources.clear()
    store.sections.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_full_drafting_flow(client: AsyncClient):
    # 1. Create submission
    r = await client.post("/api/v1/submissions", json={
        "submission_id": "NDA-2026-08471",
        "compound": "BVL-2188",
        "indication": "Moderate-to-severe atopic dermatitis",
        "authority": "fda",
    })
    assert r.status_code == 201, r.text
    sub = r.json()
    sub_id = sub["id"]
    assert sub["sections_total"] > 0
    assert sub["status"] == "draft"

    # 2. Ingest a CSR source
    r = await client.post(f"/api/v1/submissions/{sub_id}/sources", json={
        "title": "CSR-2026-BVL-2188-P3",
        "doc_type": "csr",
        "content": "Phase III pivotal CSR full text..." * 100,
        "version": "1.0",
    })
    assert r.status_code == 201, r.text

    # 3. Trigger draft of M2.5 (Clinical Overview)
    r = await client.post(
        f"/api/v1/submissions/{sub_id}/sections/M2.5/draft",
        json={},
    )
    assert r.status_code == 202

    # 4. Wait for background task (mock LLM is instant; small sleep covers task scheduling)
    await asyncio.sleep(0.3)

    # 5. Fetch the drafted section
    r = await client.get(f"/api/v1/submissions/{sub_id}/sections/M2.5")
    assert r.status_code == 200
    sec = r.json()
    assert sec["status"] == "drafted"
    assert sec["content"]
    assert len(sec["citations"]) >= 1
    # Verify citations actually point to ingested source IDs
    for cite in sec["citations"]:
        assert cite["chunk_id"].startswith(("CSR", "PROTOCOL", "SAP", "CMC", "NONCLINICAL"))


@pytest.mark.asyncio
async def test_compliance_flags_missing_sources(client: AsyncClient):
    r = await client.post("/api/v1/submissions", json={
        "submission_id": "NDA-EMPTY",
        "compound": "EMPTY-001",
        "indication": "Test indication",
    })
    sub_id = r.json()["id"]
    r = await client.get(f"/api/v1/submissions/{sub_id}/compliance")
    assert r.status_code == 200
    report = r.json()
    rule_ids = {i["rule_id"] for i in report["issues"]}
    assert "CTD-AUTOCOMPOSE-NO-SOURCES" in rule_ids
    assert "ICH-M4Q-NO-CMC-SOURCE" in rule_ids


@pytest.mark.asyncio
async def test_unknown_submission_returns_404(client: AsyncClient):
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    r = await client.get(f"/api/v1/submissions/{fake_uuid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_unknown_section_id_rejected(client: AsyncClient):
    r = await client.post("/api/v1/submissions", json={
        "submission_id": "NDA-001",
        "compound": "X", "indication": "Y",
    })
    sub_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/submissions/{sub_id}/sections/M99.99/draft",
        json={},
    )
    assert r.status_code == 400
