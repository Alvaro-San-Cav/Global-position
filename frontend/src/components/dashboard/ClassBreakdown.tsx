import { useState } from 'react'
import { AlertTriangle, ChevronDown, CircleCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ClassSlice, RebalanceResponse, RebalanceRow } from '@/api/types'
import { fmtEur, fmtPct } from '@/lib/format'
import { cn } from '@/lib/utils'

// Stable colour per known class; unknown classes fall back by index.
const CLASS_COLORS: Record<string, string> = {
  Acciones: '#6366f1',
  ETF: '#06b6d4',
  'Oro / Materias primas': '#f59e0b',
  Bonos: '#10b981',
  Cripto: '#f7931a',
}
const FALLBACK = ['#8b5cf6', '#ec4899', '#3b82f6', '#14b8a6', '#a855f7', '#64748b']

function colorFor(name: string, i: number): string {
  return CLASS_COLORS[name] ?? FALLBACK[i % FALLBACK.length]
}

/** "Cripto está en 20,4 % (objetivo 25,0 %, banda ±3,0 %) — comprar 5361,85 €" */
function driftMessage(r: RebalanceRow): string {
  const head =
    `${r.asset_class} está en ${fmtPct(r.actual_pct, 1)} ` +
    `(objetivo ${fmtPct(r.target_pct ?? 0, 1)}, banda ±${fmtPct(r.band_pct, 1)})`
  if (r.action_eur == null) return head
  const verb = r.action_eur > 0 ? 'comprar' : 'vender'
  return `${head} — ${verb} ${fmtEur(Math.abs(r.action_eur))}`
}

export function ClassBreakdown({
  classes,
  rebalance,
}: {
  classes: ClassSlice[]
  rebalance?: RebalanceResponse
}) {
  const [open, setOpen] = useState<string | null>(null)
  if (!classes.length) return null

  const configured = rebalance?.configured ?? false
  const byClass = new Map<string, RebalanceRow>(
    (rebalance?.rows ?? []).map((r) => [r.asset_class, r]),
  )
  // Only classes that actually have a target can deviate from it.
  const offTarget = (rebalance?.rows ?? []).filter(
    (r) => r.has_target && r.status !== 'ok',
  )
  const violations = rebalance?.violations ?? []
  const alerts = configured ? offTarget.length + violations.length : 0

  return (
    <div>
      {/* Stacked proportion bar */}
      <div className="mb-4 flex h-3 w-full overflow-hidden rounded-full bg-card2">
        {classes.map((c, i) => (
          <div
            key={c.name}
            className="h-full"
            style={{ width: `${c.pct}%`, background: colorFor(c.name, i) }}
            title={`${c.name} · ${fmtPct(c.pct, 1)}`}
          />
        ))}
      </div>

      {/* Legend / list */}
      <div className="space-y-1">
        {classes.map((c, i) => {
          const isOpen = open === c.name
          const row = configured ? byClass.get(c.name) : undefined
          return (
            <div key={c.name} className="rounded-[var(--radius-card)]">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : c.name)}
                className="flex w-full items-center gap-3 px-1 py-1.5 text-left hover:bg-card2"
              >
                <span
                  className="size-3 shrink-0 rounded-[3px]"
                  style={{ background: colorFor(c.name, i) }}
                />
                <span className="flex-1 truncate text-sm text-txt">{c.name}</span>
                {row && (
                  <>
                    <span className="hidden text-xs tabular-nums text-txt3 sm:inline">
                      {row.has_target ? `obj. ${fmtPct(row.target_pct ?? 0, 1)}` : 'sin objetivo'}
                    </span>
                    <span
                      className={cn(
                        'flex w-20 flex-col items-end text-right text-xs font-medium tabular-nums',
                        row.within_band
                          ? 'text-txt3'
                          : (row.drift_pct ?? 0) > 0
                            ? 'text-red'
                            : 'text-amber',
                      )}
                    >
                      {row.has_target ? (
                        <>
                          <span>
                            {(row.drift_pct ?? 0) > 0 ? '+' : ''}
                            {fmtPct(row.drift_pct ?? 0, 1)}
                          </span>
                          {row.action_eur != null && (
                            <span className="text-[10px] font-normal leading-tight">
                              {row.action_eur > 0 ? '+' : ''}
                              {fmtEur(row.action_eur, 0)}
                            </span>
                          )}
                        </>
                      ) : (
                        '—'
                      )}
                    </span>
                  </>
                )}
                <span className="text-sm tabular-nums text-txt2">{fmtEur(c.value)}</span>
                <span className="w-14 text-right text-sm font-medium tabular-nums text-txt">
                  {fmtPct(c.pct, 1)}
                </span>
                <ChevronDown
                  className={cn(
                    'size-4 shrink-0 text-txt3 transition-transform',
                    isOpen && 'rotate-180',
                  )}
                />
              </button>

              {isOpen && (
                <div className="mb-1 ml-6 border-l border-border-subtle pl-3">
                  {c.members.map((m) => (
                    <div
                      key={m.symbol}
                      className="flex items-center gap-2 py-0.5 text-xs text-txt2"
                    >
                      <span className="flex-1 truncate">{m.name}</span>
                      <span className="tabular-nums">{fmtEur(m.value)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ── Desviaciones vs cartera objetivo ── */}
      <div className="mt-4 border-t border-border-subtle pt-3">
        {!configured ? (
          <p className="text-xs text-txt3">
            Define tu{' '}
            <Link to="/objetivo" className="font-medium text-accent hover:underline">
              cartera objetivo
            </Link>{' '}
            para ver aquí las desviaciones.
          </p>
        ) : (
          <>
            <h4 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-txt3">
              Desviaciones vs objetivo
            </h4>

            {rebalance?.note && (
              <p className="mb-2 rounded-[var(--radius-card)] bg-amber-dim px-3 py-2 text-xs text-amber">
                {rebalance.note}
              </p>
            )}

            {alerts === 0 ? (
              <p className="flex items-center gap-2 text-xs text-green">
                <CircleCheck className="size-3.5 shrink-0" />
                Todas las clases dentro de la banda de tolerancia.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {offTarget.map((r) => (
                  <li
                    key={r.asset_class}
                    className={cn(
                      'flex items-start gap-2 rounded-[var(--radius-card)] px-3 py-2 text-xs text-txt',
                      r.status === 'vender' ? 'bg-red-dim/60' : 'bg-amber-dim/60',
                    )}
                  >
                    <AlertTriangle
                      className={cn(
                        'mt-0.5 size-3.5 shrink-0',
                        r.status === 'vender' ? 'text-red' : 'text-amber',
                      )}
                    />
                    <span>{driftMessage(r)}</span>
                  </li>
                ))}
                {violations.map((v, i) => (
                  <li
                    key={`${v.kind}-${v.target}-${i}`}
                    className="flex items-start gap-2 rounded-[var(--radius-card)] bg-red-dim/60 px-3 py-2 text-xs text-txt"
                  >
                    <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-red" />
                    <span>{v.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </div>
  )
}
