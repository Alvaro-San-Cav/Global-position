"""
conftest.py – Pytest configuration for Global-Position tests.

Sets UTF-8 as the default I/O encoding on Windows (needed for emoji in
print() calls captured by pytest under cp1252 consoles).
"""

import sys


def pytest_configure(config):
    # Force UTF-8 stdout/stderr so emoji in production code doesn't crash
    # tests running under Windows cp1252 consoles.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


import json  # noqa: E402
import os  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Redirect every config path to tmp_path so tests never touch real data."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src import config

    inp = tmp_path / "input"
    proc = tmp_path / "processing"
    out = tmp_path / "output"
    for d in (inp, proc, out):
        d.mkdir()
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps({
        "stock_sources": [], "crypto_sources": [
            {"name": "Binance", "file_pattern": "binance*.csv", "column_map": {"Date": "UTC_Time"}}
        ],
    }), encoding="utf-8")

    monkeypatch.setattr(config, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INPUT_DIR", str(inp))
    monkeypatch.setattr(config, "PROCESSING_DIR", str(proc))
    monkeypatch.setattr(config, "OUTPUT_DIR", str(out))
    monkeypatch.setattr(config, "OPERATIONS_FILE", str(proc / "operaciones.csv"))
    monkeypatch.setattr(config, "CRYPTO_DB", str(proc / "crypto.csv"))
    monkeypatch.setattr(config, "CASH_FILE", str(proc / "cash.json"))
    monkeypatch.setattr(config, "BACKUP_DIR", str(proc / "backup"))
    monkeypatch.setattr(config, "SOURCES_FILE", str(sources))
    monkeypatch.setattr(config, "FX_CACHE_FILE", str(proc / "cache" / "fx.csv"))
    monkeypatch.setattr(config, "PRICES_CACHE_FILE", str(proc / "cache" / "prices.csv"))
    return tmp_path
