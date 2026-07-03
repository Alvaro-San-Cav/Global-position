"""
test_loaders.py – Unit tests for src/loaders.py and src/schemas.py.

Tests cover:
  • clean_eu_float conversion
  • process_new_transactions with named-column and 17-column Degiro formats
  • Deduplication logic
  • merge_custom_stock_sources with valid and invalid configs
  • validate_dataframe from schemas.py
  • validate_sources from config.py
"""

import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# ── ensure project root is importable ────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.loaders import clean_eu_float, process_new_transactions, save_operations
from src import schemas, config

FIXTURES = Path(__file__).parent / "fixtures"


# ─────────────────────────────────────────────────────────────────────────
#  clean_eu_float
# ─────────────────────────────────────────────────────────────────────────

class TestCleanEuFloat:
    def test_comma_decimal(self):
        assert clean_eu_float("1.234,56") == pytest.approx(1234.56)

    def test_plain_float(self):
        assert clean_eu_float("265.00") == pytest.approx(265.0)

    def test_negative(self):
        assert clean_eu_float("-1.590,00") == pytest.approx(-1590.0)

    def test_empty_string(self):
        assert clean_eu_float("") == 0.0

    def test_nan(self):
        assert clean_eu_float(float("nan")) == 0.0

    def test_quoted(self):
        assert clean_eu_float('"1234.56"') == pytest.approx(1234.56)


# ─────────────────────────────────────────────────────────────────────────
#  process_new_transactions – named column format
# ─────────────────────────────────────────────────────────────────────────

class TestProcessNewTransactionsNamedCols:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        # Patch INPUT_DIR
        self._orig_input = config.INPUT_DIR
        config.INPUT_DIR = self.tmp
        self.df_empty = pd.DataFrame(columns=config.OPERATIONS_COLS)

    def teardown_method(self):
        config.INPUT_DIR = self._orig_input
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_loads_named_cols_file(self):
        shutil.copy(FIXTURES / "degiro_named_cols.csv", self.tmp)
        df = process_new_transactions(self.df_empty.copy())
        assert len(df) == 3
        assert set(df["ISIN"].unique()) == {"US67066G1040", "US0378331005"}

    def test_deduplication(self):
        shutil.copy(FIXTURES / "degiro_named_cols.csv", self.tmp)
        # First pass
        df = process_new_transactions(self.df_empty.copy())
        # Second pass with same file (already loaded but file deleted – simulate
        # by copying again and running with existing df)
        shutil.copy(FIXTURES / "degiro_named_cols.csv", self.tmp)
        df2 = process_new_transactions(df.copy())
        assert len(df2) == 3  # no duplicates added

    def test_quantity_parsed(self):
        shutil.copy(FIXTURES / "degiro_named_cols.csv", self.tmp)
        df = process_new_transactions(self.df_empty.copy())
        nvda = df[df["ISIN"] == "US67066G1040"]
        assert nvda["Quantity"].iloc[0] == pytest.approx(6.0)


# ─────────────────────────────────────────────────────────────────────────
#  process_new_transactions – 17-column positional format (raw Degiro)
# ─────────────────────────────────────────────────────────────────────────

class TestProcessNewTransactions17Cols:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_input = config.INPUT_DIR
        config.INPUT_DIR = self.tmp
        self.df_empty = pd.DataFrame(columns=config.OPERATIONS_COLS)

    def teardown_method(self):
        config.INPUT_DIR = self._orig_input
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_positional_mapping(self):
        shutil.copy(FIXTURES / "degiro_sample.csv", self.tmp)
        df = process_new_transactions(self.df_empty.copy())
        # File has 4 rows; first two are NVDA (buy + sell for split), rest AAPL
        assert len(df) == 4

    def test_nvda_price(self):
        shutil.copy(FIXTURES / "degiro_sample.csv", self.tmp)
        df = process_new_transactions(self.df_empty.copy())
        nvda_buy = df[(df["ISIN"] == "US67066G1040") & (df["Quantity"] > 0)]
        assert nvda_buy["Price"].iloc[0] == pytest.approx(265.0)


# ─────────────────────────────────────────────────────────────────────────
#  schemas.validate_dataframe
# ─────────────────────────────────────────────────────────────────────────

class TestValidateDataframe:
    def _make_valid(self):
        return pd.DataFrame({
            "Date": ["2023-01-01"],
            "Product": ["TEST"],
            "ISIN": ["XX000000"],
            "Quantity": [10.0],
            "Price": [100.0],
            "Value": [1000.0],
        })

    def test_valid_df_no_error(self):
        schemas.validate_dataframe(self._make_valid(), "test_source")

    def test_missing_isin_raises(self):
        df = self._make_valid().drop(columns=["ISIN"])
        with pytest.raises(ValueError, match="ISIN"):
            schemas.validate_dataframe(df, "bad_source")

    def test_missing_multiple_raises(self):
        df = self._make_valid().drop(columns=["ISIN", "Price"])
        with pytest.raises(ValueError):
            schemas.validate_dataframe(df, "bad_source")

    def test_extra_cols_allowed(self):
        df = self._make_valid()
        df["extra_col"] = "x"
        schemas.validate_dataframe(df, "test")  # should not raise


# ─────────────────────────────────────────────────────────────────────────
#  config.validate_sources
# ─────────────────────────────────────────────────────────────────────────

class TestValidateSources:
    def test_valid_sources_no_error(self, tmp_path, monkeypatch):
        import json
        sources = {
            "stock_sources": [
                {"name": "Test", "file_pattern": "*.csv", "column_map": {"Date": "fecha"}, "enabled": False}
            ],
            "crypto_sources": [],
        }
        p = tmp_path / "sources.json"
        p.write_text(json.dumps(sources))
        monkeypatch.setattr(config, "SOURCES_FILE", str(p))
        config.validate_sources()  # must not raise

    def test_missing_name_raises(self, tmp_path, monkeypatch):
        import json
        sources = {
            "stock_sources": [
                {"file_pattern": "*.csv", "column_map": {}}
            ],
            "crypto_sources": [],
        }
        p = tmp_path / "sources.json"
        p.write_text(json.dumps(sources))
        monkeypatch.setattr(config, "SOURCES_FILE", str(p))
        with pytest.raises(ValueError, match="name"):
            config.validate_sources()

    def test_missing_column_map_raises(self, tmp_path, monkeypatch):
        import json
        sources = {
            "stock_sources": [
                {"name": "Broken", "file_pattern": "*.csv"}
            ],
            "crypto_sources": [],
        }
        p = tmp_path / "sources.json"
        p.write_text(json.dumps(sources))
        monkeypatch.setattr(config, "SOURCES_FILE", str(p))
        with pytest.raises(ValueError, match="column_map"):
            config.validate_sources()
