"""
market_data.py – Ticker resolution, price download and FX rates.

Uses yfinance exclusively (no Selenium/browser required).
"""

import threading
import time

import pandas as pd
import yfinance as yf

from . import config

# Cache files are read/written from FastAPI's sync threadpool, so concurrent
# requests could interleave writes and produce header/value misalignment.
_CACHE_LOCK = threading.Lock()


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


def update_tickers_in_operations(df_ops: pd.DataFrame, interactive: bool = False) -> pd.DataFrame:
    """
    Fill missing ticker column values via yfinance.

    ``interactive=False`` (default, server use) never calls ``input()``: ISINs
    that cannot be resolved are only reported. The CLI passes
    ``interactive=True`` to additionally prompt for a manual ticker.
    """
    if 'ticker' not in df_ops.columns:
        df_ops['ticker'] = ''

    df_ops['ticker'] = df_ops['ticker'].fillna('').astype(str).str.strip()

    bad = df_ops['ticker'].isin(['', 'None', 'nan', 'Not found'])
    isin_missing = df_ops.loc[bad, 'ISIN'].dropna().unique().tolist()
    isin_missing = [i for i in isin_missing if i and str(i).strip()]

    if not isin_missing:
        print("[ok] All ISINs already have a ticker.")
        return df_ops

    resolved = lookup_tickers_batch(isin_missing)

    for isin, ticker in resolved.items():
        df_ops.loc[df_ops['ISIN'] == isin, 'ticker'] = ticker

    # Check for still-missing
    still_bad = df_ops['ticker'].isin(['', 'None', 'nan', 'Not found'])
    still_missing = df_ops.loc[still_bad, 'ISIN'].dropna().unique().tolist()
    still_missing = [i for i in still_missing if i and str(i).strip()]

    if still_missing:
        print("[!] Some ISINs could not be resolved automatically: "
              + ", ".join(str(i) for i in still_missing))
        if interactive:
            print("Enter the Yahoo Finance ticker manually (press Enter to skip):")
            for isin in still_missing:
                product = df_ops.loc[df_ops['ISIN'] == isin, 'Product'].iloc[0]
                user = input(f"  Ticker for {isin} ({product}): ").strip()
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
        with _CACHE_LOCK:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None


def _save_cache(df: pd.DataFrame, path: str, merge: bool = True) -> None:
    """Write a cache CSV atomically.

    With ``merge=True`` (default) the new frame is merged over what is on disk
    (``df.combine_first(prev)``): new non-NaN values win, but columns AND rows
    already cached are never dropped. Callers may request a subset of columns
    (e.g. /api/tax asks for FX without crypto coins) or a shorter date range;
    overwriting would evict history and force full re-downloads. Two concurrent
    writers used to interleave partial CSVs and misalign headers, hence the
    lock + tmp file + os.replace.

    ``merge=False`` writes ``df`` verbatim (used after truncating anomalous rows
    so they are not resurrected from disk).
    """
    import os
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with _CACHE_LOCK:
        out = df
        if merge:
            try:
                prev = pd.read_csv(path, index_col=0, parse_dates=True)
                prev.index = pd.to_datetime(prev.index)
            except Exception:
                prev = None
            if prev is not None and not prev.empty:
                out = df.combine_first(prev)
        out = out.sort_index()
        out = out.reindex(sorted(out.columns), axis=1)

        tmp = f"{path}.tmp"
        out.to_csv(tmp)
        os.replace(tmp, path)


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


def _truncate_fx_cache_at_anomaly(df: pd.DataFrame | None,
                                  max_ratio: float = 5.0) -> tuple[pd.DataFrame | None, bool]:
    """
    Cut the FX cache at the first day where any column jumps implausibly.

    A misaligned write (or a bad yfinance response) can shift values between
    columns, e.g. BTC suddenly holding 1.6 instead of 57000. No real FX or coin
    moves 5x in a day, so everything from that day on is dropped and will be
    re-downloaded.
    """
    if df is None or df.empty or len(df) < 2:
        return df, False

    num = df.apply(pd.to_numeric, errors='coerce').sort_index()
    prev = num.shift(1)
    ratio = (num / prev).abs()
    # prev<=0 gives inf/0 ratios that are not real jumps (e.g. a 0 placeholder).
    bad = (((ratio > max_ratio) | (ratio < 1 / max_ratio))
           & num.notna() & prev.notna() & (prev > 0))
    bad_days = num.index[bad.any(axis=1)]
    if len(bad_days) == 0:
        return df, False

    cut = bad_days.min()
    cols = [c for c in num.columns if bad.loc[cut, c]]
    print(f"  [!] FX cache anomaly on {cut.date()} ({', '.join(cols)}) - "
          f"discarding cached rows from that day onwards.")
    return df.loc[df.index < cut], True


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


_OVERLAP_DAYS = 3  # re-download this many days before the last cached day (M5)

# In-process memo so a ticker/column that cannot be refreshed (delisted, weekend,
# holiday, listed after start_date) is not re-downloaded on every request.
#   key: (cache_path, name, kind, day)  kind in {"extend", "backfill"}
_ATTEMPTED: set[tuple] = set()


def _daily(df: pd.DataFrame, all_days: pd.DatetimeIndex) -> pd.DataFrame:
    """Reindex to a daily calendar forward-filling from values BEFORE the first
    requested day too (so a weekend start_date still gets Friday's price)."""
    if df is None or df.empty:
        return df
    df = df[~df.index.duplicated(keep='last')].sort_index()
    return df.reindex(df.index.union(all_days)).ffill().reindex(all_days)


def _plan_downloads(cached: pd.DataFrame | None, names: list[str], start_ts: pd.Timestamp,
                    today: pd.Timestamp, force_refresh: bool,
                    path: str) -> dict[str, tuple[pd.Timestamp, str]]:
    """Decide, per ticker/column, from which day it must be (re)downloaded.

    Coverage is evaluated PER COLUMN (first/last *valid* value), never with the
    global ``cached.index.max()``: a column can be NaN on days another column
    already extended (A1), start later than ``start_date`` (M4), be entirely
    NaN (B6) or end on a partial/forward-filled day (M5 -> 3 day overlap).
    Returns {name: (download_start, kind)} with kind in full/backfill/extend;
    names absent from the dict are up to date. Callers must call
    ``_mark_done`` after a successful download of a backfill/extend entry.
    """
    plan: dict[str, tuple[pd.Timestamp, str]] = {}
    for name in names:
        if cached is None or name not in cached.columns or not cached[name].notna().any():
            plan[name] = (start_ts, "full")
            continue
        s = cached[name]
        first = pd.Timestamp(s.first_valid_index()).normalize()
        last = pd.Timestamp(s.last_valid_index()).normalize()

        if first > start_ts and (path, name, "backfill", today) not in _ATTEMPTED:
            plan[name] = (start_ts, "backfill")
            continue

        if not force_refresh:
            if last >= today:
                continue
            if (path, name, "extend", today) in _ATTEMPTED:
                continue
        plan[name] = (max(start_ts, last - pd.Timedelta(days=_OVERLAP_DAYS)), "extend")
    return plan


def _mark_done(path: str, name: str, kind: str, today: pd.Timestamp) -> None:
    if kind in ("backfill", "extend"):
        _ATTEMPTED.add((path, name, kind, today))


def fetch_prices(tickers: list[str], start_date,
                 force_refresh: bool = False) -> pd.DataFrame:
    """
    Download historical Close prices with incremental disk cache.

    Coverage is tracked per ticker (see ``_plan_downloads``): each ticker is
    re-downloaded from its own last valid day minus a small overlap, or from
    ``start_date`` when it is missing, all-NaN or starts later than requested.
    Rows forward-filled for the returned frame are never persisted as data.
    With force_refresh, the recent tail is re-downloaded even if cached.
    """
    today = pd.Timestamp.today().normalize()
    if not tickers:
        return pd.DataFrame()

    # Keep requested order while avoiding duplicate yfinance downloads.
    tickers = list(dict.fromkeys(tickers))
    start_ts = pd.Timestamp(start_date).normalize()
    all_days = pd.date_range(start=start_ts, end=today)
    cached = _load_cache(config.PRICES_CACHE_FILE)
    if cached is not None and cached.empty:
        cached = None

    def _extract_close(raw: pd.DataFrame, requested: list[str]) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame()

        # NOTE: no ffill here - NaN days (exchange holidays) must not be
        # persisted as if they were real quotes.
        out = raw
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

    plan = _plan_downloads(cached, tickers, start_ts, today, force_refresh,
                           config.PRICES_CACHE_FILE)

    if not plan:
        print(f"[+] Prices loaded from cache ({len(tickers)} ticker(s)).")
        data = _daily(cached, all_days)[tickers]
        return _apply_price_adjustments(data)

    # Batch tickers that share the same download start.
    by_start: dict[pd.Timestamp, list[str]] = {}
    for t, (dl_start, _kind) in plan.items():
        by_start.setdefault(dl_start, []).append(t)

    new_frames = []
    for dl_start, group in by_start.items():
        frame = _download_close(group, dl_start)
        if not frame.empty:
            new_frames.append(frame)
            for t in frame.columns:
                if t in plan and frame[t].notna().any():
                    _mark_done(config.PRICES_CACHE_FILE, t, plan[t][1], today)

    new_data = pd.concat(new_frames, axis=1) if new_frames else pd.DataFrame()

    # Merge with cache: freshly downloaded values win, the rest of history stays.
    if cached is not None and not new_data.empty:
        data = new_data.combine_first(cached).sort_index()
    elif not new_data.empty:
        data = new_data
    else:
        data = cached if cached is not None else pd.DataFrame()

    if not new_data.empty:
        _save_cache(data, config.PRICES_CACHE_FILE)

    if data is None or data.empty:
        return pd.DataFrame()

    data = _daily(data, all_days)

    # Configurable price adjustments (from sources.json -> price_adjustments).
    # Applied here AND on the cache-hit early return via the same helper.
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
                   force_refresh: bool = False) -> pd.DataFrame:
    """
    Download EUR conversion rates.

    For normal currencies the rate is inverted (EUR->X  ->  X->EUR).
    For crypto coins (BTC, ETH ...) the yfinance ticker XXX-EUR already
    gives us coin->EUR directly.

    The disk cache is shared by every caller (some ask for crypto coins, some
    don't), so columns can have uneven coverage. Coverage is therefore judged
    PER COLUMN (first/last valid value) and only the missing stretch of each
    column is downloaded (3 day overlap); the cache is merged on save, never
    shrinking columns or dropping history.

    Parameters
    ----------
    currencies   : iterable of currency codes found in operations
    crypto_coins : additional crypto coin names that need FX (BTC, ETH...)

    Returns
    -------
    DataFrame indexed by date, one column per requested currency (+ EUR),
    value = X->EUR. Requested columns that could not be obtained are omitted.
    """
    today    = pd.Timestamp.today().normalize()
    start_ts = pd.Timestamp(start_date).normalize()
    all_days = pd.date_range(start=start_ts, end=today)

    # Build required coin set
    to_download: dict[str, str] = {}  # coin -> yf ticker
    req_currencies = set(c for c in currencies if pd.notna(c) and str(c).strip()) - {'EUR'}
    for coin in req_currencies:
        coin = str(coin).strip().upper()
        to_download[coin] = _FX_TICKER_MAP.get(coin, f"EUR{coin}=X")
    if crypto_coins:
        for coin in crypto_coins:
            coin = coin.strip().upper()
            to_download[coin] = f"{coin}-EUR"

    required_cols = list(to_download.keys())

    # Check cache
    cached = _load_cache(config.FX_CACHE_FILE)
    cached, cache_fixed = _normalize_legacy_fx_cache(cached)
    cached, cache_cut = _truncate_fx_cache_at_anomaly(cached)
    cache_fixed = cache_fixed or cache_cut
    if cache_fixed and cached is not None:
        # Rewrite as-is (merge=False): truncated rows must not be resurrected.
        _save_cache(cached, config.FX_CACHE_FILE, merge=False)
    if cached is not None and cached.empty:
        cached = None
    if cached is not None:
        cached = cached[~cached.index.duplicated(keep='last')].sort_index()

    plan = _plan_downloads(cached, required_cols, start_ts, today, force_refresh,
                           config.FX_CACHE_FILE)

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
            s = s.dropna()
            if s.empty:
                return None
            s = s[~s.index.duplicated(keep='last')]
            if fx_ticker.endswith('-EUR'):
                return s
            return 1 / s
        except Exception as e:
            print(f"  [x] FX error for {coin} ({fx_ticker}): {e}")
            return None

    updates: dict[str, pd.Series] = {}
    for coin, (dl_start, kind) in plan.items():
        s = _download_coin(coin, to_download[coin], dl_start)
        if s is None:
            continue
        _mark_done(config.FX_CACHE_FILE, coin, kind, today)
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        if cached is not None and coin in cached.columns:
            s = s.combine_first(cached[coin])  # new values win; history preserved
        updates[coin] = s.sort_index()

    if updates:
        # RAW rates, NOT forward-filled: filled rows must not become cached data.
        # Persisting merges with whatever is on disk (other columns/rows kept).
        _save_cache(pd.DataFrame(updates).sort_index(), config.FX_CACHE_FILE)

    # Raw (un-adjusted) view of every required column we have any data for.
    raw_cols: dict[str, pd.Series] = {}
    for coin in required_cols:
        if coin in updates:
            raw_cols[coin] = updates[coin]
        elif cached is not None and coin in cached.columns and cached[coin].notna().any():
            raw_cols[coin] = cached[coin]

    if raw_cols:
        raw_df = pd.DataFrame(raw_cols).sort_index()
        result_raw = _daily(raw_df, all_days)
    else:
        result_raw = pd.DataFrame(index=all_days)
    result_raw['EUR'] = 1.0

    if cached is not None and not plan:
        print(f"[+] FX rates loaded from cache (up to {cached.index.max().date()}).")
    return _stabilize_gbx_rates(_apply_fx_adjustments(result_raw))
