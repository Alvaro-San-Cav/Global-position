"""
test_api.py – Contract tests for the FastAPI server.

Network-dependent endpoints (/api/dashboard, /api/tax, /api/report/*) are NOT
exercised here to keep the suite offline and fast.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import server
from src.api_models import Operation, SourceFileInfo

import pytest

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _isolate(isolated_data):
    """Every test in this module runs against a temp data dir, never real data."""
    server._invalidate_dashboard()
    yield


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_openapi_has_dashboard_schema():
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    schemas = r.json()["components"]["schemas"]
    assert "DashboardResponse" in schemas
    assert "Metrics" in schemas


def test_operations_list_shape():
    r = client.get("/api/operations")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        Operation(**data[0])  # validates against contract


def test_operations_post_rejects_zero_quantity():
    r = client.post("/api/operations", json={
        "Date": "2025-01-01", "Product": "Test", "ISIN": "US0000000000",
        "Quantity": 0, "Price": 10.0, "Coin": "USD",
    })
    assert r.status_code >= 400


def test_operations_post_rejects_missing_fields():
    r = client.post("/api/operations", json={"Date": "2025-01-01"})
    assert r.status_code == 422  # Pydantic validation


def test_sources_get_is_dict():
    r = client.get("/api/sources")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert "stock_sources" in body


def test_pending_files_list():
    r = client.get("/api/pending-files")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_source_files_shape():
    r = client.get("/api/source-files")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        SourceFileInfo(**data[0])


def test_crypto_list_shape():
    r = client.get("/api/crypto")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_report_pdf_returns_pdf_or_404():
    r = client.get("/api/report/pdf")
    assert r.status_code in (200, 404)


def test_asset_classes_shape():
    r = client.get("/api/asset-classes")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["known_classes"], list)
    assert "Acciones" in body["known_classes"]
    assert isinstance(body["items"], list)
    if body["items"]:
        it = body["items"][0]
        assert {"symbol", "name", "auto", "effective", "kind"} <= set(it.keys())
