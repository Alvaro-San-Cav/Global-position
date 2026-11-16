"""
Sube un resumen del patrimonio a LifeDeck (PWA personal) para verlo en el móvil.

LifeDeck expone /api/finance con un token Bearer de ámbito 'finance' (el mismo que usa PersAcc;
se genera en LifeDeck › Ajustes › Conexión con PersAcc):
  GET  ?op=ping       → {ok: true}
  POST ?op=portfolio  {as_of, net_worth, portfolio_value, cash, crypto_value, invested, gain,
                       return_pct, twr_annual_pct, top[], classes[], series[]} → {ok: true}

Solo se envían totales, reparto y una serie reducida: nunca operaciones sueltas.
La configuración (URL, token) vive en processing/lifedeck.json, que está en .gitignore.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import Any

from src import config
from src.file_lock import interprocess_lock

_log = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(config.PROCESSING_DIR, "lifedeck.json")
TIMEOUT = 15
MAX_POINTS = 180
MAX_SLICES = 12
MAX_POSITIONS = 150

_ERRORS = {
    "unauthorized": "Token no válido. Genera uno en LifeDeck › Ajustes › Conexión con PersAcc.",
    "server_not_configured": "El servidor de LifeDeck no está configurado.",
}

_lock = threading.Lock()


class LifeDeckError(Exception):
    """Error comprensible para la UI. `transient`: fallo de red/servidor que merece reintento."""

    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


# ── configuración ───────────────────────────────────────────────────────────
# El servidor y la tarea en segundo plano (otro proceso) escriben este fichero. En Windows, abrirlo
# mientras el otro hace os.replace (o al revés) da PermissionError momentáneo: se reintenta.
_IO_RETRIES = 8
_IO_RETRY_DELAY = 0.05


def _read_settings() -> dict[str, Any]:
    """Lee la configuración. {} solo si el fichero no existe; otros errores se propagan."""
    for attempt in range(_IO_RETRIES):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("lifedeck.json no contiene un objeto")
            return data
        except FileNotFoundError:
            return {}
        except PermissionError:
            if attempt == _IO_RETRIES - 1:
                raise
            time.sleep(_IO_RETRY_DELAY * (attempt + 1))
    return {}  # pragma: no cover


def load_settings(strict: bool = False) -> dict[str, Any]:
    """Configuración actual. Con strict=False (UI) un fichero ilegible se ve como vacío;
    con strict=True se propaga el error para no actuar sobre datos que no se han podido leer."""
    try:
        return _read_settings()
    except (OSError, ValueError):
        if strict:
            raise
        _log.warning("No se pudo leer %s", CONFIG_FILE, exc_info=True)
        return {}


def _write_settings(data: dict[str, Any]) -> None:
    directory = os.path.dirname(CONFIG_FILE)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix="lifedeck.json.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        for attempt in range(_IO_RETRIES):
            try:
                os.replace(tmp, CONFIG_FILE)
                break
            except PermissionError:
                if attempt == _IO_RETRIES - 1:
                    raise
                time.sleep(_IO_RETRY_DELAY * (attempt + 1))
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    """Lee-modifica-escribe bajo cerrojo (hilos y procesos). Si la lectura falla NO escribe:
    reescribir solo el parche borraría la URL y el token guardados."""
    with _lock, interprocess_lock(CONFIG_FILE):
        cur = _read_settings()
        cur.update({k: v for k, v in patch.items() if v is not None})
        _write_settings(cur)
        return cur


def public_settings() -> dict[str, Any]:
    """Para la UI: nunca devuelve el token."""
    s = load_settings()
    return {
        "enabled": bool(s.get("enabled")),
        "url": s.get("url") or "",
        "has_token": bool(s.get("token")),
        "last_push_at": s.get("last_push_at"),
        "last_error": s.get("last_error"),
        "auto_minutes": int(s.get("auto_minutes") or 30),
        "last_auto_at": s.get("last_auto_at"),
        "last_auto_error": s.get("last_auto_error") or None,
    }


# ── cliente HTTP ────────────────────────────────────────────────────────────
def _request(method: str, op: str, body: dict | None = None, s: dict | None = None) -> dict:
    if s is None:
        try:
            s = _read_settings()
        except (OSError, ValueError) as exc:
            raise LifeDeckError(f"No se pudo leer la configuración de LifeDeck: {exc}", transient=True) from None
    url = str(s.get("url") or "").strip().rstrip("/")
    token = str(s.get("token") or "").strip()
    if not url:
        raise LifeDeckError("Falta la URL de LifeDeck.")
    if not token:
        raise LifeDeckError("Falta el token de LifeDeck.")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{url}/api/finance?op={op}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            text = res.read().decode("utf-8") or "{}"
            return json.loads(text)
    except urllib.error.HTTPError as exc:
        code = ""
        try:
            code = json.loads(exc.read().decode("utf-8")).get("error", "")
        except Exception:
            pass
        raise LifeDeckError(_ERRORS.get(code, f"LifeDeck respondió {exc.code} ({code or 'error'})."),
                            transient=exc.code >= 500 or exc.code == 429) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LifeDeckError(f"No se pudo conectar con LifeDeck: {getattr(exc, 'reason', exc)}",
                            transient=True) from None


def test_connection() -> tuple[bool, str]:
    try:
        _request("GET", "ping")
        return True, "Conectado a LifeDeck."
    except LifeDeckError as exc:
        return False, str(exc)


# ── resumen ─────────────────────────────────────────────────────────────────
def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 2) if f == f and abs(f) != float("inf") else None


def _downsample(points: list[dict], n: int = MAX_POINTS) -> list[dict]:
    if len(points) <= n:
        return points
    step = len(points) / (n - 1)
    out = [points[int(i * step)] for i in range(n - 1)]
    out.append(points[-1])
    return out


def latest_price_date(path: str | None = None) -> str | None:
    """Día (YYYY-MM-DD) de la cotización real más reciente en la caché de precios.

    La caché solo guarda cotizaciones descargadas (el relleno hasta hoy se hace al leerla), así que
    si Yahoo falla esta fecha se queda atrás aunque el panel diga «hoy». None si no hay caché."""
    path = path or config.PRICES_CACHE_FILE
    for attempt in range(_IO_RETRIES):
        try:
            last = None
            with open(path, encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                next(reader, None)  # cabecera
                for row in reader:
                    if row and any(c.strip() for c in row[1:]):
                        last = row[0]
            if not last:
                return None
            return date.fromisoformat(last.strip()[:10]).isoformat()
        except PermissionError:
            if attempt == _IO_RETRIES - 1:
                return None
            time.sleep(_IO_RETRY_DELAY * (attempt + 1))
        except (OSError, ValueError, csv.Error):
            return None
    return None  # pragma: no cover


def build_payload(dash: dict, prices_as_of: str | None = None) -> dict:
    """Convierte la respuesta de /api/dashboard en el resumen que acepta LifeDeck.

    `prices_as_of`: día de la última cotización real. Si es anterior a la fecha del panel (que
    siempre rellena hasta hoy), as_of usa esa fecha para no presentar precios viejos como de hoy."""
    m = dash.get("metrics") or {}
    portfolio = _num(dash.get("portfolio_total_value"))
    net = _num(dash.get("net_worth"))
    if net is None:
        raise LifeDeckError("El panel no tiene patrimonio calculado.")

    top = []
    for a in (dash.get("top_assets") or [])[:MAX_SLICES]:
        v = _num(a.get("value"))
        if v is None or not a.get("name"):
            continue
        top.append({"name": str(a["name"])[:80], "value": v, "pct": round(v / portfolio * 100, 2) if portfolio else None})

    classes = []
    for c in (dash.get("class_breakdown") or [])[:MAX_SLICES]:
        v = _num(c.get("value"))
        if v is None or not c.get("name"):
            continue
        classes.append({"name": str(c["name"])[:80], "value": v, "pct": _num(c.get("pct"))})

    positions = []
    for a in (dash.get("composition_full") or [])[:MAX_POSITIONS]:
        v = _num(a.get("value"))
        if v is None or v <= 0 or not a.get("name"):
            continue
        positions.append({"name": str(a["name"])[:80], "value": v,
                          "pct": round(v / portfolio * 100, 2) if portfolio else None})

    chart = dash.get("portfolio_chart") or {}
    invested = {p.get("x"): _num(p.get("y")) for p in (chart.get("invested") or [])}
    series = [
        {"d": str(p.get("x"))[:10], "v": _num(p.get("y")), "i": invested.get(p.get("x"))}
        for p in (chart.get("value") or [])
        if p.get("x") and _num(p.get("y")) is not None
    ]

    as_of = str(m.get("fecha_actual") or (series[-1]["d"] if series else datetime.now().strftime("%Y-%m-%d")))[:10]
    if prices_as_of and prices_as_of[:10] < as_of:
        as_of = prices_as_of[:10]
    return {
        "as_of": as_of,
        "prices_as_of": prices_as_of[:10] if prices_as_of else None,
        "net_worth": net,
        "portfolio_value": portfolio,
        "cash": _num(dash.get("cash_total")),
        "crypto_value": _num(dash.get("crypto_total_value")),
        "invested": _num(m.get("capital_total")),
        "gain": _num(m.get("plusvalia_total")),
        "return_pct": _num(m.get("rentabilidad_total")),
        "twr_annual_pct": _num(m.get("twr_total_anual")),
        "top": top,
        "classes": classes,
        "positions": positions,
        "series": _downsample(series),
    }


def _record(patch: dict[str, Any]) -> None:
    """Guarda estado (hora/error) sin que un fallo de disco cambie el resultado de la subida."""
    try:
        save_settings(patch)
    except (OSError, ValueError):
        _log.warning("No se pudo guardar el estado de LifeDeck %s", list(patch), exc_info=True)


def push(dash: dict) -> dict:
    """Sube el resumen y guarda la hora/error en la configuración.

    Devuelve {ok, last_push_at, as_of, prices_as_of}. Si la subida fue bien pero no se puede
    anotar en lifedeck.json, sigue contando como éxito (el móvil ya tiene los datos)."""
    try:
        payload = build_payload(dash, latest_price_date())
        _request("POST", "portfolio", payload)
    except LifeDeckError as exc:
        _record({"last_error": str(exc)})
        raise
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _record({"last_push_at": now, "last_error": ""})
    return {"ok": True, "last_push_at": now, "as_of": payload["as_of"], "prices_as_of": payload["prices_as_of"]}


def push_in_background(dash: dict) -> None:
    """Tras recalcular el panel: sube sin bloquear si está activado. Los errores quedan en last_error."""
    s = load_settings()
    if not (s.get("enabled") and s.get("url") and s.get("token")):
        return

    def run():
        try:
            push(dash)
        except LifeDeckError as exc:
            _log.warning("LifeDeck push failed: %s", exc)
        except Exception:
            _log.exception("LifeDeck push crashed")

    threading.Thread(target=run, name="lifedeck-push", daemon=True).start()
