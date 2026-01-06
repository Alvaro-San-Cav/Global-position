import time
import os
import pandas as pd
import yfinance as yf

from . import config
from . import loaders # Use loaders.INPUT_FILE

def save_ticker_update(isin, ticker):
    """Updates the ticker for a given ISIN in the CSV file."""
    try:
        if not os.path.exists(loaders.INPUT_FILE):
             return 0
             
        df = pd.read_csv(loaders.INPUT_FILE)
        # Check if ISIN exists
        mask = df['ISIN'] == isin
        if mask.any():
            df.loc[mask, 'ticker'] = ticker
            df.to_csv(loaders.INPUT_FILE, index=False)
            return mask.sum()
        return 0
    except Exception as e:
        print(f"❌ Error saving ticker to CSV: {e}")
        return 0

def lookup_ticker_yfinance(isin):
    """
    Uses yfinance Search API to look up a single ISIN and retrieve the Yahoo Ticker.
    This is the fast, primary method that doesn't require Selenium/Chrome.
    
    Returns the ticker symbol or None if not found.
    """
    try:
        search = yf.Search(isin, max_results=5)
        
        if not search.quotes:
            return None
        
        # Yahoo returns multiple results if the value trades on multiple exchanges.
        # First result is typically the most relevant (origin market or highest volume).
        # Common suffixes: .SW (Swiss), .MC (Spain), .DE (Germany), none (US)
        return search.quotes[0]['symbol']
    
    except Exception as e:
        print(f"  ⚠️ YFinance search error for {isin}: {e}")
        return None


def lookup_tickers_from_isin_yf(isin_list):
    """
    Primary method: Uses yfinance Search API to lookup ISINs.
    Fast and doesn't require Selenium/Chrome dependencies.
    
    Returns dict of {isin: ticker} for successfully resolved ISINs.
    """
    if not isin_list:
        return {}
    
    tickers = {}
    print(f"  🔍 Trying yfinance lookup for {len(isin_list)} ISINs...")
    
    for i, isin in enumerate(isin_list):
        ticker = lookup_ticker_yfinance(isin)
        if ticker:
            print(f"  ✅ ISIN: {isin} -> Ticker: {ticker}")
            tickers[isin] = ticker
        else:
            print(f"  ❌ ISIN: {isin} -> Not found via yfinance")
        
        # Rate limiting to avoid being blocked by Yahoo
        if i < len(isin_list) - 1:  # No need to sleep after last item
            time.sleep(0.5)
    
    return tickers


def lookup_ticker_from_isin(isin_list):
    """
    Uses yfinance Search API to lookup ISINs and retrieve Yahoo Tickers.
    
    Returns dict of {isin: ticker} for all resolved ISINs.
    """
    return lookup_tickers_from_isin_yf(isin_list)

def update_tickers_in_operations(df_ops):
    """
    Checks for ISINs missing tickers in the DataFrame and updates them using yfinance or Manual Input.
    Updates the CSV directly.
    """
    if 'ticker' not in df_ops.columns:
        df_ops['ticker'] = ''
    
    df_ops['ticker'] = df_ops['ticker'].fillna('').astype(str).str.strip()
    
    missing_ticker_mask = (df_ops['ticker'] == '') | (df_ops['ticker'] == 'None') | (df_ops['ticker'] == 'nan')
    isin_missing = df_ops.loc[missing_ticker_mask, 'ISIN'].dropna().unique().tolist()
    isin_missing = [i for i in isin_missing if i and str(i).strip() != '']

    if isin_missing:
        print(f"Fetching tickers for {len(isin_missing)} ISINs...")
        
        # 1. Try Automation
        isin_to_ticker = lookup_ticker_from_isin(isin_missing)
        
        updated_count = 0
        for isin, ticker in isin_to_ticker.items():
            if ticker and ticker != 'Not found':
                rows = save_ticker_update(isin, ticker)
                updated_count += rows
                df_ops.loc[df_ops['ISIN'] == isin, 'ticker'] = ticker

        # 2. Check remaining
        still_missing_mask = df_ops['ticker'].isin(['', 'None', 'Not found', 'nan'])
        still_missing_isins = df_ops.loc[still_missing_mask, 'ISIN'].dropna().unique().tolist()
        still_missing_isins = [i for i in still_missing_isins if i and str(i).strip() != '']
        
        if still_missing_isins:
            print("\n⚠️  Some ISINs could not be resolved automatically.")
            print("Please enter the Yahoo Finance Ticker manually for the following ISINs:")
            print("(Press Enter to skip)")
            
            for isin in still_missing_isins:
                product_name = df_ops.loc[df_ops['ISIN'] == isin, 'Product'].iloc[0]
                user_input = input(f"  👉 Ticker for {isin} ({product_name}): ").strip()
                if user_input:
                    rows = save_ticker_update(isin, user_input)
                    updated_count += rows
                    df_ops.loc[df_ops['ISIN'] == isin, 'ticker'] = user_input
                    
        print(f"Total updated records in CSV: {updated_count}")

    return df_ops

def fetch_prices(tickers, start_date):
    """Fetch historical prices for list of tickers."""
    end_date = pd.Timestamp.today()
    if not tickers:
        return pd.DataFrame()
        
    print(f"Downloading data for {len(tickers)} tickers...")
    try:
        data = yf.download(tickers, start=start_date, end=end_date, auto_adjust=False, progress=False)
    except Exception as e:
        print(f"Error downloading yfinance data: {e}")
        return pd.DataFrame()
    
    if data.empty:
        return data

    data = data.ffill()
    
    if isinstance(data.columns, pd.MultiIndex):
        if 'Close' in data.columns.get_level_values(0):
             data = data['Close']
        else:
             try:
                data = data.xs('Close', axis=1, level=0, drop_level=True)
             except:
                pass 

    all_days = pd.date_range(start=start_date, end=end_date)
    data = data.reindex(all_days).ffill()
    
    if 'NEPTF' in data.columns:
        data['NEPTF'] = data['NEPTF'] / 1000
    if 'PSH.L' in data.columns:
        data['PSH.L'] = data['PSH.L'] / 100
        
    return data

def fetch_fx_rates(currencies, start_date):
    """Fetch EUR conversion rates for given currencies."""
    end_date = pd.Timestamp.today()
    currencies = set(currencies) - {'EUR'}
    
    fx_map = {
        'USD': 'EURUSD=X',
        'GBX': 'EURGBP=X',
        'BTC': 'BTC-EUR',
        'ETH': 'ETH-EUR',
        'CHF': 'EURCHF=X',
        'DKK': 'EURDKK=X', 
        'PLN': 'EURPLN=X'
    }
    
    fx_prices = {}
    all_days = pd.date_range(start=start_date, end=end_date)

    for coin in currencies:
        if pd.isna(coin) or str(coin).strip() == '': continue
        
        ticker = fx_map.get(coin, f"EUR{coin}=X") 
        try:
            d = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
            if not d.empty:
                s = d['Close'].squeeze()
                
                if coin in ['BTC', 'ETH']:
                     fx_prices[coin] = s.reindex(all_days).ffill()
                else:
                     fx_prices[coin] = (1 / s).reindex(all_days).ffill()

        except Exception as e:
            print(f"Error fetching FX for {coin}: {e}")
            
    if 'GBX' in fx_prices:
        fx_prices['GBX'] = fx_prices['GBX'] / 100
        
    fx_prices['EUR'] = pd.Series(1.0, index=all_days)
    
    return pd.DataFrame(fx_prices).sort_index().ffill()
