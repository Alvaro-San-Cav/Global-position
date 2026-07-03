"""
test_logic.py – Verifica que la lógica del script Global-Position
reproduce los mismos cálculos que el notebook original.

Cada test usa datos sintéticos (sin red, sin ficheros reales) y compara
la salida de las funciones del script con valores calculados a mano
siguiendo la lógica del notebook.
"""

import sys
import os

import numpy as np
import pandas as pd
import pytest

# ── Importar módulos del proyecto ──────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src import config
from src.core import (
    SplitManager,
    calculate_stock_portfolio,
    calculate_crypto_portfolio,
    compute_twr,
    compute_metrics as _compute_metrics,
    classify_asset,
    normalize_date_series,
    _to_tznaive_safe,
)


# ═══════════════════════════════════════════════════════════════════════
#  1. SPLIT DETECTION  (notebook: detectar_splits_dfops)
# ═══════════════════════════════════════════════════════════════════════

class TestSplitDetection:
    """La detección de splits busca pares de operaciones en la misma fecha
    y ticker cuyo Value suma 0 y cuyo ratio qty/price es consistente."""

    def _make_split_ops(self, ticker="ACME", date="2024-06-15",
                        old_qty=-10, new_qty=40, old_price=100.0):
        """Crear un par de operaciones que represente un split 4:1."""
        new_price = old_price * abs(old_qty) / abs(new_qty)  # 25.0
        sell_value = abs(old_qty) * old_price   # 1000
        buy_value  = -sell_value                # -1000  (sumando → 0)
        return pd.DataFrame({
            "Date":     [date, date],
            "Product":  [ticker, ticker],
            "ISIN":     ["XX1234", "XX1234"],
            "Quantity": [old_qty, new_qty],     # -10, +40
            "Price":    [old_price, new_price], # 100, 25
            "Coin":     ["EUR", "EUR"],
            "Value":    [sell_value, buy_value], # +1000, -1000
            "eur":      ["EUR", "EUR"],
            "ticker":   [ticker, ticker],
        })

    def test_detect_basic_4_to_1(self):
        """Un split 4:1 con Value=0 debe detectarse con ratio=4."""
        df = self._make_split_ops()
        splits = SplitManager.detect_splits_from_ops(df)
        assert len(splits) == 1
        assert splits[0]["ticker"] == "ACME"
        assert np.isclose(splits[0]["ratio"], 4.0, atol=0.01)

    def test_detect_2_to_1(self):
        """Un split 2:1."""
        df = self._make_split_ops(old_qty=-10, new_qty=20, old_price=100.0)
        splits = SplitManager.detect_splits_from_ops(df)
        assert len(splits) == 1
        assert np.isclose(splits[0]["ratio"], 2.0, atol=0.01)

    def test_no_split_normal_trade(self):
        """Una compra normal (Value != 0) NO debe detectarse como split."""
        df = pd.DataFrame({
            "Date":     ["2024-03-01"],
            "Product":  ["ACME"],
            "ISIN":     ["XX1234"],
            "Quantity": [5],
            "Price":    [50.0],
            "Coin":     ["EUR"],
            "Value":    [250.0],
            "eur":      ["EUR"],
            "ticker":   ["ACME"],
        })
        splits = SplitManager.detect_splits_from_ops(df)
        assert len(splits) == 0


# ═══════════════════════════════════════════════════════════════════════
#  2. SPLIT APPLICATION  (notebook: aplicar_splits_con_factores_mismo_dia)
# ═══════════════════════════════════════════════════════════════════════

class TestSplitApplication:
    """El _apply_factors multiplica Quantity por el factor acumulado."""

    def _base_ops(self):
        """3 operaciones de 'ABC' en diferentes fechas."""
        return pd.DataFrame({
            "Date":     ["2024-01-01", "2024-06-15", "2024-09-01"],
            "Product":  ["ABC"] * 3,
            "ISIN":     ["ISN1"] * 3,
            "Quantity": [10, -10, 5],   # compra, split-sell, compra post
            "Price":    [100, 100, 25],
            "Coin":     ["EUR"] * 3,
            "Value":    [1000, -1000, 125],
            "eur":      ["EUR"] * 3,
            "ticker":   ["ABC"] * 3,
        })

    def test_factor_before_split(self):
        """Fila ANTES del split (2024-01-01) debe multiplicar por el ratio."""
        df = self._base_ops()
        splits = [{"ticker": "ABC", "fecha": pd.Timestamp("2024-06-15"), "ratio": 4.0}]
        result = SplitManager._apply_factors(df, splits)
        # Row at 2024-01-01 is BEFORE split → factor = ratio = 4.0
        row0 = result.iloc[0]
        assert np.isclose(row0["adj_factor"], 4.0)
        assert np.isclose(row0["Quantity_adj"], 40.0)  # 10 * 4

    def test_factor_after_split(self):
        """Fila DESPUÉS del split (2024-09-01) debe tener factor 1."""
        df = self._base_ops()
        splits = [{"ticker": "ABC", "fecha": pd.Timestamp("2024-06-15"), "ratio": 4.0}]
        result = SplitManager._apply_factors(df, splits)
        # Row at 2024-09-01 is after all splits → for..else → factor = 1.0
        row2 = result.iloc[2]
        assert np.isclose(row2["adj_factor"], 1.0)
        assert np.isclose(row2["Quantity_adj"], 5.0)

    def test_same_day_logic(self):
        """El mismo día del split, la dirección qty determina el factor.
        Para ratio>1 (forward split): sell (qty<0) → factor=ratio*future,
        buy (qty>0) → factor=future only."""
        df = pd.DataFrame({
            "Date":     ["2024-06-15", "2024-06-15"],
            "Product":  ["ABC", "ABC"],
            "ISIN":     ["X", "X"],
            "Quantity": [-10, 40],       # sell old, buy new
            "Price":    [100, 25],
            "Coin":     ["EUR", "EUR"],
            "Value":    [1000, -1000],
            "eur":      ["EUR", "EUR"],
            "ticker":   ["ABC", "ABC"],
        })
        splits = [{"ticker": "ABC", "fecha": pd.Timestamp("2024-06-15"), "ratio": 4.0}]
        result = SplitManager._apply_factors(df, splits)

        # ratio>1, sell (qty<0) → factor_post = 4 (ratio*1 since no future splits)
        sell_row = result[result["Quantity"] == -10].iloc[0]
        assert np.isclose(sell_row["adj_factor"], 4.0)

        # ratio>1, buy (qty>0) → factor_pre = 1 (no future splits)
        buy_row = result[result["Quantity"] == 40].iloc[0]
        assert np.isclose(buy_row["adj_factor"], 1.0)


# ═══════════════════════════════════════════════════════════════════════
#  3. STOCK PORTFOLIO VALUATION  (notebook cells 6 & 8)
# ═══════════════════════════════════════════════════════════════════════

class TestStockPortfolio:
    """Verificar qty acumulada × precio × FX = valor de cartera."""

    @pytest.fixture()
    def portfolio_data(self):
        """Crear un mini-portfolio con 2 tickers en 5 días."""
        dates = pd.date_range("2024-01-01", periods=5)
        # Operaciones
        df_ops = pd.DataFrame({
            "Date":         [dates[0], dates[0], dates[2]],
            "Product":      ["Stock A", "Stock B", "Stock A"],
            "ISIN":         ["ISN_A", "ISN_B", "ISN_A"],
            "Quantity":     [10, 5, 3],
            "Quantity_adj": [10, 5, 3],
            "Price":        [100.0, 200.0, 110.0],
            "Coin":         ["USD", "EUR", "USD"],
            "Value":        [1000.0, 1000.0, 330.0],
            "eur":          ["EUR", "EUR", "EUR"],
            "ticker":       ["A", "B", "A"],
        })
        # Precios (Close)
        prices = pd.DataFrame({
            "A": [100, 102, 105, 103, 110],
            "B": [200, 198, 195, 200, 205],
        }, index=dates)
        # FX rates (USD→EUR = 0.9, EUR→EUR = 1.0)
        fx = pd.DataFrame({
            "USD": [0.9, 0.9, 0.9, 0.9, 0.9],
            "EUR": [1.0, 1.0, 1.0, 1.0, 1.0],
        }, index=dates)
        return df_ops, prices, fx, dates

    def test_valor_total_cartera_day0(self, portfolio_data):
        """Día 0: 10 acc A × 100 × 0.9 + 5 acc B × 200 × 1.0 = 1900."""
        df_ops, prices, fx, dates = portfolio_data
        vtc, ad, vc = calculate_stock_portfolio(df_ops, prices, fx)
        expected_day0 = 10 * 100 * 0.9 + 5 * 200 * 1.0  # 900 + 1000 = 1900
        assert np.isclose(vtc.loc[dates[0]], expected_day0, rtol=0.001)

    def test_valor_total_cartera_day2(self, portfolio_data):
        """Día 2: (10+3) × 105 × 0.9 + 5 × 195 × 1.0 = 1228.5 + 975 = 2203.5."""
        df_ops, prices, fx, dates = portfolio_data
        vtc, ad, vc = calculate_stock_portfolio(df_ops, prices, fx)
        expected_day2 = 13 * 105 * 0.9 + 5 * 195 * 1.0
        assert np.isclose(vtc.loc[dates[2]], expected_day2, rtol=0.001)

    def test_aporte_diario_cumulative(self, portfolio_data):
        """Capital aportado acumulado al final = sum de flows con signo."""
        df_ops, prices, fx, dates = portfolio_data
        vtc, ad, vc = calculate_stock_portfolio(df_ops, prices, fx)
        # Uses broker cash flow (Value) when present:
        # Day 0: +1000 (A) +1000 (B)
        # Day 2: +330  (A)
        # Total = 2330
        expected_total = 1000 + 1000 + 330
        assert np.isclose(ad.iloc[-1], expected_total, rtol=0.01)

    def test_valor_cartera_has_both_tickers(self, portfolio_data):
        """El DataFrame valor_cartera debe tener columnas A y B."""
        df_ops, prices, fx, dates = portfolio_data
        vtc, ad, vc = calculate_stock_portfolio(df_ops, prices, fx)
        assert "A" in vc.columns
        assert "B" in vc.columns

    def test_aporte_zero_value_uses_notebook_fallback_for_configured_ticker(self, monkeypatch):
        """Para tickers configurados (p.ej. SAP), Value=0 usa EST_eur como en notebook."""
        dates = pd.date_range("2024-01-01", periods=3)
        df_ops = pd.DataFrame({
            "Date": [dates[0]],
            "Product": ["SAP SE"],
            "ISIN": ["DE0007164600"],
            "Quantity": [10.0],
            "Price": [100.0],
            "Coin": ["EUR"],
            "Value": [0.0],
            "eur": ["EUR"],
            "ticker": ["SAP.DE"],
        })
        prices = pd.DataFrame({"SAP.DE": [100.0, 101.0, 102.0]}, index=dates)
        fx = pd.DataFrame({"EUR": [1.0, 1.0, 1.0]}, index=dates)

        monkeypatch.setattr(config, "get_zero_value_flow_from_est_tickers", lambda: ["SAP.DE"])

        _, aporte, _ = calculate_stock_portfolio(df_ops, prices, fx)

        # Notebook-style fallback for SAP rows with Value=0: flow ~= Price*FX (=100)
        assert np.isclose(aporte.iloc[-1], 100.0, rtol=0.001)


# ═══════════════════════════════════════════════════════════════════════
#  4. CRYPTO PORTFOLIO VALUATION  (notebook cell 10)
# ═══════════════════════════════════════════════════════════════════════

class TestCryptoPortfolio:
    """El cálculo crypto: balance_acumulado × rate (coin→EUR)."""

    @pytest.fixture()
    def crypto_data(self):
        dates = pd.date_range("2024-01-01", periods=5)
        df_crypto = pd.DataFrame({
            "Date":     [dates[0], dates[2]],
            "Coin":     ["BTC", "BTC"],
            "Quantity": [0.5, 0.3],
        })
        # FX: BTC-EUR prices (coin→EUR, as returned by market_data)
        fx = pd.DataFrame({
            "BTC": [40000, 41000, 42000, 43000, 44000],
            "EUR": [1.0, 1.0, 1.0, 1.0, 1.0],
        }, index=dates)
        return df_crypto, fx, dates

    def test_valor_total_crypto_last_day(self, crypto_data):
        """Último día: (0.5+0.3) BTC × 44000 EUR/BTC = 35200."""
        df_crypto, fx, dates = crypto_data
        vtc, aporte, vceur = calculate_crypto_portfolio(df_crypto, fx)
        # Last common date value
        assert vtc is not None
        last_shared = vtc.index[-1]
        expected = 0.8 * fx.loc[last_shared, "BTC"]
        assert np.isclose(vtc.iloc[-1], expected, rtol=0.01)

    def test_aporte_crypto(self, crypto_data):
        """Capital aportado crypto = sum(Qty × rate_del_día) para buys."""
        df_crypto, fx, dates = crypto_data
        vtc, aporte, vceur = calculate_crypto_portfolio(df_crypto, fx)
        assert aporte is not None
        # Day 0: 0.5 BTC × 40000 = 20000
        # Day 2: 0.3 BTC × 42000 = 12600
        # Total = 32600
        expected_aporte = 0.5 * 40000 + 0.3 * 42000
        assert np.isclose(aporte.iloc[-1], expected_aporte, rtol=0.01)


# ═══════════════════════════════════════════════════════════════════════
#  5. TWR  (notebook cell 12)
# ═══════════════════════════════════════════════════════════════════════

class TestTWR:
    """
    TWR = ∏(1 + r_i) - 1, donde r_i = (V_i - V_{i-1} - CF_i) / (V_{i-1} + CF_i).

    La lógica del notebook y del script difieren en el manejo del epsilon:
    - Notebook: denom + 1e-12 (nunca salta días)
    - Script: salta días con abs(denom) < 1.0 y clampea r ∈ [-0.99, 5.0]

    Ambos deben coincidir cuando los valores son razonables.
    """

    def test_simple_no_flows(self):
        """Sin flujos, TWR = simple return."""
        dates = pd.date_range("2024-01-01", periods=4)
        values = pd.Series([1000, 1050, 1080, 1100], index=dates)
        contribs = pd.Series([1000, 1000, 1000, 1000], index=dates)

        twr_t, twr_a = compute_twr(values, contribs)

        # Sin flujos → TWR = (1100/1000) - 1 = 0.10
        # Pero TWR chain-links daily: (1050/1000)*(1080/1050)*(1100/1080) - 1
        day1 = 1050 / 1000 - 1   # 0.05
        day2 = 1080 / 1050 - 1   # ~0.02857
        day3 = 1100 / 1080 - 1   # ~0.01852
        expected = (1 + day1) * (1 + day2) * (1 + day3) - 1
        assert np.isclose(twr_t, expected, atol=0.001)

    def test_with_contribution(self):
        """Con un aporte en el día 2, el TWR no debe verse afectado."""
        dates = pd.date_range("2024-01-01", periods=3)
        # Day 0: start at 1000 with 1000 invested
        # Day 1: value goes to 1100, add 500 more → contrib=1500
        # Day 2: value goes to 1700
        values = pd.Series([1000, 1100, 1700], index=dates)
        contribs = pd.Series([1000, 1500, 1500], index=dates)

        twr_t, _ = compute_twr(values, contribs, annualize=False)

        # Day 1: CF=500, denom=1000+500=1500, r=(1100-1000-500)/1500 = -400/1500
        # Wait, that doesn't look right. Let me recalculate.
        # Actually: V_prev=1000, V_curr=1100, CF=500
        # r = (1100 - 1000 - 500) / (1000 + 500) = -400/1500 = -0.2667
        # Day 2: CF=0, denom=1100+0=1100, r=(1700-1100-0)/1100 = 600/1100 = 0.5454
        # TWR = (1-0.2667)*(1+0.5454) - 1 = 0.7333*1.5454 - 1 ≈ 0.1333
        day1_r = (1100 - 1000 - 500) / (1000 + 500)
        day2_r = (1700 - 1100 - 0) / (1100 + 0)
        expected = (1 + day1_r) * (1 + day2_r) - 1
        assert np.isclose(twr_t, expected, atol=0.01)

    def test_twr_annualization(self):
        """La anualización usa (1+TWR)^(365.25/days) - 1."""
        dates = pd.date_range("2024-01-01", periods=366)
        values = pd.Series(np.linspace(1000, 1100, 366), index=dates)
        contribs = pd.Series([1000.0] * 366, index=dates)

        twr_t, twr_a = compute_twr(values, contribs, annualize=True)
        days = (dates[-1] - dates[0]).days
        years = days / 365.25
        expected_annual = (1 + twr_t) ** (1 / years) - 1
        assert np.isclose(twr_a, expected_annual, atol=0.001)


# ═══════════════════════════════════════════════════════════════════════
#  6. METRICS AGGREGATION  (main._compute_metrics, mirrors notebook cell 12)
# ═══════════════════════════════════════════════════════════════════════

class TestMetrics:
    """Verificar que _compute_metrics produce CAGR, rentabilidad, pesos
    consistentes con la fórmula del notebook."""

    def test_stocks_only(self):
        """Sin crypto, las métricas totales == métricas acciones."""
        dates = pd.date_range("2024-01-01", periods=365)
        vtc = pd.Series(np.linspace(10000, 12000, 365), index=dates)
        ad  = pd.Series(np.linspace(10000, 10500, 365), index=dates)

        m = _compute_metrics(vtc, ad, None, None, None)

        # Stock values
        assert np.isclose(m["capital_aportado_acciones"], ad.iloc[-1])
        assert np.isclose(m["valor_actual_acciones"], vtc.iloc[-1])
        assert np.isclose(m["plusvalia_acciones"], vtc.iloc[-1] - ad.iloc[-1])

        # Rentabilidad
        expected_rent = (vtc.iloc[-1] - ad.iloc[-1]) / ad.iloc[-1] * 100
        assert np.isclose(m["rentabilidad_acciones"], expected_rent, atol=0.1)

        # Totals match stocks when no crypto
        assert np.isclose(m["capital_total"], m["capital_aportado_acciones"])
        assert np.isclose(m["valor_total"], m["valor_actual_acciones"])
        assert np.isclose(m["peso_acciones"], 100.0, atol=0.1)
        assert np.isclose(m["peso_crypto"], 0.0, atol=0.1)

    def test_with_crypto(self):
        """Con crypto, los totales combinan ambos."""
        dates = pd.date_range("2024-01-01", periods=100)
        vtc = pd.Series([10000.0] * 100, index=dates)
        ad  = pd.Series([8000.0] * 100, index=dates)
        vtc_crypto = pd.Series([5000.0] * 100, index=dates)
        ad_crypto  = pd.Series([4000.0] * 100, index=dates)
        vc_eur     = pd.DataFrame({"BTC": [5000.0] * 100}, index=dates)

        m = _compute_metrics(vtc, ad, vtc_crypto, ad_crypto, vc_eur)

        assert np.isclose(m["capital_total"], 8000 + 4000)
        assert np.isclose(m["valor_total"], 10000 + 5000)
        assert np.isclose(m["plusvalia_total"], 15000 - 12000)

        expected_peso_acc = 10000 / 15000 * 100
        expected_peso_cry = 5000 / 15000 * 100
        assert np.isclose(m["peso_acciones"], expected_peso_acc, atol=0.1)
        assert np.isclose(m["peso_crypto"], expected_peso_cry, atol=0.1)

    def test_cagr_formula(self):
        """CAGR = ((V/C)^(1/años) - 1) × 100."""
        dates = pd.date_range("2024-01-01", periods=730)
        vtc = pd.Series([10000.0] * 730, index=dates)
        vtc.iloc[-1] = 12000.0
        ad  = pd.Series([10000.0] * 730, index=dates)

        m = _compute_metrics(vtc, ad, None, None, None)

        dias = (dates[-1] - dates[0]).days
        anhos = dias / 365.25
        expected_cagr = ((12000 / 10000) ** (1 / anhos) - 1) * 100
        assert np.isclose(m["cagr_acciones"], expected_cagr, atol=0.1)


# ═══════════════════════════════════════════════════════════════════════
#  7. DATE HELPERS
# ═══════════════════════════════════════════════════════════════════════

class TestDateHelpers:
    """Verificar que las funciones de normalización de fechas coinciden
    con la lógica del notebook."""

    def test_tz_aware_to_naive(self):
        ts = pd.Timestamp("2024-06-15 14:30:00", tz="US/Eastern")
        result = _to_tznaive_safe(ts)
        assert result.tz is None
        assert result == pd.Timestamp("2024-06-15")

    def test_nat_handled(self):
        result = _to_tznaive_safe(pd.NaT)
        assert pd.isna(result)

    def test_normalize_date_series(self):
        s = pd.Series(["2024-01-15 10:30:00", "2024-02-20 08:00:00"])
        result = normalize_date_series(s)
        assert all(result.dt.hour == 0)
        assert result.iloc[0] == pd.Timestamp("2024-01-15")


# ═══════════════════════════════════════════════════════════════════════
#  8. APORTE DIARIO SIGN LOGIC  (script difference)
# ═══════════════════════════════════════════════════════════════════════

class TestAporteDiarioSign:
    """El notebook suma EST_eur directamente. El script aplica signo
    según Quantity: buy (+), sell (-). Verificar que con datos normales
    el resultado es coherente."""

    def test_buy_adds_sell_subtracts(self):
        """Compra 10 a 100€ y venta de 5 a 110€."""
        dates = pd.date_range("2024-01-01", periods=10)
        df_ops = pd.DataFrame({
            "Date":         [dates[0], dates[5]],
            "Product":      ["X", "X"],
            "ISIN":         ["ISN", "ISN"],
            "Quantity":     [10, -5],
            "Quantity_adj": [10, -5],
            "Price":        [100.0, 110.0],
            "Coin":         ["EUR", "EUR"],
            "Value":        [1000.0, -550.0],
            "eur":          ["EUR", "EUR"],
            "ticker":       ["X", "X"],
        })
        prices = pd.DataFrame({"X": np.linspace(100, 120, 10)}, index=dates)
        fx = pd.DataFrame({"EUR": [1.0] * 10}, index=dates)

        vtc, ad, vc = calculate_stock_portfolio(df_ops, prices, fx)

        # Day 0: buy  10 × 100 × 1.0 = +1000
        # Day 5: sell  5 × 110 × 1.0 = -550  (negative flow = capital back)
        # Net aporte = 1000 - 550 = 450
        assert np.isclose(ad.iloc[-1], 450.0, rtol=0.01)


class TestClassifyAsset:
    """Asset-class classifier used for the dashboard breakdown."""

    def test_gold_before_etf(self):
        # 'PHYSICAL GOLD ETC' contains ISHARES (ETF kw) but gold wins.
        assert classify_asset("PPFB.DE", "ISHARES PHYSICAL GOLD ETC") == "Oro / Materias primas"

    def test_etf_by_ucits(self):
        assert classify_asset("EQQQ.MI", "INVESCO POWERSHARES EQQQ NASDAQ-100 UCITS ETF") == "ETF"

    def test_bond_keyword(self):
        assert classify_asset("AGG", "ISHARES CORE US AGGREGATE BOND ETF") == "Bonos"

    def test_crypto_symbol(self):
        assert classify_asset("BTC", "Bitcoin") == "Cripto"
        assert classify_asset("ETH-EUR", "Ethereum") == "Cripto"

    def test_default_stock(self):
        assert classify_asset("SAP.DE", "SAP SE") == "Acciones"

    def test_override_wins(self):
        assert classify_asset("PPFB.DE", "ISHARES PHYSICAL GOLD ETC",
                              {"PPFB.DE": "Acciones"}) == "Acciones"
