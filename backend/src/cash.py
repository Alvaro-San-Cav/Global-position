"""
cash.py – Cash balances held in the brokerage account.

Cash is a set of balances per currency (not market operations), stored in
processing/cash.json as {"EUR": 1234.56, "USD": 500}. It is reported in the
dashboard as an "Efectivo" asset class but is intentionally kept OUT of the P&L
metrics (plusvalía, TWR, CAGR) — cash has no market return.
"""

import json
import logging
import os
import time

import pandas as pd

from . import config

log = logging.getLogger("ingesta.cash")


def load_cash() -> dict[str, float]:
    """Return {CURRENCY: amount} of cash balances (empty if none)."""
    if not os.path.exists(config.CASH_FILE):
        return {}
    try:
        with open(config.CASH_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if raw is not None and not isinstance(raw, dict):
            raise ValueError("cash.json no es un objeto JSON")
    except Exception as e:
        # Corrupt file: move it aside so a later save_cash cannot silently
        # destroy the user's data and we don't re-log on every call.
        bak = f"{config.CASH_FILE}.corrupt-{int(time.time())}.bak"
        try:
            os.replace(config.CASH_FILE, bak)
        except OSError:
            bak = "(no se pudo renombrar)"
        msg = f"cash.json ilegible ({e}); conservado como {bak}"
        log.error(msg)
        try:
            config.get_logger().error(msg)
        except Exception:
            pass
        return {}
    out: dict[str, float] = {}
    for k, v in (raw or {}).items():
        cur = str(k).strip().upper()
        if not cur:
            continue
        try:
            amount = float(v)
        except (TypeError, ValueError):
            continue
        if amount != 0:
            out[cur] = amount
    return out


def save_cash(balances: dict) -> dict[str, float]:
    """Persist cash balances, dropping empty/zero/invalid entries. Returns the cleaned dict."""
    clean: dict[str, float] = {}
    for k, v in (balances or {}).items():
        cur = str(k).strip().upper()
        if not cur:
            continue
        try:
            amount = float(v)
        except (TypeError, ValueError):
            continue
        if amount != 0:
            clean[cur] = round(amount, 2)
    os.makedirs(config.PROCESSING_DIR, exist_ok=True)
    with config.DATA_LOCK:
        config.atomic_write_json(config.CASH_FILE, clean, indent=2)
    return clean


def cash_to_eur(balances: dict[str, float], fx_rates: pd.DataFrame | None,
                missing: list[str] | None = None) -> dict[str, float]:
    """Convert each cash balance to EUR using the latest FX rate.

    fx_rates: DataFrame indexed by date, columns are currencies with values
    XXX→EUR (as built by market_data.fetch_fx_rates). EUR is 1.0. Currencies
    without a rate are assumed already in EUR (rate 1.0) for backwards
    compatibility; pass a list as `missing` to collect those currencies so the
    caller can warn instead of silently assuming 1.0.
    """
    out: dict[str, float] = {}
    latest = None
    if fx_rates is not None and not fx_rates.empty:
        latest = fx_rates.ffill().iloc[-1]
    for cur, amount in balances.items():
        if cur == "EUR":
            rate = 1.0
        elif latest is not None and cur in latest.index and pd.notna(latest[cur]):
            try:
                rate = float(latest[cur])
            except (TypeError, ValueError):
                rate = 1.0
                if missing is not None:
                    missing.append(cur)
        else:
            rate = 1.0
            if missing is not None:
                missing.append(cur)
        out[cur] = round(amount * rate, 2)
    return out
