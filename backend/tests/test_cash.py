"""test_cash.py – Cash store: load/save cleaning and FX conversion."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import cash, config


def test_save_cleans_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CASH_FILE", str(tmp_path / "cash.json"))
    monkeypatch.setattr(config, "PROCESSING_DIR", str(tmp_path))

    cleaned = cash.save_cash({"eur": "1000.5", "usd": 200, "chf": 0, "": 5, "bad": "x"})
    # lowercase→upper, zero dropped, empty dropped, non-numeric dropped
    assert cleaned == {"EUR": 1000.5, "USD": 200.0}
    assert cash.load_cash() == {"EUR": 1000.5, "USD": 200.0}


def test_load_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CASH_FILE", str(tmp_path / "nope.json"))
    assert cash.load_cash() == {}


def test_cash_to_eur_uses_latest_fx():
    idx = pd.date_range("2024-01-01", periods=3)
    fx = pd.DataFrame({"USD": [0.9, 0.9, 0.87], "EUR": [1.0, 1.0, 1.0]}, index=idx)
    out = cash.cash_to_eur({"EUR": 1000, "USD": 1000}, fx)
    assert out["EUR"] == 1000.0
    assert out["USD"] == 870.0  # 1000 × latest 0.87


def test_cash_to_eur_unknown_currency_is_identity():
    out = cash.cash_to_eur({"XYZ": 500}, None)
    assert out["XYZ"] == 500.0
