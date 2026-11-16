"""
Tarea en segundo plano (la lanza el Programador de tareas, ver src/lifedeck_auto.py):
recalcula el panel con precios frescos y sube el resumen a LifeDeck. Sin ventana ni servidor.

Resultado en processing/lifedeck.json (last_auto_at / last_auto_error) y processing/lifedeck-job.log.
Uso manual: python lifedeck_job.py
"""
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
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

# Tras despertar el PC, StartWhenAvailable lanza la tarea al instante y la Wi-Fi/DNS puede no estar
# lista: se reintenta un par de veces antes de dar el error (la tarea tiene 20 min de límite).
ATTEMPTS = 3
RETRY_DELAY = 60
# Fin de semana + festivo: a partir de aquí unos precios «de hace días» ya son sospechosos.
STALE_DAYS = 4


def _setup_logging() -> None:
    os.makedirs(config.PROCESSING_DIR, exist_ok=True)
    h = RotatingFileHandler(os.path.join(config.PROCESSING_DIR, "lifedeck-job.log"),
                            maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h])
    # yfinance escribe ERROR por cada símbolo muerto en cada ejecución y el detector de splits
    # repite los mismos splits históricos: tapaban los fallos reales del job.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    logging.getLogger("ingesta").propagate = False  # sigue yendo a su propio log (config.get_logger)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save(patch: dict) -> None:
    """Anota el resultado; si ni eso se puede, al menos queda en el log (pythonw no tiene consola)."""
    try:
        lifedeck.save_settings(patch)
    except Exception:
        log.exception("No se pudo guardar el estado en lifedeck.json")


def _prices_stamp():
    """Marca de la caché de precios: si no cambia tras un recálculo forzado, Yahoo no ha dado nada."""
    try:
        return os.path.getmtime(config.PRICES_CACHE_FILE)
    except OSError:
        return None


def _stale_warning(prices_as_of, today: date) -> str:
    if not prices_as_of:
        return ""
    try:
        d = date.fromisoformat(str(prices_as_of)[:10])
    except ValueError:
        return ""
    if today - d > timedelta(days=STALE_DAYS):
        return f"Precios sin actualizar desde el {d:%d/%m}: Yahoo no respondió; se subieron los últimos conocidos."
    return ""


def run(build=None, *, sleep=time.sleep, prices_stamp=None, attempts: int = ATTEMPTS,
        retry_delay: float = RETRY_DELAY, today: date | None = None) -> int:
    try:
        s = lifedeck.load_settings(strict=True)
    except Exception:
        # No se escribe nada: con la configuración ilegible, guardar podría pisar la URL/token.
        log.exception("No se pudo leer lifedeck.json; se reintentará en la próxima ejecución")
        return 1
    if not (s.get("url") and s.get("token")):
        log.info("LifeDeck sin configurar: nada que hacer.")
        _save({"last_auto_at": _now(), "last_auto_error": "Falta la URL o el token de LifeDeck."})
        return 0
    if build is None:
        import server  # import tardío: carga pandas/yfinance solo cuando hace falta
        build = server._build_dashboard
        prices_stamp = prices_stamp or _prices_stamp
    prices_stamp = prices_stamp or (lambda: None)

    warning = ""
    res: dict = {}
    for attempt in range(1, attempts + 1):
        last = attempt == attempts
        try:
            before = prices_stamp()
            dash = build(force_refresh=True)
            if "error" in dash:
                raise lifedeck.LifeDeckError(str(dash["error"]))
            no_new_prices = before is not None and prices_stamp() == before
            if no_new_prices and not last:
                log.info("Sin precios nuevos (intento %d/%d); reintento en %ds.", attempt, attempts, retry_delay)
                sleep(retry_delay)
                continue
            res = lifedeck.push(dash) or {}
            if no_new_prices:
                warning = "No se pudieron descargar precios nuevos; se subieron los últimos conocidos."
            break
        except lifedeck.LifeDeckError as exc:
            if exc.transient and not last:
                log.warning("Fallo transitorio (intento %d/%d): %s; reintento en %ds.",
                            attempt, attempts, exc, retry_delay)
                sleep(retry_delay)
                continue
            log.error("Fallo al actualizar LifeDeck: %s", exc)
            _save({"last_auto_at": _now(), "last_auto_error": str(exc) or exc.__class__.__name__})
            return 1
        except Exception as exc:  # nunca revienta: deja el error para la UI
            log.exception("Fallo al actualizar LifeDeck")
            _save({"last_auto_at": _now(), "last_auto_error": str(exc) or exc.__class__.__name__})
            return 1

    prices_as_of = res.get("prices_as_of") if isinstance(res, dict) else None
    warning = _stale_warning(prices_as_of, today or date.today()) or warning
    _save({"last_auto_at": _now(), "last_auto_error": warning})
    log.info("Patrimonio subido a LifeDeck (as_of=%s, precios=%s)%s.",
             res.get("as_of") if isinstance(res, dict) else None, prices_as_of,
             f" · aviso: {warning}" if warning else "")
    return 0


if __name__ == "__main__":
    _setup_logging()
    sys.exit(run())
