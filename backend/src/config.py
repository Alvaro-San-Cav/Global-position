"""
config.py – Paths and settings for Global Position.

All paths are relative to the repo root.
Custom data sources (extra stock feeds, crypto exchanges) are defined
in sources.json at the repo root – edit that file to add your own.
"""

import json
import logging
import os

# ── Paths ────────────────────────────────────────────────────────────────
# Repo root: backend/src/config.py → three levels up.
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUT_DIR      = os.path.join(BASE_DIR, "input")
PROCESSING_DIR = os.path.join(BASE_DIR, "processing")
OUTPUT_DIR     = os.path.join(BASE_DIR, "output")
HIST_DIR       = os.path.join(OUTPUT_DIR, "hist-inf")

# Master database files (processing/)
OPERATIONS_FILE = os.path.join(PROCESSING_DIR, "operaciones.csv")
CRYPTO_DB       = os.path.join(PROCESSING_DIR, "crypto.csv")

# Backup & audit log
BACKUP_DIR           = os.path.join(PROCESSING_DIR, "backup")
LOG_FILE             = os.path.join(PROCESSING_DIR, "ingesta.log")
BACKUP_RETENTION_DAYS = 30

# Incremental price cache
PRICE_CACHE_DIR   = os.path.join(PROCESSING_DIR, "cache")
PRICES_CACHE_FILE = os.path.join(PRICE_CACHE_DIR, "prices.csv")
FX_CACHE_FILE     = os.path.join(PRICE_CACHE_DIR, "fx.csv")

# Expected column order for stock operations
OPERATIONS_COLS = [
    "Date", "Product", "ISIN", "Quantity", "Price", "Coin", "Value", "eur", "ticker"
]

# ── Custom sources (from sources.json) ───────────────────────────────────
SOURCES_FILE = os.path.join(BASE_DIR, "backend", "sources.json")

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

def get_benchmark() -> tuple[str, str]:
    """Return (ticker, name) for the configured benchmark, or ('', '') if disabled."""
    bm = load_sources().get("benchmark", {})
    ticker = bm.get("ticker", "").strip()
    name   = bm.get("name", ticker)
    return ticker, name


def get_asset_classes() -> dict[str, str]:
    """Return {SYMBOL_UPPER: asset_class} overrides from sources.json.

    Overrides win over the automatic classifier (core.classify_asset), letting
    the user pin a ticker to a class (e.g. a gold miner to "Acciones").
    """
    raw = load_sources().get("asset_classes", {})
    out: dict[str, str] = {}
    for k, v in raw.items():
        if k == "_comment" or not str(v).strip():
            continue
        out[str(k).strip().upper()] = str(v).strip()
    return out


def get_zero_value_flow_from_est_tickers() -> list[str]:
    """
    Return tickers that should estimate invested flow when Value==0.

    Useful for custom vest feeds (e.g. SAP) that intentionally persist Value=0
    but still need an estimated contribution on vest dates, mirroring notebook
    behavior for capital line continuity.
    """
    raw = load_sources().get("zero_value_flow_from_est_eur_tickers", [])
    out: list[str] = []
    for item in raw:
        s = str(item).strip()
        if s:
            out.append(s)
    return out

# ── Shared ingesta logger ─────────────────────────────────────────────────

def get_logger() -> logging.Logger:
    """Return (and lazily configure) the shared ingesta file logger."""
    logger = logging.getLogger("ingesta")
    if not logger.handlers:
        os.makedirs(PROCESSING_DIR, exist_ok=True)
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

# ── sources.json validation ───────────────────────────────────────────────

_REQUIRED_STOCK_FIELDS  = {"name", "file_pattern", "column_map"}
_REQUIRED_CRYPTO_FIELDS = {"name", "file_pattern", "column_map"}

def validate_sources() -> None:
    """Raise ValueError if sources.json is missing required fields in any source."""
    data = load_sources()

    for i, src in enumerate(data.get("stock_sources", [])):
        missing = _REQUIRED_STOCK_FIELDS - set(src.keys())
        if missing:
            raise ValueError(
                f"sources.json stock_sources[{i}] ('{src.get('name', '?')}') "
                f"tiene campos obligatorios ausentes: {sorted(missing)}"
            )

    for i, src in enumerate(data.get("crypto_sources", [])):
        missing = _REQUIRED_CRYPTO_FIELDS - set(src.keys())
        if missing:
            raise ValueError(
                f"sources.json crypto_sources[{i}] ('{src.get('name', '?')}') "
                f"tiene campos obligatorios ausentes: {sorted(missing)}"
            )

