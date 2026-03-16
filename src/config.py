"""
config.py – Paths and settings for Global Position.

All paths are relative to the repo root.
Custom data sources (extra stock feeds, crypto exchanges) are defined
in sources.json at the repo root – edit that file to add your own.
"""

import json
import os

# ── Paths ────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR      = os.path.join(BASE_DIR, "input")
PROCESSING_DIR = os.path.join(BASE_DIR, "processing")
OUTPUT_DIR     = os.path.join(BASE_DIR, "output")
HIST_DIR       = os.path.join(OUTPUT_DIR, "hist-inf")

# Master database files (processing/)
OPERATIONS_FILE = os.path.join(PROCESSING_DIR, "operaciones.csv")
CRYPTO_DB       = os.path.join(PROCESSING_DIR, "crypto.csv")

# Expected column order for stock operations
OPERATIONS_COLS = [
    "Date", "Product", "ISIN", "Quantity", "Price", "Coin", "Value", "eur", "ticker"
]

# ── Custom sources (from sources.json) ───────────────────────────────────
SOURCES_FILE = os.path.join(BASE_DIR, "sources.json")

def load_sources() -> dict:
    """Return the parsed sources.json or empty structure if it doesn't exist."""
    if not os.path.exists(SOURCES_FILE):
        return {"stock_sources": [], "crypto_sources": []}
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def get_stock_sources() -> list[dict]:
    """Return enabled custom stock sources."""
    return [s for s in load_sources().get("stock_sources", []) if s.get("enabled", False)]

def get_crypto_sources() -> list[dict]:
    """Return enabled custom crypto sources."""
    return [s for s in load_sources().get("crypto_sources", []) if s.get("enabled", False)]

def get_price_adjustments() -> dict[str, float]:
    """Return {ticker: divisor} for price adjustments (e.g. NEPTF: 1000)."""
    raw = load_sources().get("price_adjustments", {})
    return {k: float(v) for k, v in raw.items() if k != "_comment"}

def get_fx_adjustments() -> dict[str, float]:
    """Return {currency: divisor} for FX adjustments (e.g. GBX: 100)."""
    raw = load_sources().get("fx_adjustments", {})
    return {k: float(v) for k, v in raw.items() if k != "_comment"}

