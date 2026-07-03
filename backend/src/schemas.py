"""
schemas.py – Canonical data contract for stock operations.

All loaders must produce DataFrames that conform to OPERACION_REQUIRED_COLS
before data is concatenated or persisted.  Call validate_dataframe() to
surface column mismatches as explicit errors rather than silent NaN columns.
"""

from __future__ import annotations

import pandas as pd

# Columns every operation row must have
OPERACION_REQUIRED_COLS: frozenset[str] = frozenset({
    "Date", "Product", "ISIN", "Quantity", "Price", "Value",
})

# Columns that are optional but recognised
OPERACION_OPTIONAL_COLS: frozenset[str] = frozenset({
    "Coin", "eur", "ticker",
})

OPERACION_ALL_COLS: frozenset[str] = OPERACION_REQUIRED_COLS | OPERACION_OPTIONAL_COLS

# Expected dtypes after normalisation (used for documentation; not enforced here)
OPERACION_DTYPES: dict[str, str] = {
    "Date":     "datetime64[ns]",
    "Product":  "object",
    "ISIN":     "object",
    "Quantity": "float64",
    "Price":    "float64",
    "Coin":     "object",
    "Value":    "float64",
    "eur":      "object",
    "ticker":   "object",
}


def validate_dataframe(df: pd.DataFrame, source_name: str = "desconocida") -> None:
    """
    Raise ValueError if df is missing any of OPERACION_REQUIRED_COLS.

    Parameters
    ----------
    df          : DataFrame to validate
    source_name : Human-readable label for error messages
    """
    missing = OPERACION_REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"Fuente '{source_name}' produce un DataFrame sin columnas obligatorias: "
            f"{sorted(missing)}. "
            f"Columnas disponibles: {sorted(df.columns.tolist())}"
        )


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply standard type coercions to a raw operations DataFrame.
    Returns a copy; does not mutate the input.
    """
    df = df.copy()
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    for col in ("Quantity", "Price", "Value"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "eur" not in df.columns:
        df["eur"] = "EUR"
    return df
