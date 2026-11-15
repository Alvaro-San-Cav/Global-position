"""
Tarea en segundo plano (la lanza el Programador de tareas, ver src/lifedeck_auto.py):
recalcula el panel con precios frescos y sube el resumen a LifeDeck. Sin ventana ni servidor.

Resultado en processing/lifedeck.json (last_auto_at / last_auto_error) y processing/lifedeck-job.log.
Uso manual: python lifedeck_job.py
"""
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

# pythonw (sin ventana) deja stdout/stderr a None: cualquier write directo reventaría.
if sys.stdout is None or sys.stderr is None:
    _devnull = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.stdout or _devnull
    sys.stderr = sys.stderr or _devnull

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import config, lifedeck  # noqa: E402

log = logging.getLogger("lifedeck_job")


def _setup_logging() -> None:
    os.makedirs(config.PROCESSING_DIR, exist_ok=True)
    h = RotatingFileHandler(os.path.join(config.PROCESSING_DIR, "lifedeck-job.log"),
                            maxBytes=256_000, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(build=None) -> int:
    s = lifedeck.load_settings()
    if not (s.get("url") and s.get("token")):
        log.info("LifeDeck sin configurar: nada que hacer.")
        lifedeck.save_settings({"last_auto_at": _now(), "last_auto_error": "Falta la URL o el token de LifeDeck."})
        return 0
    try:
        if build is None:
            import server  # import tardío: carga pandas/yfinance solo cuando hace falta
            build = server._build_dashboard
        dash = build(force_refresh=True)
        if "error" in dash:
            raise lifedeck.LifeDeckError(str(dash["error"]))
        lifedeck.push(dash)
    except Exception as exc:  # nunca revienta: deja el error para la UI
        log.exception("Fallo al actualizar LifeDeck")
        lifedeck.save_settings({"last_auto_at": _now(), "last_auto_error": str(exc) or exc.__class__.__name__})
        return 1
    lifedeck.save_settings({"last_auto_at": _now(), "last_auto_error": ""})
    log.info("Patrimonio subido a LifeDeck.")
    return 0


if __name__ == "__main__":
    _setup_logging()
    sys.exit(run())
