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

from collections import deque

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────
#  FIFO gain/loss calculation
# ─────────────────────────────────────────────────────────────────────────

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
    fx_rates : DataFrame with currency columns and daily FX rates (coin→EUR).
               If None, prices are assumed to already be in EUR.

    Returns
    -------
    DataFrame with columns:
        ticker, fecha_venta, qty_vendida,
        precio_venta_eur, coste_base_eur, plusvalia_eur,
        annyo  (fiscal year of the sale)
    """
    df = df_ops.copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.sort_values('Date')

    qty_col = 'Quantity_adj' if 'Quantity_adj' in df.columns else 'Quantity'
    df['_qty'] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
    df['_price'] = pd.to_numeric(df['Price'], errors='coerce').fillna(0)

    # Build FX lookup: date → {currency: rate}
    fx_lookup: dict[pd.Timestamp, dict[str, float]] = {}
    if fx_rates is not None:
        fx = fx_rates.copy()
        fx.index = pd.to_datetime(fx.index)
        fx = fx.sort_index().ffill()
        for date, row in fx.iterrows():
            fx_lookup[date.normalize()] = row.to_dict()

    def _to_eur(price: float, coin: str, date: pd.Timestamp) -> float:
        if not coin or coin.upper() == 'EUR':
            return price
        if pd.isna(date):
            return price
        day = date.normalize()
        rates = fx_lookup.get(day, {})
        # Try exact date, then nearest previous
        if not rates and fx_lookup:
            prev = [d for d in fx_lookup if d <= day]
            if prev:
                rates = fx_lookup[max(prev)]
        rate = rates.get(coin.upper(), rates.get(coin, None))
        return price * rate if rate else price

    records: list[dict] = []

    for ticker, grp in df.groupby('ticker'):
        lots: deque[dict] = deque()  # {'qty': float, 'price_eur': float, 'date': Timestamp}

        for _, row in grp.sort_values('Date').iterrows():
            date  = row['Date']
            if pd.isna(date):
                continue
            qty   = float(row['_qty'])
            price = float(row['_price'])
            coin  = str(row.get('Coin', 'EUR'))

            price_eur = _to_eur(price, coin, date)

            if qty > 0:
                # Buy – add lot to queue
                lots.append({'qty': qty, 'price_eur': price_eur, 'date': date})

            elif qty < 0:
                # Sell – consume lots FIFO
                qty_to_sell = abs(qty)
                cost_basis  = 0.0
                proceeds    = qty_to_sell * price_eur

                while qty_to_sell > 1e-9 and lots:
                    lot = lots[0]
                    matched = min(lot['qty'], qty_to_sell)
                    cost_basis  += matched * lot['price_eur']
                    lot['qty']   -= matched
                    qty_to_sell  -= matched
                    if lot['qty'] < 1e-9:
                        lots.popleft()

                # Remaining qty_to_sell with no lot (short or missing history)
                # treated as zero cost basis
                gain = proceeds - cost_basis
                records.append({
                    'ticker':          ticker,
                    'fecha_venta':     date,
                    'qty_vendida':     abs(qty),
                    'precio_venta_eur': price_eur,
                    'coste_base_eur':  cost_basis,
                    'plusvalia_eur':   gain,
                    'annyo':           date.year,
                })

    if not records:
        return pd.DataFrame(columns=[
            'ticker', 'fecha_venta', 'qty_vendida',
            'precio_venta_eur', 'coste_base_eur', 'plusvalia_eur', 'annyo',
        ])

    return pd.DataFrame(records).sort_values(['fecha_venta', 'ticker']).reset_index(drop=True)


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
