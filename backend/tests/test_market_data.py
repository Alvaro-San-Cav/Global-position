"""
test_market_data.py - Unit tests for src/market_data.py cache behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, market_data


def _mock_close_download(index: pd.DatetimeIndex, values_by_ticker: dict[str, list[float]]) -> pd.DataFrame:
    cols = pd.MultiIndex.from_tuples([("Close", t) for t in values_by_ticker.keys()])
    out = pd.DataFrame(index=index, columns=cols, dtype=float)
    for ticker, values in values_by_ticker.items():
        out[("Close", ticker)] = values
    return out


def test_fetch_prices_backfills_new_ticker_from_start_date(tmp_path, monkeypatch):
    today = pd.Timestamp.today().normalize()
    start_date = today - pd.Timedelta(days=6)
    last_cached = today - pd.Timedelta(days=2)

    cache_index = pd.date_range(start=start_date, end=last_cached, freq="D")
    cached_prices = pd.DataFrame({"AAPL": [100.0 + i for i in range(len(cache_index))]}, index=cache_index)

    cache_file = tmp_path / "prices.csv"
    cached_prices.to_csv(cache_file)

    monkeypatch.setattr(config, "PRICES_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(config, "get_price_adjustments", lambda: {})

    calls: list[tuple[tuple[str, ...], pd.Timestamp]] = []

    def fake_download(tickers, start, end, auto_adjust, progress):
        requested = [tickers] if isinstance(tickers, str) else list(tickers)
        dl_start = pd.Timestamp(start).normalize()
        calls.append((tuple(requested), dl_start))

        idx = pd.date_range(start=dl_start, end=today, freq="D")
        values = {}
        for t in requested:
            base = 200.0 if t == "SAP.DE" else 120.0
            values[t] = [base + i for i in range(len(idx))]
        return _mock_close_download(idx, values)

    monkeypatch.setattr(market_data.yf, "download", fake_download)

    result = market_data.fetch_prices(["AAPL", "SAP.DE"], start_date)

    assert "SAP.DE" in result.columns
    assert result["SAP.DE"].notna().all()
    assert result.index.min() == start_date

    assert any(req == ("SAP.DE",) and dl_start == start_date for req, dl_start in calls)
    assert any(req == ("AAPL",) and dl_start == last_cached + pd.Timedelta(days=1) for req, dl_start in calls)


def test_price_adjustments_applied_on_full_cache_hit(tmp_path, monkeypatch):
    """Regression: price_adjustments must apply even when the cache is complete
    up to today and no download happens. Prices are cached RAW; the divisor
    (e.g. PSH.L /100 for pence) has to be applied on the cache-hit return path.
    """
    today = pd.Timestamp.today().normalize()
    start_date = today - pd.Timedelta(days=4)
    cache_index = pd.date_range(start=start_date, end=today, freq="D")
    # Raw pence prices stored in cache (e.g. 5000 pence = £50).
    cached_prices = pd.DataFrame(
        {"PSH.L": [5000.0] * len(cache_index), "AAPL": [200.0] * len(cache_index)},
        index=cache_index,
    )
    cache_file = tmp_path / "prices.csv"
    cached_prices.to_csv(cache_file)

    monkeypatch.setattr(config, "PRICES_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(config, "get_price_adjustments", lambda: {"PSH.L": 100})

    def fail_download(*args, **kwargs):
        raise AssertionError("no download expected on a full cache hit")

    monkeypatch.setattr(market_data.yf, "download", fail_download)

    result = market_data.fetch_prices(["PSH.L", "AAPL"], start_date)

    # PSH.L divided by 100 (pence -> pounds); AAPL untouched.
    assert result["PSH.L"].iloc[-1] == 50.0
    assert result["AAPL"].iloc[-1] == 200.0
