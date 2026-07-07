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
import shutil
from datetime import date, datetime, timedelta

import pandas as pd

from . import config, schemas


# ─────────────────────────────────────────────────────────────────────────
# Backup helpers
# ─────────────────────────────────────────────────────────────────────────

def _backup_file(src_path: str) -> None:
    """Copy src_path to BACKUP_DIR with today's date suffix, then prune old backups."""
    if not os.path.exists(src_path):
        return
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src_path))[0]
    dest = os.path.join(config.BACKUP_DIR, f"{stem}_{date.today().isoformat()}.csv")
    shutil.copy2(src_path, dest)
    _prune_backups(stem)


def _prune_backups(stem: str) -> None:
    """Remove backups for `stem` older than BACKUP_RETENTION_DAYS days."""
    cutoff = datetime.now() - timedelta(days=config.BACKUP_RETENTION_DAYS)
    for fname in os.listdir(config.BACKUP_DIR):
        if not (fname.startswith(stem) and fname.endswith(".csv")):
            continue
        fpath = os.path.join(config.BACKUP_DIR, fname)
        if datetime.fromtimestamp(os.path.getmtime(fpath)) < cutoff:
            os.remove(fpath)

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

    df['Date'] = pd.to_datetime(df['Date'], format='%Y-%m-%d', errors='coerce')
    return df.sort_values('Date', kind='mergesort')


def _pending_transaction_files() -> list[str]:
    """Names of CSVs in input/ that are generic Degiro transaction files
    (i.e. NOT matched by any custom stock/crypto source pattern)."""
    input_dir = config.INPUT_DIR
    if not os.path.exists(input_dir):
        return []

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

    return [
        f for f in os.listdir(input_dir)
        if f.lower().endswith('.csv') and not _should_skip(f)
    ]


def _parse_degiro_file(filepath: str) -> pd.DataFrame | None:
    """Read a single Degiro-format CSV and return a normalised DataFrame with
    columns [Date, Product, ISIN, Quantity, Price, Coin, Value, eur].
    Returns None when the column layout is not recognised."""
    log = config.get_logger()
    fname = os.path.basename(filepath)
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
            msg = f"Saltado {fname}: columnas no reconocidas {df_new.columns.tolist()}"
            print(f"  ⚠️ Skipping {fname}: column mismatch {df_new.columns.tolist()}")
            log.warning(msg)
            return None

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
    return df_f


def _split_new_vs_dup(df_f: pd.DataFrame, df_ops: pd.DataFrame) -> tuple[list[pd.Series], int]:
    """Split parsed rows into (new_rows, duplicate_count) vs existing df_ops."""
    df_ops['Date']     = pd.to_datetime(df_ops['Date'], errors='coerce')
    df_ops['Quantity'] = pd.to_numeric(df_ops['Quantity'], errors='coerce')
    df_ops['Price']    = pd.to_numeric(df_ops['Price'], errors='coerce')

    new_rows: list[pd.Series] = []
    for _, row in df_f.iterrows():
        match = df_ops[
            (df_ops['Date'] == row['Date'])
            & (df_ops['ISIN'] == row['ISIN'])
            & (df_ops['Quantity'] == row['Quantity'])
            & (df_ops['Price'] == row['Price'])
        ]
        if match.empty:
            new_rows.append(row)
    return new_rows, len(df_f) - len(new_rows)


def preview_new_transactions(df_ops: pd.DataFrame) -> list[dict]:
    """Detect new Degiro transactions in input/ WITHOUT mutating anything
    (no file deletion, no save). Returns one dict per pending file with the
    rows that WOULD be added, for a confirmation preview."""
    result: list[dict] = []
    for fname in _pending_transaction_files():
        filepath = os.path.join(config.INPUT_DIR, fname)
        try:
            df_f = _parse_degiro_file(filepath)
            if df_f is None:
                result.append({
                    "file": fname, "kind": "stock", "error":
                    "Formato de columnas no reconocido.", "entries": [],
                })
                continue
            new_rows, n_dup = _split_new_vs_dup(df_f, df_ops.copy())
            entries = [
                {
                    "date": (r['Date'].strftime('%Y-%m-%d')
                             if pd.notna(r['Date']) else str(r['Date'])),
                    "product": None if pd.isna(r['Product']) else str(r['Product']),
                    "isin": None if pd.isna(r['ISIN']) else str(r['ISIN']),
                    "quantity": None if pd.isna(r['Quantity']) else round(float(r['Quantity']), 6),
                    "price": None if pd.isna(r['Price']) else round(float(r['Price']), 5),
                    "coin": None if pd.isna(r.get('Coin')) else str(r['Coin']),
                    "value": None if pd.isna(r['Value']) else round(float(r['Value']), 2),
                }
                for r in new_rows
            ]
            result.append({
                "file": fname, "kind": "stock",
                "rows_read": len(df_f), "new": len(new_rows), "duplicates": n_dup,
                "entries": entries,
            })
        except Exception as e:
            result.append({"file": fname, "kind": "stock", "error": str(e), "entries": []})
    return result


def process_new_transactions(df_ops: pd.DataFrame) -> pd.DataFrame:
    """
    Scan input/ for new Degiro-format CSV files, deduplicate against
    existing df_ops, concatenate, sort and return the updated DF.
    Processed files are deleted from input/.

    Files matching any custom stock-source pattern or any crypto-source
    pattern in sources.json are skipped here (they have their own loader).
    """
    if not os.path.exists(config.INPUT_DIR):
        print("ℹ️  input/ folder does not exist.")
        return df_ops

    csv_files = _pending_transaction_files()
    if not csv_files:
        print("ℹ️  No new transaction files in input/.")
        return df_ops

    log = config.get_logger()
    print(f"📂 Found {len(csv_files)} transaction file(s) in input/...")
    new_rows: list[pd.Series] = []

    for fname in csv_files:
        filepath = os.path.join(config.INPUT_DIR, fname)
        try:
            df_f = _parse_degiro_file(filepath)
            if df_f is None:
                continue

            file_new_rows, n_dup = _split_new_vs_dup(df_f, df_ops)
            n_added = len(file_new_rows)
            new_rows.extend(file_new_rows)

            os.remove(filepath)
            print(f"  ✅ Processed & deleted: {fname}")
            log.info(
                f"process_new_transactions: archivo={fname} "
                f"filas_leídas={len(df_f)} nuevas={n_added} duplicadas={n_dup}"
            )

        except Exception as e:
            print(f"  ❌ Error processing {fname}: {e}")
            log.error(f"process_new_transactions: error en {fname}: {e}")

    if new_rows:
        df_ops = pd.concat([df_ops, pd.DataFrame(new_rows)], ignore_index=True)
        df_ops = df_ops.sort_values('Date', kind='mergesort')
        print(f"🟢 {len(new_rows)} new transaction(s) added.")
        log.info(f"process_new_transactions: total {len(new_rows)} transacciones nuevas añadidas")
    else:
        print("ℹ️  All transactions already existed. Nothing added.")
        log.info("process_new_transactions: sin transacciones nuevas (todo ya existía)")

    return df_ops


def save_operations(df_ops: pd.DataFrame) -> None:
    """Persist the operations DF to processing/operaciones.csv."""
    log = config.get_logger()
    os.makedirs(config.PROCESSING_DIR, exist_ok=True)
    _backup_file(config.OPERATIONS_FILE)
    df_export = df_ops.loc[:, ~df_ops.columns.duplicated()].copy()
    df_export['eur'] = 'EUR'
    cols = [c for c in config.OPERATIONS_COLS if c in df_export.columns]
    df_export[cols].to_csv(config.OPERATIONS_FILE, index=False)
    log.info(f"save_operations: {len(df_export)} filas guardadas → {config.OPERATIONS_FILE}")
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
                # Custom sources use ISO format (YYYY-MM-DD); dayfirst=True would swap
                # month and day for ambiguous dates like "2023-07-06" → "2023-06-07".
                df_mapped['Date'] = pd.to_datetime(df_mapped['Date'], dayfirst=False, errors='coerce')
                for col in ['Quantity', 'Price', 'Value']:
                    if col in df_mapped.columns:
                        df_mapped[col] = pd.to_numeric(df_mapped[col], errors='coerce')
                if 'eur' not in df_mapped.columns:
                    df_mapped['eur'] = 'EUR'

                # Drop rows with bad dates or zero/negative quantity
                df_mapped = df_mapped.dropna(subset=['Date'])
                if 'Quantity' in df_mapped.columns:
                    df_mapped = df_mapped[df_mapped['Quantity'] > 0]

                # If compute_value_from_price is set, derive Value = Price × Quantity
                # so that invested capital is distributed correctly across vest dates.
                if src.get("compute_value_from_price", False):
                    if 'Price' in df_mapped.columns and 'Quantity' in df_mapped.columns:
                        df_mapped['Value'] = (df_mapped['Price'] * df_mapped['Quantity']).fillna(0.0)

                # Validate required columns before concat
                schemas.validate_dataframe(df_mapped, source_name=name)

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
    """Load normalised crypto operations, with fallback to raw exports."""
    cols = ['Date', 'Product', 'Coin', 'Quantity', 'ticker']
    if not os.path.exists(config.CRYPTO_DB):
        # Fallback: if crypto.csv does not exist yet, try parsing raw exchange
        # exports located in processing/ (and input/ if present).
        sources = config.get_crypto_sources()
        if not sources:
            return pd.DataFrame(columns=cols)

        frames: list[pd.DataFrame] = []
        for src in sources:
            pattern = src.get("file_pattern", "")
            for base_dir in [config.PROCESSING_DIR, config.INPUT_DIR]:
                if not os.path.exists(base_dir):
                    continue
                matched = [
                    f for f in os.listdir(base_dir)
                    if fnmatch.fnmatch(f.lower(), pattern.lower())
                ]
                for fname in matched:
                    filepath = os.path.join(base_dir, fname)
                    try:
                        df_raw = pd.read_csv(filepath)
                    except Exception:
                        continue
                    parsed = _parse_crypto_rows(df_raw, src)
                    if parsed:
                        frames.append(pd.DataFrame(parsed))

        if not frames:
            return pd.DataFrame(columns=cols)

        df = pd.concat(frames, ignore_index=True)
        # Keep one row per Date/Coin/Quantity key to avoid duplicates between
        # input/ and processing/ copies of the same export.
        df['_key'] = (
            df['Date'].astype(str) + '_'
            + df['Coin'].astype(str) + '_'
            + df['Quantity'].astype(str)
        )
        df = df.drop_duplicates('_key').drop(columns=['_key'])
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        return df.sort_values('Date').reset_index(drop=True)

    df = pd.read_csv(config.CRYPTO_DB)
    df.columns = [c.strip() for c in df.columns]
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    return df.sort_values('Date')


def save_crypto_operations(df_crypto: pd.DataFrame) -> None:
    """Persist crypto operations DF to processing/crypto.csv with backup."""
    log = config.get_logger()
    os.makedirs(config.PROCESSING_DIR, exist_ok=True)
    _backup_file(config.CRYPTO_DB)

    cols = ['Date', 'Product', 'Coin', 'Quantity', 'ticker']
    df_export = df_crypto.loc[:, ~df_crypto.columns.duplicated()].copy()
    for col in cols:
        if col not in df_export.columns:
            df_export[col] = None

    df_export = df_export[cols].sort_values('Date', kind='mergesort')
    df_export.to_csv(config.CRYPTO_DB, index=False)
    log.info(f"save_crypto_operations: {len(df_export)} filas guardadas → {config.CRYPTO_DB}")
    print(f"💾 Crypto operations saved → {config.CRYPTO_DB}")


def _parse_crypto_rows(df_raw: pd.DataFrame, src: dict) -> list[dict]:
    """Parse a raw crypto export dataframe into normalised rows."""
    col_map      = src.get("column_map", {})
    coins_filter = set(c.upper() for c in src.get("coins", []))
    enforce_coins_filter = bool(src.get("enforce_coins_filter", False))
    buy_ops      = set(src.get("buy_operations", []))

    date_col = col_map.get("Date", "UTC_Time")
    coin_col = col_map.get("Coin", "Coin")
    qty_col  = col_map.get("Quantity", "Change")
    op_col   = col_map.get("Operation", "Operation")

    out: list[dict] = []
    for _, row in df_raw.iterrows():
        coin = str(row.get(coin_col, '')).strip().upper()
        qty_raw = pd.to_numeric(row.get(qty_col), errors='coerce')
        if pd.isna(qty_raw):
            continue
        change = float(qty_raw)

        # Coin filter
        if enforce_coins_filter and coins_filter and coin not in coins_filter:
            continue

        # Operation filter (if column exists)
        if op_col in df_raw.columns and buy_ops:
            op = str(row.get(op_col, '')).strip()
            if op not in buy_ops:
                continue

        # Only positive amounts
        if change <= 0:
            continue

        dt = pd.to_datetime(row.get(date_col), errors='coerce')
        if pd.isna(dt):
            continue

        out.append({
            'Date':     dt,
            'Product':  coin,
            'Coin':     coin,
            'Quantity': change,
            'ticker':   f"{coin}-EUR",
        })

    return out


def preview_new_crypto_transactions() -> list[dict]:
    """Detect new crypto transactions in input/ WITHOUT saving or deleting.
    Only pending files in input/ are reported (processing/ files are permanent
    sources, not part of the confirm-before-save flow)."""
    sources = config.get_crypto_sources()
    result: list[dict] = []
    if not sources or not os.path.exists(config.INPUT_DIR):
        return result

    df_current = load_crypto_operations()
    existing = set()
    if len(df_current) > 0:
        existing = set(
            df_current['Date'].astype(str) + '_'
            + df_current['Coin'].astype(str) + '_'
            + df_current['Quantity'].astype(str)
        )

    for src in sources:
        pattern = src.get("file_pattern", "")
        name    = src.get("name", pattern)
        matched = [
            f for f in os.listdir(config.INPUT_DIR)
            if fnmatch.fnmatch(f.lower(), pattern.lower())
        ]
        for fname in matched:
            filepath = os.path.join(config.INPUT_DIR, fname)
            try:
                df_raw = pd.read_csv(filepath)
                file_rows = _parse_crypto_rows(df_raw, src)
                entries, n_dup = [], 0
                for r in file_rows:
                    key = f"{r['Date']}_{r['Coin']}_{r['Quantity']}"
                    if key in existing:
                        n_dup += 1
                        continue
                    entries.append({
                        "date": (r['Date'].strftime('%Y-%m-%d')
                                 if pd.notna(r['Date']) else str(r['Date'])),
                        "coin": str(r['Coin']),
                        "quantity": round(float(r['Quantity']), 8),
                        "ticker": str(r['ticker']),
                    })
                result.append({
                    "file": fname, "kind": "crypto", "source": name,
                    "rows_read": len(file_rows), "new": len(entries), "duplicates": n_dup,
                    "entries": entries,
                })
            except Exception as e:
                result.append({"file": fname, "kind": "crypto", "source": name,
                               "error": str(e), "entries": []})
    return result


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
    processing_dir = config.PROCESSING_DIR
    if not os.path.exists(input_dir) and not os.path.exists(processing_dir):
        return df_current

    log = config.get_logger()
    new_rows: list[dict] = []

    for src in sources:
        pattern        = src.get("file_pattern", "")
        name           = src.get("name", pattern)

        matched_sources: list[tuple[str, str, bool]] = []
        if os.path.exists(input_dir):
            matched_sources.extend([
                (f, os.path.join(input_dir, f), True)
                for f in os.listdir(input_dir)
                if fnmatch.fnmatch(f.lower(), pattern.lower())
            ])
        if os.path.exists(processing_dir):
            matched_sources.extend([
                (f, os.path.join(processing_dir, f), False)
                for f in os.listdir(processing_dir)
                if fnmatch.fnmatch(f.lower(), pattern.lower())
            ])

        if not matched_sources:
            continue

        print(f"📥 Processing '{name}': {len(matched_sources)} file(s)...")

        for fname, filepath, from_input in matched_sources:
            try:
                df_raw = pd.read_csv(filepath)
                file_rows = _parse_crypto_rows(df_raw, src)

                new_rows.extend(file_rows)
                if from_input:
                    os.remove(filepath)
                    print(f"  ✅ Processed & deleted: {fname}")
                else:
                    print(f"  ✅ Processed: {fname}")
                log.info(
                    f"process_crypto_transactions: archivo={fname} fuente='{name}' "
                    f"filas_válidas={len(file_rows)} origen={'input' if from_input else 'processing'}"
                )

            except Exception as e:
                print(f"  ❌ Error with {fname}: {e}")
                log.error(f"process_crypto_transactions: error en {fname}: {e}")

    if not new_rows:
        print("ℹ️  No new crypto transactions found.")
        return df_current

    df_new = pd.DataFrame(new_rows)

    # Dedup against existing
    n_dup = 0
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
    save_crypto_operations(df_updated)
    log.info(
        f"process_crypto_transactions: {len(df_updated)} filas totales guardadas "
        f"(nuevas={len(df_new) - n_dup} duplicadas={n_dup}) → {config.CRYPTO_DB}"
    )
    return df_updated
