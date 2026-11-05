"""
tax.py – Fiscal gain/loss calculation using FIFO matching.

For each ticker, buy lots are queued in chronological order.
Each sell consumes lots from the front of the queue (oldest first).

Usage
-----
    from src.tax import calculate_fifo_gains, tax_summary

    df_gains = calculate_fifo_gains(df_ops, fx_rates)
    summary  = tax_summary(df_gains)
"""

from __future__ import annotations

import logging
from collections import deque

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────
#  FIFO gain/loss calculation
# ─────────────────────────────────────────────────────────────────────────

_GAIN_COLUMNS = [
    'ticker', 'fecha_venta', 'qty_vendida',
    'precio_venta_eur', 'coste_base_eur', 'plusvalia_eur', 'annyo',
    'sin_historial', 'sin_fx',
]

_EPS = 1e-9
_log = logging.getLogger(__name__)


def _build_fx_resolver(fx_rates: pd.DataFrame | None):
    """Return ``rate(coin, day) -> float | None`` (coin -> EUR).

    Rates are forward-filled and back-filled (first known rate for earlier
    dates); lookup is a binary search on the sorted index (no O(n) scans).
    Returns None for the rate when the coin has no usable rate.
    """
    if fx_rates is None:
        return None
    fx = fx_rates.copy()
    fx.index = pd.to_datetime(fx.index)
    fx = fx[~fx.index.duplicated(keep='last')].sort_index().ffill().bfill()
    idx = fx.index
    arrays = {str(c).upper(): fx[c].to_numpy(dtype=float) for c in fx.columns}

    def rate(coin: str, day: pd.Timestamp):
        arr = arrays.get(coin.upper())
        if arr is None or len(idx) == 0:
            return None
        pos = int(idx.searchsorted(day, side='right')) - 1
        if pos < 0:
            pos = 0  # before first known rate -> first known rate
        r = arr[pos]
        if pd.isna(r) or r <= 0:
            return None
        return float(r)

    return rate


def calculate_fifo_gains(
    df_ops: pd.DataFrame,
    fx_rates: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Compute realised FIFO gains for all stock operations.

    Parameters
    ----------
    df_ops   : Stock operations DataFrame with columns:
               Date, ticker, Quantity (Quantity_adj if splits applied), Price, Coin
    fx_rates : DataFrame with currency columns and daily FX rates (coin->EUR).
               If None, prices are assumed to already be in EUR.

    Returns
    -------
    DataFrame with columns:
        ticker, fecha_venta, qty_vendida,
        precio_venta_eur, coste_base_eur, plusvalia_eur,
        annyo  (fiscal year of the sale),
        sin_historial (bool) - the sale exceeded the lots on record (missing
            purchase history / short); the unmatched quantity has NO cost basis
            and therefore the gain is overstated until the history is loaded,
        sin_fx (bool) - no FX rate was available for the row's currency; the
            row's EUR amounts are reported as 0.0 and a warning is logged.

    Ordering: operations are sorted with a STABLE sort by date; on the same day
    purchases are processed before sales so a same-day buy+sell does not look
    like a sale without history.

    Corporate actions: a same-day, same-ticker pair of opposite quantities with
    (approximately) zero net value and clearly different unit prices is treated
    as a split / swap. It produces NO sale row; the consumed lots are carried
    over to the new quantity keeping total cost basis and acquisition date.

    Known limitations (not implemented):
      * Broker commissions / fees are not part of the cost basis nor deducted
        from proceeds (the engine only sees Price and Quantity).
      * The Spanish "regla de los 2 meses" (anti-wash-sale: a loss is not
        computable if the same security is repurchased within 2 months, 1 year
        for non-listed) is NOT applied; losses are always recognised.
      * Single EUR conversion at the operation date.
    """
    df = df_ops.copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

    qty_col = 'Quantity_adj' if 'Quantity_adj' in df.columns else 'Quantity'
    df['_qty'] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
    df['_price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)
    # Buys before sells on the same day; stable so file order breaks other ties.
    df['_is_sell'] = (df['_qty'] < 0).astype(int)
    df = df.sort_values(['Date', '_is_sell'], kind='stable')

    fx_rate = _build_fx_resolver(fx_rates)

    def _to_eur(price: float, coin: str, date: pd.Timestamp) -> tuple[float, bool]:
        """Return (price_eur, ok). ok=False when the currency has no rate."""
        if not coin or coin.upper() in ('EUR', 'NAN', 'NONE'):
            return price, True
        if fx_rate is None:  # no FX provided: prices already in EUR
            return price, True
        r = fx_rate(coin, date.normalize())
        if r is None:
            return float('nan'), False
        return price * r, True

    records: list[dict] = []

    def _consume(lots: deque, qty: float) -> tuple[float, float, pd.Timestamp | None]:
        """FIFO-consume ``qty`` from lots -> (cost, unmatched_qty, earliest lot date)."""
        cost = 0.0
        first_date = None
        while qty > _EPS and lots:
            lot = lots[0]
            matched = min(lot['qty'], qty)
            cost += matched * lot['price_eur']
            if first_date is None:
                first_date = lot['date']
            lot['qty'] -= matched
            qty -= matched
            if lot['qty'] < _EPS:
                lots.popleft()
        return cost, max(qty, 0.0), first_date

    for ticker, grp in df.groupby('ticker', sort=False):
        lots: deque[dict] = deque()  # {'qty', 'price_eur', 'date'}
        grp = grp[grp['Date'].notna()]

        for date, day in grp.groupby('Date', sort=True):
            rows = []
            for _, row in day.iterrows():
                qty = float(row['_qty'])
                if qty == 0:
                    continue
                coin = str(row.get('Coin', 'EUR')).strip()
                price_eur, ok = _to_eur(float(row['_price']), coin, date)
                rows.append((qty, price_eur, ok, coin))
            if not rows:
                continue

            # -- split / swap pair: opposite sides, value-neutral, prices differ --
            buys = [r for r in rows if r[0] > 0]
            sells = [r for r in rows if r[0] < 0]
            if buys and sells and all(r[2] for r in rows):
                b_qty = sum(r[0] for r in buys)
                s_qty = -sum(r[0] for r in sells)
                b_val = sum(r[0] * r[1] for r in buys)
                s_val = -sum(r[0] * r[1] for r in sells)
                gross = max(b_val, s_val)
                if gross > 0 and abs(b_val - s_val) <= 1e-3 * gross and s_qty > 0 and b_qty > 0:
                    b_unit, s_unit = b_val / b_qty, s_val / s_qty
                    if abs(b_unit / s_unit - 1.0) > 0.01:
                        cost, unmatched, first_date = _consume(lots, s_qty)
                        cost += unmatched * s_unit  # no history: carry at sell price
                        lots.append({
                            'qty': b_qty,
                            'price_eur': cost / b_qty,
                            'date': first_date if first_date is not None else date,
                        })
                        continue

            for qty, price_eur, ok, coin in rows:  # buys already first (stable order)
                if qty > 0:
                    if not ok:
                        _log.warning("tax: sin tipo FX para %s (%s, %s); compra valorada a 0 EUR",
                                     coin, ticker, date.date())
                    lots.append({'qty': qty, 'price_eur': price_eur if ok else 0.0, 'date': date})
                    continue

                qty_to_sell = -qty
                cost_basis, unmatched, _ = _consume(lots, qty_to_sell)
                proceeds = qty_to_sell * price_eur if ok else 0.0
                if not ok:
                    _log.warning("tax: sin tipo FX para %s (%s, %s); venta marcada sin_fx",
                                 coin, ticker, date.date())
                records.append({
                    'ticker':           ticker,
                    'fecha_venta':      date,
                    'qty_vendida':      qty_to_sell,
                    'precio_venta_eur': price_eur if ok else 0.0,
                    'coste_base_eur':   cost_basis,
                    'plusvalia_eur':    (proceeds - cost_basis) if ok else 0.0,
                    'annyo':            date.year,
                    'sin_historial':    bool(unmatched > 1e-6),
                    'sin_fx':           not ok,
                })

    if not records:
        return pd.DataFrame(columns=_GAIN_COLUMNS)

    out = pd.DataFrame(records)
    return out.sort_values(['fecha_venta', 'ticker'], kind='stable').reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────
#  Summary aggregation
# ─────────────────────────────────────────────────────────────────────────

def tax_summary(df_gains: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate FIFO gains by fiscal year and ticker.

    Returns DataFrame with columns:
        annyo, ticker, plusvalia_eur, n_ventas
    """
    if df_gains.empty:
        return pd.DataFrame(columns=['annyo', 'ticker', 'plusvalia_eur', 'n_ventas'])

    summary = (
        df_gains
        .groupby(['annyo', 'ticker'], as_index=False)
        .agg(
            plusvalia_eur=('plusvalia_eur', 'sum'),
            n_ventas=('qty_vendida', 'count'),
        )
        .sort_values(['annyo', 'plusvalia_eur'], ascending=[True, False])
    )
    return summary


def annual_tax_summary(df_gains: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate total gains/losses per fiscal year.

    Returns DataFrame with columns:
        annyo, plusvalia_total_eur, plusvalias_eur, minusvalias_eur, n_ventas
    """
    if df_gains.empty:
        return pd.DataFrame()

    result = (
        df_gains
        .groupby('annyo', as_index=False)
        .agg(
            plusvalia_total_eur=('plusvalia_eur', 'sum'),
            n_ventas=('qty_vendida', 'count'),
        )
    )
    # Compute positive/negative separately
    pos = df_gains[df_gains['plusvalia_eur'] > 0].groupby('annyo')['plusvalia_eur'].sum()
    neg = df_gains[df_gains['plusvalia_eur'] < 0].groupby('annyo')['plusvalia_eur'].sum()

    result = result.set_index('annyo')
    result['plusvalias_eur']   = pos
    result['minusvalias_eur']  = neg
    result = result.fillna(0).reset_index()
    return result.sort_values('annyo')
