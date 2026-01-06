import pandas as pd
import os
import sys

# Ensure we can import from database package in root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from database import manager (Removed for CSV migration)
from . import config

INPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "input", "Transactions.csv")
OPERATIONS_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "processing", "operaciones.csv")

def load_operations():
    """Loads operations from processing/operaciones.csv (master database)."""
    if not os.path.exists(OPERATIONS_DB):
        # Return empty DF with expected columns if DB doesn't exist yet
        return pd.DataFrame(columns=["Date", "Product", "ISIN", "Quantity", "Price", "Coin", "Value", "eur", "ticker"])
    
    try:
        df = pd.read_csv(OPERATIONS_DB)
        
        # Normalize header: remove leading/trailing spaces
        df.columns = [c.strip() for c in df.columns]
        
        # Ensure expected columns exist
        expected_cols = ["Date", "Product", "ISIN", "Quantity", "Price", "Coin", "Value", "eur", "ticker"]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = None
        
        # Ensure Date is datetime
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        return df.sort_values('Date')
        
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return pd.DataFrame(columns=["Date", "Product", "ISIN", "Quantity", "Price", "Coin", "Value", "eur", "ticker"])

def clean_eu_float(x):
    """Converts European number format (1.234,56) to python float (1234.56)."""
    if pd.isna(x) or str(x).strip() == '':
        return 0.0
    x_str = str(x)
    clean_str = x_str.replace('.', '').replace(',', '.')
    try:
        return float(clean_str)
    except ValueError:
        return 0.0

def parse_date(date_str):
    try:
        from datetime import datetime
        return datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d")
    except:
        return date_str

def process_new_transactions(df_ops):
    """
    Checks for new CSV files in input/ folder (INCLUDING Transactions.csv).
    Parses them (simulating Degiro/Broker format) and appends valid rows to processing/operaciones.csv.
    Deletes all processed files including Transactions.csv.
    """
    input_dir = os.path.dirname(INPUT_FILE)
    if not os.path.exists(input_dir):
        return df_ops

    # Identify ALL CSV files in input/ (including Transactions.csv)
    new_files = [
        f for f in os.listdir(input_dir) 
        if f.lower().endswith(".csv")
    ]
    
    if not new_files:
        return df_ops

    print(f"Indexando {len(new_files)} nuevos ficheros de transacciones...")
    
    # Load current "database" from processing/operaciones.csv
    if os.path.exists(OPERATIONS_DB):
        df_current = pd.read_csv(OPERATIONS_DB)
    else:
        df_current = pd.DataFrame(columns=["Date", "Product", "ISIN", "Quantity", "Price", "Coin", "Value", "eur", "ticker", "order_id"])

    # Ensure columns for appending
    cols = ["Date", "Product", "ISIN", "Quantity", "Price", "Coin", "Value", "eur", "ticker", "order_id"]
    for c in cols:
        if c not in df_current.columns:
            df_current[c] = None

    new_rows = []
    
    for fname in new_files:
        filepath = os.path.join(input_dir, fname)
        try:
            df_new = pd.read_csv(filepath)
            
            # NOTEBOOK LOGIC REPLICATION
            # Renaming columns based on relative position if Headers match partial naming
            col_names = df_new.columns.tolist()
            
            if "Price" in col_names and "Value" in col_names:
                price_idx = col_names.index("Price")
                value_idx = col_names.index("Value")
                
                # Rename column after 'Price' to 'Coin'
                if price_idx + 1 < len(col_names):
                     # Only if it's not already named Coin? Notebook forces rename.
                     new_col = col_names[price_idx + 1]
                     df_new.rename(columns={new_col: "Coin"}, inplace=True)
                     
                # Rename column after 'Value' to 'eur' (Local Value -> eur?)
                # Notebook logic: "Renombrar la columna después de 'Value' a 'eur'"
                if value_idx + 1 < len(col_names):
                     new_col_val = col_names[value_idx + 1]
                     df_new.rename(columns={new_col_val: "eur"}, inplace=True)

            # Filter relevant columns
            cols = ["Date", "Product", "ISIN", "Quantity", "Price", "Coin", "Value", "eur"]
            
            # Check availability
            available_cols = [c for c in cols if c in df_new.columns]
            
            if len(available_cols) < 5:
                # Fallback to previous logic for other formats? 
                # Or skip?
                # Let's try to map generic ones if above failed
                if len(df_new.columns) >= 17:
                     # Raw Degiro fallback
                     pass
                else:
                    print(f"Skipping {fname}: Columns mismatch. Found: {df_new.columns.tolist()}")
                    continue
            
            # Work on copy
            if set(["Date", "Product", "ISIN", "Quantity", "Price", "Value"]).issubset(df_new.columns):
                 df_new_filtered = df_new.copy()
            else:
                 # Try Raw Degiro mapping if needed
                if len(df_new.columns) >= 17:
                        # Construct from position using the new Transactions.csv mapping
                        df_new_filtered = pd.DataFrame()
                        df_new_filtered['Date'] = df_new.iloc[:, 0]
                        df_new_filtered['Product'] = df_new.iloc[:, 2]
                        df_new_filtered['ISIN'] = df_new.iloc[:, 3]
                        df_new_filtered['Quantity'] = df_new.iloc[:, 6]
                        df_new_filtered['Price'] = df_new.iloc[:, 7]
                        df_new_filtered['Coin'] = df_new.iloc[:, 8]
                        df_new_filtered['Value'] = df_new.iloc[:, 11]
                        df_new_filtered['eur'] = "EUR" # User requested hardcoded "EUR"
                        
                        # Order ID for deduplication
                        if 'Order ID' in df_new.columns:
                            df_new_filtered['order_id'] = df_new['Order ID']
                        else:
                            df_new_filtered['order_id'] = df_new.iloc[:, 16]
                else:
                    continue

            # Ensure columns exist
            for c in ["Coin", "order_id"]:
                if c not in df_new_filtered.columns:
                    df_new_filtered[c] = None
            
            # Clean and Convert
            df_new_filtered['Date'] = pd.to_datetime(df_new_filtered['Date'], dayfirst=True, errors='coerce')
            
            for col in ['Price', 'Value', 'Quantity']:
                if col in df_new_filtered.columns:
                    df_new_filtered[col] = (
                        df_new_filtered[col]
                        .astype(str)
                        .str.replace('"', '', regex=False)
                        .str.replace(',', '.', regex=False)
                        .astype(float)
                    )

            # Normalize final schema
            final_ops = []
            for _, row in df_new_filtered.iterrows():
                if pd.isna(row['Date']): continue
                
                op = {
                    'Date': row['Date'],
                    'Product': row.get('Product'),
                    'ISIN': row.get('ISIN'),
                    'Quantity': row.get('Quantity'),
                    'Price': row.get('Price'),
                    'Coin': row.get('Coin'),
                    'Value': row.get('Value'),
                    'eur': row.get('eur'),
                    'ticker': row.get('ticker') if 'ticker' in row else None,
                    'order_id': row.get('order_id') if 'order_id' in row else f"manual_{pd.Timestamp.now().timestamp()}_{_}"
                }
                final_ops.append(op)
            
            if final_ops:
                # Deduplication against current DB
                # Notebook uses: drop_duplicates(subset=cols_to_check) ignoring Coin, eur, ticker
                # We can do the same on the merged DF.
                new_rows.extend(final_ops)

            # Delete processed file
            try:
                os.remove(filepath)
                print(f"Procesado y eliminado: {fname}")
            except Exception as e:
                print(f"Error deleting {fname}: {e}")
                
        except Exception as e:
            print(f"Error reading {fname}: {e}")

    if new_rows:
        df_new_entries = pd.DataFrame(new_rows)
        # normalize columns
        for c in cols:
             if c not in df_new_entries.columns:
                 df_new_entries[c] = None
        
        new_count = len(df_new_entries)
        
        # Check if there's an existing database to compare against
        if len(df_current) > 0:
            # Deduplication: Only add entries that don't already exist in the DB
            # Compare on: Date, Product, ISIN, Quantity, Price, Value
            subset_check = ["Date", "Product", "ISIN", "Quantity", "Price", "Value"]
            
            # Merge to find duplicates
            df_merged = df_new_entries.merge(
                df_current[subset_check].drop_duplicates(),
                on=subset_check,
                how='left',
                indicator=True
            )
            
            # Keep only entries NOT in the existing DB
            df_unique_new = df_new_entries[df_merged['_merge'] == 'left_only']
            duplicates_removed = new_count - len(df_unique_new)
            
            if duplicates_removed > 0:
                print(f"ℹ️  Eliminados {duplicates_removed} duplicados (ya existían en operaciones.csv).")
            
            # Concat existing + unique new entries
            df_updated = pd.concat([df_current, df_unique_new[cols]], ignore_index=True)
            print(f"✅ Se han añadido {len(df_unique_new)} nuevas transacciones.")
        else:
            # No existing DB, just use all new entries
            df_updated = df_new_entries[cols].copy()
            print(f"✅ Se han añadido {new_count} transacciones (primera carga).")
        
        # Return sorted df (ascending date = "mas pronto primero")
        df_updated['Date'] = pd.to_datetime(df_updated['Date'], errors='coerce')
        return df_updated.sort_values('Date', ascending=True)

    return df_ops

def merge_sap_data(df_ops):
    """Merges SAP stock data. Adjusted to append to DF in memory, valid for run-time analysis."""
    # This logic assumes we just want to ADD valid SAP entries to the analysis DF.
    # We do NOT persist SAP entries to DB here to avoid polluting the persistent 'real' transactions 
    # unless SAP entries are considered real transactions. 
    # The original logic just concatenated them.
    
    if not os.path.exists(config.SAP_FILE):
        return df_ops

    sap_df = pd.read_csv(config.SAP_FILE, parse_dates=["date"])
    sap_df = sap_df[["date", "available", "strike_price"]].dropna(subset=["available"])
    sap_df = sap_df[sap_df["available"].astype(str).str.strip() != ""]

    sap_ops = pd.DataFrame({
        "Date": sap_df["date"],
        "Product": "SAP SE",
        "ISIN": "DE0007164600",
        "Quantity": sap_df["available"],
        "Price": sap_df["strike_price"],
        "Coin": "DOL", # Original was USD, but let's check. Assuming USD/DOL.
        "Value": 0.0,
        "eur": "EUR",
        "ticker": "SAP"
    })
    
    # Ensure logic compatibility
    sap_ops["Coin"] = "USD"
    
    # Concatenate
    df_combined = pd.concat([df_ops, sap_ops], ignore_index=True)
    return df_combined.sort_values("Date").reset_index(drop=True)


# ==================== CRYPTO (BINANCE) FUNCTIONS ====================

CRYPTO_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "processing", "crypto.csv")

def load_crypto_operations():
    """Loads crypto operations from processing/crypto.csv."""
    if not os.path.exists(CRYPTO_DB):
        return pd.DataFrame(columns=["Date", "Product", "Coin", "Quantity", "ticker"])
    
    try:
        df = pd.read_csv(CRYPTO_DB)
        df.columns = [c.strip() for c in df.columns]
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        return df.sort_values('Date')
    except Exception as e:
        print(f"❌ Error loading crypto CSV: {e}")
        return pd.DataFrame(columns=["Date", "Product", "Coin", "Quantity", "ticker"])


def process_binance_transactions(df_crypto=None):
    """
    Processes Binance export files from input/ folder.
    Parses crypto transactions and appends to processing/crypto.csv.
    Deletes processed input files.
    
    Binance export format:
    "User_ID","UTC_Time","Account","Operation","Coin","Change","Remark"
    
    We extract:
    - Transaction Buy, Binance Convert (positive Change) for crypto coins
    - Exclude EUR, USDT intermediate conversions
    """
    input_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "input")
    
    if not os.path.exists(input_dir):
        return df_crypto if df_crypto is not None else load_crypto_operations()
    
    # Find Binance CSV files (case insensitive)
    binance_files = [
        f for f in os.listdir(input_dir)
        if f.lower().endswith(".csv") and "binance" in f.lower()
    ]
    
    if not binance_files:
        print("ℹ️  No Binance files found in input/")
        return df_crypto if df_crypto is not None else load_crypto_operations()
    
    print(f"📥 Processing {len(binance_files)} Binance file(s)...")
    
    # Load current crypto DB
    if os.path.exists(CRYPTO_DB):
        df_current = pd.read_csv(CRYPTO_DB)
        df_current['Date'] = pd.to_datetime(df_current['Date'], errors='coerce')
    else:
        df_current = pd.DataFrame(columns=["Date", "Product", "Coin", "Quantity", "ticker"])
    
    # Crypto coins to track (exclude fiat and stablecoins used as intermediaries)
    CRYPTO_COINS = {'BTC', 'ETH', 'MEME', 'BONK', 'SOL', 'ADA', 'XRP', 'DOT', 'LINK', 'MATIC', 'AVAX', 'DOGE', 'SHIB'}
    
    # Operations that represent actual crypto acquisitions
    BUY_OPERATIONS = {
        'Transaction Buy',
        'Binance Convert',  # Only positive Change values
        'Deposit',  # Crypto deposits
        'Crypto Box',  # Rewards
    }
    
    new_rows = []
    
    for fname in binance_files:
        filepath = os.path.join(input_dir, fname)
        try:
            df_binance = pd.read_csv(filepath)
            
            # Validate expected columns
            required_cols = ['UTC_Time', 'Operation', 'Coin', 'Change']
            if not all(c in df_binance.columns for c in required_cols):
                print(f"⚠️ Skipping {fname}: Missing required columns. Found: {df_binance.columns.tolist()}")
                continue
            
            # Filter for relevant operations
            for _, row in df_binance.iterrows():
                operation = str(row.get('Operation', '')).strip()
                coin = str(row.get('Coin', '')).strip().upper()
                change = float(row.get('Change', 0))
                
                # Only process crypto coins (not fiat/stablecoins)
                if coin not in CRYPTO_COINS:
                    continue
                
                # Only process buy operations with positive change
                if operation not in BUY_OPERATIONS:
                    continue
                    
                if change <= 0:
                    continue
                
                # Create standardized record
                new_rows.append({
                    'Date': pd.to_datetime(row['UTC_Time'], errors='coerce'),
                    'Product': coin,  # Use coin as product name
                    'Coin': coin,
                    'Quantity': change,
                    'ticker': f"{coin}-EUR"  # Yahoo Finance crypto ticker format
                })
            
            # Delete processed file
            try:
                os.remove(filepath)
                print(f"  ✅ Processed and deleted: {fname}")
            except Exception as e:
                print(f"  ⚠️ Error deleting {fname}: {e}")
                
        except Exception as e:
            print(f"  ❌ Error processing {fname}: {e}")
    
    if new_rows:
        df_new = pd.DataFrame(new_rows)
        
        # Deduplicate against existing records
        if len(df_current) > 0:
            # Create composite key for deduplication
            df_current['_key'] = df_current['Date'].astype(str) + '_' + df_current['Coin'] + '_' + df_current['Quantity'].astype(str)
            df_new['_key'] = df_new['Date'].astype(str) + '_' + df_new['Coin'] + '_' + df_new['Quantity'].astype(str)
            
            existing_keys = set(df_current['_key'].tolist())
            df_unique = df_new[~df_new['_key'].isin(existing_keys)].drop(columns=['_key'])
            df_current = df_current.drop(columns=['_key'])
            
            duplicates_removed = len(df_new) - len(df_unique)
            if duplicates_removed > 0:
                print(f"ℹ️  Removed {duplicates_removed} duplicate entries.")
            
            df_updated = pd.concat([df_current, df_unique], ignore_index=True)
        else:
            df_updated = df_new
        
        # Sort and save
        df_updated = df_updated.sort_values('Date', ascending=True)
        df_updated.to_csv(CRYPTO_DB, index=False)
        print(f"✅ Saved {len(df_updated)} crypto transactions to processing/crypto.csv")
        
        return df_updated
    
    return df_current


