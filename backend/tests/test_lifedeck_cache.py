"""Caché de precios compartida entre el servidor y la tarea de LifeDeck (otro proceso)."""
import os
import threading

import pandas as pd

from src import file_lock, market_data


def _frame(col, day, value):
    return pd.DataFrame({col: [value]}, index=pd.to_datetime([day]))


def test_save_cache_merges_and_leaves_no_temp_files(tmp_path):
    path = str(tmp_path / "prices.csv")
    market_data._save_cache(_frame("AAA", "2026-11-13", 1.0), path)
    market_data._save_cache(_frame("BBB", "2026-11-14", 2.0), path)
    df = market_data._load_cache(path)
    assert list(df.columns) == ["AAA", "BBB"] and len(df) == 2
    assert sorted(n for n in os.listdir(tmp_path) if not n.endswith(".lock")) == ["prices.csv"]


def test_save_cache_concurrent_writers_do_not_lose_columns(tmp_path, monkeypatch):
    # Sin el cerrojo de hilos (simula dos procesos): el de fichero debe bastar.
    import contextlib

    monkeypatch.setattr(market_data, "_CACHE_LOCK", contextlib.nullcontext())
    path = str(tmp_path / "prices.csv")
    errors = []

    def write(i):
        try:
            market_data._save_cache(_frame(f"T{i}", "2026-11-14", float(i)), path)
        except Exception as exc:  # pragma: no cover - el test falla abajo
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    df = pd.read_csv(path, index_col=0)
    assert sorted(df.columns) == sorted(f"T{i}" for i in range(8))


def test_interprocess_lock_excludes_second_holder(tmp_path):
    path = str(tmp_path / "x.json")
    with file_lock.interprocess_lock(path) as first:
        assert first is True
        with file_lock.interprocess_lock(path, timeout=0.2) as second:
            assert second is False  # ocupado: sigue sin él tras el timeout
    with file_lock.interprocess_lock(path, timeout=0.2) as again:
        assert again is True
