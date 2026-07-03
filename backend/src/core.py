"""
core.py – Portfolio calculations.

Faithfully ports the notebook logic for:
  • Split detection & adjustment  (stocks)
  • Stock portfolio valuation     (quantity × price_EUR, invested capital)
  • Crypto portfolio valuation    (cumulative balance × FX, cost basis)
  • TWR (Time-Weighted Return)    (daily chain-linking)
"""

from collections import defaultdict

import numpy as np
import pandas as pd
import yfinance as yf

from . import config


# ─────────────────────────────────────────────────────────────────────────
# Date helpers (tz-naive, normalised to midnight)
# ─────────────────────────────────────────────────────────────────────────

def _to_tznaive_safe(x):
    if pd.isna(x):
        return pd.NaT
    ts = pd.to_datetime(x)
    if pd.isna(ts):
        return pd.NaT
    if getattr(ts, "tz", None) is not None:
        ts = ts.tz_convert(None) if hasattr(ts, "tz_convert") else ts.tz_localize(None)
    return ts.normalize()


def normalize_date_series(s):
    return pd.to_datetime(s).map(lambda x: _to_tznaive_safe(x) if not pd.isna(x) else pd.NaT)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SPLITS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SplitManager:
    """Detects and applies stock splits exactly like the notebook."""

    # -- detect splits already recorded in operations (value-neutral pairs) --
    @staticmethod
    def detect_splits_from_ops(df_ops, tol=1e-3):
        df_ops = df_ops.copy()
        df_ops['Date'] = normalize_date_series(df_ops['Date'])
        df_nz = df_ops[df_ops['Value'] != 0].copy()

        splits: list[dict] = []
        for (fecha, ticker), grupo in df_nz.groupby(['Date', 'ticker']):
            if abs(grupo['Value'].sum()) > 1e-6:
                continue
            pos = grupo[grupo['Quantity'] > 0]
            neg = grupo[grupo['Quantity'] < 0]
            if pos.empty or neg.empty:
                continue

            pos_qty   = pos['Quantity'].sum()
            neg_qty   = neg['Quantity'].sum()
            pos_price = (pos['Quantity'].abs() * pos['Price']).sum() / pos['Quantity'].abs().sum()
            neg_price = (neg['Quantity'].abs() * neg['Price']).sum() / neg['Quantity'].abs().sum()

            if abs(neg_qty) < 1e-12 or pos_price <= 0 or neg_price <= 0:
                continue

            ratio_cand = abs(pos_qty) / abs(neg_qty)
            if abs((pos_price / neg_price) - (1.0 / ratio_cand)) < tol:
                splits.append({'ticker': ticker, 'fecha': _to_tznaive_safe(fecha), 'ratio': float(ratio_cand)})
            else:
                ratio_cand2 = abs(neg_qty) / abs(pos_qty)
                if abs((neg_price / pos_price) - (1.0 / ratio_cand2)) < tol:
                    splits.append({'ticker': ticker, 'fecha': _to_tznaive_safe(fecha), 'ratio': float(ratio_cand2)})
        return splits

    # -- fetch yfinance split history for a ticker --
    @staticmethod
    def get_yfinance_splits(ticker):
        try:
            s = yf.Ticker(ticker).splits
            return {_to_tznaive_safe(f): float(r) for f, r in s.items()}
        except Exception:
            return {}

    # -- find splits that happened *after* our last op (holding period) --
    @staticmethod
    def detect_post_holding_splits(df_ops, ticker, detected_splits):
        df_ops = df_ops.copy()
        df_ops['Date'] = normalize_date_series(df_ops['Date'])

        fechas_detectadas = set(
            _to_tznaive_safe(s['fecha']) for s in detected_splits if s['ticker'] == ticker
        )
        fechas_tenencia = df_ops.loc[df_ops['ticker'] == ticker, 'Date']
        if fechas_tenencia.empty:
            return []

        ultima = _to_tznaive_safe(fechas_tenencia.max())
        yf_splits = SplitManager.get_yfinance_splits(ticker)

        faltantes: list[dict] = []
        for fecha, ratio in yf_splits.items():
            fecha = _to_tznaive_safe(fecha)
            if fecha not in fechas_detectadas and fecha > ultima:
                faltantes.append({'ticker': ticker, 'fecha': fecha, 'ratio': ratio})
        return faltantes

    # -- orchestrate detection + application --
    @staticmethod
    def apply_splits(df_ops) -> pd.DataFrame:
        log = config.get_logger()
        print("[*] Detecting and applying splits...")

        splits_ops = SplitManager.detect_splits_from_ops(df_ops)
        print(f"   [ok] {len(splits_ops)} split(s) found in operations")
        for s in splits_ops:
            log.info(
                f"split detectado (operaciones): ticker={s['ticker']} "
                f"fecha={s['fecha'].date()} ratio={s['ratio']:.4f}"
            )

        splits_post: list[dict] = []
        for t in df_ops['ticker'].dropna().unique():
            splits_post.extend(SplitManager.detect_post_holding_splits(df_ops, t, splits_ops))
        print(f"   [ok] {len(splits_post)} post-holding split(s) found via yfinance")
        for s in splits_post:
            log.info(
                f"split detectado (yfinance post-holding): ticker={s['ticker']} "
                f"fecha={s['fecha'].date()} ratio={s['ratio']:.4f}"
            )

        all_splits = splits_ops + splits_post
        if not all_splits:
            log.info("apply_splits: sin splits detectados")
        return SplitManager._apply_factors(df_ops, all_splits)

    @staticmethod
    def _apply_factors(df_ops, splits) -> pd.DataFrame:
        """Apply split factors with same-day handling (notebook logic)."""
        df_adj = df_ops.copy()
        df_adj['Date'] = normalize_date_series(df_adj['Date'])
        df_adj['adj_factor'] = 1.0

        splits_by_ticker: dict[str, list[tuple]] = defaultdict(list)
        for s in splits:
            splits_by_ticker[s['ticker']].append((_to_tznaive_safe(s['fecha']), float(s['ratio'])))

        for ticker, splits_list in splits_by_ticker.items():
            splits_list = sorted(splits_list, key=lambda x: x[0])
            fechas_splits = [f for f, _ in splits_list]
            ratios        = [r for _, r in splits_list]

            mask = df_adj['ticker'] == ticker
            fechas_filas = df_adj.loc[mask, 'Date'].dt.normalize()
            qtys = df_adj.loc[mask, 'Quantity']

            for idx, fila_fecha in fechas_filas.items():
                qty = qtys.loc[idx]
                factor = 1.0

                for i, split_fecha in enumerate(fechas_splits):
                    if fila_fecha < split_fecha:
                        # Accumulate all remaining splits
                        for j in range(i, len(ratios)):
                            factor *= ratios[j]
                        break
                    elif fila_fecha == split_fecha:
                        # Same-day: direction-dependent (notebook logic)
                        factor_pre = 1.0
                        for j in range(i + 1, len(ratios)):
                            factor_pre *= ratios[j]
                        factor_post = factor_pre * ratios[i]

                        if ratios[i] > 1:
                            factor = factor_post if qty < 0 else factor_pre
                        else:
                            factor = factor_pre if qty < 0 else factor_post
                        break
                else:
                    factor = 1.0

                df_adj.at[idx, 'adj_factor'] = factor

        df_adj['Quantity_adj'] = df_adj['Quantity'] * df_adj['adj_factor']

        if splits:
            print(f"\n[+] {len(splits)} split(s) applied:")
            for s in sorted(splits, key=lambda x: (x['ticker'], x['fecha'])):
                print(f"   - {s['ticker']}: Ratio {s['ratio']:.2f}  ({s['fecha'].date()})")
        else:
            print("[+] No splits to apply.")
        return df_adj


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STOCK PORTFOLIO VALUATION    (notebook steps 4-5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calculate_stock_portfolio(df_ops, prices, fx_rates):
    """
    Returns
    -------
    valor_total_cartera : pd.Series  – daily total portfolio value (EUR)
    aporte_diario       : pd.Series  – cumulative net invested capital (EUR)
    valor_cartera       : pd.DataFrame – daily value per ticker (EUR)
    """
    df_ops = df_ops.copy()
    df_ops['Date'] = normalize_date_series(df_ops['Date'])
    prices = prices.copy()
    prices.index = normalize_date_series(prices.index)
    fx_rates = fx_rates.copy()
    fx_rates.index = normalize_date_series(fx_rates.index)

    all_days = prices.index  # full daily range from market_data

    # ── 1. Add FX rate & EUR-estimated price per operation ──────────────
    def _add_fx(df, fx):
        """Notebook: añadir_fx_rate()"""
        fx = fx.sort_index().ffill()
        fx_lookup = fx.copy()
        fx_lookup['Fecha'] = fx_lookup.index

        merged = pd.merge(df, fx_lookup, left_on='Date', right_on='Fecha', how='left')
        merged['fx_rate'] = merged.apply(
            lambda row: row.get(row['Coin'], np.nan) if pd.notna(row.get('Coin')) else np.nan,
            axis=1,
        )
        merged['EST_eur'] = merged['Price'] * merged['fx_rate']
        # Drop the added FX columns
        drop_cols = list(fx.columns) + ['Fecha']
        merged.drop(columns=[c for c in drop_cols if c in merged.columns], inplace=True)
        return merged

    df_ops = _add_fx(df_ops, fx_rates)

    # ── 2. Cumulative quantities ────────────────────────────────────────
    qty_col = 'Quantity_adj' if 'Quantity_adj' in df_ops.columns else 'Quantity'
    df_qty = df_ops.groupby(['Date', 'ticker'])[qty_col].sum().unstack(fill_value=0)
    df_qty = df_qty.reindex(all_days, fill_value=0).fillna(0)
    qty_acumulada = df_qty.cumsum()

    # ── 3. Prices in EUR ────────────────────────────────────────────────
    ticker_moneda = df_ops.drop_duplicates('ticker').set_index('ticker')['Coin']
    fx_al_ticker = pd.DataFrame(index=all_days)
    for ticker in prices.columns:
        moneda = ticker_moneda.get(ticker, 'EUR')
        if moneda in fx_rates.columns:
            fx_al_ticker[ticker] = fx_rates[moneda].reindex(all_days).ffill()
        else:
            fx_al_ticker[ticker] = 1.0

    precios_eur = prices * fx_al_ticker

    # ── 4. Valor de cartera ─────────────────────────────────────────────
    common = qty_acumulada.columns.intersection(precios_eur.columns)
    valor_cartera = (qty_acumulada[common] * precios_eur[common]).fillna(0)
    valor_total_cartera = valor_cartera.sum(axis=1)

    # ── 5. Capital aportado acumulado ───────────────────────────────────
    # Prefer broker cash flow (Value) for invested capital. We only use
    # qty*price*fx as fallback when Value is missing. Optionally, some custom
    # sources (e.g. SAP vest feeds) can request notebook-like fallback when
    # Value==0 via sources.json (zero_value_flow_from_est_eur_tickers).
    raw_qty = pd.to_numeric(df_ops['Quantity'], errors='coerce').fillna(0.0)
    qty_sign = raw_qty.apply(lambda q: 1.0 if q > 0 else (-1.0 if q < 0 else 0.0))

    value_eur = pd.to_numeric(df_ops.get('Value', np.nan), errors='coerce')
    flow_from_value = value_eur.abs() * qty_sign

    est_eur = pd.to_numeric(df_ops['EST_eur'], errors='coerce').fillna(0.0)
    flow_estimated_qty = raw_qty.abs() * est_eur * qty_sign
    flow_estimated_unit = est_eur * qty_sign

    df_ops['_flow_eur'] = flow_from_value.where(~value_eur.isna(), flow_estimated_qty)

    special_tickers = set(config.get_zero_value_flow_from_est_tickers())
    if special_tickers and 'ticker' in df_ops.columns:
        ticker_s = df_ops['ticker'].fillna('').astype(str).str.strip()
        zero_value_mask = value_eur.eq(0)
        special_mask = ticker_s.isin(special_tickers)
        use_unit_est_mask = zero_value_mask & special_mask
        if use_unit_est_mask.any():
            df_ops.loc[use_unit_est_mask, '_flow_eur'] = flow_estimated_unit[use_unit_est_mask]

    aporte_diario = (
        df_ops.groupby('Date')['_flow_eur']
        .sum()
        .reindex(all_days, fill_value=0)
        .cumsum()
    )
    df_ops.drop(columns=['_flow_eur'], inplace=True, errors='ignore')

    return valor_total_cartera, aporte_diario, valor_cartera


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CRYPTO PORTFOLIO VALUATION   (notebook steps 7-8)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calculate_crypto_portfolio(df_crypto, fx_rates):
    """
    Parameters
    ----------
    df_crypto : DataFrame  with Date, Coin, Quantity
    fx_rates  : DataFrame  with coins as columns (BTC, ETH…) and EUR→coin rates

    Returns
    -------
    valor_total_crypto          : Series  – daily total crypto value (EUR)
    aporte_crypto_eur_acumulado : Series  – cumulative cost basis (EUR)
    valor_crypto_eur            : DataFrame – value per coin (EUR)
    """
    if df_crypto is None or len(df_crypto) == 0:
        return None, None, None

    df_crypto = df_crypto.copy()
    df_crypto['Date_dt'] = pd.to_datetime(df_crypto['Date'], errors='coerce')
    df_crypto['Date_day'] = df_crypto['Date_dt'].dt.date
    df_crypto['Quantity'] = pd.to_numeric(df_crypto['Quantity'], errors='coerce')
    df_crypto = df_crypto.dropna(subset=['Quantity', 'Date_dt'])
    df_crypto = df_crypto.sort_values('Date_dt')

    coins = df_crypto['Coin'].dropna().unique().tolist()

    # Daily change per coin
    df_diario = df_crypto.groupby(['Date_day', 'Coin'])['Quantity'].sum().unstack(fill_value=0)
    all_days = pd.date_range(df_diario.index.min(), pd.Timestamp.today().normalize()).date
    df_diario = df_diario.reindex(all_days, fill_value=0)

    # Cumulative balance
    df_acumulado = df_diario.cumsum()
    df_acumulado.index = pd.to_datetime(df_acumulado.index)

    # Extend to today
    fecha_final = pd.Timestamp.today().normalize()
    fechas = pd.date_range(df_acumulado.index.min(), fecha_final, freq='D')
    df_acumulado = df_acumulado.reindex(fechas, method='ffill')

    # Align with FX rates
    fx_rates = fx_rates.copy()
    fx_rates.index = pd.to_datetime(fx_rates.index)
    common = df_acumulado.index.intersection(fx_rates.index)

    coins_available = [c for c in coins if c in df_acumulado.columns and c in fx_rates.columns]
    if not coins_available:
        return None, None, None

    df_acum_a = df_acumulado.loc[common, coins_available]
    df_fx_a   = fx_rates.loc[common, coins_available]

    # FX rates are EUR→coin  (from market_data); crypto coins like BTC-EUR
    # come back as coin→EUR already.  The notebook inverts them because its
    # rates are stored as  1/price  (EUR per coin).  Our market_data returns
    # the rate already as coin→EUR for crypto, so we just multiply directly.
    valor_crypto_eur = df_acum_a * df_fx_a
    valor_total_crypto = valor_crypto_eur.sum(axis=1)

    # ── Cost basis (capital aportado) ───────────────────────────────────
    # Notebook: for buys (Change > 0), EUR paid = Change / fx_rate_of_day
    # with notebook's fx_rate = EUR→coin, so EUR = Qty / rate.
    # Since our fx_rates are coin→EUR, EUR paid = Qty * rate.
    df_buys = df_crypto[df_crypto['Quantity'] > 0].copy()
    df_buys['Date_day_dt'] = pd.to_datetime(df_buys['Date_day'])

    fx_lookup = fx_rates.copy()
    fx_lookup['Date_day_dt'] = fx_lookup.index

    df_buys = df_buys.merge(fx_lookup, on='Date_day_dt', how='left', suffixes=('', '_fx'))

    def _get_rate(row):
        coin = row['Coin']
        return row.get(coin, np.nan)

    df_buys['fx_rate'] = df_buys.apply(_get_rate, axis=1)
    df_buys['EUR_pagado'] = df_buys['Quantity'] * df_buys['fx_rate']

    aporte = (
        df_buys.groupby('Date_day_dt')['EUR_pagado']
        .sum()
        .cumsum()
        .reindex(fechas, method='ffill')
        .fillna(0)
    )

    # Start the crypto series when investment actually begins (first positive buy).
    # This avoids showing a pre-investment flat segment in the dashboard chart.
    first_investment_date = aporte[aporte > 0].index.min() if not aporte.empty else None
    if pd.notna(first_investment_date):
        valor_total_crypto = valor_total_crypto.loc[valor_total_crypto.index >= first_investment_date]
        aporte = aporte.loc[aporte.index >= first_investment_date]
        valor_crypto_eur = valor_crypto_eur.loc[valor_crypto_eur.index >= first_investment_date]

    return valor_total_crypto, aporte, valor_crypto_eur


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TWR (Time-Weighted Return)   (notebook step 9)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def compute_twr(values: pd.Series, cum_contribs: pd.Series,
                flow_at='start', annualize=True):
    """
    Time-Weighted Return.

    Parameters
    ----------
    values       : daily portfolio value
    cum_contribs : cumulative contributions (invested capital)
    flow_at      : 'start', 'end' or 'auto' (cash-flow timing assumption)
                   - start: all flows at period start
                   - end: all flows at period end
                   - auto: positive flows at start, negative flows at end

    Returns
    -------
    (twr_total, twr_annual) as decimals (multiply ×100 for %).
    """
    vals = values.sort_index().astype(float).ffill()
    contrib = cum_contribs.reindex(vals.index).ffill().fillna(0.0)
    net = contrib.diff().fillna(contrib.iloc[0] if len(contrib) > 0 else 0.0)

    rets = []
    eps = 1e-12
    for i in range(1, len(vals)):
        V_prev = vals.iloc[i - 1]
        V_curr = vals.iloc[i]
        CF = net.iloc[i]

        numer = None
        if flow_at == 'start':
            denom = V_prev + CF
            numer = V_curr - V_prev - CF
        elif flow_at == 'end':
            denom = V_prev
            numer = V_curr - CF - V_prev
        elif flow_at == 'auto':
            # Robust hybrid for daily-close data with unknown intraday timing:
            # buys/contributions behave like start-of-day flows, while
            # withdrawals/sales behave like end-of-day flows.
            if CF >= 0:
                denom = V_prev + CF
                numer = V_curr - V_prev - CF
            else:
                denom = V_prev
                numer = V_curr - CF - V_prev
        else:
            raise ValueError("flow_at must be 'start', 'end' or 'auto'")

        # Skip days where the portfolio barely exists (avoids div-by-tiny)
        if abs(denom) < 1.0:
            continue

        r = numer / denom

        # Clamp extreme single-day returns to avoid chain-link blowups
        r = max(min(r, 5.0), -0.99)
        rets.append(r)

    if not rets:
        return 0.0, 0.0

    twr_total = np.prod([1 + r for r in rets]) - 1.0

    if annualize:
        days = (vals.index[-1] - vals.index[0]).days
        years = days / 365.25 if days > 0 else 1.0
        twr_annual = (1 + twr_total) ** (1 / years) - 1.0 if years > 0 else 0.0
    else:
        twr_annual = 0.0

    return twr_total, twr_annual


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BENCHMARK COMPARISON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def compute_benchmark_return(
    benchmark_ticker: str,
    start_date,
    end_date=None,
) -> tuple[pd.Series, float, float]:
    """
    Download benchmark price series and compute its total & annualised return
    over the same period as the portfolio.

    Returns
    -------
    price_series  : pd.Series  – daily close prices (normalised to 100 at start)
    total_return  : float      – decimal total return (e.g. 0.35 = +35%)
    annual_return : float      – annualised return (decimal)
    """
    if end_date is None:
        end_date = pd.Timestamp.today().normalize()

    start_date = _to_tznaive_safe(pd.Timestamp(start_date))
    end_date   = _to_tznaive_safe(pd.Timestamp(end_date))

    try:
        raw = yf.download(
            benchmark_ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=(end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if raw.empty:
            return pd.Series(dtype=float), 0.0, 0.0

        close = raw["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close.index = normalize_date_series(close.index)
        close = close.sort_index().ffill()

        # Reindex to full daily calendar
        all_days = pd.date_range(close.index.min(), end_date, freq="D")
        close = close.reindex(all_days).ffill()

        # Normalise to 100 at start
        start_val = close.iloc[0]
        if start_val == 0 or pd.isna(start_val):
            return pd.Series(dtype=float), 0.0, 0.0
        normalised = close / start_val * 100.0

        total_ret = (close.iloc[-1] / close.iloc[0]) - 1.0
        days = (close.index[-1] - close.index[0]).days
        years = days / 365.25 if days > 0 else 1.0
        annual_ret = (1 + total_ret) ** (1 / years) - 1.0 if years > 0 else 0.0

        return normalised, total_ret, annual_ret

    except Exception as e:
        print(f"[!] No se pudo descargar benchmark '{benchmark_ticker}': {e}")
        return pd.Series(dtype=float), 0.0, 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FAILED ASSETS SUMMARY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def summarize_failed_assets(df_failed_ops, df_failed_crypto, fx_rates):
    """
    Produce a summary DataFrame of assets (stocks and crypto) that could not be valued.
    Returns: DataFrame with ['Asset', 'Type', 'Quantity', 'Invested Capital (EUR)']
    """
    rows = []
    
    # ── 1. Stocks ────────────────────────────────────────────────────────
    if df_failed_ops is not None and not df_failed_ops.empty:
        df_ops = df_failed_ops.copy()
        
        # Calculate EST_eur for each operation to get invested capital
        df_ops['Date'] = normalize_date_series(df_ops['Date'])
        fx = fx_rates.copy()
        fx.index = normalize_date_series(fx.index)
        fx = fx.sort_index().ffill()
        
        fx_lookup = fx.copy()
        fx_lookup['Fecha'] = fx_lookup.index
        merged = pd.merge(df_ops, fx_lookup, left_on='Date', right_on='Fecha', how='left')
        merged['fx_rate'] = merged.apply(
            lambda row: row.get(row['Coin'], np.nan) if pd.notna(row.get('Coin')) else np.nan,
            axis=1,
        )
        merged['EST_eur'] = merged['Price'] * merged['fx_rate']
        
        qty_col = 'Quantity_adj' if 'Quantity_adj' in merged.columns else 'Quantity'
        merged['_qty_signed'] = merged[qty_col]
        
        # Invested capital logic (same as calculate_stock_portfolio)
        merged['_flow_eur'] = merged['_qty_signed'].abs() * merged['EST_eur']
        merged['_flow_eur'] = merged['_flow_eur'] * merged['_qty_signed'].apply(
            lambda q: 1.0 if q > 0 else (-1.0 if q < 0 else 0.0)
        )
        
        for ticker, group in merged.groupby('ticker'):
            qty = group['_qty_signed'].sum()
            invested = group['_flow_eur'].sum()
            if abs(qty) > 1e-6 or abs(invested) > 1e-2:
                rows.append({
                    'Asset': ticker,
                    'Type': 'Stock',
                    'Quantity': qty,
                    'Invested Capital (EUR)': invested
                })
                
    # ── 2. Crypto ────────────────────────────────────────────────────────
    if df_failed_crypto is not None and not df_failed_crypto.empty:
        df_cry = df_failed_crypto.copy()
        df_cry['Date_dt'] = pd.to_datetime(df_cry['Date'], errors='coerce')
        df_cry['Date_day'] = df_cry['Date_dt'].dt.date
        df_cry['Quantity'] = pd.to_numeric(df_cry['Quantity'], errors='coerce')
        
        # Calculate invested capital
        fx = fx_rates.copy()
        fx.index = pd.to_datetime(fx.index)
        fx_lookup = fx.copy()
        fx_lookup['Date_day_dt'] = fx_lookup.index
        
        df_buys = df_cry[df_cry['Quantity'] > 0].copy()
        if not df_buys.empty:
            df_buys['Date_day_dt'] = pd.to_datetime(df_buys['Date_day'])
            df_buys = df_buys.merge(fx_lookup, on='Date_day_dt', how='left')
            
            def _get_rate(row):
                coin = row['Coin']
                return row.get(coin, np.nan)
                
            df_buys['fx_rate'] = df_buys.apply(_get_rate, axis=1)
            df_buys['EUR_pagado'] = df_buys['Quantity'] * df_buys['fx_rate']
        
        for coin, group in df_cry.groupby('Coin'):
            qty = group['Quantity'].sum()
            
            invested_capital = 0.0
            if not df_buys.empty:
                invested_capital = df_buys[df_buys['Coin'] == coin]['EUR_pagado'].sum()
                
            if abs(qty) > 1e-8 or abs(invested_capital) > 1e-2:
                rows.append({
                    'Asset': coin,
                    'Type': 'Crypto',
                    'Quantity': qty,
                    'Invested Capital (EUR)': invested_capital
                })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────
#  Consolidated metrics  (mirrors notebook step 9)
# ─────────────────────────────────────────────────────────────────────────

def compute_metrics(valor_total_cartera, aporte_diario,
                     valor_total_crypto, aporte_crypto,
                     valor_crypto_eur) -> dict:
    m: dict = {}
    has_crypto = (valor_total_crypto is not None and not valor_total_crypto.empty)

    # ── Acciones ─────────────────────────────────────────────────────
    cap_acc = aporte_diario.iloc[-1]
    val_acc = valor_total_cartera.iloc[-1]
    pv_acc  = val_acc - cap_acc
    rent_acc = (pv_acc / cap_acc * 100) if cap_acc > 0 else 0

    dias_acc  = (valor_total_cartera.index[-1] - valor_total_cartera.index[0]).days
    anhos_acc = dias_acc / 365.25
    cagr_acc  = ((val_acc / cap_acc) ** (1 / anhos_acc) - 1) * 100 \
                if anhos_acc > 0 and cap_acc > 0 else 0

    # Use robust mixed timing for dashboard metrics:
    # contributions at start-of-day, withdrawals at end-of-day.
    twr_acc_t, twr_acc_a = compute_twr(valor_total_cartera, aporte_diario, flow_at='auto')
    m.update(
        capital_aportado_acciones=cap_acc,
        valor_actual_acciones=val_acc,
        plusvalia_acciones=pv_acc,
        rentabilidad_acciones=rent_acc,
        cagr_acciones=cagr_acc,
        twr_acciones_total=twr_acc_t * 100,
        twr_acciones_anual=twr_acc_a * 100,
    )

    # ── Crypto ───────────────────────────────────────────────────────
    cap_cry = val_cry = pv_cry = rent_cry = cagr_cry = 0.0
    twr_cry_t = twr_cry_a = 0.0
    dias_cry = anhos_cry = 0

    if has_crypto and aporte_crypto is not None:
        cap_cry = aporte_crypto.iloc[-1]
        val_cry = valor_total_crypto.iloc[-1]
        pv_cry  = val_cry - cap_cry
        rent_cry = (pv_cry / cap_cry * 100) if cap_cry > 0 else 0

        dias_cry  = (valor_total_crypto.index[-1] - valor_total_crypto.index[0]).days
        anhos_cry = dias_cry / 365.25
        cagr_cry  = ((val_cry / cap_cry) ** (1 / anhos_cry) - 1) * 100 \
                    if anhos_cry > 0 and cap_cry > 0 else 0

        twr_cry_t, twr_cry_a = compute_twr(valor_total_crypto, aporte_crypto, flow_at='auto')
        twr_cry_t *= 100; twr_cry_a *= 100

    m.update(
        capital_aportado_crypto=cap_cry,
        valor_actual_crypto=val_cry,
        plusvalia_crypto=pv_cry,
        rentabilidad_crypto=rent_cry,
        cagr_crypto=cagr_cry,
        twr_cripto_total=twr_cry_t,
        twr_cripto_anual=twr_cry_a,
    )

    # ── Totales combinados ───────────────────────────────────────────
    cap_tot = cap_acc + cap_cry
    val_tot = val_acc + val_cry
    pv_tot  = val_tot - cap_tot
    rent_tot = (pv_tot / cap_tot * 100) if cap_tot > 0 else 0

    dias_tot  = max(dias_acc, dias_cry) if has_crypto else dias_acc
    anhos_tot = dias_tot / 365.25
    cagr_tot  = ((val_tot / cap_tot) ** (1 / anhos_tot) - 1) * 100 \
                if anhos_tot > 0 and cap_tot > 0 else 0

    # TWR combinado
    if has_crypto:
        common_idx = valor_total_cartera.index.union(valor_total_crypto.index).sort_values()
        vc  = valor_total_cartera.reindex(common_idx).ffill().fillna(0)
        vcy = valor_total_crypto.reindex(common_idx).ffill().fillna(0)
        v_comb = vc + vcy
        a_acc  = aporte_diario.reindex(common_idx).ffill().fillna(0)
        a_cry  = aporte_crypto.reindex(common_idx).ffill().fillna(0)
        a_comb = a_acc + a_cry
        twr_tot_t, twr_tot_a = compute_twr(v_comb, a_comb, flow_at='auto')
    else:
        twr_tot_t, twr_tot_a = twr_acc_t, twr_acc_a

    peso_acc = (val_acc / val_tot * 100) if val_tot > 0 else 100
    peso_cry = (val_cry / val_tot * 100) if val_tot > 0 else 0

    m.update(
        capital_total=cap_tot,
        valor_total=val_tot,
        plusvalia_total=pv_tot,
        rentabilidad_total=rent_tot,
        cagr_total=cagr_tot,
        twr_total_total=twr_tot_t * 100,
        twr_total_anual=twr_tot_a * 100,
        peso_acciones=peso_acc,
        peso_crypto=peso_cry,
        dias_totales=dias_tot,
        anhos_totales=anhos_tot,
        fecha_actual=valor_total_cartera.index[-1].strftime('%Y-%m-%d'),
    )
    return m
