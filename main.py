import sys
import os
import pandas as pd
from src import loaders, market_data, core, reporter

def run_analysis():
    print("🚀 Starting Global Position Analysis (Stocks Only)...")

    # 1. Load Data (from CSV)
    try:
        df_ops = loaders.load_operations()
        print(f"✅ Operations loaded: {len(df_ops)} records.")
    except Exception as e:
        print(f"❌ Error loading operations: {e}")
        return

    # 2. Update Tickers
    try:
        df_ops = market_data.update_tickers_in_operations(df_ops)
        tickers = [t for t in df_ops['ticker'].dropna().unique().tolist() if t and str(t).strip() != '']
        currencies = df_ops['Coin'].dropna().unique().tolist()
        print(f"ℹ️  Unique Tickers: {len(tickers)}")
    except Exception as e:
        print(f"❌ Error updating tickers: {e}")
        return

    # 3. Market Data
    try:
        print("📥 Fetching historical prices...")
        start_date = df_ops['Date'].min()
        prices = market_data.fetch_prices(tickers, start_date)
        
        print("📥 Fetching FX rates...")
        fx_rates = market_data.fetch_fx_rates(currencies, start_date)
    except Exception as e:
        print(f"❌ Error fetching market data: {e}")
        return

    # 4. Splits Logic
    try:
        df_adj = core.SplitManager.apply_splits(df_ops)
    except Exception as e:
        print(f"❌ Error applying splits: {e}")
        return

    # 5. Valuation
    try:
        # Calculate Portfolio (Stocks)
        total_value, invested_daily, valor_cartera = core.calculate_portfolio(df_adj, prices, fx_rates)
        
        # Summary Console
        if total_value.empty:
            print("⚠️ Portfolio value is empty. Check data availability.")
            return

        current_val = total_value.iloc[-1]
        invested_val = invested_daily.iloc[-1]
        pnl = current_val - invested_val
        pnl_pct = (pnl / invested_val) * 100 if invested_val != 0 else 0
        
        print("\n" + "="*60)
        print("            💼 PORTFOLIO FINANCIAL SUMMARY (STOCKS)            ")
        print("="*60)
        print(f"📅 Date: {total_value.index[-1].date()}")
        print(f"💰 Net Invested Capital:      € {invested_val:,.2f}")
        print(f"📊 Current Portfolio Value:   € {current_val:,.2f}")
        print(f"📈 P&L:                       € {pnl:,.2f} ({pnl_pct:+.2f}%)")
        print("="*60)
        
        # 6. Crypto Portfolio (NEW)  
        crypto_value = crypto_invested = crypto_breakdown = None
        try:
            print("\n🪙 Loading crypto data...")
            df_crypto = loaders.load_crypto_operations()
            
            if df_crypto is not None and len(df_crypto) > 0:
                # Get unique crypto tickers from data
                crypto_tickers = df_crypto['Coin'].dropna().unique().tolist()
                
                # Fetch crypto prices (they're in EUR already from yfinance)
                if crypto_tickers:
                    # Fetch prices for BTC-EUR, ETH-EUR, etc.
                    crypto_ticker_list = [f"{coin}-EUR" for coin in crypto_tickers]
                    start_date_crypto = df_crypto['Date'].min()
                    
                    print(f"📥 Fetching crypto prices for {len(crypto_tickers)} coins...")
                    prices_crypto_raw = market_data.fetch_prices(crypto_ticker_list, start_date_crypto)
                    
                    # Rename columns to match Coin names (remove -EUR suffix)
                    prices_crypto = prices_crypto_raw.copy()
                    prices_crypto.columns = [col.replace('-EUR', '') for col in prices_crypto.columns]
                    
                    # Calculate crypto portfolio
                    crypto_value, crypto_invested, crypto_breakdown = core.calculate_crypto_portfolio(
                        df_crypto, prices_crypto
                    )
                    
                    if crypto_value is not None and not crypto_value.empty:
                        crypto_curr = crypto_value.iloc[-1]
                        print(f"\n✅ Crypto Portfolio Value: € {crypto_curr:,.2f}")
            else:
                print("ℹ️  No crypto data found.")
        
        except Exception as e:
            print(f"⚠️ Warning: Could not load crypto data: {e}")
            import traceback
            traceback.print_exc()
        
        # 7. Generator PDF (with both stocks and crypto if available)
        data = {
            'stocks': {'value': total_value, 'invested': invested_daily, 'breakdown': valor_cartera}
        }
        
        if crypto_value is not None:
            data['crypto'] = {'value': crypto_value, 'invested': crypto_invested, 'breakdown': crypto_breakdown}
        
        reporter.generate_full_report(data, output_dir="output")
        
    except Exception as e:
        print(f"❌ Error calculating valuation: {e}")
        import traceback
        traceback.print_exc()
        return

def process_transactions():
    print("🔎 Checking for new transactions in 'input/'...")
    try:
        df_ops = loaders.load_operations()
        df_updated = loaders.process_new_transactions(df_ops)
        
        # Match tickers
        print("🔍 Matching tickers...")
        df_updated = market_data.update_tickers_in_operations(df_updated)
        
        # Save to processing/operaciones.csv
        processing_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processing")
        if not os.path.exists(processing_dir):
            os.makedirs(processing_dir)
        
        output_path = os.path.join(processing_dir, "operaciones.csv")
        # Enforce column order and fixed values
        
        # 1. Remove duplicate columns (keep first)
        df_updated = df_updated.loc[:, ~df_updated.columns.duplicated()]
        
        df_export = df_updated.copy()
        
        # 2. Fix Numeric Format for Price and Value
        for col in ['Price', 'Value']:
            if col in df_export.columns:
                 df_export[col] = df_export[col].apply(loaders.clean_eu_float)

        # 3. Enforce eur = EUR
        df_export['eur'] = 'EUR'
        
        cols_to_save = ["Date", "Product", "ISIN", "Quantity", "Price", "Coin", "Value", "eur", "ticker"]
        df_export[cols_to_save].to_csv(output_path, index=False)
        print(f"✅ Operations saved to {output_path}")
        
        print("✅ Transaction processing complete.")
    except Exception as e:
        print(f"❌ Error processing transactions: {e}")

def process_crypto_transactions():
    """Process crypto transactions from Binance exports in input/ folder."""
    print("🪙 Checking for Binance crypto exports in 'input/'...")
    try:
        df_crypto = loaders.process_binance_transactions()
        if df_crypto is not None and len(df_crypto) > 0:
            print(f"\n📊 Crypto Portfolio Summary:")
            print(f"   • Total transactions: {len(df_crypto)}")
            for coin in df_crypto['Coin'].unique():
                qty = df_crypto[df_crypto['Coin'] == coin]['Quantity'].sum()
                print(f"   • {coin}: {qty:.8f}")
        print("✅ Crypto transaction processing complete.")
    except Exception as e:
        print(f"❌ Error processing crypto transactions: {e}")
        import traceback
        traceback.print_exc()

def main():
    while True:
        print("\n=== GLOBAL POSITION MANAGER ===")
        print("1. 📊 Run Analysis & Generate Report")
        print("2. 📥 Process New Transactions (from input/)")
        print("3. 🪙 Process Crypto Transactions (Binance)")
        print("4. 🚪 Exit")
        
        choice = input("Select an option: ")
        
        if choice == "1":
            run_analysis()
        elif choice == "2":
            process_transactions()
        elif choice == "3":
            process_crypto_transactions()
        elif choice == "4":
            print("Bye!")
            sys.exit()
        else:
            print("Invalid option.")

if __name__ == "__main__":
    main()

