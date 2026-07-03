"""
Global Position – FastAPI Web Server

Usage:
    python server.py
    uvicorn server:app --reload --port 8000
"""

import json
import os
import sys
import traceback

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
from src import config, core, loaders, market_data, tax
from src.api_models import (
    AssetClassesResponse,
    CashResponse,
    CashUpdate,
    CryptoOperationCreate,
    DashboardResponse,
    OkResponse,
    Operation,
    OperationCreate,
    CryptoOperation,
    MutationResult,
    ProcessResult,
    ReportResult,
    SourceData,
    SourceFileInfo,
    TaxResponse,
    UploadResponse,
)

app = FastAPI(
    title="Global Position",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Frontend build output (served in production). During Stage 2 the legacy
# web/ folder at the repo root is still used; Stage 9 switches to frontend/dist.
WEB_DIR = os.path.join(config.BASE_DIR, "frontend", "dist")
if not os.path.isdir(WEB_DIR):
    WEB_DIR = os.path.join(config.BASE_DIR, "web")

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


def _build_dashboard() -> dict:
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
    prices   = market_data.fetch_prices(tickers, start_date)
    fx_rates = market_data.fetch_fx_rates(currencies, start_date,
                                          crypto_coins=crypto_coins or None)

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
    for sym, val in vpa.items():
        cls = core.classify_asset(str(sym), _asset_display_name(str(sym)), class_overrides)
        class_totals[cls] = class_totals.get(cls, 0.0) + float(val)
        class_members.setdefault(cls, []).append(
            {"name": _asset_display_name(str(sym)), "symbol": str(sym), "value": round(float(val), 2)}
        )

    # Cash → "Efectivo" class (converted to EUR, kept OUT of P&L metrics).
    cash_eur_by_cur = cash_store.cash_to_eur(cash_balances, fx_rates)
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
        correlation = {
            "threshold_pct": 1.5,
            "assets": [],
            "matrix": {"labels": [], "values": []},
            "top_positive": [],
            "top_negative": [],
            "history_days": 0,
            "note": f"No se pudo calcular correlaciones: {corr_e}",
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
    }


# ─────────────────────────────────────────────────────────────────────────
#  API routes  (must be declared BEFORE the static-file catch-all)
# ─────────────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=OkResponse)
def api_health():
    return {"ok": True}


@app.get("/api/dashboard", response_model=DashboardResponse)
def api_dashboard(refresh: bool = False):
    global _dashboard_cache
    if not _dashboard_cache or refresh:
        try:
            _dashboard_cache = _build_dashboard()
        except Exception as e:
            traceback.print_exc()
            return JSONResponse({"error": str(e)}, status_code=500)
    return _dashboard_cache


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
        raise HTTPException(500, str(e))


@app.post("/api/operations", response_model=MutationResult)
async def api_operations_post(body: OperationCreate):
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

        df = loaders.load_operations()
        df_new = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        df_new["Date"] = pd.to_datetime(df_new["Date"], errors="coerce")
        loaders.save_operations(df_new)

        global _dashboard_cache
        _dashboard_cache = {}

        return {"ok": True, "row": row}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/crypto", response_model=list[CryptoOperation])
def api_crypto():
    try:
        df = loaders.load_crypto_operations()
        if df is None or df.empty:
            return []
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d %H:%M").fillna("")
        return _df_to_records(df)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/crypto", response_model=MutationResult)
async def api_crypto_post(body: CryptoOperationCreate):
    try:
        date_raw = body.Date
        coin = str(body.Coin or "").strip().upper()
        quantity = pd.to_numeric(body.Quantity, errors="coerce")
        product = str(body.Product or "").strip()
        ticker = str(body.ticker or "").strip()

        dt = pd.to_datetime(date_raw, errors="coerce")
        if pd.isna(dt):
            raise HTTPException(400, "Fecha inválida")
        if not coin:
            raise HTTPException(400, "Coin es obligatorio")
        if pd.isna(quantity) or float(quantity) <= 0.0:
            raise HTTPException(400, "Quantity debe ser un número positivo")

        if not product:
            product = coin
        if not ticker:
            ticker = f"{coin}-EUR"

        row = {
            "Date": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "Product": product,
            "Coin": coin,
            "Quantity": float(quantity),
            "ticker": ticker,
        }

        df = loaders.load_crypto_operations()
        df_new = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        df_new["Date"] = pd.to_datetime(df_new["Date"], errors="coerce")
        loaders.save_crypto_operations(df_new)

        global _dashboard_cache
        _dashboard_cache = {}

        return {"ok": True, "row": row}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


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

        fx_rates = market_data.fetch_fx_rates(currencies, start_date)
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
        raise HTTPException(500, str(e))


@app.get("/api/sources")
def api_sources_get():
    try:
        if os.path.exists(config.SOURCES_FILE):
            with open(config.SOURCES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/sources", response_model=OkResponse)
async def api_sources_post(request: Request):
    try:
        body = await request.json()
        with open(config.SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=4, ensure_ascii=False)
        global _dashboard_cache
        _dashboard_cache = {}          # invalidate cache
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/upload", response_model=UploadResponse)
async def api_upload(files: list[UploadFile] = File(...)):
    os.makedirs(config.INPUT_DIR, exist_ok=True)
    saved = []
    for f in files:
        dest = os.path.join(config.INPUT_DIR, f.filename)
        content = await f.read()
        with open(dest, "wb") as fh:
            fh.write(content)
        saved.append(f.filename)
    return {"saved": saved}


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
                result.append({"source": name, "file": fname, "error": str(e), "entries": []})
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


@app.delete("/api/pending-files/{filename}", response_model=OkResponse)
def api_delete_pending(filename: str):
    path = os.path.join(config.INPUT_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return {"ok": True}
    raise HTTPException(404, "File not found")


@app.get("/api/invalidate", response_model=OkResponse)
def api_invalidate():
    global _dashboard_cache
    _dashboard_cache = {}
    return {"ok": True}


def _cash_response() -> dict:
    balances = cash_store.load_cash()
    # Convert with cached FX if available (no network); EUR/unknown → rate 1.0.
    fx = market_data._load_cache(config.FX_CACHE_FILE)
    eur = cash_store.cash_to_eur(balances, fx)
    entries = [
        {"currency": cur, "amount": round(amt, 2), "eur": eur.get(cur, round(amt, 2))}
        for cur, amt in sorted(balances.items())
    ]
    return {"balances": entries, "total_eur": round(sum(e["eur"] for e in entries), 2)}


@app.get("/api/cash", response_model=CashResponse)
def api_cash_get():
    try:
        return _cash_response()
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/cash", response_model=CashResponse)
def api_cash_post(body: CashUpdate):
    try:
        cash_store.save_cash(body.balances)
        global _dashboard_cache
        _dashboard_cache = {}
        return _cash_response()
    except Exception as e:
        raise HTTPException(500, str(e))


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
        raise HTTPException(500, str(e))


# ─────────────────────────────────────────────────────────────────────────
#  Ingesta + informes
# ─────────────────────────────────────────────────────────────────────────

@app.post("/api/process", response_model=ProcessResult)
def api_process():
    """Ingest pending CSVs from input/ into processing/ (mirrors CLI opts 2 & 3)."""
    global _dashboard_cache
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
            df_updated = market_data.update_tickers_in_operations(df_updated)
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

        _dashboard_cache = {}
        return {
            "ok": True,
            "stock_added": stock_added,
            "crypto_added": crypto_added,
            "files": files_seen,
            "message": f"{stock_added} operaciones y {crypto_added} movimientos crypto añadidos.",
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))


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
    global _dashboard_cache
    try:
        import main  # lazy: avoids importing the CLI menu at server startup
        main.run_analysis()
        _dashboard_cache = {}
        path = _latest_report()
        return {
            "ok": True,
            "file": os.path.basename(path) if path else None,
            "message": "Informe generado.",
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, str(e))


# ─────────────────────────────────────────────────────────────────────────
#  Static files + SPA fallback
# ─────────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/{path:path}")
def spa_fallback(path: str):
    full = os.path.join(WEB_DIR, path)
    if os.path.isfile(full):
        return FileResponse(full)
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


# ─────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("🚀  Global Position → http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
