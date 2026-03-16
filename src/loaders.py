"""
loaders.py – Generic data loading for stocks and crypto.

Stock operations come from:
  1. Degiro-format CSVs dropped in input/        (broker transactions)
  2. Custom stock sources defined in sources.json (RSUs, vests, etc.)

Crypto operations come from:
  1. Exchange CSV exports dropped in input/       (parsed per sources.json)

Everything is normalised and deduplicated before saving.
"""

import fnmatch
import os

import pandas as pd

from . import config

# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def clean_eu_float(x) -> float:
    """European number format (1.234,56) → float 1234.56."""
    if pd.isna(x) or str(x).strip() == "":
        return 0.0
    s = str(x).replace('"', '').replace(' ', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────
# Stock operations  (processing/operaciones.csv)
# ─────────────────────────────────────────────────────────────────────────

def load_operations() -> pd.DataFrame:
    """Load the master stock-operations CSV from processing/."""
    path = config.OPERATIONS_FILE
    if not os.path.exists(path):
        return pd.DataFrame(columns=config.OPERATIONS_COLS)

    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    for col in config.OPERATIONS_COLS:
        if col not in df.columns:
            df[col] = None

    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
    return df.sort_values('Date', kind='mergesort')


def process_new_transactions(df_ops: pd.DataFrame) -> pd.DataFrame:
    """
    Scan input/ for new Degiro-format CSV files, deduplicate against
    existing df_ops, concatenate, sort and return the updated DF.
    Processed files are deleted from input/.

    Files matching any custom stock-source pattern or any crypto-source
    pattern in sources.json are skipped here (they have their own loader).
    """
    input_dir = config.INPUT_DIR
    if not os.path.exists(input_dir):
        print("ℹ️  input/ folder does not exist.")
        return df_ops

    # Patterns to skip (handled by custom loaders)
    skip_patterns = set()
    for src in config.load_sources().get("stock_sources", []):
        skip_patterns.add(src.get("file_pattern", ""))
    for src in config.load_sources().get("crypto_sources", []):
        skip_patterns.add(src.get("file_pattern", ""))

    def _should_skip(fname: str) -> bool:
        for pat in skip_patterns:
            if pat and fnmatch.fnmatch(fname.lower(), pat.lower()):
                return True
        return False

    csv_files = [
        f for f in os.listdir(input_dir)
        if f.lower().endswith('.csv') and not _should_skip(f)
    ]

    if not csv_files:
        print("ℹ️  No new transaction files in input/.")
        return df_ops

    print(f"📂 Found {len(csv_files)} transaction file(s) in input/...")
    new_rows: list[pd.Series] = []

    for fname in csv_files:
        filepath = os.path.join(input_dir, fname)
        try:
            df_new = pd.read_csv(filepath)

            # Column mapping (Degiro quirks) ─────────────────────────────
            rename_dict: dict[str, str] = {}
            if 'Value EUR' in df_new.columns:
                rename_dict['Value EUR'] = 'Value'
            elif 'Local value' in df_new.columns and 'Value' not in df_new.columns:
                rename_dict['Local value'] = 'Value'
            if rename_dict:
                df_new.rename(columns=rename_dict, inplace=True)

            # Sort by datetime when Time column exists
            if 'Date' in df_new.columns and 'Time' in df_new.columns:
                df_new['_dt'] = pd.to_datetime(
                    df_new['Date'].astype(str) + ' ' + df_new['Time'].astype(str),
                    dayfirst=True, errors='coerce',
                )
                df_new = df_new.sort_values('_dt').drop(columns=['_dt'])

            if 'eur' not in df_new.columns:
                df_new['eur'] = 'EUR'

            want = ['Date', 'Product', 'ISIN', 'Quantity', 'Price', 'Coin', 'Value', 'eur']
            required = {'Date', 'Product', 'ISIN', 'Quantity', 'Price', 'Value'}

            if not required.issubset(df_new.columns):
                # Try positional mapping for raw Degiro 17-column format
                if len(df_new.columns) >= 17:
                    raw = pd.DataFrame()
                    raw['Date']     = df_new.iloc[:, 0]
                    raw['Product']  = df_new.iloc[:, 2]
                    raw['ISIN']     = df_new.iloc[:, 3]
                    raw['Quantity'] = df_new.iloc[:, 6]
                    raw['Price']    = df_new.iloc[:, 7]
                    raw['Coin']     = df_new.iloc[:, 8]
                    raw['Value']    = df_new.iloc[:, 11]
                    raw['eur']      = 'EUR'
                    df_new = raw
                else:
                    print(f"  ⚠️ Skipping {fname}: column mismatch {df_new.columns.tolist()}")
                    continue

            for c in want:
                if c not in df_new.columns:
                    df_new[c] = None

            df_f = df_new[want].copy()
            df_f['Date'] = pd.to_datetime(df_f['Date'], dayfirst=True, errors='coerce')
            for col in ['Price', 'Value']:
                df_f[col] = (
                    df_f[col].astype(str)
                    .str.replace('"', '', regex=False)
                    .str.replace(',', '.', regex=False)
                    .astype(float)
                )
            df_f['Quantity'] = pd.to_numeric(df_f['Quantity'], errors='coerce')

            # Normalise ops types for dedup comparison
            df_ops['Date']     = pd.to_datetime(df_ops['Date'], errors='coerce')
            df_ops['Quantity'] = pd.to_numeric(df_ops['Quantity'], errors='coerce')
            df_ops['Price']    = pd.to_numeric(df_ops['Price'], errors='coerce')

            for _, row in df_f.iterrows():
                match = df_ops[
                    (df_ops['Date'] == row['Date'])
                    & (df_ops['ISIN'] == row['ISIN'])
                    & (df_ops['Quantity'] == row['Quantity'])
                    & (df_ops['Price'] == row['Price'])
                ]
                if match.empty:
                    new_rows.append(row)

            os.remove(filepath)
            print(f"  ✅ Processed & deleted: {fname}")

        except Exception as e:
            print(f"  ❌ Error processing {fname}: {e}")

    if new_rows:
        df_ops = pd.concat([df_ops, pd.DataFrame(new_rows)], ignore_index=True)
        df_ops = df_ops.sort_values('Date', kind='mergesort')
        print(f"🟢 {len(new_rows)} new transaction(s) added.")
    else:
        print("ℹ️  All transactions already existed. Nothing added.")

    return df_ops


def save_operations(df_ops: pd.DataFrame) -> None:
    """Persist the operations DF to processing/operaciones.csv."""
    os.makedirs(config.PROCESSING_DIR, exist_ok=True)
    df_export = df_ops.loc[:, ~df_ops.columns.duplicated()].copy()
    df_export['eur'] = 'EUR'
    cols = [c for c in config.OPERATIONS_COLS if c in df_export.columns]
    df_export[cols].to_csv(config.OPERATIONS_FILE, index=False)
    print(f"💾 Operations saved → {config.OPERATIONS_FILE}")


# ─────────────────────────────────────────────────────────────────────────
# Custom stock sources  (defined in sources.json → stock_sources)
# ─────────────────────────────────────────────────────────────────────────

def merge_custom_stock_sources(df_ops: pd.DataFrame) -> pd.DataFrame:
    """
    For each enabled stock_source in sources.json, look for matching files
    in input/, parse them according to column_map + defaults, and append
    the resulting rows to df_ops (in-memory only, not persisted).
    """
    sources = config.get_stock_sources()
    if not sources:
        return df_ops

    input_dir = config.INPUT_DIR
    if not os.path.exists(input_dir):
        return df_ops

    for src in sources:
        pattern = src.get("file_pattern", "")
        col_map = src.get("column_map", {})
        defaults = src.get("defaults", {})
        name = src.get("name", pattern)

        matched_files = [
            f for f in os.listdir(input_dir)
            if fnmatch.fnmatch(f.lower(), pattern.lower())
        ]
        if not matched_files:
            continue

        for fname in matched_files:
            filepath = os.path.join(input_dir, fname)
            try:
                df_src = pd.read_csv(filepath)

                # Build normalised DataFrame using column_map
                ops: dict[str, object] = {}
                for target_col, source_col in col_map.items():
                    if source_col in df_src.columns:
                        ops[target_col] = df_src[source_col]

                if 'Date' not in ops:
                    print(f"  ⚠️ Source '{name}': no Date mapping – skipping {fname}")
                    continue

                df_mapped = pd.DataFrame(ops)

                # Apply defaults for missing columns
                for col, val in defaults.items():
                    if col not in df_mapped.columns:
                        df_mapped[col] = val

                # Ensure standard columns
                df_mapped['Date'] = pd.to_datetime(df_mapped['Date'], dayfirst=True, errors='coerce')
                for col in ['Quantity', 'Price', 'Value']:
                    if col in df_mapped.columns:
                        df_mapped[col] = pd.to_numeric(df_mapped[col], errors='coerce')
                if 'eur' not in df_mapped.columns:
                    df_mapped['eur'] = 'EUR'

                # Drop rows with bad dates
                df_mapped = df_mapped.dropna(subset=['Date'])

                n = len(df_mapped)
                df_ops = pd.concat([df_ops, df_mapped], ignore_index=True)
                print(f"  🟢 {n} rows merged from '{name}' ({fname})")

            except Exception as e:
                print(f"  ❌ Error loading '{name}' from {fname}: {e}")

    df_ops = df_ops.sort_values('Date', kind='mergesort').reset_index(drop=True)
    return df_ops


# ─────────────────────────────────────────────────────────────────────────
# Crypto operations  (processing/crypto.csv)
# ─────────────────────────────────────────────────────────────────────────

def load_crypto_operations() -> pd.DataFrame:
    """Load the crypto operations CSV from processing/."""
    cols = ['Date', 'Product', 'Coin', 'Quantity', 'ticker']
    if not os.path.exists(config.CRYPTO_DB):
        return pd.DataFrame(columns=cols)

    df = pd.read_csv(config.CRYPTO_DB)
    df.columns = [c.strip() for c in df.columns]
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    return df.sort_values('Date')


def process_crypto_transactions() -> pd.DataFrame:
    """
    For each enabled crypto_source in sources.json, scan input/ for
    matching CSV files, parse them according to the source config,
    deduplicate against the existing crypto DB, and persist.

    Returns the updated crypto DF.
    """
    sources = config.get_crypto_sources()
    df_current = load_crypto_operations()

    if not sources:
        return df_current

    input_dir = config.INPUT_DIR
    if not os.path.exists(input_dir):
        return df_current

    new_rows: list[dict] = []

    for src in sources:
        pattern        = src.get("file_pattern", "")
        col_map        = src.get("column_map", {})
        coins_filter   = set(c.upper() for c in src.get("coins", []))
        buy_ops        = set(src.get("buy_operations", []))
        name           = src.get("name", pattern)

        matched = [f for f in os.listdir(input_dir)
                   if fnmatch.fnmatch(f.lower(), pattern.lower())]

        if not matched:
            continue

        print(f"📥 Processing '{name}': {len(matched)} file(s)...")

        for fname in matched:
            filepath = os.path.join(input_dir, fname)
            try:
                df_raw = pd.read_csv(filepath)

                # Resolve source column names
                date_col = col_map.get("Date", "UTC_Time")
                coin_col = col_map.get("Coin", "Coin")
                qty_col  = col_map.get("Quantity", "Change")
                op_col   = col_map.get("Operation", "Operation")

                for _, row in df_raw.iterrows():
                    coin = str(row.get(coin_col, '')).strip().upper()
                    change = float(row.get(qty_col, 0))

                    # Coin filter
                    if coins_filter and coin not in coins_filter:
                        continue

                    # Operation filter (if column exists)
                    if op_col in df_raw.columns and buy_ops:
                        op = str(row.get(op_col, '')).strip()
                        if op not in buy_ops:
                            continue

                    # Only positive amounts
                    if change <= 0:
                        continue

                    new_rows.append({
                        'Date':     pd.to_datetime(row.get(date_col), errors='coerce'),
                        'Product':  coin,
                        'Coin':     coin,
                        'Quantity': change,
                        'ticker':   f"{coin}-EUR",
                    })

                os.remove(filepath)
                print(f"  ✅ Processed & deleted: {fname}")

            except Exception as e:
                print(f"  ❌ Error with {fname}: {e}")

    if not new_rows:
        print("ℹ️  No new crypto transactions found.")
        return df_current

    df_new = pd.DataFrame(new_rows)

    # Dedup against existing
    if len(df_current) > 0:
        df_current['_key'] = (
            df_current['Date'].astype(str) + '_'
            + df_current['Coin'] + '_'
            + df_current['Quantity'].astype(str)
        )
        df_new['_key'] = (
            df_new['Date'].astype(str) + '_'
            + df_new['Coin'] + '_'
            + df_new['Quantity'].astype(str)
        )
        existing = set(df_current['_key'])
        df_unique = df_new[~df_new['_key'].isin(existing)].drop(columns=['_key'])
        df_current = df_current.drop(columns=['_key'])
        df_updated = pd.concat([df_current, df_unique], ignore_index=True)
        n_dup = len(df_new) - len(df_unique)
        if n_dup > 0:
            print(f"ℹ️  {n_dup} duplicate(s) skipped.")
    else:
        df_updated = df_new

    df_updated = df_updated.sort_values('Date')
    os.makedirs(config.PROCESSING_DIR, exist_ok=True)
    df_updated.to_csv(config.CRYPTO_DB, index=False)
    print(f"💾 {len(df_updated)} crypto transactions saved → {config.CRYPTO_DB}")
    return df_updated
