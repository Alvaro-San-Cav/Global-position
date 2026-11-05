"""
Target ("cartera tipo") vs actual rebalancing engine.

Given the current net worth (portfolio + cash), the per-asset-class breakdown
and a target-allocation config, compute:

  * per-class rows: target% / actual% / drift / tolerance band / status and the
    EUR amount to buy or sell to hit the target,
  * rule violations: single-asset max weight, per-class min/max limits and the
    cash buffer.

Pure functions, no I/O — the server passes in the already-computed dashboard
figures so this stays offline and cheap.
"""

from __future__ import annotations

CASH_CLASS = "Efectivo"


def _num(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _is_blank(v) -> bool:
    return v is None or str(v).strip() in ("", "None", "null")


def _parse_pct(v, label: str, warnings: list[str], *, lo: float = 0.0,
               hi: float = 100.0, on_negative: str = "reject"):
    """Parse a percentage in [lo, hi].

    Returns None when the value is blank, non numeric (warning added) or
    rejected (negative with on_negative="reject", warning added). Values above
    ``hi`` are clamped (warning added). Blank is NOT a warning: it means "unset".
    """
    if _is_blank(v):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        warnings.append(f"{label}: valor no numérico ({v!r}) ignorado.")
        return None
    if x != x or x in (float("inf"), float("-inf")):
        warnings.append(f"{label}: valor no finito ignorado.")
        return None
    if x < lo:
        if on_negative == "reject":
            warnings.append(f"{label}: {x:g}% es negativo, ignorado.")
            return None
        warnings.append(f"{label}: {x:g}% es negativo, se usa {lo:g}%.")
        return lo
    if x > hi:
        warnings.append(f"{label}: {x:g}% supera {hi:g}%, se limita a {hi:g}%.")
        return hi
    return x


def compute_rebalance(net_worth: float, class_breakdown: list[dict], cfg: dict) -> dict:
    """Build the rebalancing control panel.

    Args:
        net_worth: total value (stocks + crypto + cash) in EUR.
        class_breakdown: list of {name, value, pct, members:[{name,symbol,value}]}.
        cfg: target_portfolio config (see config.get_target_portfolio).

    Validation: every percentage must lie in 0-100. Negative or non numeric
    targets are rejected (the class simply has no target), values above 100 are
    clamped; each correction adds a message to ``note``. ``max_asset_pct`` of
    0/None/blank means "no single-asset limit" (it must not flag every asset);
    the same 0-means-unset rule applies to class ``max`` limits.

    Returns a JSON-serialisable dict (see api_models.RebalanceResponse).
    """
    cfg = cfg if isinstance(cfg, dict) else {}
    warnings: list[str] = []
    targets_raw = cfg.get("targets", {}) or {}
    targets: dict[str, float] = {}
    for k, v in targets_raw.items():
        t = _parse_pct(v, f"Objetivo {k}", warnings)
        if t is not None:
            targets[str(k)] = t
    band = _parse_pct(cfg.get("band_pct"), "Banda", warnings, on_negative="clamp") or 0.0
    max_asset = _parse_pct(cfg.get("max_asset_pct"), "Peso máx. por activo", warnings)
    if max_asset is not None and max_asset <= 0:
        max_asset = None  # 0 = sin límite
    class_limits = cfg.get("class_limits", {}) or {}
    cash_buffer = cfg.get("cash_buffer", {}) or {}

    configured = bool(targets)
    nw = _num(net_worth)

    actual_by_class = {c["name"]: _num(c.get("value")) for c in class_breakdown}
    members_by_class = {c["name"]: (c.get("members") or []) for c in class_breakdown}

    # Union of target classes and classes actually held, targets first (stable order).
    ordered = list(targets.keys())
    for name in actual_by_class:
        if name not in ordered:
            ordered.append(name)

    rows: list[dict] = []
    for cls in ordered:
        act_eur = actual_by_class.get(cls, 0.0)
        act_pct = (act_eur / nw * 100.0) if nw else 0.0

        # A class the user never assigned a target to is NOT a 0% target — it is
        # simply unconstrained. Report it, but never tell them to liquidate it.
        if cls not in targets or not configured:
            rows.append({
                "asset_class": cls,
                "has_target": False,
                "target_pct": None,
                "target_eur": None,
                "actual_pct": round(act_pct, 2),
                "actual_eur": round(act_eur, 2),
                "drift_pct": None,
                "band_pct": round(band, 2),
                "within_band": True,
                "action_eur": None,
                "status": "sin_objetivo" if configured else "ok",
            })
            continue

        tgt_pct = targets[cls]
        tgt_eur = nw * tgt_pct / 100.0
        drift = act_pct - tgt_pct
        within = abs(drift) <= band
        action_eur = tgt_eur - act_eur  # +buy / -sell
        rows.append({
            "asset_class": cls,
            "has_target": True,
            "target_pct": round(tgt_pct, 2),
            "target_eur": round(tgt_eur, 2),
            "actual_pct": round(act_pct, 2),
            "actual_eur": round(act_eur, 2),
            "drift_pct": round(drift, 2),
            "band_pct": round(band, 2),
            "within_band": within,
            "action_eur": round(action_eur, 2),
            "status": "ok" if within else ("comprar" if action_eur > 0 else "vender"),
        })

    violations: list[dict] = []

    # ── Rule: single-asset max weight ──
    if max_asset is not None and nw > 0:
        for cls, members in members_by_class.items():
            for m in members:
                val = _num(m.get("value"))
                pct = val / nw * 100.0
                if pct > max_asset + 1e-9:
                    violations.append({
                        "kind": "max_asset",
                        "target": m.get("name") or m.get("symbol") or "?",
                        "message": (
                            f"{m.get('name') or m.get('symbol')} pesa "
                            f"{pct:.1f}% (máx {max_asset:.0f}%) — vender "
                            f"~{val - nw * max_asset / 100.0:,.0f} €"
                        ),
                        "actual_pct": round(pct, 2),
                        "limit_pct": round(max_asset, 2),
                    })

    # ── Rule: per-class min / max limits ──
    for cls, lim in class_limits.items():
        if not isinstance(lim, dict):
            continue
        act_pct = (actual_by_class.get(cls, 0.0) / nw * 100.0) if nw else 0.0
        lo = _parse_pct(lim.get("min"), f"Mínimo {cls}", warnings)
        hi = _parse_pct(lim.get("max"), f"Máximo {cls}", warnings)
        if hi is not None and hi <= 0:
            hi = None  # 0 = sin límite
        if lo is not None and lo > 0 and act_pct < lo - 1e-9:
            violations.append({
                "kind": "class_min",
                "target": cls,
                "message": f"{cls} está en {act_pct:.1f}% (mín {lo:.0f}%) — comprar",
                "actual_pct": round(act_pct, 2),
                "limit_pct": round(lo, 2),
            })
        if hi is not None and act_pct > hi + 1e-9:
            violations.append({
                "kind": "class_max",
                "target": cls,
                "message": f"{cls} está en {act_pct:.1f}% (máx {hi:.0f}%) — vender",
                "actual_pct": round(act_pct, 2),
                "limit_pct": round(hi, 2),
            })

    # ── Rule: cash buffer ──
    cb_pct = _parse_pct(cash_buffer.get("pct"), "Colchón %", warnings, on_negative="clamp") or 0.0
    cb_amount = max(_num(cash_buffer.get("amount")), 0.0)
    required_cash = max(nw * cb_pct / 100.0, cb_amount)
    if required_cash > 0:
        actual_cash = actual_by_class.get(CASH_CLASS, 0.0)
        deficit = required_cash - actual_cash
        if deficit > 1e-9:
            violations.append({
                "kind": "cash_buffer",
                "target": CASH_CLASS,
                "message": (
                    f"Colchón de efectivo: {actual_cash:,.0f} € < "
                    f"{required_cash:,.0f} € requerido — falta {deficit:,.0f} €"
                ),
                "actual_pct": round((actual_cash / nw * 100.0) if nw else 0.0, 2),
                "limit_pct": round((required_cash / nw * 100.0) if nw else 0.0, 2),
            })

    # Targets need not add up to 100% — classes without a target absorb the rest.
    # Only overshooting 100% is impossible to satisfy.
    target_sum = round(sum(targets.values()), 2)
    notes: list[str] = list(warnings)
    if configured and target_sum > 100.0 + 0.01:
        notes.append(
            f"Los objetivos suman {target_sum:.0f}% (no pueden superar el 100%)."
        )

    return {
        "configured": configured,
        "net_worth": round(nw, 2),
        "target_sum_pct": target_sum,
        "band_pct": round(band, 2),
        "rows": rows,
        "violations": violations,
        "note": " ".join(notes),
    }
