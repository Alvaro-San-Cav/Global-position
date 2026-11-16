"""
Cerrojo entre procesos basado en un fichero `<ruta>.lock` (msvcrt en Windows, fcntl en POSIX).

Lo usan el servidor y la tarea en segundo plano de LifeDeck (procesos distintos) para no pisarse
al reescribir processing/lifedeck.json o las cachés de precios/FX. Es cooperativo: solo excluye a
quien también lo pide. Si no se consigue en `timeout` segundos se sigue igualmente (con aviso),
porque las escrituras ya son atómicas (temporal único + os.replace) y es preferible a bloquearse.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Iterator

_log = logging.getLogger(__name__)


def _try_lock(fd: int) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def interprocess_lock(path: str, timeout: float = 15.0, poll: float = 0.05) -> Iterator[bool]:
    """Exclusión entre procesos sobre `path + '.lock'`. Devuelve si se obtuvo el cerrojo."""
    lock_path = path + ".lock"
    fd = None
    acquired = False
    try:
        os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as exc:
        _log.warning("No se pudo abrir %s: %s", lock_path, exc)
    if fd is not None:
        deadline = time.monotonic() + timeout
        while True:
            if _try_lock(fd):
                acquired = True
                break
            if time.monotonic() >= deadline:
                _log.warning("Cerrojo %s ocupado %.0f s; se continúa sin él", lock_path, timeout)
                break
            time.sleep(poll)
    try:
        yield acquired
    finally:
        if fd is not None:
            if acquired:
                _unlock(fd)
            os.close(fd)
