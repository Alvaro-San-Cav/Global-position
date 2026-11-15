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

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src import config

_log = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(config.PROCESSING_DIR, "lifedeck.json")
TIMEOUT = 15
MAX_POINTS = 180
MAX_SLICES = 12

_ERRORS = {
    "unauthorized": "Token no válido. Genera uno en LifeDeck › Ajustes › Conexión con PersAcc.",
    "server_not_configured": "El servidor de LifeDeck no está configurado.",
}

_lock = threading.Lock()


class LifeDeckError(Exception):
    pass


# ── configuración ───────────────────────────────────────────────────────────
def load_settings() -> dict[str, Any]:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        cur = load_settings()
        cur.update({k: v for k, v in patch.items() if v is not None})
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_FILE)
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
    }


# ── cliente HTTP ────────────────────────────────────────────────────────────
def _request(method: str, op: str, body: dict | None = None, s: dict | None = None) -> dict:
    s = s if s is not None else load_settings()
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
        raise LifeDeckError(_ERRORS.get(code, f"LifeDeck respondió {exc.code} ({code or 'error'}).")) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LifeDeckError(f"No se pudo conectar con LifeDeck: {getattr(exc, 'reason', exc)}") from None


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


def build_payload(dash: dict) -> dict:
    """Convierte la respuesta de /api/dashboard en el resumen que acepta LifeDeck."""
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

    chart = dash.get("portfolio_chart") or {}
    invested = {p.get("x"): _num(p.get("y")) for p in (chart.get("invested") or [])}
    series = [
        {"d": str(p.get("x"))[:10], "v": _num(p.get("y")), "i": invested.get(p.get("x"))}
        for p in (chart.get("value") or [])
        if p.get("x") and _num(p.get("y")) is not None
    ]

    as_of = str(m.get("fecha_actual") or (series[-1]["d"] if series else datetime.now().strftime("%Y-%m-%d")))[:10]
    return {
        "as_of": as_of,
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
        "series": _downsample(series),
    }


def push(dash: dict) -> dict:
    """Sube el resumen y guarda la hora/error en la configuración."""
    try:
        _request("POST", "portfolio", build_payload(dash))
    except LifeDeckError as exc:
        save_settings({"last_error": str(exc)})
        raise
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_settings({"last_push_at": now, "last_error": ""})
    return {"ok": True, "last_push_at": now}


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
