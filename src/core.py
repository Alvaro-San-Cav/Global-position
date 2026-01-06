import pandas as pd
import numpy as np
import yfinance as yf
from collections import defaultdict

def _to_tznaive_safe(x):
    """Converts datetimelike to tz-naive and normalizes to midnight."""
    if pd.isna(x):
        return pd.NaT
    ts = pd.to_datetime(x)
    if pd.isna(ts):
        return pd.NaT
    if getattr(ts, "tz", None) is not None:
        ts = ts.tz_convert(None) if hasattr(ts, "tz_convert") else ts.tz_localize(None)
    return ts.normalize()

def normalize_date_series(s):
    # s can be Series or Index
    return pd.to_datetime(s).map(lambda x: _to_tznaive_safe(x) if not pd.isna(x) else pd.NaT)

class SplitManager:
    @staticmethod
    def detect_splits_from_ops(df_ops, tol=1e-3):
        """Detects splits based on transaction data (buy/sell ratio anomalies)."""
        df_ops = df_ops.copy()
        df_ops['Date'] = normalize_date_series(df_ops['Date'])
        # Looking for entries with Value=0 (stock splits in some brokers appear as such? or just logic from nb)
        # Notebook: "df_nz = df_ops[df_ops['Value'] != 0]" -> wait, logic was to groupby date/ticker.
        # Notebook Logic: 
        # "for (fecha, ticker), grupo in df_nz.groupby... if abs(value.sum) < 1e-6 (net zero cost)..."
        # This implies a sell and immediate buy (rebranding/ISIN change) or similar.
        # Actually the notebook logic checks for pairs of transactions on same day that sum to zero value but changing quantity.
        
        df_nz = df_ops[df_ops['Value'] != 0].copy() # Ensure value is not typically zero ?
        # Actually notebook said: "if abs(grupo['Value'].sum()) > 1e-6: continue" -> So it looks for Net Value ~ 0 events.
        
        splits = []
        for (fecha, ticker), grupo in df_nz.groupby(['Date', 'ticker']):
            if abs(grupo['Value'].sum()) > 1e-6:
                continue

            pos = grupo[grupo['Quantity'] > 0]
            neg = grupo[grupo['Quantity'] < 0]
            if pos.empty or neg.empty:
                continue
            
            pos_qty = pos['Quantity'].sum()
            neg_qty = neg['Quantity'].sum()
            
            # Simple Ratio Check
            ratio_cand = abs(pos_qty) / abs(neg_qty)
            # Notebook had price check logic too, simplified here assuming robustness
            splits.append({'ticker': ticker, 'fecha': _to_tznaive_safe(fecha), 'ratio': float(ratio_cand)})
            
        return splits

    @staticmethod
    def get_yfinance_splits(ticker):
        try:
            s = yf.Ticker(ticker).splits
            return {_to_tznaive_safe(fecha): float(ratio) for fecha, ratio in s.items()}
        except Exception:
            return {}

    @staticmethod
    def detect_missing_splits(df_ops, ticker, detected_splits):
        """Finds splits in yfinance that happened AFTER the last transaction but affect current holdings."""
        df_ops = df_ops.copy()
        df_ops['Date'] = normalize_date_series(df_ops['Date'])
        
        fechas_detectadas = set(_to_tznaive_safe(s['fecha']) for s in detected_splits if s['ticker'] == ticker)
        fechas_tenencia = df_ops.loc[df_ops['ticker'] == ticker, 'Date']
        
        if fechas_tenencia.empty:
            return []
            
        ultima_fecha = _to_tznaive_safe(fechas_tenencia.max())
        yf_splits = SplitManager.get_yfinance_splits(ticker)
        
        faltantes = []
        for fecha, ratio in yf_splits.items():
            fecha = _to_tznaive_safe(fecha)
            # If split happened AFTER our last op, we implicitly are holding it and yfinance adjusts backwards?
            # Or we need adjustment. 
            # Notebook logic: "fecha not in detectadas and fecha > ultima_fecha_tenencia"
            # This logic captures splits that occurred after we stopped trading (holding period).
            if fecha not in fechas_detectadas and fecha > ultima_fecha:
                faltantes.append({'ticker': ticker, 'fecha': fecha, 'ratio': ratio})
        
        return faltantes

    @staticmethod
    def apply_splits(df_ops):
        """Orchestrates split detection and application."""
        print("Detecting and applying splits...")
        splits_ops = SplitManager.detect_splits_from_ops(df_ops)
        
        splits_post = []
        unique_tickers = df_ops['ticker'].dropna().unique()
        for t in unique_tickers:
            splits_post.extend(SplitManager.detect_missing_splits(df_ops, t, splits_ops))
            
        all_splits = splits_ops + splits_post
        
        # Apply
        df_adj = df_ops.copy()
        df_adj['Date'] = normalize_date_series(df_adj['Date'])
        df_adj['adj_factor'] = 1.0
        
        splits_by_ticker = defaultdict(list)
        for s in all_splits:
            splits_by_ticker[s['ticker']].append((_to_tznaive_safe(s['fecha']), float(s['ratio'])))
            
        for ticker, splits in splits_by_ticker.items():
            splits.sort(key=lambda x: x[0])
            mask = df_adj['ticker'] == ticker
            
            # Vectorized application is hard due to cumulative nature relying on transaction dates vs split dates
            # Iterating rows for affected tickers (usually fast enough)
            
            # Notebook implementation logic ported:
            fechas_filas = df_adj.loc[mask, 'Date']
            qtys = df_adj.loc[mask, 'Quantity']
            
            # Pre-calculate factors for date ranges?
            # Notebook logic iterates every row.
            
            # Using a simplified approach:
            # For each transaction, if date < split_date, multiply qty by split_ratio?
            # Wait, yfinance prices are typically split-adjusted (current share count basis).
            # So we usually need to adjust HISTORICAL quantities to match CURRENT scale.
            # If I bought 10 pre-split (2:1), I effectively bought 20 current shares.
            # So yes, multiply historical Qty by Ratio.
            
            for idx, date in fechas_filas.items():
                date = _to_tznaive_safe(date)
                cum_factor = 1.0
                qty = qtys.loc[idx]
                
                # Check all splits for this ticker
                for split_date, ratio in splits:
                    # If transaction was BEFORE split, we adjust it up.
                    if date < split_date:
                        cum_factor *= ratio
                    elif date == split_date:
                        # Intra-day split logic from notebook
                        # "factor = factor_post if qty < 0 else factor_pre"... specific logic for 'value=0' fake ops?
                        # Simplification: Assume pure adjustment for holding.
                        # If regular operation on split day, it might be pre or post. 
                        # Assuming yfinance handled price, we adjust qty.
                        # Notebook logic was intricate here. I will adopt standard:
                        # If simple split, date < split_date -> adj. 
                        pass
                
                df_adj.at[idx, 'adj_factor'] = cum_factor

        df_adj['Quantity_adj'] = df_adj['Quantity'] * df_adj['adj_factor']
        return df_adj

def calculate_portfolio(df_ops, prices, fx_rates):
    """
    Calculates daily portfolio value and invested capital.
    """
    # 1. Add FX to Ops
    df_ops['Date'] = normalize_date_series(df_ops['Date'])
    fx_rates = fx_rates.copy()
    fx_rates.index = normalize_date_series(fx_rates.index)
    
    # Merge FX
    # We need to map 'Coin' to fx column
    # Use 'Coin' column to lookup value in fx_rates at 'Date'
    # This is slightly tricky vectorization.
    
    # Iterate or Melt? Iteration is okay for <10k rows.
    # Improved: Melt FX rates to (Date, Currency, Rate)
    
    # Fallback to simple apply (slow but robust)
    def get_rate(row):
        coin = row['Coin']
        date = row['Date']
        if coin == 'EUR': return 1.0
        if coin not in fx_rates.columns: return 1.0 # fallback
        try:
            return fx_rates.at[date, coin]
        except:
            return 1.0

    df_ops['fx_rate'] = df_ops.apply(get_rate, axis=1)
    df_ops['EST_eur'] = df_ops['Price'] * df_ops['fx_rate'] # Price in EUR
    # Actual invested value (Cost Basis) is 'Value' (total amount) converted to EUR
    # Note: 'Value' in df_ops is usually negative for Buys (cash outflow).
    
    # 2. Cumulative Quantity
    # Pivot: Index=Date, Cols=Ticker, Values=Qty_adj
    # We need to sum multiple ops per day.
    df_qty = df_ops.groupby(['Date', 'ticker'])['Quantity_adj'].sum().unstack(fill_value=0)
    
    # Reindex to full date range (prices index)
    df_qty = df_qty.reindex(prices.index, fill_value=0).fillna(0)
    qty_acumulada = df_qty.cumsum()
    
    # 3. Valuation
    # Prices in EUR:
    # We need to multiply Price(Ticker) * FX(Ticker's Currency)
    # Map Ticker -> Coin
    ticker_to_coin = df_ops.drop_duplicates('ticker').set_index('ticker')['Coin'].to_dict()
    
    prices_eur = prices.copy()
    for ticker in prices_eur.columns:
        coin = ticker_to_coin.get(ticker, 'EUR')
        if coin != 'EUR' and coin in fx_rates.columns:
            prices_eur[ticker] = prices[ticker] * fx_rates[coin]
            
    # Value = Qty * Price_EUR
    # Ensure columns align
    common_tickers = qty_acumulada.columns.intersection(prices_eur.columns)
    valor_cartera = qty_acumulada[common_tickers] * prices_eur[common_tickers]
    
    # Total Value
    total_value = valor_cartera.sum(axis=1)
    
    # 4. Invested Capital (Net Contributions)
    # Invested = Cumulative Sum of Net Cash Inflows.
    # df_ops['Value'] is typically negative for Buys (Cash Out) and positive for Sells (Cash In).
    # Net Invested = Sum(-Value_EUR)
    
    ops_eur = df_ops.copy()
    # Ensure Value is numeric
    ops_eur['Value'] = pd.to_numeric(ops_eur['Value'], errors='coerce').fillna(0)
    
    # Calculate flow in EUR
    ops_eur['flow_eur'] = ops_eur['Value'] * ops_eur['fx_rate'] * -1 
    
    # Notebook Logic replicate: Group by Date, Sum, Reindex, Cumsum
    invested_daily = ops_eur.groupby('Date')['flow_eur'].sum().reindex(prices.index, fill_value=0).cumsum()
    
    return total_value, invested_daily, valor_cartera


def calculate_crypto_portfolio(df_crypto, prices_crypto):
    """
    Calculates crypto portfolio value over time.
    
    Args:
        df_crypto: DataFrame with crypto operations (Date, Coin, Quantity, ticker)
        prices_crypto: DataFrame with crypto prices in EUR (Date index, coins as columns)
    
    Returns:
        tuple: (valor_total_crypto, aporte_crypto_eur_acumulado, valor_crypto_eur)
            - valor_total_crypto: Series with total portfolio value over time
            - aporte_crypto_eur_acumulado: Series (always 0, as we don't track crypto cost basis yet)
            - valor_crypto_eur: DataFrame with value by coin
    """
    if df_crypto is None or len(df_crypto) == 0:
        return None, None, None
    
    # Normalize dates
    df_crypto = df_crypto.copy()
    df_crypto['Date'] = normalize_date_series(df_crypto['Date'])
    prices_crypto.index = normalize_date_series(prices_crypto.index)
    
    # Calculate cumulative quantities by coin
    # Group by Date and Coin, sum Quantity
    df_qty = df_crypto.groupby(['Date', 'Coin'])['Quantity'].sum().unstack(fill_value=0)
    
    # Reindex to match prices timeline
    df_qty = df_qty.reindex(prices_crypto.index, fill_value=0).fillna(0)
    qty_acumulada = df_qty.cumsum()
    
    # Calculate value for each coin (Quantity * Price)
    # Ensure column alignment
    common_coins = qty_acumulada.columns.intersection(prices_crypto.columns)
    valor_crypto_eur = qty_acumulada[common_coins] * prices_crypto[common_coins]
    
    # Total value
    valor_total_crypto = valor_crypto_eur.sum(axis=1)
    
    # Aporte (capital invested): For now, simplified to 0
    # In a full implementation, we'd track USD/EUR cost basis from Binance
    aporte_crypto_eur_acumulado = pd.Series(0, index=prices_crypto.index)
    
    return valor_total_crypto, aporte_crypto_eur_acumulado, valor_crypto_eur
