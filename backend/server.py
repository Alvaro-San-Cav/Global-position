"""
Global Position – FastAPI Web Server

Usage:
    python server.py
    uvicorn server:app --reload --port 8000
"""

import fnmatch
import json
import logging
import os
import sys
import tempfile
import threading
import time
import traceback
import re
from datetime import datetime

# Ensure UTF-8 output on Windows (avoids emoji UnicodeEncodeError in print statements)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import glob

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import cash as cash_store
from src import config, core, lifedeck, lifedeck_auto, loaders, market_data, tax
from src import target as target_engine
from src.api_models import (
    AssetClassesResponse,
    CashResponse,
    CashUpdate,
    RebalanceResponse,
    TargetConfig,
    CryptoOperationCreate,
    DashboardResponse,
    OkResponse,
    Operation,
    OperationCreate,
    CryptoOperation,
    MutationResult,
    ProcessCommit,
    ProcessPreview,
    ProcessResult,
    ReportResult,
    SourceData,
    SourcesPayload,
    SourceFileContent,
    SourceFileInfo,
    TaxResponse,
    UploadResponse,
)

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Build the dashboard with fresh market data as soon as the server starts,
    so the app opens with up-to-date values without pressing 'Actualizar'."""
    def _warm():
        try:
            _get_dashboard(refresh=True)
            print("[+] Dashboard warm-up completed.")
        except Exception as e:
            print(f"[-] Dashboard warm-up failed: {e}")
    threading.Thread(target=_warm, daemon=True, name="dashboard-warmup").start()
    yield


app = FastAPI(
    title="Global Position",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frontend build output (served in production): frontend/dist. If it has not
# been built yet, fall back to the legacy web/ folder at the repo root.
WEB_DIR = os.path.join(config.BASE_DIR, "frontend", "dist")
if not os.path.isdir(WEB_DIR):
    WEB_DIR = os.path.join(config.BASE_DIR, "web")

# ─────────────────────────────────────────────────────────────────────────
#  Errors: log the detail, never leak internal paths/exceptions to the client
# ─────────────────────────────────────────────────────────────────────────

_log = logging.getLogger("globalpos.server")
GENERIC_ERROR = "Error interno del servidor. Consulta processing/ingesta.log para más detalle."


def _log_exception(e: BaseException, ctx: str = "") -> None:
    _log.exception("Unhandled error %s: %s", ctx, e)
    try:
        config.get_logger().error(f"server error {ctx}: {type(e).__name__}: {e}")
    except Exception:
        pass


def _internal_error(e: BaseException, ctx: str = "") -> HTTPException:
    """Log `e` and return a generic 500 (use as `raise _internal_error(e)`)."""
    _log_exception(e, ctx)
    return HTTPException(500, GENERIC_ERROR)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    _log_exception(exc, f"{request.method} {request.url.path}")
    return JSONResponse({"detail": GENERIC_ERROR, "error": GENERIC_ERROR}, status_code=500)


# ─────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────

def _clean(val):
    """Make a single value JSON-safe (no NaN/Inf)."""
    if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
        return None
    if isinstance(val, float):
        return round(val, 4)
    return val


def _clean_dict(d: dict) -> dict:
    return {k: _clean(v) for k, v in d.items()}


def _series_to_xy(s: pd.Series) -> list[dict]:
    """Date-indexed Series → [{x: 'YYYY-MM-DD', y: float}, ...]"""
    out = []
    for idx, val in s.items():
        if pd.isna(val):
            continue
        out.append({
            "x": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
            "y": round(float(val), 2),
        })
    return out


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    return df.where(pd.notna(df), None).to_dict(orient="records")


def _combine_series(a: pd.Series, b: pd.Series | None = None) -> pd.Series:
    """Align two date series and sum them (with forward-fill)."""
    if b is None or b.empty:
        return a.sort_index().copy()
    idx = a.index.union(b.index).sort_values()
    aa = a.reindex(idx).ffill().fillna(0.0)
    bb = b.reindex(idx).ffill().fillna(0.0)
    return aa + bb


def _benchmark_with_flows(bm_index: pd.Series, cum_flows: pd.Series) -> pd.Series:
    """
    Project benchmark value by applying the same net cash-flows as the portfolio.

    bm_index must be a positive benchmark level series (e.g. normalized to 100).
    cum_flows is cumulative invested capital in EUR.
    """
    if bm_index is None or bm_index.empty or cum_flows is None or cum_flows.empty:
        return pd.Series(dtype=float)

    px = bm_index.sort_index().astype(float).replace(0, np.nan).ffill().dropna()
    if px.empty:
        return pd.Series(dtype=float)

    idx = px.index.union(cum_flows.index).sort_values()
    px = px.reindex(idx).ffill()
    contrib = cum_flows.reindex(idx).ffill().fillna(0.0)
    net = contrib.diff().fillna(contrib.iloc[0] if len(contrib) > 0 else 0.0)

    vals = []
    prev_px = None
    val = 0.0
    for ts in idx:
        p = float(px.loc[ts])
        if not np.isfinite(p) or p <= 0:
            vals.append(np.nan)
            continue

        if prev_px is not None and np.isfinite(prev_px) and prev_px > 0:
            val = val * (p / prev_px)

        val += float(net.loc[ts])
        prev_px = p
        vals.append(val)

    out = pd.Series(vals, index=idx).ffill()
    return out.reindex(cum_flows.index).ffill()


def _resolve_tickers_silent(df: pd.DataFrame) -> pd.DataFrame:
    if "ticker" not in df.columns:
        df["ticker"] = ""
    df["ticker"] = df["ticker"].fillna("").astype(str).str.strip()
    bad = df["ticker"].isin(["", "None", "nan", "Not found"])
    isin_missing = df.loc[bad, "ISIN"].dropna().unique().tolist()
    isin_missing = [i for i in isin_missing if i and str(i).strip()]
    if isin_missing:
        resolved = market_data.lookup_tickers_batch(isin_missing)
        for isin, ticker in resolved.items():
            df.loc[df["ISIN"] == isin, "ticker"] = ticker
    return df


# ─────────────────────────────────────────────────────────────────────────
#  Dashboard cache
# ─────────────────────────────────────────────────────────────────────────

_dashboard_cache: dict = {}
_dashboard_cache_day: str = ""       # YYYY-MM-DD of the build; stale on day change
_dashboard_lock = threading.Lock()   # single builder; GETs wait for the result
_cache_state_lock = threading.Lock() # guards cache dict/day/version (very short holds)
_cache_version: int = 0              # bumped on every invalidation


def _invalidate_dashboard() -> None:
    """Drop the cached dashboard. Bumps the version so a build that started
    BEFORE this call (with now-stale data) will not be stored when it ends."""
    global _dashboard_cache, _dashboard_cache_day, _cache_version
    with _cache_state_lock:
        _cache_version += 1
        _dashboard_cache = {}
        _dashboard_cache_day = ""


def _get_dashboard(refresh: bool = False) -> dict:
    """Return the cached dashboard, rebuilding when empty, on explicit refresh,
    or when the cache was built on a previous day (long-lived hidden server).

    Results containing "error" are never cached. If a *refresh* build fails
    (e.g. yfinance down) the previous cached dashboard is kept and returned."""
    global _dashboard_cache, _dashboard_cache_day
    today = pd.Timestamp.today().strftime("%Y-%m-%d")

    def _snapshot():
        with _cache_state_lock:
            return _dashboard_cache, _dashboard_cache_day, _cache_version

    cached, cday, _ = _snapshot()
    if cached and not refresh and cday == today:
        return cached
    with _dashboard_lock:
        # Re-check: another thread may have rebuilt while we waited.
        cached, cday, version = _snapshot()
        if cached and not refresh and cday == today:
            return cached
        try:
            result = _build_dashboard(force_refresh=refresh)
        except Exception:
            if cached:
                _log.exception("Dashboard rebuild failed; serving previous cache")
                return cached
            raise
        if "error" in result:
            # Don't cache errors; on refresh keep whatever good result we had.
            return cached if (refresh and cached) else result
        with _cache_state_lock:
            if version == _cache_version:        # nothing invalidated meanwhile
                _dashboard_cache = result
                _dashboard_cache_day = today
        # Fresh build → push the net-worth summary to LifeDeck (no-op unless enabled; never blocks).
        try:
            lifedeck.push_in_background(result)
        except Exception:
            _log.exception("LifeDeck push scheduling failed")
        return result


def _build_dashboard(force_refresh: bool = False) -> dict:
    df_ops = loaders.load_operations()
    if df_ops.empty:
        return {"error": "No hay operaciones en processing/operaciones.csv"}

    df_merged = loaders.merge_custom_stock_sources(df_ops.copy())
    df_merged = _resolve_tickers_silent(df_merged)

    tickers = [t for t in df_merged["ticker"].dropna().unique() if t and str(t).strip()]
    currencies = df_merged["Coin"].dropna().unique().tolist()

    # Cash balances (per currency); ensure their FX is fetched too.
    cash_balances = cash_store.load_cash()
    for cur in cash_balances:
        if cur not in currencies and cur != "EUR":
            currencies.append(cur)

    df_crypto = loaders.load_crypto_operations()
    has_crypto = df_crypto is not None and len(df_crypto) > 0
    crypto_coins = df_crypto["Coin"].dropna().unique().tolist() if has_crypto else []

    start_date = df_merged["Date"].min()
    if has_crypto:
        # Crypto bought before the first stock still needs FX/benchmark history.
        crypto_min = pd.to_datetime(df_crypto["Date"], errors="coerce").min()
        if pd.notna(crypto_min) and (pd.isna(start_date) or crypto_min < start_date):
            start_date = crypto_min
    prices   = market_data.fetch_prices(tickers, start_date,
                                        force_refresh=force_refresh)
    fx_rates = market_data.fetch_fx_rates(currencies, start_date,
                                          crypto_coins=crypto_coins or None,
                                          force_refresh=force_refresh)

    # Exclude failed tickers
    failed_tickers = [t for t in tickers if t not in prices.columns] if not prices.empty else tickers
    if failed_tickers:
        df_merged = df_merged[~df_merged["ticker"].isin(failed_tickers)].copy()

    df_adj = core.SplitManager.apply_splits(df_merged)
    vtc, ad, vc = core.calculate_stock_portfolio(df_adj, prices, fx_rates)

    # Prefer displaying human-readable product names instead of raw tickers.
    ticker_name_map: dict[str, str] = {}
    if {"ticker", "Product", "Date"}.issubset(df_merged.columns):
        dn = df_merged[["ticker", "Product", "Date"]].copy()
        dn["ticker"] = dn["ticker"].fillna("").astype(str).str.strip()
        dn["Product"] = dn["Product"].fillna("").astype(str).str.strip()
        dn = dn[(dn["ticker"] != "") & (dn["Product"] != "")]
        if not dn.empty:
            dn = dn.sort_values("Date", ascending=False, kind="mergesort")
            ticker_name_map = dn.drop_duplicates("ticker").set_index("ticker")["Product"].to_dict()

    def _asset_display_name(symbol: str) -> str:
        s = str(symbol)
        return ticker_name_map.get(s, s)

    vtc_crypto = aporte_crypto = vc_eur = None
    if has_crypto:
        vtc_crypto, aporte_crypto, vc_eur = core.calculate_crypto_portfolio(df_crypto, fx_rates)
        if vtc_crypto is None or vtc_crypto.empty:
            has_crypto = False

    # Main chart should represent the full portfolio (stocks + crypto)
    if has_crypto and vtc_crypto is not None and aporte_crypto is not None:
        vtc_total = _combine_series(vtc, vtc_crypto)
        ad_total = _combine_series(ad, aporte_crypto)
    else:
        vtc_total = vtc
        ad_total = ad

    metrics = core.compute_metrics(
        vtc, ad,
        vtc_crypto if has_crypto else None,
        aporte_crypto if has_crypto else None,
        vc_eur if has_crypto else None,
    )

    # Benchmark
    bm_xy = None
    bm_ticker, bm_name = config.get_benchmark()
    if bm_ticker:
        bm_series, bm_total, bm_annual = core.compute_benchmark_return(bm_ticker, start_date=start_date)
        if bm_series is not None and not bm_series.empty:
            metrics["benchmark_ticker"] = bm_ticker
            metrics["benchmark_name"]   = bm_name
            metrics["benchmark_total"]  = bm_total * 100
            metrics["benchmark_annual"] = bm_annual * 100
            bm_scaled = _benchmark_with_flows(bm_series, ad_total)
            if bm_scaled.empty:
                cap0 = float(ad_total.dropna().iloc[0]) if not ad_total.dropna().empty else 1.0
                bm_scaled = (bm_series / 100.0 * cap0).reindex(vtc_total.index).ffill()
            bm_xy = _series_to_xy(bm_scaled)

    # Composition pie
    ultima = vc.index[-1]
    vpa = vc.loc[ultima].copy()
    if has_crypto and vc_eur is not None and not vc_eur.empty and ultima in vc_eur.index:
        for coin in vc_eur.columns:
            vpa[coin] = vc_eur.loc[ultima, coin]
    vpa = vpa[vpa > 0].sort_values(ascending=False)
    pcts = vpa / vpa.sum() * 100
    grandes = vpa[pcts >= 2].copy()
    if (pcts < 2).any():
        grandes["Otros"] = vpa[pcts < 2].sum()

    # Breakdown by general asset class (Acciones / ETF / Oro / Bonos / Cripto / Efectivo…)
    class_overrides = config.get_asset_classes()
    class_totals: dict[str, float] = {}
    class_members: dict[str, list[dict]] = {}
    crypto_symbols = (
        {str(c) for c in vc_eur.columns} if (has_crypto and vc_eur is not None) else set()
    ) | {str(c) for c in crypto_coins}
    for sym, val in vpa.items():
        if str(sym) in crypto_symbols:
            # Held crypto is always "Cripto" (an explicit user override still wins).
            cls = class_overrides.get(str(sym).strip().upper()) or "Cripto"
        else:
            cls = core.classify_asset(str(sym), _asset_display_name(str(sym)), class_overrides)
        class_totals[cls] = class_totals.get(cls, 0.0) + float(val)
        class_members.setdefault(cls, []).append(
            {"name": _asset_display_name(str(sym)), "symbol": str(sym), "value": round(float(val), 2)}
        )

    # Cash → "Efectivo" class (converted to EUR, kept OUT of P&L metrics).
    cash_missing_fx: list[str] = []
    cash_eur_by_cur = cash_store.cash_to_eur(cash_balances, fx_rates, missing=cash_missing_fx)
    cash_total = round(sum(cash_eur_by_cur.values()), 2)
    if cash_total > 0:
        class_totals["Efectivo"] = class_totals.get("Efectivo", 0.0) + cash_total
        for cur, eur in sorted(cash_eur_by_cur.items(), key=lambda kv: kv[1], reverse=True):
            class_members.setdefault("Efectivo", []).append(
                {"name": f"Efectivo {cur}", "symbol": cur, "value": round(float(eur), 2)}
            )

    total_all = sum(class_totals.values()) or 1.0
    class_breakdown = [
        {
            "name": cls,
            "value": round(v, 2),
            "pct": round(v / total_all * 100, 4),
            "members": sorted(class_members[cls], key=lambda x: x["value"], reverse=True),
        }
        for cls, v in sorted(class_totals.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # Stock correlations (assets above weight threshold in stock sleeve)
    correlation: dict = {
        "threshold_pct": 1.5,
        "assets": [],
        "matrix": {"labels": [], "values": []},
        "top_positive": [],
        "top_negative": [],
        "history_days": 0,
        "note": "",
    }
    try:
        vpa_stocks = vc.loc[ultima].copy()
        vpa_stocks = vpa_stocks[vpa_stocks > 0]
        total_stocks = float(vpa_stocks.sum()) if not vpa_stocks.empty else 0.0
        threshold = 0.015

        if total_stocks <= 0:
            correlation["note"] = "Sin posiciones en acciones para calcular correlaciones."
        else:
            selected = vpa_stocks[(vpa_stocks / total_stocks) > threshold].sort_values(ascending=False)
            selected_symbols = [str(s) for s in selected.index.tolist()]
            correlation["assets"] = [
                {
                    "name": _asset_display_name(sym),
                    "symbol": sym,
                    "weight": round(float(selected.loc[sym] / total_stocks * 100), 4),
                }
                for sym in selected_symbols
            ]
            correlation["threshold_pct"] = round(threshold * 100, 2)

            if len(selected_symbols) < 2:
                correlation["note"] = (
                    "Se necesitan al menos 2 activos por encima del umbral "
                    "para construir la matriz de correlación."
                )
            else:
                # Mirror notebook logic for correlation comparability:
                # download full historical close data from 2000, then pct_change().corr().
                corr_raw = yf.download(selected_symbols, start='2000-01-01', progress=False)
                if corr_raw is None or corr_raw.empty:
                    correlation["note"] = "No se pudo descargar histórico para calcular correlaciones."
                else:
                    if isinstance(corr_raw.columns, pd.MultiIndex):
                        corr_data = corr_raw['Close'] if 'Close' in corr_raw.columns.get_level_values(0) else corr_raw
                    else:
                        corr_data = corr_raw

                    if isinstance(corr_data, pd.Series):
                        corr_data = corr_data.to_frame(name=selected_symbols[0])

                    corr_data = corr_data.dropna(axis=1, how='all').dropna(how='all')
                    returns = corr_data.ffill().pct_change(fill_method=None).dropna(how='all')

                    corr_matrix = returns.corr()
                    corr_matrix = corr_matrix.dropna(axis=0, how='all').dropna(axis=1, how='all')
                    labels = [c for c in corr_matrix.columns if c in corr_matrix.index]

                    if len(labels) < 2:
                        correlation["note"] = "No hay suficiente histórico común para calcular correlaciones fiables."
                    else:
                        labels = sorted(labels, key=lambda s: str(s).upper())
                        corr_matrix = corr_matrix.loc[labels, labels]
                        values = []
                        for r in labels:
                            row_vals = []
                            for c in labels:
                                v = corr_matrix.loc[r, c]
                                row_vals.append(None if pd.isna(v) else round(float(v), 4))
                            values.append(row_vals)

                        pairs = []
                        for i, a1 in enumerate(labels):
                            for j in range(i + 1, len(labels)):
                                v = corr_matrix.iloc[i, j]
                                if pd.notna(v):
                                    pairs.append({
                                        "asset_1": a1,
                                        "asset_2": labels[j],
                                        "corr": round(float(v), 4),
                                    })

                        correlation["matrix"] = {"labels": labels, "values": values}
                        correlation["history_days"] = int(len(corr_data))
                        correlation["top_positive"] = sorted(pairs, key=lambda x: x["corr"], reverse=True)[:5]
                        correlation["top_negative"] = sorted(pairs, key=lambda x: x["corr"])[:5]
    except Exception as corr_e:
        _log_exception(corr_e, "correlation")
        correlation = {
            "threshold_pct": 1.5,
            "assets": [],
            "matrix": {"labels": [], "values": []},
            "top_positive": [],
            "top_negative": [],
            "history_days": 0,
            "note": "No se pudo calcular correlaciones (ver log del servidor).",
        }

    # Crypto chart
    crypto_chart = None
    if has_crypto and vtc_crypto is not None and not vtc_crypto.empty:
        crypto_chart = {
            "value":    _series_to_xy(vtc_crypto),
            "invested": _series_to_xy(aporte_crypto) if aporte_crypto is not None else [],
        }

    # Current crypto breakdown (percentage over total crypto + EUR value)
    crypto_breakdown: list[dict] = []
    crypto_total_value = 0.0
    if has_crypto and vc_eur is not None and not vc_eur.empty:
        latest_crypto_day = vc_eur.index[-1]
        crypto_vpa = vc_eur.loc[latest_crypto_day].copy()
        crypto_vpa = crypto_vpa[crypto_vpa > 0].sort_values(ascending=False)
        crypto_total_value = float(crypto_vpa.sum()) if not crypto_vpa.empty else 0.0
        if crypto_total_value > 0:
            crypto_breakdown = [
                {
                    "name": _asset_display_name(str(k)),
                    "symbol": str(k),
                    "value": round(float(v), 2),
                    "pct": round(float(v) / crypto_total_value * 100, 4),
                }
                for k, v in crypto_vpa.items()
            ]

    return {
        "metrics":   _clean_dict(metrics),
        "has_crypto": has_crypto,
        "portfolio_chart": {
            "value":     _series_to_xy(vtc_total),
            "invested":  _series_to_xy(ad_total),
            "benchmark": bm_xy,
        },
        "composition": [
            {"name": _asset_display_name(str(k)), "symbol": str(k), "value": round(float(v), 2)}
            for k, v in grandes.items()
        ],
        "composition_full": [
            {"name": _asset_display_name(str(k)), "symbol": str(k), "value": round(float(v), 2)}
            for k, v in vpa.items()
        ],
        "portfolio_total_value": round(float(vpa.sum()), 2),
        "cash_total": cash_total,
        "net_worth": round(float(vpa.sum()) + cash_total, 2),
        "top_assets":  [
            {"name": _asset_display_name(str(k)), "symbol": str(k), "value": round(float(v), 2)}
            for k, v in vpa.head(10).items()
        ],
        "class_breakdown": class_breakdown,
        "correlation": correlation,
        "crypto_chart": crypto_chart,
        "crypto_breakdown": crypto_breakdown,
        "crypto_total_value": round(crypto_total_value, 2),
        "failed_tickers": failed_tickers,
        "cash_missing_fx": sorted(set(cash_missing_fx)),
    }


# ─────────────────────────────────────────────────────────────────────────
#  API routes  (must be declared BEFORE the static-file catch-all)
# ─────────────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=OkResponse)
def api_health():
    return {"ok": True}


# ── LifeDeck (resumen de patrimonio en el móvil) ─────────────────────────
def _lifedeck_public() -> dict:
    data = lifedeck.public_settings()
    data["auto_supported"] = lifedeck_auto.supported()
    data["auto_enabled"] = lifedeck_auto.is_installed()
    return data


@app.get("/api/lifedeck")
def api_lifedeck_get():
    return _lifedeck_public()


@app.post("/api/lifedeck/auto")
async def api_lifedeck_auto(request: Request):
    """Activa/desactiva la tarea programada que recalcula y sube a LifeDeck sin abrir la app."""
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
        raise HTTPException(400, "Cuerpo inválido")
    try:
        if body["enabled"]:
            s = lifedeck.load_settings()
            if not (s.get("url") and s.get("token")):
                raise HTTPException(409, "Guarda antes la URL y el token de LifeDeck.")
            minutes = int(body.get("minutes") or s.get("auto_minutes") or 30)
            if minutes not in lifedeck_auto.INTERVALS:
                raise HTTPException(400, "Intervalo no permitido")
            lifedeck_auto.install(minutes)
            lifedeck.save_settings({"auto_minutes": minutes})
        else:
            lifedeck_auto.uninstall()
    except lifedeck_auto.AutoError as exc:
        return JSONResponse({"message": str(exc)}, status_code=502)
    return _lifedeck_public()


@app.post("/api/lifedeck")
async def api_lifedeck_post(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Cuerpo inválido")
    patch: dict = {}
    if "enabled" in body:
        patch["enabled"] = bool(body["enabled"])
    if isinstance(body.get("url"), str):
        url = body["url"].strip().rstrip("/")
        if url and not re.match(r"^https?://", url):
            raise HTTPException(400, "La URL debe empezar por https://")
        patch["url"] = url
    # token vacío = no cambiarlo
    if isinstance(body.get("token"), str) and body["token"].strip():
        patch["token"] = body["token"].strip()
    lifedeck.save_settings(patch)
    return _lifedeck_public()


@app.post("/api/lifedeck/test")
def api_lifedeck_test():
    ok, msg = lifedeck.test_connection()
    return {"ok": ok, "message": msg}


@app.post("/api/lifedeck/push")
def api_lifedeck_push():
    try:
        dash = _get_dashboard()
        if "error" in dash:
            return JSONResponse({"ok": False, "message": dash["error"]}, status_code=409)
        res = lifedeck.push(dash)
        return {"ok": True, "message": "Patrimonio subido a LifeDeck.", "last_push_at": res["last_push_at"]}
    except lifedeck.LifeDeckError as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=502)
    except Exception as e:
        _log_exception(e, "lifedeck push")
        return JSONResponse({"ok": False, "message": GENERIC_ERROR}, status_code=500)


@app.get("/api/dashboard", response_model=DashboardResponse)
def api_dashboard(refresh: bool = False):
    try:
        return _get_dashboard(refresh=refresh)
    except Exception as e:
        _log_exception(e, "dashboard")
        return JSONResponse({"error": GENERIC_ERROR}, status_code=500)


@app.get("/api/operations", response_model=list[Operation])
def api_operations():
    try:
        df = loaders.load_operations()
        if df.empty:
            return []
        cols = ["Date", "Product", "ticker", "ISIN", "Quantity", "Price", "Coin", "Value"]
        df = df[[c for c in cols if c in df.columns]].copy()
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d").fillna("")
        return _df_to_records(df)
    except Exception as e:
        raise _internal_error(e)


@app.post("/api/operations", response_model=MutationResult)
def api_operations_post(body: OperationCreate):
    try:
        date_raw = body.Date
        product = str(body.Product or "").strip()
        isin = str(body.ISIN or "").strip()
        quantity = pd.to_numeric(body.Quantity, errors="coerce")
        price = pd.to_numeric(body.Price, errors="coerce")
        coin = str(body.Coin or "").strip().upper() or "EUR"
        ticker = str(body.ticker or "").strip()
        value_raw = body.Value

        dt = pd.to_datetime(date_raw, errors="coerce")
        if pd.isna(dt):
            raise HTTPException(400, "Fecha inválida")
        if not product:
            raise HTTPException(400, "Product es obligatorio")
        if not isin:
            raise HTTPException(400, "ISIN es obligatorio")
        if pd.isna(quantity) or float(quantity) == 0.0:
            raise HTTPException(400, "Quantity debe ser un número distinto de 0")
        if pd.isna(price):
            raise HTTPException(400, "Price debe ser numérico")

        if value_raw is None or str(value_raw).strip() == "":
            gross = abs(float(quantity) * float(price))
            value = -gross if float(quantity) > 0 else gross
        else:
            value = pd.to_numeric(value_raw, errors="coerce")
            if pd.isna(value):
                raise HTTPException(400, "Value debe ser numérico")
            value = float(value)

        row = {
            "Date": dt.strftime("%Y-%m-%d"),
            "Product": product,
            "ISIN": isin,
            "Quantity": float(quantity),
            "Price": float(price),
            "Coin": coin,
            "Value": float(value),
            "eur": "EUR",
            "ticker": ticker,
        }

        with config.DATA_LOCK:
            df = loaders.load_operations()
            df_new = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            df_new["Date"] = pd.to_datetime(df_new["Date"], errors="coerce")
            loaders.save_operations(df_new)

        _invalidate_dashboard()

        return {"ok": True, "row": row}
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(e)


def _load_crypto_sorted() -> pd.DataFrame:
    """Load crypto ops in a stable, deterministic order with positional index.

    GET and the PUT/DELETE-by-id endpoints all go through this so a row's `id`
    (its position) refers to the same row across calls (until the CSV changes).
    The `fingerprint` (content hash) lets clients detect that a positional id
    went stale; see _check_crypto_fingerprint.
    """
    df = loaders.load_crypto_operations()
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Product", "Coin", "Quantity", "ticker"])
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.sort_values("Date", kind="mergesort").reset_index(drop=True)


def _row_fingerprint(r) -> str:
    return loaders.crypto_fingerprint(r["Date"], r["Coin"], r["Quantity"], r.get("ticker"))


def _check_crypto_fingerprint(df: pd.DataFrame, row_id: int, fingerprint: str | None) -> None:
    """409 if the client supplied a fingerprint and the row at `row_id` differs."""
    if not fingerprint:
        return
    if _row_fingerprint(df.iloc[row_id]) != fingerprint:
        raise HTTPException(
            409,
            "El movimiento ha cambiado desde que se cargó la lista. Recarga e inténtalo de nuevo.",
        )


@app.get("/api/crypto", response_model=list[CryptoOperation])
def api_crypto():
    try:
        with config.DATA_LOCK:
            df = _load_crypto_sorted()
        if df.empty:
            return []
        fps = [_row_fingerprint(r) for _, r in df.iterrows()]
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d %H:%M").fillna("")
        df.insert(0, "id", range(len(df)))
        df.insert(1, "fingerprint", fps)
        return _df_to_records(df)
    except Exception as e:
        raise _internal_error(e)


_CRYPTO_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
    "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
)
_CRYPTO_MIN_DATE = pd.Timestamp("1990-01-01")


def _parse_crypto_date(raw: str) -> pd.Timestamp:
    txt = str(raw or "").strip()
    for fmt in _CRYPTO_DATE_FORMATS:
        try:
            return pd.Timestamp(datetime.strptime(txt, fmt))
        except ValueError:
            continue
    raise HTTPException(
        400, "Fecha inválida: usa YYYY-MM-DD, 'YYYY-MM-DD HH:MM[:SS]' o DD/MM/YYYY."
    )


def _validate_crypto_body(body: CryptoOperationCreate) -> dict:
    """Validate + normalise a crypto op payload into a persistable row dict."""
    coin = str(body.Coin or "").strip().upper()
    quantity = pd.to_numeric(body.Quantity, errors="coerce")
    product = str(body.Product or "").strip()
    ticker = str(body.ticker or "").strip()

    dt = _parse_crypto_date(body.Date)
    if dt < _CRYPTO_MIN_DATE:
        raise HTTPException(400, "La fecha no puede ser anterior a 1990.")
    if dt.normalize() > pd.Timestamp.today().normalize():
        raise HTTPException(400, "La fecha no puede ser futura.")
    if not coin:
        raise HTTPException(400, "Coin es obligatorio")
    if not re.fullmatch(r"[A-Z0-9._-]{1,32}", coin):
        raise HTTPException(400, "Coin solo admite letras, números, '.', '_' y '-'.")
    if pd.isna(quantity) or not np.isfinite(float(quantity)) or float(quantity) <= 0.0:
        raise HTTPException(400, "Quantity debe ser un número positivo")

    if not product:
        product = coin
    if not ticker:
        ticker = f"{coin}-EUR"

    return {
        "Date": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "Product": product,
        "Coin": coin,
        "Quantity": float(quantity),
        "ticker": ticker,
    }


@app.post("/api/crypto", response_model=MutationResult)
def api_crypto_post(body: CryptoOperationCreate):
    try:
        row = _validate_crypto_body(body)

        with config.DATA_LOCK:
            df = loaders.load_crypto_operations()
            df_new = pd.concat([df, pd.DataFrame([row])], ignore_index=True) if len(df) else pd.DataFrame([row])
            df_new["Date"] = pd.to_datetime(df_new["Date"], errors="coerce")
            loaders.save_crypto_operations(df_new)
            # Re-adding a row by hand lifts a previous "deleted" mark on that key.
            loaders.update_crypto_tombstones(
                remove=[loaders.crypto_dedup_key(row["Date"], row["Coin"], row["Quantity"])]
            )

        _invalidate_dashboard()
        return {"ok": True, "row": row}
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(e)


@app.put("/api/crypto/{row_id}", response_model=MutationResult)
def api_crypto_put(row_id: int, body: CryptoOperationCreate, fingerprint: str | None = None):
    try:
        row = _validate_crypto_body(body)
        fingerprint = fingerprint or body.fingerprint

        with config.DATA_LOCK:
            df = _load_crypto_sorted()
            if row_id < 0 or row_id >= len(df):
                raise HTTPException(404, "Movimiento no encontrado")
            _check_crypto_fingerprint(df, row_id, fingerprint)

            old = df.iloc[row_id]
            old_key = loaders.crypto_dedup_key(old["Date"], old["Coin"], old["Quantity"])
            new_key = loaders.crypto_dedup_key(row["Date"], row["Coin"], row["Quantity"])

            for col, val in row.items():
                df.loc[row_id, col] = val
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            loaders.save_crypto_operations(df)
            if old_key != new_key:
                # Don't let the original exchange row resurrect on next ingestion.
                loaders.update_crypto_tombstones(add=[old_key], remove=[new_key])

        _invalidate_dashboard()
        return {"ok": True, "row": row}
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(e)


@app.delete("/api/crypto/{row_id}", response_model=MutationResult)
def api_crypto_delete(row_id: int, fingerprint: str | None = None):
    try:
        with config.DATA_LOCK:
            df = _load_crypto_sorted()
            if row_id < 0 or row_id >= len(df):
                raise HTTPException(404, "Movimiento no encontrado")
            _check_crypto_fingerprint(df, row_id, fingerprint)

            removed = df.iloc[row_id].where(pd.notna(df.iloc[row_id]), None).to_dict()
            key = loaders.crypto_dedup_key(removed["Date"], removed["Coin"], removed["Quantity"])
            if isinstance(removed.get("Date"), pd.Timestamp):
                removed["Date"] = removed["Date"].strftime("%Y-%m-%d %H:%M:%S")
            df = df.drop(index=row_id).reset_index(drop=True)
            loaders.save_crypto_operations(df)
            # Mark as deleted so re-ingesting the exchange export doesn't bring it back.
            loaders.update_crypto_tombstones(add=[key])

        _invalidate_dashboard()
        return {"ok": True, "row": removed}
    except HTTPException:
        raise
    except Exception as e:
        raise _internal_error(e)


@app.get("/api/tax", response_model=TaxResponse)
def api_tax():
    try:
        df = loaders.load_operations()
        if df.empty:
            return {"gains": [], "annual": [], "by_ticker": []}

        df_merged = loaders.merge_custom_stock_sources(df.copy())
        df_merged  = _resolve_tickers_silent(df_merged)
        currencies = df_merged["Coin"].dropna().unique().tolist()
        start_date = df_merged["Date"].min()

        # Same FX universe as the dashboard (cash currencies + crypto coins).
        for cur in cash_store.load_cash():
            if cur not in currencies and cur != "EUR":
                currencies.append(cur)
        df_crypto = loaders.load_crypto_operations()
        crypto_coins: list[str] = []
        if df_crypto is not None and len(df_crypto) > 0:
            crypto_coins = df_crypto["Coin"].dropna().unique().tolist()
            crypto_min = pd.to_datetime(df_crypto["Date"], errors="coerce").min()
            if pd.notna(crypto_min) and (pd.isna(start_date) or crypto_min < start_date):
                start_date = crypto_min

        fx_rates = market_data.fetch_fx_rates(currencies, start_date,
                                              crypto_coins=crypto_coins or None)
        df_adj   = core.SplitManager.apply_splits(df_merged)
        df_gains = tax.calculate_fifo_gains(df_adj, fx_rates)

        if df_gains.empty:
            return {"gains": [], "annual": [], "by_ticker": []}

        annual    = tax.annual_tax_summary(df_gains)
        by_ticker = tax.tax_summary(df_gains)

        g = df_gains.copy()
        g["fecha_venta"] = pd.to_datetime(g["fecha_venta"]).dt.strftime("%Y-%m-%d")

        return {
            "gains":     _df_to_records(g),
            "annual":    _df_to_records(annual),
            "by_ticker": _df_to_records(by_ticker),
        }
    except Exception as e:
        traceback.print_exc()
        raise _internal_error(e)


@app.get("/api/sources")
def api_sources_get():
    try:
        if os.path.exists(config.SOURCES_FILE):
            with open(config.SOURCES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        raise _internal_error(e)


def _check_file_pattern(pattern: str, where: str) -> None:
    if (not pattern.strip() or "/" in pattern or "\\" in pattern or ".." in pattern
            or "\x00" in pattern):
        raise HTTPException(
            422, f"{where}: file_pattern no válido (no puede contener '/', '\\' ni '..')."
        )


@app.post("/api/sources", response_model=OkResponse)
def api_sources_post(body: SourcesPayload):
    """Replace sources.json. Typed + validated; malformed JSON → 422; atomic write."""
    for key in ("stock_sources", "crypto_sources"):
        for i, src in enumerate(getattr(body, key)):
            _check_file_pattern(src.file_pattern, f"{key}[{i}]")
    try:
        config.save_sources(body.model_dump(exclude_unset=True))
        _invalidate_dashboard()
        return {"ok": True}
    except Exception as e:
        raise _internal_error(e)


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_UPLOAD_CHUNK = 1024 * 1024


def _inside_dir(root: str, path: str) -> bool:
    """True if realpath(path) is inside realpath(root)."""
    r = os.path.realpath(root)
    p = os.path.realpath(path)
    try:
        return os.path.commonpath([r, p]) == r and p != r
    except ValueError:      # different drives on Windows
        return False


def _safe_input_name(filename: str | None, *, strict: bool = False) -> str:
    """Sanitise a client-supplied file name for input/. Raises HTTPException(400).

    - non-strict (upload): takes the basename (after '\\' → '/') so browsers that
      send full paths work, but rejects '..' segments outright.
    - strict (delete): the name must already be a bare file name.
    """
    if not filename or not str(filename).strip():
        raise HTTPException(400, "Nombre de archivo vacío.")
    norm = str(filename).replace("\\", "/")
    parts = norm.split("/")
    if ".." in parts:
        raise HTTPException(400, "Nombre de archivo no válido.")
    base = parts[-1].strip()
    if strict and base != filename:
        raise HTTPException(400, "Nombre de archivo no válido.")
    if (not base or base in (".", "..") or any(ord(c) < 32 for c in base)
            or any(c in base for c in ':*?"<>|')):
        raise HTTPException(400, "Nombre de archivo no válido.")
    if not base.lower().endswith(".csv"):
        raise HTTPException(400, "Solo se admiten archivos .csv.")
    if not _inside_dir(config.INPUT_DIR, os.path.join(config.INPUT_DIR, base)):
        raise HTTPException(400, "Nombre de archivo no válido.")
    return base


@app.post("/api/upload", response_model=UploadResponse)
def api_upload(files: list[UploadFile] = File(...)):
    os.makedirs(config.INPUT_DIR, exist_ok=True)
    # Validate every name first so a bad one aborts the whole request.
    names = [_safe_input_name(f.filename) for f in files]
    tmp_paths: list[str] = []
    try:
        for f, name in zip(files, names):
            fd, tmp = tempfile.mkstemp(dir=config.INPUT_DIR, prefix=".upload-", suffix=".tmp")
            tmp_paths.append(tmp)
            size = 0
            with os.fdopen(fd, "wb") as fh:
                while True:
                    chunk = f.file.read(_UPLOAD_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            413, f"'{name}' supera el límite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
                        )
                    fh.write(chunk)
        for tmp, name in zip(tmp_paths, names):
            os.replace(tmp, os.path.join(config.INPUT_DIR, name))
        tmp_paths = []
    finally:
        for tmp in tmp_paths:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return {"saved": names}


@app.get("/api/source-data", response_model=list[SourceData])
def api_source_data():
    """Return parsed vest/position entries from all enabled stock sources."""
    import fnmatch
    sources = config.get_stock_sources()
    result = []
    if not os.path.exists(config.INPUT_DIR):
        return result

    for src in sources:
        pattern  = src.get("file_pattern", "")
        col_map  = src.get("column_map", {})
        defaults = src.get("defaults", {})
        name     = src.get("name", pattern)

        date_col = col_map.get("Date", "date")
        qty_col  = col_map.get("Quantity", "available")
        price_col = col_map.get("Price", "strike_price")

        matched = [
            f for f in os.listdir(config.INPUT_DIR)
            if fnmatch.fnmatch(f.lower(), pattern.lower())
        ]
        for fname in matched:
            try:
                df = pd.read_csv(os.path.join(config.INPUT_DIR, fname))
                entries = []
                for _, row in df.iterrows():
                    qty   = pd.to_numeric(row.get(qty_col, 0), errors="coerce")
                    price = pd.to_numeric(row.get(price_col, 0), errors="coerce")
                    date  = str(row.get(date_col, ""))
                    if pd.isna(qty) or qty <= 0:
                        continue
                    parsed_date = pd.to_datetime(date, dayfirst=False, errors="coerce")
                    entries.append({
                        "date":     parsed_date.strftime("%Y-%m-%d") if pd.notna(parsed_date) else date,
                        "quantity": round(float(qty), 6),
                        "price":    round(float(price) if pd.notna(price) else 0, 5),
                        "value":    round(float(qty * price) if pd.notna(price) else 0, 2),
                    })
                entries.sort(key=lambda x: x["date"])
                result.append({
                    "source":      name,
                    "file":        fname,
                    "ticker":      defaults.get("ticker", ""),
                    "product":     defaults.get("Product", ""),
                    "coin":        defaults.get("Coin", "EUR"),
                    "total_qty":   round(sum(e["quantity"] for e in entries), 6),
                    "total_value": round(sum(e["value"] for e in entries), 2),
                    "entries":     entries,
                })
            except Exception as e:
                _log_exception(e, f"source-data {fname}")
                result.append({"source": name, "file": fname,
                               "error": "No se pudo leer el archivo.", "entries": []})
    return result


@app.get("/api/pending-files", response_model=list[str])
def api_pending():
    if not os.path.exists(config.INPUT_DIR):
        return []
    # Patterns from sources.json are "permanent" source files — not pending transactions
    sources = config.load_sources()
    source_patterns = set()
    for src in sources.get("stock_sources", []):
        if p := src.get("file_pattern"):
            source_patterns.add(p.lower())
    for src in sources.get("crypto_sources", []):
        if p := src.get("file_pattern"):
            source_patterns.add(p.lower())

    def _is_source_file(fname: str) -> bool:
        import fnmatch
        return any(fnmatch.fnmatch(fname.lower(), pat) for pat in source_patterns)

    return [
        f for f in os.listdir(config.INPUT_DIR)
        if f.lower().endswith(".csv") and not _is_source_file(f)
    ]


@app.get("/api/source-files", response_model=list[SourceFileInfo])
def api_source_files():
    """List files in input/ that are permanent source files (match a sources.json pattern)."""
    import fnmatch
    if not os.path.exists(config.INPUT_DIR):
        return []
    sources = config.load_sources()
    source_patterns: list[dict] = []
    for src in sources.get("stock_sources", []):
        if p := src.get("file_pattern"):
            source_patterns.append({"pattern": p.lower(), "name": src.get("name", p), "enabled": src.get("enabled", False)})
    for src in sources.get("crypto_sources", []):
        if p := src.get("file_pattern"):
            source_patterns.append({"pattern": p.lower(), "name": src.get("name", p), "enabled": src.get("enabled", False)})

    result = []
    for fname in os.listdir(config.INPUT_DIR):
        if not fname.lower().endswith(".csv"):
            continue
        for sp in source_patterns:
            if fnmatch.fnmatch(fname.lower(), sp["pattern"]):
                result.append({"file": fname, "source": sp["name"], "enabled": sp["enabled"]})
                break
    return result


def _resolve_source_file(filename: str) -> str:
    """Sanitise `filename` and return its absolute path in input/, ensuring it
    is a .csv matching a configured source pattern. Raises HTTPException."""
    import fnmatch
    safe = os.path.basename(filename)            # strip any path traversal
    if safe != filename or not safe.lower().endswith(".csv"):
        raise HTTPException(400, "Nombre de archivo no válido.")

    sources = config.load_sources()
    patterns = [
        s.get("file_pattern", "").lower()
        for s in sources.get("stock_sources", []) + sources.get("crypto_sources", [])
        if s.get("file_pattern")
    ]
    if not any(fnmatch.fnmatch(safe.lower(), p) for p in patterns):
        raise HTTPException(403, "El archivo no es una fuente configurada.")

    path = os.path.join(config.INPUT_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(404, "Archivo no encontrado.")
    return path


@app.get("/api/source-file/{filename}", response_model=SourceFileContent)
def api_source_file_get(filename: str):
    """Return the raw CSV (columns + string cells) of a configured source file."""
    path = _resolve_source_file(filename)
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
        config.get_logger().warning(f"api_source_file_get: {filename} ilegible: {e}")
        raise HTTPException(400, "El archivo CSV está vacío o está corrupto.")
    df.columns = [str(c).strip() for c in df.columns]
    return {
        "file": os.path.basename(path),
        "columns": list(df.columns),
        "rows": df.astype(str).values.tolist(),
    }


@app.put("/api/source-file/{filename}", response_model=SourceFileContent)
def api_source_file_put(filename: str, body: SourceFileContent):
    """Overwrite a configured source file with edited rows (with backup)."""
    path = _resolve_source_file(filename)
    if not body.columns:
        raise HTTPException(400, "Se requiere al menos una columna.")
    columns = [str(c).strip() for c in body.columns]
    if any(not c for c in columns):
        raise HTTPException(422, "Hay columnas con nombre vacío.")
    dups = sorted({c for c in columns if columns.count(c) > 1})
    if dups:
        raise HTTPException(422, f"Columnas duplicadas: {', '.join(dups)}.")
    ncol = len(columns)
    for i, r in enumerate(body.rows):
        if len(r) != ncol:
            raise HTTPException(
                422, f"La fila {i + 1} tiene {len(r)} celdas pero hay {ncol} columnas."
            )

    with config.DATA_LOCK:
        loaders._backup_file(path)
        df = pd.DataFrame(body.rows, columns=columns)
        config.atomic_to_csv(df, path, index=False)
    config.get_logger().info(
        f"api_source_file_put: {len(body.rows)} filas guardadas → {path}"
    )
    _invalidate_dashboard()
    return {"file": os.path.basename(path), "columns": columns, "rows": body.rows}


@app.delete("/api/pending-files/{filename}", response_model=OkResponse)
def api_delete_pending(filename: str):
    safe = _safe_input_name(filename, strict=True)
    path = os.path.join(config.INPUT_DIR, safe)
    if os.path.isfile(path):
        os.remove(path)
        return {"ok": True}
    raise HTTPException(404, "File not found")


@app.post("/api/invalidate", response_model=OkResponse)
def api_invalidate():
    _invalidate_dashboard()
    return {"ok": True}


@app.get("/api/invalidate")
def api_invalidate_get_not_allowed():
    # Mutating action: GET is not allowed any more (use POST).
    raise HTTPException(405, "Usa POST /api/invalidate.", headers={"Allow": "POST"})


def _cash_response() -> dict:
    balances = cash_store.load_cash()
    # Convert with cached FX if available (no network), applying the same FX
    # divisors as the dashboard (e.g. GBX/100). Currencies without a rate are
    # NOT converted (rate 1.0) and are reported in `missing_fx` + `warning`.
    fx = market_data._load_cache(config.FX_CACHE_FILE)
    if fx is not None and not fx.empty:
        fx = fx.copy()
        for cur, divisor in config.get_fx_adjustments().items():
            if cur in fx.columns and divisor:
                fx[cur] = fx[cur] / divisor
    missing: list[str] = []
    eur = cash_store.cash_to_eur(balances, fx, missing=missing)
    entries = [
        {"currency": cur, "amount": round(amt, 2), "eur": eur.get(cur, round(amt, 2))}
        for cur, amt in sorted(balances.items())
    ]
    missing = sorted(set(missing))
    return {
        "balances": entries,
        "total_eur": round(sum(e["eur"] for e in entries), 2),
        "missing_fx": missing,
        "warning": (
            f"Sin tipo de cambio para {', '.join(missing)}: se muestra el importe sin convertir."
            if missing else None
        ),
    }


@app.get("/api/cash", response_model=CashResponse)
def api_cash_get():
    try:
        return _cash_response()
    except Exception as e:
        raise _internal_error(e)


@app.post("/api/cash", response_model=CashResponse)
def api_cash_post(body: CashUpdate):
    try:
        cash_store.save_cash(body.balances)
        _invalidate_dashboard()
        return _cash_response()
    except Exception as e:
        raise _internal_error(e)


# Suggested classes offered in the UI (plus any class already used in overrides).
KNOWN_ASSET_CLASSES = ["Acciones", "ETF", "Oro / Materias primas", "Bonos", "Cripto", "Efectivo"]


@app.get("/api/asset-classes", response_model=AssetClassesResponse)
def api_asset_classes():
    """Per-ticker asset-class view for the settings editor.

    Offline/fast: derives held symbols from operations + crypto WITHOUT hitting
    the network, and reports the automatic class, the override (if any) and the
    effective class for each.
    """
    try:
        overrides = config.get_asset_classes()  # {SYMBOL_UPPER: class}
        items: list[dict] = []
        seen: set[str] = set()

        # ── Stocks ──
        df = loaders.load_operations()
        if not df.empty:
            df = loaders.merge_custom_stock_sources(df)
            df["ticker"] = df.get("ticker", "").fillna("").astype(str).str.strip()
            df["Product"] = df.get("Product", "").fillna("").astype(str).str.strip()
            named = df[(df["ticker"] != "")].sort_values("Date", kind="mergesort")
            name_map = named.drop_duplicates("ticker", keep="last").set_index("ticker")["Product"].to_dict()
            for sym in sorted(name_map.keys(), key=lambda s: s.upper()):
                up = sym.upper()
                if up in seen:
                    continue
                seen.add(up)
                product = name_map.get(sym, "") or sym
                auto = core.classify_asset(sym, product)
                ov = overrides.get(up)
                items.append({
                    "symbol": sym, "name": product, "auto": auto,
                    "override": ov, "effective": ov or auto, "kind": "stock",
                })

        # ── Crypto ──
        df_c = loaders.load_crypto_operations()
        if df_c is not None and not df_c.empty and "Coin" in df_c.columns:
            for coin in sorted(df_c["Coin"].dropna().astype(str).str.strip().unique()):
                up = coin.upper()
                if not coin or up in seen:
                    continue
                seen.add(up)
                auto = core.classify_asset(coin, coin)
                ov = overrides.get(up)
                items.append({
                    "symbol": coin, "name": coin, "auto": auto,
                    "override": ov, "effective": ov or auto, "kind": "crypto",
                })

        known = list(dict.fromkeys(KNOWN_ASSET_CLASSES + [v for v in overrides.values()]))
        return {"known_classes": known, "items": items}
    except Exception as e:
        traceback.print_exc()
        raise _internal_error(e)


# ─────────────────────────────────────────────────────────────────────────
#  Cartera objetivo (target portfolio) + rebalanceo
# ─────────────────────────────────────────────────────────────────────────

@app.get("/api/target", response_model=TargetConfig)
def api_target_get():
    """Return the stored target ("cartera tipo") + diversification rules."""
    try:
        return TargetConfig(**config.get_target_portfolio())
    except Exception:
        # Corrupt/legacy content → return defaults rather than 500.
        return TargetConfig()


@app.post("/api/target", response_model=TargetConfig)
def api_target_post(body: TargetConfig):
    """Persist the target config; invalidate the dashboard cache."""
    try:
        config.save_target_portfolio(body.model_dump())
        _invalidate_dashboard()
        return body
    except Exception as e:
        raise _internal_error(e)


@app.get("/api/rebalance", response_model=RebalanceResponse)
def api_rebalance():
    """Control panel: what to do to hit the target vs current holdings (cartera+cash).

    Reuses the dashboard computation (net worth + class breakdown incl. cash),
    so it reflects the exact same figures shown on the Dashboard.
    """
    try:
        dash = _get_dashboard()
        if dash.get("error"):
            raise HTTPException(400, dash["error"])
        net_worth = dash.get("net_worth") or 0.0
        class_breakdown = dash.get("class_breakdown") or []
        cfg = config.get_target_portfolio()
        return target_engine.compute_rebalance(net_worth, class_breakdown, cfg)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise _internal_error(e)


# ─────────────────────────────────────────────────────────────────────────
#  Ingesta + informes
# ─────────────────────────────────────────────────────────────────────────

@app.post("/api/process/preview", response_model=ProcessPreview)
def api_process_preview():
    """Detect what /api/process WOULD add, without saving or deleting anything.
    Powers the confirmation preview shown before committing new transactions."""
    files: list[dict] = []
    try:
        df_ops = loaders.load_operations()
        files.extend(loaders.preview_new_transactions(df_ops))
    except Exception as e:
        config.get_logger().warning(f"api_process_preview stocks: {e}")
    try:
        files.extend(loaders.preview_new_crypto_transactions())
    except Exception as e:
        config.get_logger().warning(f"api_process_preview crypto: {e}")

    total_new = sum(f.get("new", 0) for f in files)
    total_dup = sum(f.get("duplicates", 0) for f in files)
    return {"files": files, "total_new": total_new, "total_duplicates": total_dup}


@app.post("/api/process", response_model=ProcessResult)
def api_process():
    """Ingest pending CSVs from input/ into processing/ (mirrors CLI opts 2 & 3)."""
    stock_added = 0
    crypto_added = 0
    files_seen: list[str] = []
    try:
        if os.path.isdir(config.INPUT_DIR):
            files_seen = [f for f in os.listdir(config.INPUT_DIR) if f.lower().endswith(".csv")]

        # Stocks
        try:
            df_ops = loaders.load_operations()
            before = len(df_ops)
            df_updated = loaders.process_new_transactions(df_ops)
            df_updated = _resolve_tickers_silent(df_updated)
            loaders.save_operations(df_updated)
            stock_added = max(0, len(df_updated) - before)
        except Exception as e:
            config.get_logger().warning(f"api_process stocks: {e}")

        # Crypto
        try:
            df_crypto_before = loaders.load_crypto_operations()
            before_c = 0 if df_crypto_before is None else len(df_crypto_before)
            df_c = loaders.process_crypto_transactions()
            crypto_added = max(0, (0 if df_c is None else len(df_c)) - before_c)
        except Exception as e:
            config.get_logger().warning(f"api_process crypto: {e}")

        _invalidate_dashboard()
        return {
            "ok": True,
            "stock_added": stock_added,
            "crypto_added": crypto_added,
            "files": files_seen,
            "message": f"{stock_added} operaciones y {crypto_added} movimientos crypto añadidos.",
        }
    except Exception as e:
        traceback.print_exc()
        raise _internal_error(e)


def _to_float(v, default=0.0) -> float:
    """Parse a possibly-string/European/US number into float."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    n = loaders._parse_number(v)
    return default if n is None else n


@app.post("/api/process/commit", response_model=ProcessResult)
def api_process_commit(body: ProcessCommit):
    """Persist the (possibly edited) rows the user confirmed in the preview,
    then delete the source files from input/. Unlike /api/process this saves
    exactly what the client sends — supporting edit/delete before saving."""
    stock_rows: list[dict] = []
    crypto_rows: list[dict] = []
    files_to_delete: set[str] = set()

    for f in body.files:
        files_to_delete.add(os.path.basename(str(f.file).replace("\\", "/")))
        if f.kind == "crypto":
            for e in f.entries:
                coin = str(e.get("coin", "")).strip().upper()
                if not coin:
                    continue
                crypto_rows.append({
                    "Date": e.get("date"),
                    "Product": coin,
                    "Coin": coin,
                    "Quantity": _to_float(e.get("quantity")),
                    "ticker": e.get("ticker") or f"{coin}-EUR",
                })
        else:
            for e in f.entries:
                stock_rows.append({
                    "Date": e.get("date"),
                    "Product": e.get("product") or "",
                    "ISIN": e.get("isin") or "",
                    "Quantity": _to_float(e.get("quantity")),
                    "Price": _to_float(e.get("price")),
                    "Coin": e.get("coin") or "EUR",
                    "Value": _to_float(e.get("value")),
                    "eur": "EUR",
                })

    stock_added = 0
    crypto_added = 0
    try:
        if stock_rows:
            df_ops = loaders.load_operations()
            before = len(df_ops)
            df_new = pd.DataFrame(stock_rows)
            df_new["Date"] = pd.to_datetime(df_new["Date"], errors="coerce")
            df_ops = pd.concat([df_ops, df_new], ignore_index=True)
            df_ops = df_ops.sort_values("Date", kind="mergesort")
            # Resolve tickers silently — never prompt on stdin (server context).
            df_ops = _resolve_tickers_silent(df_ops)
            loaders.save_operations(df_ops)
            stock_added = len(df_ops) - before

        if crypto_rows:
            df_c = loaders.load_crypto_operations()
            before_c = 0 if df_c is None else len(df_c)
            df_cn = pd.DataFrame(crypto_rows)
            df_cn["Date"] = pd.to_datetime(df_cn["Date"], errors="coerce")
            df_c = pd.concat([df_c, df_cn], ignore_index=True) if before_c else df_cn
            df_c = df_c.sort_values("Date", kind="mergesort")
            loaders.save_crypto_operations(df_c)
            crypto_added = len(df_c) - before_c

        # Remove the confirmed source files from input/.
        deleted: list[str] = []
        for fn in files_to_delete:
            if not fn.lower().endswith(".csv"):
                continue
            p = os.path.join(config.INPUT_DIR, fn)
            if fn in (".", "..") or not _inside_dir(config.INPUT_DIR, p):
                continue
            if os.path.isfile(p):
                os.remove(p)
                deleted.append(fn)

        _invalidate_dashboard()
        config.get_logger().info(
            f"api_process_commit: stock={stock_added} crypto={crypto_added} "
            f"archivos_borrados={deleted}"
        )
        return {
            "ok": True,
            "stock_added": stock_added,
            "crypto_added": crypto_added,
            "files": deleted,
            "message": f"{stock_added} operaciones y {crypto_added} movimientos crypto guardados.",
        }
    except Exception as e:
        traceback.print_exc()
        raise _internal_error(e)


def _latest_report() -> str | None:
    pdfs = glob.glob(os.path.join(config.OUTPUT_DIR, "resumen_cartera_*.pdf"))
    return max(pdfs, key=os.path.getmtime) if pdfs else None


@app.get("/api/report/pdf")
def api_report_pdf():
    path = _latest_report()
    if not path or not os.path.isfile(path):
        raise HTTPException(404, "No hay informe generado todavía.")
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


@app.post("/api/report/generate", response_model=ReportResult)
def api_report_generate():
    """Run the full pipeline and generate a fresh PDF report."""
    started = time.time()
    try:
        import main  # lazy: avoids importing the CLI menu at server startup
        main.run_analysis()
    except BaseException as e:   # run_analysis may raise SystemExit on config errors
        if isinstance(e, (KeyboardInterrupt, GeneratorExit)):
            raise
        _log_exception(e, "report/generate")
        _invalidate_dashboard()
        return JSONResponse(
            {"ok": False, "file": None,
             "message": "No se pudo generar el informe. Consulta el log del servidor."},
            status_code=500,
        )
    _invalidate_dashboard()
    path = _latest_report()
    if not path or os.path.getmtime(path) < started - 2:
        return JSONResponse(
            {"ok": False, "file": None, "message": "El análisis terminó pero no se generó ningún PDF nuevo."},
            status_code=500,
        )
    return {"ok": True, "file": os.path.basename(path), "message": "Informe generado."}


# ─────────────────────────────────────────────────────────────────────────
#  Static files + SPA fallback
# ─────────────────────────────────────────────────────────────────────────

# index.html must never be cached: it references the hashed asset bundles, so a
# stale copy would keep loading an old build. The hashed assets themselves are
# immutable (their name changes on every build) and can be cached normally.
_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _index_response() -> FileResponse:
    return FileResponse(os.path.join(WEB_DIR, "index.html"), headers=_NO_CACHE)


@app.get("/")
def index():
    return _index_response()


@app.get("/{path:path}")
def spa_fallback(path: str):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(404, "Not found")
    full = os.path.join(WEB_DIR, path)
    if _inside_dir(WEB_DIR, full) and os.path.isfile(full):
        return FileResponse(os.path.realpath(full))
    return _index_response()


# ─────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    # Local-only by default: this app has no auth. Override with GP_HOST (e.g. 0.0.0.0)
    # only on a trusted network.
    _host = os.environ.get("GP_HOST", "127.0.0.1")
    print(f"🚀  Global Position → http://{_host}:8000")
    uvicorn.run(app, host=_host, port=8000)
