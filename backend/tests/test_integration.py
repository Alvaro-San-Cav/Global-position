"""
test_integration.py – End-to-end pipeline tests with mocked market data.

Tests the full flow:
  load operations → apply splits → calculate portfolio → compute metrics

yfinance calls are mocked so tests run without network access.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import core


# ─────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────

def _make_ops() -> pd.DataFrame:
    """Synthetic operations: buy NVDA, buy AAPL, sell half AAPL."""
    return pd.DataFrame({
        "Date":     pd.to_datetime(["2021-01-04", "2021-03-01", "2022-06-01"]),
        "Product":  ["NVIDIA", "APPLE", "APPLE"],
        "ISIN":     ["US67066G1040", "US0378331005", "US0378331005"],
        "Quantity": [10.0, 20.0, -10.0],
        "Price":    [500.0, 130.0, 155.0],
        "Coin":     ["USD", "USD", "USD"],
        "Value":    [-5000.0, -2600.0, 1550.0],
        "eur":      ["EUR", "EUR", "EUR"],
        "ticker":   ["NVDA", "AAPL", "AAPL"],
    })


def _make_prices(ops: pd.DataFrame) -> pd.DataFrame:
    """Daily close prices from first op to today+1, constant for simplicity."""
    idx = pd.date_range(ops["Date"].min(), pd.Timestamp.today().normalize(), freq="D")
    return pd.DataFrame({
        "NVDA": 600.0,
        "AAPL": 170.0,
    }, index=idx)


def _make_fx(ops: pd.DataFrame) -> pd.DataFrame:
    idx = pd.date_range(ops["Date"].min(), pd.Timestamp.today().normalize(), freq="D")
    return pd.DataFrame({"USD": 1.0}, index=idx)  # 1:1 for simplicity


# ─────────────────────────────────────────────────────────────────────────
#  E2E: No splits
# ─────────────────────────────────────────────────────────────────────────

class TestPipelineNoSplits:
    def setup_method(self):
        self.ops = _make_ops()
        self.prices = _make_prices(self.ops)
        self.fx = _make_fx(self.ops)

    def _run(self):
        with patch.object(core.SplitManager, "get_yfinance_splits", return_value={}):
            df_adj = core.SplitManager.apply_splits(self.ops)
        return core.calculate_stock_portfolio(df_adj, self.prices, self.fx)

    def test_valor_total_positive(self):
        vtc, ad, vc = self._run()
        assert vtc.iloc[-1] > 0

    def test_aporte_cumulative_positive(self):
        vtc, ad, vc = self._run()
        assert ad.iloc[-1] > 0

    def test_nvda_qty_correct(self):
        with patch.object(core.SplitManager, "get_yfinance_splits", return_value={}):
            df_adj = core.SplitManager.apply_splits(self.ops)
        vtc, ad, vc = core.calculate_stock_portfolio(df_adj, self.prices, self.fx)
        # NVDA: 10 shares × $600 USD (fx=1) = €6000
        assert vc["NVDA"].iloc[-1] == pytest.approx(6000.0, rel=1e-3)

    def test_aapl_qty_after_sell(self):
        """After selling 10 of 20, should hold 10 AAPL @ $170 = $1700."""
        with patch.object(core.SplitManager, "get_yfinance_splits", return_value={}):
            df_adj = core.SplitManager.apply_splits(self.ops)
        vtc, ad, vc = core.calculate_stock_portfolio(df_adj, self.prices, self.fx)
        assert vc["AAPL"].iloc[-1] == pytest.approx(1700.0, rel=1e-3)

    def test_sell_reduces_capital(self):
        """Selling returns capital: total aporte < total buys."""
        vtc, ad, vc = self._run()
        total_buys = 10 * 500 + 20 * 130  # 7600
        total_sell = 10 * 155              # 1550
        expected_net = total_buys - total_sell
        assert ad.iloc[-1] == pytest.approx(expected_net, rel=1e-2)

    def test_twr_positive_when_gains(self):
        """With rising prices relative to cost, TWR should be > 0."""
        vtc, ad, vc = self._run()
        twr_t, twr_a = core.compute_twr(vtc, ad)
        assert twr_t > 0


# ─────────────────────────────────────────────────────────────────────────
#  E2E: With a simulated split (4:1 on NVDA after buy)
# ─────────────────────────────────────────────────────────────────────────

class TestPipelineWithSplit:
    def setup_method(self):
        # Buy 10 NVDA, then split 4:1 (represented as sell 10 + buy 40 same day, zero value)
        self.ops = pd.DataFrame({
            "Date":     pd.to_datetime(["2021-01-04", "2021-07-20", "2021-07-20"]),
            "Product":  ["NVIDIA", "NVIDIA", "NVIDIA"],
            "ISIN":     ["US67066G1040"] * 3,
            "Quantity": [10.0, -10.0, 40.0],
            "Price":    [500.0, 500.0, 125.0],
            "Coin":     ["USD"] * 3,
            "Value":    [-5000.0, 5000.0, -5000.0],
            "eur":      ["EUR"] * 3,
            "ticker":   ["NVDA"] * 3,
        })
        idx = pd.date_range("2021-01-04", pd.Timestamp.today().normalize(), freq="D")
        self.prices = pd.DataFrame({"NVDA": 130.0}, index=idx)
        self.fx = pd.DataFrame({"USD": 1.0}, index=idx)

    def test_split_detected_and_applied(self):
        with patch.object(core.SplitManager, "get_yfinance_splits", return_value={}):
            df_adj = core.SplitManager.apply_splits(self.ops)
        # After 4:1 split, original 10 shares → 40 adj
        buy_row = df_adj[(df_adj["Quantity"] == 10.0)]
        assert buy_row["Quantity_adj"].iloc[0] == pytest.approx(40.0)


# ─────────────────────────────────────────────────────────────────────────
#  E2E: Metrics computation
# ─────────────────────────────────────────────────────────────────────────

class TestMetricsIntegration:
    def test_cagr_formula(self):
        """CAGR computed from value/capital over known period."""
        n_days = 365
        idx = pd.date_range("2022-01-01", periods=n_days + 1, freq="D")
        # Capital stays at 1000, value grows to 1100 linearly
        capital = pd.Series(1000.0, index=idx)
        value   = pd.Series(np.linspace(1000.0, 1100.0, n_days + 1), index=idx)

        twr_t, twr_a = core.compute_twr(value, capital)
        # No new flows after day 0, so TWR ≈ 10% total
        assert twr_t == pytest.approx(0.10, abs=0.02)

    def test_failed_assets_empty_when_all_present(self):
        ops = _make_ops()
        fx = _make_fx(ops)
        result = core.summarize_failed_assets(None, None, fx)
        assert result.empty
