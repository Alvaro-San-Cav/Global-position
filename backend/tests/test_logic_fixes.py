"""
test_logic_fixes.py - Regression tests for the audit fixes (A1, M2-M9, B1-B9).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, market_data
from src.core import (
    calculate_crypto_portfolio,
    classify_asset,
    compute_twr,
    summarize_failed_assets,
)
from src.target import compute_rebalance
from src.tax import calculate_fifo_gains


# ═══════════════════════════════════════════════════════════════════════
#  B1  TWR guard
# ═══════════════════════════════════════════════════════════════════════

class TestTwrGuards:
    def test_contribution_into_unvalued_portfolio_is_not_minus_100(self):
        idx = pd.date_range("2024-01-01", periods=4)
        vals = pd.Series([0.0, 0.0, 1000.0, 1100.0], index=idx)
        contrib = pd.Series([0.0, 0.0, 1000.0, 1000.0], index=idx)
        total, _ = compute_twr(vals, contrib, flow_at="auto")
        assert np.isfinite(total)
        assert total > -0.5

    def test_nan_values_do_not_poison_chain(self):
        idx = pd.date_range("2024-01-01", periods=5)
        vals = pd.Series([np.nan, np.nan, 1000.0, 1100.0, 1210.0], index=idx)
        contrib = pd.Series([0.0, 0.0, 1000.0, 1000.0, 1000.0], index=idx)
        total, annual = compute_twr(vals, contrib, flow_at="auto")
        assert np.isfinite(total) and np.isfinite(annual)
        assert total == pytest.approx(0.21, abs=1e-6)


# ═══════════════════════════════════════════════════════════════════════
#  M8  classify_asset
# ═══════════════════════════════════════════════════════════════════════

class TestClassify:
    def test_goldman_is_not_gold(self):
        assert classify_asset("GS", "GOLDMAN SACHS GROUP") == "Acciones"

    def test_boiler_is_not_oil(self):
        assert classify_asset("BLR", "BOILER SYSTEMS INC") == "Acciones"

    def test_oil_word_still_matches(self):
        assert classify_asset("XYZ", "WTI CRUDE OIL ETC") == "Oro / Materias primas"

    def test_etc_inside_word_is_not_etf(self):
        assert classify_asset("ETCH", "ETCHING TECHNOLOGIES") == "Acciones"

    def test_more_crypto_symbols(self):
        for sym in ("LTC", "DOT", "LINK", "AVAX", "MATIC", "SOL", "ADA", "XRP", "DOGE"):
            assert classify_asset(sym, sym) == "Cripto"

    def test_commodities_stem(self):
        assert classify_asset("X", "BROAD COMMODITIES INDEX") == "Oro / Materias primas"


# ═══════════════════════════════════════════════════════════════════════
#  M6 / M7  FIFO
# ═══════════════════════════════════════════════════════════════════════

def _ops(rows):
    return pd.DataFrame(rows, columns=["Date", "ticker", "Quantity", "Price", "Coin"])


class TestFifo:
    def test_same_day_buy_before_sell_regardless_of_file_order(self):
        # Sell listed BEFORE the buy of the same day: must still match the buy.
        df = _ops([
            ("2024-01-01", "AAA", 10, 10.0, "EUR"),
            ("2024-02-01", "AAA", -5, 20.0, "EUR"),
            ("2024-02-01", "AAA", 5, 15.0, "EUR"),
        ])
        g = calculate_fifo_gains(df)
        assert len(g) == 1
        row = g.iloc[0]
        assert not row["sin_historial"]
        # Sale consumes the OLDEST lot (10 @ 10): gain = 5*20 - 5*10 = 50
        assert row["plusvalia_eur"] == pytest.approx(50.0)

    def test_same_day_buy_then_sell_without_history_is_matched(self):
        df = _ops([
            ("2024-03-01", "BBB", -4, 12.0, "EUR"),
            ("2024-03-01", "BBB", 4, 10.0, "EUR"),
        ])
        g = calculate_fifo_gains(df)
        assert len(g) == 1
        assert not g.iloc[0]["sin_historial"]
        assert g.iloc[0]["plusvalia_eur"] == pytest.approx(8.0)

    def test_sale_without_enough_lots_flagged(self):
        df = _ops([
            ("2024-01-01", "CCC", 2, 10.0, "EUR"),
            ("2024-02-01", "CCC", -5, 20.0, "EUR"),
        ])
        g = calculate_fifo_gains(df)
        assert bool(g.iloc[0]["sin_historial"]) is True
        assert g.iloc[0]["coste_base_eur"] == pytest.approx(20.0)

    def test_complete_history_not_flagged(self):
        df = _ops([
            ("2024-01-01", "CCC", 5, 10.0, "EUR"),
            ("2024-02-01", "CCC", -5, 20.0, "EUR"),
        ])
        g = calculate_fifo_gains(df)
        assert bool(g.iloc[0]["sin_historial"]) is False
        assert bool(g.iloc[0]["sin_fx"]) is False

    def test_split_pair_generates_no_spurious_gain(self):
        # 2:1 split recorded as sell 10 @ 100 / buy 20 @ 50 the same day.
        df = _ops([
            ("2024-01-01", "SPL", 10, 100.0, "EUR"),
            ("2024-06-01", "SPL", -10, 100.0, "EUR"),
            ("2024-06-01", "SPL", 20, 50.0, "EUR"),
            ("2024-09-01", "SPL", -20, 60.0, "EUR"),
        ])
        g = calculate_fifo_gains(df)
        assert len(g) == 1  # only the real sale
        # cost basis carried over: 10*100 = 1000 -> 20 sh @ 50; sell 20 @ 60
        assert g.iloc[0]["coste_base_eur"] == pytest.approx(1000.0)
        assert g.iloc[0]["plusvalia_eur"] == pytest.approx(200.0)
        assert not g.iloc[0]["sin_historial"]

    def test_fx_uses_nearest_previous_rate(self):
        fx = pd.DataFrame({"USD": [0.9, 0.8]},
                          index=pd.to_datetime(["2024-01-01", "2024-03-01"]))
        df = _ops([
            ("2024-01-10", "US", 10, 100.0, "USD"),
            ("2024-02-10", "US", -10, 110.0, "USD"),
        ])
        g = calculate_fifo_gains(df, fx)
        # both converted with 0.9 (nearest previous): 10*(110-100)*0.9 = 90
        assert g.iloc[0]["plusvalia_eur"] == pytest.approx(90.0)

    def test_fx_before_first_rate_uses_first_known(self):
        fx = pd.DataFrame({"USD": [0.5]}, index=pd.to_datetime(["2024-06-01"]))
        df = _ops([
            ("2024-01-10", "US", 1, 100.0, "USD"),
            ("2024-01-20", "US", -1, 120.0, "USD"),
        ])
        g = calculate_fifo_gains(df, fx)
        assert g.iloc[0]["precio_venta_eur"] == pytest.approx(60.0)

    def test_missing_currency_is_flagged_not_unconverted(self):
        fx = pd.DataFrame({"USD": [0.9]}, index=pd.to_datetime(["2024-01-01"]))
        df = _ops([
            ("2024-01-10", "JP", 1, 1000.0, "JPY"),
            ("2024-01-20", "JP", -1, 1200.0, "JPY"),
        ])
        g = calculate_fifo_gains(df, fx)
        row = g.iloc[0]
        assert bool(row["sin_fx"]) is True
        assert row["precio_venta_eur"] != 1200.0  # NOT silently left in JPY
        assert np.isfinite(row["plusvalia_eur"])


# ═══════════════════════════════════════════════════════════════════════
#  M2 / M3  crypto
# ═══════════════════════════════════════════════════════════════════════

class TestCryptoFlows:
    def test_sell_reduces_capital(self):
        dates = pd.date_range("2024-01-01", periods=5)
        df = pd.DataFrame({
            "Date": [dates[0], dates[3]],
            "Coin": ["BTC", "BTC"],
            "Quantity": [1.0, -0.4],
        })
        fx = pd.DataFrame({"BTC": [100.0, 110.0, 120.0, 130.0, 140.0]}, index=dates)
        _, aporte, _ = calculate_crypto_portfolio(df, fx)
        # +1*100 at day0, -0.4*130 = -52 at day3  -> 48
        assert aporte.loc[dates[2]] == pytest.approx(100.0)
        assert aporte.iloc[-1] == pytest.approx(48.0)

    def test_purchases_before_fx_history_are_not_dropped(self):
        dates = pd.date_range("2024-01-10", periods=3)
        df = pd.DataFrame({
            "Date": [pd.Timestamp("2024-01-01")],
            "Coin": ["ETH"],
            "Quantity": [2.0],
        })
        fx = pd.DataFrame({"ETH": [10.0, 11.0, 12.0]}, index=dates)
        vtc, aporte, _ = calculate_crypto_portfolio(df, fx)
        assert vtc.index.min() == pd.Timestamp("2024-01-01")
        assert vtc.loc["2024-01-01"] == pytest.approx(20.0)  # first known rate
        assert aporte.iloc[-1] == pytest.approx(20.0)
        assert vtc.iloc[-1] == pytest.approx(24.0)

    def test_failed_assets_capital_uses_value(self):
        ops = pd.DataFrame({
            "Date": [pd.Timestamp("2024-01-02")],
            "ticker": ["ZZZ"], "Coin": ["EUR"],
            "Quantity": [10.0], "Price": [5.0], "Value": [-80.0],
        })
        fx = pd.DataFrame({"EUR": [1.0]}, index=[pd.Timestamp("2024-01-02")])
        out = summarize_failed_assets(ops, None, fx)
        # Broker Value (80) wins over qty*price (50), as in calculate_stock_portfolio
        assert out.iloc[0]["Invested Capital (EUR)"] == pytest.approx(80.0)


# ═══════════════════════════════════════════════════════════════════════
#  A1 / M4 / M5 / B5 / B6  market_data caches
# ═══════════════════════════════════════════════════════════════════════

def _close_frame(index, values_by_ticker):
    cols = pd.MultiIndex.from_tuples([("Close", t) for t in values_by_ticker])
    out = pd.DataFrame(index=index, columns=cols, dtype=float)
    for t, v in values_by_ticker.items():
        out[("Close", t)] = v
    return out


@pytest.fixture()
def fx_env(tmp_path, monkeypatch):
    market_data._ATTEMPTED.clear()
    cache_file = tmp_path / "fx.csv"
    monkeypatch.setattr(config, "FX_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(config, "get_fx_adjustments", lambda: {})
    monkeypatch.setattr(config, "PRICES_CACHE_FILE", str(tmp_path / "prices.csv"))
    monkeypatch.setattr(config, "get_price_adjustments", lambda: {})
    yield cache_file
    market_data._ATTEMPTED.clear()


class TestFxCacheCoverage:
    def test_uneven_column_coverage_is_redownloaded_per_column(self, fx_env, monkeypatch):
        today = pd.Timestamp.today().normalize()
        start = today - pd.Timedelta(days=30)
        idx = pd.date_range(start, today)
        usd = pd.Series(1 / 1.1, index=idx)           # fresh up to today
        btc = pd.Series(50000.0, index=idx)
        btc.iloc[-12:] = np.nan                        # NaN tail (extended by a call w/o crypto)
        pd.DataFrame({"USD": usd, "BTC": btc}).to_csv(fx_env)
        btc_last = btc.last_valid_index()

        calls = []

        def fake_download(ticker, start, end, auto_adjust, progress):
            dl = pd.Timestamp(start).normalize()
            calls.append((ticker, dl))
            i = pd.date_range(dl, today)
            return pd.DataFrame({"Close": [51000.0 if ticker == "BTC-EUR" else 1.1] * len(i)}, index=i)

        monkeypatch.setattr(market_data.yf, "download", fake_download)

        res = market_data.fetch_fx_rates(["USD"], start, crypto_coins=["BTC"])

        tickers_called = [c[0] for c in calls]
        assert tickers_called == ["BTC-EUR"], "only the column with the NaN tail is refreshed"
        assert calls[0][1] == btc_last - pd.Timedelta(days=3)
        assert res["BTC"].notna().all()
        assert res["BTC"].iloc[-1] == 51000.0

        saved = pd.read_csv(fx_env, index_col=0, parse_dates=True)
        assert set(saved.columns) == {"USD", "BTC"}
        assert saved["BTC"].iloc[-1] == 51000.0

    def test_save_does_not_drop_columns_or_history(self, fx_env, monkeypatch):
        today = pd.Timestamp.today().normalize()
        start = today - pd.Timedelta(days=20)
        idx = pd.date_range(start, today)
        pd.DataFrame({"USD": 0.9, "ETH": 2000.0}, index=idx).to_csv(fx_env)

        monkeypatch.setattr(market_data.yf, "download",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no download")))
        # Later start date + subset of columns: cache must keep ETH and old rows.
        market_data.fetch_fx_rates(["USD"], today - pd.Timedelta(days=5))
        market_data._save_cache(pd.DataFrame({"USD": [0.9]}, index=[today]), str(fx_env))
        saved = pd.read_csv(fx_env, index_col=0, parse_dates=True)
        assert "ETH" in saved.columns
        assert saved.index.min() == start

    def test_ffill_rows_are_not_persisted_as_real_data(self, fx_env, monkeypatch):
        today = pd.Timestamp.today().normalize()
        start = today - pd.Timedelta(days=10)

        def fake_download(ticker, start, end, auto_adjust, progress):
            # Only the first 3 days have data (rest "missing")
            i = pd.date_range(pd.Timestamp(start).normalize(), periods=3)
            return pd.DataFrame({"Close": [1.0, 1.0, 1.0]}, index=i)

        monkeypatch.setattr(market_data.yf, "download", fake_download)
        res = market_data.fetch_fx_rates(["USD"], start)
        assert res["USD"].notna().all()  # returned frame is forward filled
        saved = pd.read_csv(fx_env, index_col=0, parse_dates=True)
        assert saved["USD"].notna().sum() == 3  # but only real rows are cached

    def test_backfill_when_start_precedes_cache(self, fx_env, monkeypatch):
        today = pd.Timestamp.today().normalize()
        cache_start = today - pd.Timedelta(days=5)
        idx = pd.date_range(cache_start, today)
        pd.DataFrame({"USD": 0.9}, index=idx).to_csv(fx_env)
        start = today - pd.Timedelta(days=15)

        calls = []

        def fake_download(ticker, start, end, auto_adjust, progress):
            dl = pd.Timestamp(start).normalize()
            calls.append(dl)
            i = pd.date_range(dl, today)
            return pd.DataFrame({"Close": [1.25] * len(i)}, index=i)

        monkeypatch.setattr(market_data.yf, "download", fake_download)
        res = market_data.fetch_fx_rates(["USD"], start)
        assert calls == [start]
        assert res["USD"].notna().all()

    def test_anomaly_ratio_ignores_non_positive_previous(self):
        idx = pd.date_range("2024-01-01", periods=3)
        df = pd.DataFrame({"X": [0.0, 5.0, 5.1]}, index=idx)
        out, cut = market_data._truncate_fx_cache_at_anomaly(df)
        assert cut is False and len(out) == 3


class TestPricesCache:
    def test_all_nan_ticker_is_fully_redownloaded(self, fx_env, monkeypatch):
        today = pd.Timestamp.today().normalize()
        start = today - pd.Timedelta(days=6)
        idx = pd.date_range(start, today)
        pd.DataFrame({"AAA": 10.0, "BBB": np.nan}, index=idx).to_csv(config.PRICES_CACHE_FILE)

        calls = []

        def fake_download(tickers, start, end, auto_adjust, progress):
            req = [tickers] if isinstance(tickers, str) else list(tickers)
            dl = pd.Timestamp(start).normalize()
            calls.append((tuple(req), dl))
            i = pd.date_range(dl, today)
            return _close_frame(i, {t: [7.0] * len(i) for t in req})

        monkeypatch.setattr(market_data.yf, "download", fake_download)
        res = market_data.fetch_prices(["AAA", "BBB"], start)
        assert (("BBB",), start) in calls
        assert res["BBB"].notna().all()

    def test_backfill_when_start_before_cached_first_valid(self, fx_env, monkeypatch):
        today = pd.Timestamp.today().normalize()
        start = today - pd.Timedelta(days=10)
        idx = pd.date_range(today - pd.Timedelta(days=4), today)
        pd.DataFrame({"AAA": 10.0}, index=idx).to_csv(config.PRICES_CACHE_FILE)

        calls = []

        def fake_download(tickers, start, end, auto_adjust, progress):
            req = [tickers] if isinstance(tickers, str) else list(tickers)
            dl = pd.Timestamp(start).normalize()
            calls.append((tuple(req), dl))
            i = pd.date_range(dl, today)
            return _close_frame(i, {t: [9.0] * len(i) for t in req})

        monkeypatch.setattr(market_data.yf, "download", fake_download)
        res = market_data.fetch_prices(["AAA"], start)
        assert calls == [(("AAA",), start)]
        assert res["AAA"].notna().all()
        # Second call in the same process must not hammer the API again.
        calls.clear()
        market_data.fetch_prices(["AAA"], start)
        assert calls == []

    def test_overlap_redownload_and_no_ffill_persisted(self, fx_env, monkeypatch):
        today = pd.Timestamp.today().normalize()
        start = today - pd.Timedelta(days=20)
        last = today - pd.Timedelta(days=8)
        idx = pd.date_range(start, last)
        pd.DataFrame({"AAA": 10.0}, index=idx).to_csv(config.PRICES_CACHE_FILE)

        calls = []

        def fake_download(tickers, start, end, auto_adjust, progress):
            req = [tickers] if isinstance(tickers, str) else list(tickers)
            dl = pd.Timestamp(start).normalize()
            calls.append(dl)
            i = pd.date_range(dl, periods=5)  # stops before today
            return _close_frame(i, {t: [11.0] * len(i) for t in req})

        monkeypatch.setattr(market_data.yf, "download", fake_download)
        market_data.fetch_prices(["AAA"], start)
        assert calls == [last - pd.Timedelta(days=3)]
        saved = pd.read_csv(config.PRICES_CACHE_FILE, index_col=0, parse_dates=True)
        assert saved.index.max() == last - pd.Timedelta(days=3) + pd.Timedelta(days=4)
        # overlapped day overwritten with the fresh value
        assert saved.loc[last, "AAA"] == 11.0


# ═══════════════════════════════════════════════════════════════════════
#  B3  target validation
# ═══════════════════════════════════════════════════════════════════════

def _breakdown():
    return [
        {"name": "Acciones", "value": 600.0, "members": [
            {"name": "ACME", "symbol": "ACME", "value": 600.0}]},
        {"name": "Efectivo", "value": 400.0, "members": []},
    ]


class TestTargetValidation:
    def test_max_asset_zero_means_unlimited(self):
        out = compute_rebalance(1000.0, _breakdown(),
                                {"targets": {"Acciones": 60}, "max_asset_pct": 0})
        assert not [v for v in out["violations"] if v["kind"] == "max_asset"]

    def test_max_asset_positive_flags(self):
        out = compute_rebalance(1000.0, _breakdown(),
                                {"targets": {"Acciones": 60}, "max_asset_pct": 50})
        assert [v for v in out["violations"] if v["kind"] == "max_asset"]

    def test_negative_target_rejected_with_note(self):
        out = compute_rebalance(1000.0, _breakdown(),
                                {"targets": {"Acciones": -10, "Efectivo": 40}})
        by = {r["asset_class"]: r for r in out["rows"]}
        assert by["Acciones"]["has_target"] is False
        assert by["Acciones"]["status"] == "sin_objetivo"
        assert by["Efectivo"]["has_target"] is True
        assert "negativo" in out["note"]

    def test_non_numeric_target_warns_and_is_ignored(self):
        out = compute_rebalance(1000.0, _breakdown(),
                                {"targets": {"Acciones": "abc", "Efectivo": 40}})
        by = {r["asset_class"]: r for r in out["rows"]}
        assert by["Acciones"]["has_target"] is False
        assert "no numérico" in out["note"]

    def test_target_over_100_clamped(self):
        out = compute_rebalance(1000.0, _breakdown(), {"targets": {"Acciones": 250}})
        row = [r for r in out["rows"] if r["asset_class"] == "Acciones"][0]
        assert row["target_pct"] == 100.0
        assert "100" in out["note"]

    def test_none_target_is_not_a_zero_target(self):
        out = compute_rebalance(1000.0, _breakdown(),
                                {"targets": {"Acciones": None, "Efectivo": 40}})
        by = {r["asset_class"]: r for r in out["rows"]}
        assert by["Acciones"]["has_target"] is False
        assert by["Acciones"]["target_pct"] is None

    def test_contract_unchanged_for_valid_config(self):
        out = compute_rebalance(1000.0, _breakdown(),
                                {"targets": {"Acciones": 50, "Efectivo": 50}, "band_pct": 5})
        assert out["configured"] is True
        assert {"rows", "violations", "note", "target_sum_pct"} <= set(out)
        by = {r["asset_class"]: r for r in out["rows"]}
        assert by["Acciones"]["action_eur"] == -100.0
        assert by["Acciones"]["status"] == "vender"
