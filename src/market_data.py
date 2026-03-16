"""
market_data.py – Ticker resolution, price download and FX rates.

Uses yfinance exclusively (no Selenium/browser required).
"""

import time

import pandas as pd
import yfinance as yf

from . import config


# ─────────────────────────────────────────────────────────────────────────
# Ticker lookup  (ISIN → Yahoo symbol via yfinance Search)
# ─────────────────────────────────────────────────────────────────────────

def lookup_ticker_yfinance(isin: str) -> str | None:
    """Look up a single ISIN via yfinance Search API."""
    try:
        search = yf.Search(isin, max_results=5)
        if search.quotes:
            return search.quotes[0]['symbol']
    except Exception as e:
        print(f"  ⚠️ yfinance search error for {isin}: {e}")
    return None


def lookup_tickers_batch(isin_list: list[str]) -> dict[str, str]:
    """Resolve a batch of ISINs. Returns {isin: ticker}."""
    result: dict[str, str] = {}
    if not isin_list:
        return result

    print(f"  🔍 Resolving {len(isin_list)} ISIN(s) via yfinance...")
    for i, isin in enumerate(isin_list):
        ticker = lookup_ticker_yfinance(isin)
        if ticker:
            print(f"  ✅ {isin} → {ticker}")
            result[isin] = ticker
        else:
            print(f"  ❌ {isin} → not found")
        if i < len(isin_list) - 1:
            time.sleep(0.5)
    return result


def update_tickers_in_operations(df_ops: pd.DataFrame) -> pd.DataFrame:
    """
    Fill missing ticker column values.  Tries yfinance first, then
    prompts the user for manual input.
    """
    if 'ticker' not in df_ops.columns:
        df_ops['ticker'] = ''

    df_ops['ticker'] = df_ops['ticker'].fillna('').astype(str).str.strip()

    bad = df_ops['ticker'].isin(['', 'None', 'nan', 'Not found'])
    isin_missing = df_ops.loc[bad, 'ISIN'].dropna().unique().tolist()
    isin_missing = [i for i in isin_missing if i and str(i).strip()]

    if not isin_missing:
        print("✅ All ISINs already have a ticker.")
        return df_ops

    resolved = lookup_tickers_batch(isin_missing)

    for isin, ticker in resolved.items():
        df_ops.loc[df_ops['ISIN'] == isin, 'ticker'] = ticker

    # Check for still-missing
    still_bad = df_ops['ticker'].isin(['', 'None', 'nan', 'Not found'])
    still_missing = df_ops.loc[still_bad, 'ISIN'].dropna().unique().tolist()
    still_missing = [i for i in still_missing if i and str(i).strip()]

    if still_missing:
        print("\n⚠️  Some ISINs could not be resolved automatically.")
        print("Enter the Yahoo Finance ticker manually (press Enter to skip):")
        for isin in still_missing:
            product = df_ops.loc[df_ops['ISIN'] == isin, 'Product'].iloc[0]
            user = input(f"  👉 Ticker for {isin} ({product}): ").strip()
            if user:
                df_ops.loc[df_ops['ISIN'] == isin, 'ticker'] = user

    return df_ops


# ─────────────────────────────────────────────────────────────────────────
# Price download
# ─────────────────────────────────────────────────────────────────────────

def fetch_prices(tickers: list[str], start_date) -> pd.DataFrame:
    """Download historical Close prices and forward-fill to a daily grid."""
    end_date = pd.Timestamp.today()
    if not tickers:
        return pd.DataFrame()

    print(f"📥 Downloading prices for {len(tickers)} ticker(s)...")
    try:
        data = yf.download(tickers, start=start_date, end=end_date,
                           auto_adjust=False, progress=False)
    except Exception as e:
        print(f"❌ yfinance download error: {e}")
        return pd.DataFrame()

    if data.empty:
        return data

    data = data.ffill()

    # Extract Close if MultiIndex
    if isinstance(data.columns, pd.MultiIndex):
        if 'Close' in data.columns.get_level_values(0):
            data = data['Close']
        else:
            try:
                data = data.xs('Close', axis=1, level=0, drop_level=True)
            except Exception:
                pass

    # Reindex to full daily range
    all_days = pd.date_range(start=start_date, end=end_date)
    data = data.reindex(all_days).ffill()

    # Configurable price adjustments (from sources.json → price_adjustments)
    for ticker, divisor in config.get_price_adjustments().items():
        if ticker in data.columns:
            data[ticker] = data[ticker] / divisor
            print(f"   ✓ {ticker} price adjusted (÷{divisor:g})")

    return data


# ─────────────────────────────────────────────────────────────────────────
# FX rates
# ─────────────────────────────────────────────────────────────────────────

# Well-known FX mapping (extend as needed)
_FX_TICKER_MAP: dict[str, str] = {
    'USD': 'EURUSD=X',
    'GBX': 'EURGBP=X',
    'GBP': 'EURGBP=X',
    'CHF': 'EURCHF=X',
    'DKK': 'EURDKK=X',
    'PLN': 'EURPLN=X',
    'SEK': 'EURSEK=X',
    'NOK': 'EURNOK=X',
    'JPY': 'EURJPY=X',
    'CAD': 'EURCAD=X',
    'AUD': 'EURAUD=X',
}


def fetch_fx_rates(currencies, start_date, crypto_coins: list[str] | None = None) -> pd.DataFrame:
    """
    Download EUR conversion rates.

    For normal currencies the rate is inverted (EUR→X  →  X→EUR).
    For crypto coins (BTC, ETH …) the yfinance ticker XXX-EUR already
    gives us coin→EUR directly.

    Parameters
    ----------
    currencies   : iterable of currency codes found in operations
    crypto_coins : additional crypto coin names that need FX (BTC, ETH…)

    Returns
    -------
    DataFrame indexed by date, one column per currency, value = X→EUR.
    """
    end_date = pd.Timestamp.today()
    all_days = pd.date_range(start=start_date, end=end_date)

    # Build download list
    to_download: dict[str, str] = {}  # coin → yf ticker
    currencies = set(c for c in currencies if pd.notna(c) and str(c).strip()) - {'EUR'}

    for coin in currencies:
        coin = str(coin).strip().upper()
        if coin in _FX_TICKER_MAP:
            to_download[coin] = _FX_TICKER_MAP[coin]
        else:
            to_download[coin] = f"EUR{coin}=X"

    # Crypto coins
    if crypto_coins:
        for coin in crypto_coins:
            coin = coin.strip().upper()
            to_download[coin] = f"{coin}-EUR"

    fx: dict[str, pd.Series] = {}

    for coin, fx_ticker in to_download.items():
        try:
            d = yf.download(fx_ticker, start=start_date, end=end_date,
                            auto_adjust=True, progress=False)
            if d.empty:
                print(f"  ⚠️ Empty data for {coin} ({fx_ticker})")
                continue

            s = d['Close'].squeeze()

            if fx_ticker.endswith('-EUR'):
                # Already coin→EUR
                fx[coin] = s.reindex(all_days).ffill()
            else:
                # EUR→X  → invert to X→EUR
                fx[coin] = (1 / s).reindex(all_days).ffill()

        except Exception as e:
            print(f"  ❌ FX error for {coin} ({fx_ticker}): {e}")

    # Configurable FX adjustments (from sources.json → fx_adjustments)
    for currency, divisor in config.get_fx_adjustments().items():
        if currency in fx:
            fx[currency] = fx[currency] / divisor
            print(f"   ✓ {currency} FX adjusted (÷{divisor:g})")

    fx['EUR'] = pd.Series(1.0, index=all_days)

    return pd.DataFrame(fx).sort_index().ffill()
