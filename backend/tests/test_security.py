"""test_security.py – path traversal, input validation, atomicity, cache and parsing.

All tests use the `isolated_data` fixture (conftest) so real data is never touched.
"""

import io
import json
import os
import sys
import threading
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import server
from src import cash, config, loaders

client = TestClient(server.app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _iso(isolated_data):
    server._invalidate_dashboard()
    return isolated_data


def _csv(name="x.csv", content=b"a,b\n1,2\n"):
    return ("files", (name, io.BytesIO(content), "text/csv"))


# ── upload / delete traversal ───────────────────────────────────────────

class TestUpload:
    def test_ok(self, isolated_data):
        r = client.post("/api/upload", files=[_csv("ops.csv")])
        assert r.status_code == 200 and r.json() == {"saved": ["ops.csv"]}
        assert (isolated_data / "input" / "ops.csv").is_file()

    @pytest.mark.parametrize("name", ["../evil.csv", "..\\evil.csv", "a/../../evil.csv"])
    def test_traversal_rejected(self, isolated_data, name):
        r = client.post("/api/upload", files=[_csv(name)])
        assert r.status_code in (400, 422)
        assert not (isolated_data / "evil.csv").exists()

    def test_backslash_path_uses_basename(self, isolated_data):
        r = client.post("/api/upload", files=[_csv("C:\\x\\ops.csv".replace("C:", ""))])
        assert r.status_code == 200
        assert (isolated_data / "input" / "ops.csv").is_file()

    @pytest.mark.parametrize("name", ["notes.txt", "x.csv.exe", ".csv.", "a:b.csv"])
    def test_non_csv_or_bad_rejected(self, name):
        r = client.post("/api/upload", files=[_csv(name)])
        assert r.status_code == 400

    def test_too_big(self, monkeypatch, isolated_data):
        monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 10)
        r = client.post("/api/upload", files=[_csv("big.csv", b"x" * 100)])
        assert r.status_code == 413
        assert os.listdir(isolated_data / "input") == []   # no leftovers (tmp cleaned)

    def test_delete_pending_traversal(self, isolated_data):
        victim = isolated_data / "victim.csv"
        victim.write_text("a\n")
        (isolated_data / "input" / "ok.csv").write_text("a\n")
        for bad in ["..%5Cvictim.csv", "..\\victim.csv", "%2e%2e%5cvictim.csv"]:
            r = client.delete(f"/api/pending-files/{bad}")
            assert r.status_code in (400, 404), bad
        assert victim.exists()
        assert client.delete("/api/pending-files/ok.csv").status_code == 200
        assert client.delete("/api/pending-files/ok.csv").status_code == 404
        assert client.delete("/api/pending-files/notcsv.txt").status_code == 400


def test_spa_fallback_does_not_escape_web_dir(monkeypatch, isolated_data):
    web = isolated_data / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>idx</html>")
    secret = isolated_data / "secret.txt"
    secret.write_text("TOPSECRET")
    monkeypatch.setattr(server, "WEB_DIR", str(web))
    r = client.get("/..%5Csecret.txt")
    assert "TOPSECRET" not in r.text
    r = client.get("/%2e%2e/secret.txt")
    assert "TOPSECRET" not in r.text
    assert client.get("/api/does-not-exist").status_code == 404


# ── invalidate ──────────────────────────────────────────────────────────

def test_invalidate_is_post_only():
    assert client.post("/api/invalidate").json() == {"ok": True}
    assert client.get("/api/invalidate").status_code == 405


# ── sources ─────────────────────────────────────────────────────────────

class TestSources:
    def _body(self, pattern="sap*.csv"):
        return {"stock_sources": [{"name": "S", "file_pattern": pattern, "column_map": {"Date": "d"}}],
                "crypto_sources": []}

    def test_valid_roundtrip_atomic(self, isolated_data):
        r = client.post("/api/sources", json=self._body())
        assert r.status_code == 200
        data = json.loads(Path(config.SOURCES_FILE).read_text(encoding="utf-8"))
        assert data["stock_sources"][0]["file_pattern"] == "sap*.csv"
        assert not [f for f in os.listdir(isolated_data) if f.endswith(".tmp")]

    @pytest.mark.parametrize("pat", ["../x.csv", "a/b.csv", "a\\b.csv", ""])
    def test_bad_pattern(self, pat):
        assert client.post("/api/sources", json=self._body(pat)).status_code == 422

    def test_malformed_json(self):
        r = client.post("/api/sources", content=b"{not json", headers={"content-type": "application/json"})
        assert r.status_code in (400, 422)

    def test_missing_fields(self):
        r = client.post("/api/sources", json={"stock_sources": [{"name": "x"}]})
        assert r.status_code == 422

    def test_failed_validation_keeps_old_file(self):
        before = Path(config.SOURCES_FILE).read_text(encoding="utf-8")
        client.post("/api/sources", json=self._body("../x"))
        assert Path(config.SOURCES_FILE).read_text(encoding="utf-8") == before

    def test_target_and_sources_concurrent_writes_stay_valid(self):
        def w1():
            for _ in range(15):
                config.save_target_portfolio({"targets": {"ETF": 50}})

        def w2():
            for _ in range(15):
                client.post("/api/sources", json=self._body())

        ts = [threading.Thread(target=w1), threading.Thread(target=w2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        json.loads(Path(config.SOURCES_FILE).read_text(encoding="utf-8"))   # never corrupt


# ── crypto CRUD ─────────────────────────────────────────────────────────

def _post_crypto(date="2024-03-01 10:00", coin="BTC", qty=1.0):
    return client.post("/api/crypto", json={"Date": date, "Coin": coin, "Quantity": qty})


class TestCrypto:
    def test_validation(self):
        assert _post_crypto(qty=0).status_code == 422
        assert _post_crypto(qty=-1).status_code == 422
        assert _post_crypto(date="1980-01-01").status_code == 400
        assert _post_crypto(date="2999-01-01").status_code == 400
        assert _post_crypto(date="garbage").status_code == 400
        assert _post_crypto(coin="B" * 40).status_code == 422
        assert _post_crypto(coin="BT/C").status_code == 400
        r = client.post("/api/crypto", json={"Date": "2024-01-01", "Coin": "BTC", "Quantity": "nan"})
        assert r.status_code == 422

    def test_get_has_id_and_fingerprint(self):
        _post_crypto()
        rows = client.get("/api/crypto").json()
        assert rows[0]["id"] == 0 and len(rows[0]["fingerprint"]) == 12

    def test_put_delete_with_fingerprint(self):
        _post_crypto("2024-01-01 10:00", "BTC", 1)
        _post_crypto("2024-02-01 10:00", "ETH", 2)
        rows = client.get("/api/crypto").json()
        eth = rows[1]
        # stale fingerprint → 409, nothing changes
        r = client.delete(f"/api/crypto/{eth['id']}", params={"fingerprint": "deadbeef0000"})
        assert r.status_code == 409
        assert len(client.get("/api/crypto").json()) == 2
        # edit with the right fingerprint
        r = client.put(f"/api/crypto/{eth['id']}", params={"fingerprint": eth["fingerprint"]},
                       json={"Date": "2024-02-01 10:00", "Coin": "ETH", "Quantity": 3})
        assert r.status_code == 200
        rows = client.get("/api/crypto").json()
        assert rows[1]["Quantity"] == 3
        # positional id now points at a different row than fingerprint says → 409
        btc = rows[0]
        r = client.delete(f"/api/crypto/1", params={"fingerprint": btc["fingerprint"]})
        assert r.status_code == 409
        assert client.delete("/api/crypto/0", params={"fingerprint": btc["fingerprint"]}).status_code == 200
        assert client.delete("/api/crypto/5").status_code == 404

    def test_delete_without_fingerprint_still_works(self):
        _post_crypto()
        assert client.delete("/api/crypto/0").status_code == 200
        assert client.get("/api/crypto").json() == []

    def test_deleted_exchange_row_is_not_resurrected(self, isolated_data):
        # crypto.csv exists first (as in real use), holding the ingested exchange row
        _post_crypto("2024-01-01 10:00", "BTC", 0.5)
        (isolated_data / "input" / "binance_1.csv").write_text(
            "UTC_Time,Coin,Change,Operation\n2024-01-01 10:00:00,BTC,0.5,Buy\n", encoding="utf-8")
        sources = {"stock_sources": [], "crypto_sources": [{
            "name": "Binance", "file_pattern": "binance*.csv", "enabled": True,
            "column_map": {"Date": "UTC_Time", "Coin": "Coin", "Quantity": "Change", "Operation": "Operation"},
            "buy_operations": ["Buy"]}]}
        Path(config.SOURCES_FILE).write_text(json.dumps(sources), encoding="utf-8")
        assert client.delete("/api/crypto/0").status_code == 200
        # re-ingest from the (still present) exchange export
        loaders.process_crypto_transactions()
        assert client.get("/api/crypto").json() == []


# ── dashboard cache ─────────────────────────────────────────────────────

class TestDashboardCache:
    def test_error_results_not_cached(self, monkeypatch):
        calls = []

        def fake(force_refresh=False):
            calls.append(1)
            return {"error": "no ops"}

        monkeypatch.setattr(server, "_build_dashboard", fake)
        server._get_dashboard()
        server._get_dashboard()
        assert len(calls) == 2 and server._dashboard_cache == {}

    def test_cached_then_invalidated(self, monkeypatch):
        n = {"i": 0}

        def fake(force_refresh=False):
            n["i"] += 1
            return {"metrics": {}, "n": n["i"]}

        monkeypatch.setattr(server, "_build_dashboard", fake)
        assert server._get_dashboard()["n"] == 1
        assert server._get_dashboard()["n"] == 1
        server._invalidate_dashboard()
        assert server._get_dashboard()["n"] == 2

    def test_invalidation_during_build_prevents_stale_store(self, monkeypatch):
        def fake(force_refresh=False):
            server._invalidate_dashboard()        # data changed while building
            return {"metrics": {}, "stale": True}

        monkeypatch.setattr(server, "_build_dashboard", fake)
        assert server._get_dashboard()["stale"] is True
        assert server._dashboard_cache == {}      # NOT stored

    def test_refresh_failure_keeps_previous_cache(self, monkeypatch):
        monkeypatch.setattr(server, "_build_dashboard", lambda force_refresh=False: {"metrics": {}, "ok": 1})
        server._get_dashboard()

        def boom(force_refresh=False):
            raise RuntimeError("yfinance down")

        monkeypatch.setattr(server, "_build_dashboard", boom)
        assert server._get_dashboard(refresh=True)["ok"] == 1
        assert server._dashboard_cache["ok"] == 1


def test_errors_do_not_leak_internal_details(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError(r"C:\secret\path\file.csv exploded")

    monkeypatch.setattr(server.loaders, "load_operations", boom)
    r = client.get("/api/operations")
    assert r.status_code == 500
    assert "secret" not in r.text


def test_report_generate_failure_returns_500(monkeypatch):
    import types
    fake_main = types.SimpleNamespace(run_analysis=lambda: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setitem(sys.modules, "main", fake_main)
    r = client.post("/api/report/generate")
    assert r.status_code == 500 and r.json()["ok"] is False


# ── source-file GET/PUT ─────────────────────────────────────────────────

class TestSourceFile:
    def _setup(self, isolated_data, content="a,b\n1,2\n"):
        Path(config.SOURCES_FILE).write_text(json.dumps({
            "stock_sources": [{"name": "S", "file_pattern": "sap*.csv", "column_map": {}}],
            "crypto_sources": []}), encoding="utf-8")
        (isolated_data / "input" / "sap1.csv").write_text(content, encoding="utf-8")

    def test_empty_csv_is_400(self, isolated_data):
        self._setup(isolated_data, content="")
        assert client.get("/api/source-file/sap1.csv").status_code == 400

    def test_put_validations_and_atomic(self, isolated_data):
        self._setup(isolated_data)
        url = "/api/source-file/sap1.csv"
        assert client.put(url, json={"file": "sap1.csv", "columns": ["a", "a"], "rows": []}).status_code == 422
        assert client.put(url, json={"file": "sap1.csv", "columns": ["a", " "], "rows": []}).status_code == 422
        assert client.put(url, json={"file": "sap1.csv", "columns": ["a", "b"], "rows": [["1"]]}).status_code == 422
        r = client.put(url, json={"file": "sap1.csv", "columns": ["a", "b"], "rows": [["3", "4"]]})
        assert r.status_code == 200
        assert client.get(url).json()["rows"] == [["3", "4"]]
        assert not [f for f in os.listdir(isolated_data / "input") if f.endswith(".tmp")]

    def test_traversal_in_source_file(self, isolated_data):
        self._setup(isolated_data)
        assert client.get("/api/source-file/..%5Csap1.csv").status_code in (400, 403, 404)


# ── cash ────────────────────────────────────────────────────────────────

class TestCash:
    def test_corrupt_json_not_silently_overwritten(self, isolated_data):
        Path(config.CASH_FILE).write_text("{broken", encoding="utf-8")
        assert cash.load_cash() == {}
        baks = [f for f in os.listdir(isolated_data / "processing") if f.endswith(".bak")]
        assert len(baks) == 1
        assert (isolated_data / "processing" / baks[0]).read_text() == "{broken"

    def test_save_atomic_no_tmp_left(self, isolated_data):
        cash.save_cash({"EUR": 10})
        assert [f for f in os.listdir(isolated_data / "processing") if f.endswith(".tmp")] == []

    def test_missing_fx_reported(self):
        miss: list[str] = []
        out = cash.cash_to_eur({"EUR": 1.0, "ZZZ": 5.0}, None, missing=miss)
        assert out["ZZZ"] == 5.0 and miss == ["ZZZ"]

    def test_api_cash_warns_without_fx(self):
        r = client.post("/api/cash", json={"balances": {"USD": 100}})
        body = r.json()
        assert r.status_code == 200 and body["missing_fx"] == ["USD"] and body["warning"]


# ── clean_eu_float ──────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("1.234,56", 1234.56), ("1,234.56", 1234.56), ("1234.56", 1234.56), ("1234,56", 1234.56),
    ("€ 1.234,56", 1234.56), ("1 234,56 €", 1234.56), ("$1,234.56", 1234.56),
    ("(1.234,56)", -1234.56), ("-1.590,00", -1590.0), ("1.234.567", 1234567.0),
    ("1,234,567.89", 1234567.89), ("1.234", 1.234), ("1,5", 1.5),
    ("", 0.0), (None, 0.0), (float("nan"), 0.0), ("abc", 0.0), (12.5, 12.5),
])
def test_clean_eu_float(raw, expected):
    assert loaders.clean_eu_float(raw) == pytest.approx(expected)


def test_degiro_parser_coerces_bad_values(isolated_data):
    f = isolated_data / "input" / "deg.csv"
    f.write_text("Date,Product,ISIN,Quantity,Price,Coin,Value\n"
                 '01-02-2024,A,US1,1,"10,5",USD,"-10,5"\n'
                 "02-02-2024,B,US2,1,oops,USD,5\n", encoding="utf-8")
    df = loaders._parse_degiro_file(str(f))
    assert len(df) == 2
    assert df.loc[0, "Price"] == pytest.approx(10.5)
    assert pd.isna(df.loc[1, "Price"])
