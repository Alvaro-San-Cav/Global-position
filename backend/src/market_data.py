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
        print(f"  [!] yfinance search error for {isin}: {e}")
    return None


def lookup_tickers_batch(isin_list: list[str]) -> dict[str, str]:
    """Resolve a batch of ISINs. Returns {isin: ticker}."""
    result: dict[str, str] = {}
    if not isin_list:
        return result

    print(f"  [*] Resolving {len(isin_list)} ISIN(s) via yfinance...")
    for i, isin in enumerate(isin_list):
        ticker = lookup_ticker_yfinance(isin)
        if ticker:
            print(f"  [+] {isin} -> {ticker}")
            result[isin] = ticker
        else:
            print(f"  [-] {isin} -> not found")
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

def _load_cache(path: str) -> pd.DataFrame | None:
    """Load a price/FX cache CSV; return None if it doesn't exist or is unreadable."""
    import os
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None


def _save_cache(df: pd.DataFrame, path: str) -> None:
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path)


def _apply_price_adjustments(data: pd.DataFrame) -> pd.DataFrame:
    """Apply sources.json price_adjustments (divisors) to a price frame.

    Prices are cached RAW (unadjusted), so the divisors (e.g. PSH.L /100 for
    pence, NEPTF /1000) must be applied on EVERY return path — both the fresh
    download and the cache-hit early returns — or cached runs would report
    prices orders of magnitude too large.
    """
    if data is None or data.empty:
        return data
    data = data.copy()
    for ticker, divisor in config.get_price_adjustments().items():
        if ticker in data.columns and divisor:
            data[ticker] = data[ticker] / divisor
    return data


def _normalize_legacy_fx_cache(df: pd.DataFrame | None) -> tuple[pd.DataFrame | None, bool]:
    """
    Normalize legacy FX cache values that may have been saved already adjusted.

    Legacy versions persisted GBX values after dividing by 100. In some refresh
    paths this happened multiple times, shrinking GBX orders of magnitude and
    causing GBX-denominated assets to look almost zero.
    """
    if df is None or df.empty:
        return df, False

    fixed = False
    out = df

    if 'GBX' in out.columns:
        s = pd.to_numeric(out['GBX'], errors='coerce').dropna()
        if not s.empty:
            med = float(s.median())
            # Raw EUR->GBP inverted rates are around ~1; GBX must be derived later
            # with /100. If cache median is tiny, it is likely legacy adjusted data.
            if med > 0:
                out = out.copy()
                for _ in range(6):
                    if med >= 0.2:
                        break
                    out['GBX'] = out['GBX'] * 100.0
                    med *= 100.0
                    fixed = True

    return out, fixed


def _apply_fx_adjustments(df: pd.DataFrame) -> pd.DataFrame:
    """Apply configured FX divisors to a copy of the raw FX dataframe."""
    out = df.copy()
    for currency, divisor in config.get_fx_adjustments().items():
        if currency in out.columns:
            out[currency] = out[currency] / divisor
            print(f"   [ok] {currency} FX adjusted (/{divisor:g})")
    return out


def _stabilize_gbx_rates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep GBX->EUR rates in a plausible scale band.

    Depending on historic cache and config changes, GBX can end up scaled as GBP
    (x100 too large) or repeatedly adjusted (x100^n too small). We normalize it
    to a stable band to avoid valuation jumps of exactly 100x.
    """
    if 'GBX' not in df.columns:
        return df

    s = pd.to_numeric(df['GBX'], errors='coerce').dropna()
    if s.empty:
        return df

    med = float(s.median())
    out = df.copy()
    changed = False

    # Typical GBX->EUR is around ~0.01 (pence to EUR). Keep within broad band.
    for _ in range(6):
        if med > 0.2:
            out['GBX'] = out['GBX'] / 100.0
            med /= 100.0
            changed = True
            continue
        if 0 < med < 0.0002:
            out['GBX'] = out['GBX'] * 100.0
            med *= 100.0
            changed = True
            continue
        break

    if changed:
        print("   [ok] GBX FX stabilized to expected scale")
    return out


def fetch_prices(tickers: list[str], start_date) -> pd.DataFrame:
    """
    Download historical Close prices with incremental disk cache.

    If a cache exists that already covers today, only missing tickers are
    downloaded. Otherwise, only the missing date range is fetched and merged.
    """
    today = pd.Timestamp.today().normalize()
    if not tickers:
        return pd.DataFrame()

    # Keep requested order while avoiding duplicate yfinance downloads.
    tickers = list(dict.fromkeys(tickers))
    all_days = pd.date_range(start=start_date, end=today)
    cached = _load_cache(config.PRICES_CACHE_FILE)

    # Determine what needs downloading.
    missing_tickers = tickers
    existing_tickers: list[str] = []
    from_date = start_date

    def _extract_close(raw: pd.DataFrame, requested: list[str]) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame()

        out = raw.ffill()
        if isinstance(out.columns, pd.MultiIndex):
            if 'Close' in out.columns.get_level_values(0):
                out = out['Close']
            else:
                try:
                    out = out.xs('Close', axis=1, level=0, drop_level=True)
                except Exception:
                    pass
        elif 'Close' in out.columns and len(requested) == 1:
            out = out[['Close']].rename(columns={'Close': requested[0]})

        if isinstance(out, pd.Series):
            name = requested[0] if requested else out.name
            out = out.to_frame(name=name)

        keep = [t for t in requested if t in out.columns]
        return out[keep] if keep else pd.DataFrame()

    def _download_close(requested: list[str], dl_start) -> pd.DataFrame:
        if not requested:
            return pd.DataFrame()
        print(f"[*] Downloading prices for {len(requested)} ticker(s) from {pd.Timestamp(dl_start).date()}...")
        try:
            raw = yf.download(
                requested,
                start=dl_start,
                end=today + pd.Timedelta(days=1),
                auto_adjust=False,
                progress=False,
            )
        except Exception as e:
            print(f"[-] yfinance download error: {e}")
            return pd.DataFrame()
        return _extract_close(raw, requested)

    if cached is not None and not cached.empty:
        existing_tickers = [t for t in tickers if t in cached.columns]
        missing_tickers = [t for t in tickers if t not in cached.columns]
        last_cached_day = cached.index.max().normalize()

        if last_cached_day >= today and not missing_tickers:
            print(f"[+] Prices loaded from cache ({len(tickers)} ticker(s), up to {last_cached_day.date()}).")
            data = cached.reindex(all_days).ffill()[tickers]
            return _apply_price_adjustments(data)

        # Existing tickers can stay incremental; missing ones need full history.
        if existing_tickers and last_cached_day >= pd.Timestamp(start_date):
            from_date = last_cached_day + pd.Timedelta(days=1)

    if pd.Timestamp(from_date) > today and not missing_tickers:
        print(f"[+] Prices fully cached for today ({today.date()}).")
        if cached is not None:
            data = cached.reindex(all_days).ffill()[[t for t in tickers if t in cached.columns]]
            return _apply_price_adjustments(data)
        return pd.DataFrame()

    new_frames = []
    if existing_tickers and pd.Timestamp(from_date) <= today:
        extended = _download_close(existing_tickers, from_date)
        if not extended.empty:
            new_frames.append(extended)

    if missing_tickers:
        backfilled = _download_close(missing_tickers, start_date)
        if not backfilled.empty:
            new_frames.append(backfilled)

    new_data = pd.concat(new_frames, axis=1) if new_frames else pd.DataFrame()

    # Merge with cache
    if cached is not None and not cached.empty and not new_data.empty:
        data = new_data.combine_first(cached).sort_index()
    elif not new_data.empty:
        data = new_data
    else:
        data = cached if cached is not None else pd.DataFrame()

    if not data.empty:
        _save_cache(data, config.PRICES_CACHE_FILE)

    data = data.reindex(all_days).ffill()

    # Configurable price adjustments (from sources.json → price_adjustments).
    # Applied here AND on the cache-hit early returns above via the same helper.
    data = _apply_price_adjustments(data)

    return data[[t for t in tickers if t in data.columns]]


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


def fetch_fx_rates(currencies, start_date, crypto_coins: list[str] | None = None,  # noqa: E501
                   ) -> pd.DataFrame:
    """
    Download EUR conversion rates.

    For normal currencies the rate is inverted (EUR→X  →  X→EUR).
    For crypto coins (BTC, ETH ...) the yfinance ticker XXX-EUR already
    gives us coin→EUR directly.

    Parameters
    ----------
    currencies   : iterable of currency codes found in operations
    crypto_coins : additional crypto coin names that need FX (BTC, ETH...)

    Returns
    -------
    DataFrame indexed by date, one column per currency, value = X→EUR.
    """
    today    = pd.Timestamp.today().normalize()
    all_days = pd.date_range(start=start_date, end=today)

    # Build required coin set
    to_download: dict[str, str] = {}  # coin → yf ticker
    req_currencies = set(c for c in currencies if pd.notna(c) and str(c).strip()) - {'EUR'}
    for coin in req_currencies:
        coin = str(coin).strip().upper()
        to_download[coin] = _FX_TICKER_MAP.get(coin, f"EUR{coin}=X")
    if crypto_coins:
        for coin in crypto_coins:
            coin = coin.strip().upper()
            to_download[coin] = f"{coin}-EUR"

    required_cols = set(to_download.keys())

    # Check cache
    cached = _load_cache(config.FX_CACHE_FILE)
    cached, cache_fixed = _normalize_legacy_fx_cache(cached)
    if cache_fixed and cached is not None:
        _save_cache(cached, config.FX_CACHE_FILE)
    if cached is not None and not cached.empty:
        last_cached_day = cached.index.max().normalize()
        cols_cached = set(cached.columns)
        if last_cached_day >= today and required_cols.issubset(cols_cached):
            print(f"[+] FX rates loaded from cache (up to {last_cached_day.date()}).")
            result_raw = cached.reindex(all_days).ffill()
            result_raw['EUR'] = 1.0
            return _stabilize_gbx_rates(_apply_fx_adjustments(result_raw))

        # Only download what's missing
        from_date = last_cached_day + pd.Timedelta(days=1) if last_cached_day >= pd.Timestamp(start_date) else start_date
        missing_coins = {c: v for c, v in to_download.items() if c not in cols_cached}
        # For existing coins only extend date range
        extend_coins  = {c: v for c, v in to_download.items() if c in cols_cached}
    else:
        cached = None
        from_date = start_date
        missing_coins = to_download
        extend_coins  = {}

    fx: dict[str, pd.Series] = {}

    def _download_coin(coin, fx_ticker, dl_start):
        try:
            d = yf.download(fx_ticker, start=dl_start, end=today + pd.Timedelta(days=1),
                            auto_adjust=True, progress=False)
            if d.empty:
                print(f"  [!] Empty data for {coin} ({fx_ticker})")
                return None
            s = d['Close']
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            if not isinstance(s, pd.Series):
                s = pd.Series([s], index=d.index[-1:])
            if fx_ticker.endswith('-EUR'):
                return s
            return 1 / s
        except Exception as e:
            print(f"  [x] FX error for {coin} ({fx_ticker}): {e}")
            return None

    # Download new coins from full start
    for coin, fx_ticker in missing_coins.items():
        s = _download_coin(coin, fx_ticker, start_date)
        if s is not None:
            fx[coin] = s.reindex(all_days).ffill()

    # Extend existing coins
    if extend_coins and pd.Timestamp(from_date) <= today:
        for coin, fx_ticker in extend_coins.items():
            s = _download_coin(coin, fx_ticker, from_date)
            if s is not None and cached is not None and coin in cached.columns:
                merged = pd.concat([cached[coin], s])
                merged = merged[~merged.index.duplicated(keep='last')].sort_index()
                fx[coin] = merged.reindex(all_days).ffill()
            elif cached is not None and coin in cached.columns:
                fx[coin] = cached[coin].reindex(all_days).ffill()

    # Merge with cache for already-known coins not re-downloaded
    if cached is not None:
        for col in cached.columns:
            if col not in fx and col in required_cols:
                fx[col] = cached[col].reindex(all_days).ffill()

    fx['EUR'] = pd.Series(1.0, index=all_days)

    result_raw = pd.DataFrame(fx).sort_index().ffill()
    # Persist RAW rates in cache; adjustments are only applied in-memory.
    _save_cache(result_raw.drop(columns=['EUR'], errors='ignore'), config.FX_CACHE_FILE)
    return _stabilize_gbx_rates(_apply_fx_adjustments(result_raw))
