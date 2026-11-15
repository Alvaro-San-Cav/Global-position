"""Resumen de patrimonio para LifeDeck: forma del payload y configuración sin exponer el token."""
import json

import pytest

from src import lifedeck


DASH = {
    "metrics": {
        "fecha_actual": "2026-11-14",
        "capital_total": 80000.0,
        "plusvalia_total": 20000.123,
        "rentabilidad_total": 25.0,
        "twr_total_anual": 9.87,
    },
    "portfolio_total_value": 100000.0,
    "cash_total": 20000.0,
    "net_worth": 120000.0,
    "crypto_total_value": 3456.789,
    "top_assets": [{"name": "Vanguard Global", "symbol": "VWCE", "value": 60000.0}],
    "class_breakdown": [{"name": "Renta variable", "value": 90000.0, "pct": 90.0, "members": []}],
    "portfolio_chart": {
        "value": [{"x": f"2026-01-{d:02d}", "y": 1000.0 + d} for d in range(1, 31)],
        "invested": [{"x": f"2026-01-{d:02d}", "y": 900.0} for d in range(1, 31)],
    },
}


def test_build_payload_maps_dashboard():
    p = lifedeck.build_payload(DASH)
    assert p["as_of"] == "2026-11-14"
    assert p["net_worth"] == 120000.0
    assert p["gain"] == 20000.12
    assert p["crypto_value"] == 3456.79
    assert p["top"] == [{"name": "Vanguard Global", "value": 60000.0, "pct": 60.0}]
    assert p["classes"][0]["pct"] == 90.0
    assert p["series"][0] == {"d": "2026-01-01", "v": 1001.0, "i": 900.0}
    assert len(p["series"]) == 30
    # nunca operaciones ni símbolos sueltos
    assert "operations" not in json.dumps(p)


def test_series_downsampled_keeps_last_point():
    pts = [{"d": f"p{i}", "v": float(i), "i": None} for i in range(1000)]
    out = lifedeck._downsample(pts, 180)
    assert len(out) == 180
    assert out[-1]["d"] == "p999"


def test_build_payload_requires_net_worth():
    with pytest.raises(lifedeck.LifeDeckError):
        lifedeck.build_payload({"metrics": {}})


def test_settings_never_expose_token(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    lifedeck.save_settings({"url": "https://example.test", "token": "secret", "enabled": True})
    pub = lifedeck.public_settings()
    assert pub == {"enabled": True, "url": "https://example.test", "has_token": True, "last_push_at": None, "last_error": None}
    assert "secret" not in json.dumps(pub)


def test_push_in_background_noop_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    called = []
    monkeypatch.setattr(lifedeck, "push", lambda d: called.append(d))
    lifedeck.push_in_background(DASH)
    assert called == []
