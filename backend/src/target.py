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


def compute_rebalance(net_worth: float, class_breakdown: list[dict], cfg: dict) -> dict:
    """Build the rebalancing control panel.

    Args:
        net_worth: total value (stocks + crypto + cash) in EUR.
        class_breakdown: list of {name, value, pct, members:[{name,symbol,value}]}.
        cfg: target_portfolio config (see config.get_target_portfolio).

    Returns a JSON-serialisable dict (see api_models.RebalanceResponse).
    """
    targets_raw = cfg.get("targets", {}) if isinstance(cfg, dict) else {}
    targets = {str(k): _num(v) for k, v in targets_raw.items() if str(v).strip() != ""}
    band = _num(cfg.get("band_pct"), 0.0)
    max_asset = cfg.get("max_asset_pct")
    max_asset = _num(max_asset) if str(max_asset).strip() not in ("", "None") else None
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
        tgt_pct = targets.get(cls, 0.0)
        tgt_eur = nw * tgt_pct / 100.0
        act_eur = actual_by_class.get(cls, 0.0)
        act_pct = (act_eur / nw * 100.0) if nw else 0.0
        drift = act_pct - tgt_pct
        within = abs(drift) <= band or not configured
        action_eur = tgt_eur - act_eur  # +buy / -sell
        if not configured or within:
            status = "ok"
        elif action_eur > 0:
            status = "comprar"
        else:
            status = "vender"
        rows.append({
            "asset_class": cls,
            "target_pct": round(tgt_pct, 2),
            "target_eur": round(tgt_eur, 2),
            "actual_pct": round(act_pct, 2),
            "actual_eur": round(act_eur, 2),
            "drift_pct": round(drift, 2),
            "band_pct": round(band, 2),
            "within_band": within,
            "action_eur": round(action_eur, 2),
            "status": status,
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
        lo = lim.get("min")
        hi = lim.get("max")
        if str(lo).strip() not in ("", "None") and act_pct < _num(lo) - 1e-9:
            violations.append({
                "kind": "class_min",
                "target": cls,
                "message": f"{cls} está en {act_pct:.1f}% (mín {_num(lo):.0f}%) — comprar",
                "actual_pct": round(act_pct, 2),
                "limit_pct": round(_num(lo), 2),
            })
        if str(hi).strip() not in ("", "None") and act_pct > _num(hi) + 1e-9:
            violations.append({
                "kind": "class_max",
                "target": cls,
                "message": f"{cls} está en {act_pct:.1f}% (máx {_num(hi):.0f}%) — vender",
                "actual_pct": round(act_pct, 2),
                "limit_pct": round(_num(hi), 2),
            })

    # ── Rule: cash buffer ──
    cb_pct = _num(cash_buffer.get("pct"))
    cb_amount = _num(cash_buffer.get("amount"))
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

    target_sum = round(sum(targets.values()), 2)
    notes: list[str] = []
    if configured and abs(target_sum - 100.0) > 0.01:
        notes.append(f"Los objetivos suman {target_sum:.0f}% (deberían sumar 100%).")

    return {
        "configured": configured,
        "net_worth": round(nw, 2),
        "target_sum_pct": target_sum,
        "band_pct": round(band, 2),
        "rows": rows,
        "violations": violations,
        "note": " ".join(notes),
    }
