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
    assert pub == {
        "enabled": True, "url": "https://example.test", "has_token": True, "last_push_at": None, "last_error": None,
        "auto_minutes": 30, "last_auto_at": None, "last_auto_error": None,
    }
    assert "secret" not in json.dumps(pub)


def test_push_in_background_noop_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    called = []
    monkeypatch.setattr(lifedeck, "push", lambda d: called.append(d))
    lifedeck.push_in_background(DASH)
    assert called == []


def test_build_payload_sends_all_positions_without_symbols():
    dash = {**DASH, "composition_full": [
        {"name": "Vanguard Global", "symbol": "VWCE", "value": 60000.0},
        {"name": "Apple", "symbol": "AAPL", "value": 1500.0},
        {"name": "Vacía", "symbol": "X", "value": 0},
    ]}
    p = lifedeck.build_payload(dash)
    assert p["positions"] == [
        {"name": "Vanguard Global", "value": 60000.0, "pct": 60.0},
        {"name": "Apple", "value": 1500.0, "pct": 1.5},
    ]
    assert "AAPL" not in json.dumps(p["positions"])


# ── robustez de la configuración y de la subida ───────────────────────────────
def test_save_settings_keeps_token_when_read_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    monkeypatch.setattr(lifedeck, "_IO_RETRY_DELAY", 0)
    lifedeck.save_settings({"url": "https://example.test", "token": "secret", "enabled": True})

    def broken(*a, **k):
        raise PermissionError("sharing violation")

    monkeypatch.setattr(lifedeck, "_read_settings", broken)
    with pytest.raises(PermissionError):
        lifedeck.save_settings({"last_auto_at": "x"})
    monkeypatch.undo()
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    s = lifedeck.load_settings()
    assert s["token"] == "secret" and s["url"] == "https://example.test" and "last_auto_at" not in s


def test_read_settings_retries_transient_permission_error(tmp_path, monkeypatch):
    path = tmp_path / "lifedeck.json"
    path.write_text(json.dumps({"token": "t"}), encoding="utf-8")
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(path))
    monkeypatch.setattr(lifedeck, "_IO_RETRY_DELAY", 0)
    real_open = open
    fails = [2]

    def flaky(file, *a, **k):
        if str(file) == str(path) and fails[0]:
            fails[0] -= 1
            raise PermissionError("busy")
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", flaky)
    assert lifedeck.load_settings(strict=True) == {"token": "t"}


def test_load_settings_strict_raises_on_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "lifedeck.json"
    path.write_text("{no json", encoding="utf-8")
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(path))
    assert lifedeck.load_settings() == {}
    with pytest.raises(ValueError):
        lifedeck.load_settings(strict=True)
    with pytest.raises(ValueError):
        lifedeck.save_settings({"enabled": True})
    assert path.read_text(encoding="utf-8") == "{no json"  # no se ha pisado


def test_save_settings_leaves_no_temp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    for i in range(3):
        lifedeck.save_settings({"n": i})
    assert sorted(p.name for p in tmp_path.iterdir() if not p.name.endswith(".lock")) == ["lifedeck.json"]
    assert lifedeck.load_settings()["n"] == 2


def test_push_success_survives_failing_status_write(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    monkeypatch.setattr(lifedeck, "latest_price_date", lambda: None)
    sent = []
    monkeypatch.setattr(lifedeck, "_request", lambda m, op, body=None, s=None: sent.append(body) or {"ok": True})

    def fail(patch):
        raise PermissionError("busy")

    monkeypatch.setattr(lifedeck, "save_settings", fail)
    res = lifedeck.push(DASH)
    assert res["ok"] is True and len(sent) == 1


def test_push_records_payload_error(tmp_path, monkeypatch):
    monkeypatch.setattr(lifedeck, "CONFIG_FILE", str(tmp_path / "lifedeck.json"))
    with pytest.raises(lifedeck.LifeDeckError):
        lifedeck.push({"metrics": {}})
    assert lifedeck.load_settings()["last_error"]


def test_build_payload_uses_real_price_date_when_stale():
    p = lifedeck.build_payload(DASH, prices_as_of="2026-11-10")
    assert p["as_of"] == "2026-11-10" and p["prices_as_of"] == "2026-11-10"
    fresh = lifedeck.build_payload(DASH, prices_as_of="2026-11-14")
    assert fresh["as_of"] == "2026-11-14"
    assert lifedeck.build_payload(DASH)["prices_as_of"] is None


def test_latest_price_date_ignores_empty_rows(tmp_path):
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(
        "Date,AAA,BBB\n2026-11-10,1.0,\n2026-11-12 00:00:00,,2.5\n2026-11-13,,\n", encoding="utf-8")
    assert lifedeck.latest_price_date(str(csv_path)) == "2026-11-12"
    assert lifedeck.latest_price_date(str(tmp_path / "missing.csv")) is None


def test_request_marks_network_errors_transient(monkeypatch):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.URLError("getaddrinfo failed")

    monkeypatch.setattr(lifedeck.urllib.request, "urlopen", boom)
    with pytest.raises(lifedeck.LifeDeckError) as ei:
        lifedeck._request("GET", "ping", s={"url": "https://example.test", "token": "t"})
    assert ei.value.transient is True
