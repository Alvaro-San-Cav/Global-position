import { useMemo, useState } from 'react'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { parseISO, subDays, subMonths, subYears } from 'date-fns'
import { Card } from '@/components/ui/card'
import type { PortfolioChart, XY } from '@/api/types'
import { fmtDate, fmtEur, fmtPct, signColor } from '@/lib/format'

type PeriodKey = 'Ayer' | 'Semana' | 'Mes' | 'Trimestre' | 'Año' | 'Histórico'

const PERIODS: { key: PeriodKey; back: (d: Date) => Date }[] = [
  { key: 'Ayer', back: (d) => subDays(d, 1) },
  { key: 'Semana', back: (d) => subDays(d, 7) },
  { key: 'Mes', back: (d) => subMonths(d, 1) },
  { key: 'Trimestre', back: (d) => subMonths(d, 3) },
  { key: 'Año', back: (d) => subYears(d, 1) },
  { key: 'Histórico', back: (d) => d },
]

/** Last point whose date is <= cutoff; falls back to the first point. */
function pointAtOrBefore(series: XY[], cutoff: Date): XY {
  let ref = series[0]
  for (const p of series) {
    if (parseISO(p.x) <= cutoff) ref = p
    else break
  }
  return ref
}

interface Delta {
  from: XY
  to: XY
  diff: number
  pct: number | null
  /** Net contributions (aportaciones) during the period. */
  flows: number
  /** Market variation excluding contributions. */
  market: number
}

function computeDelta(chart: PortfolioChart, period: PeriodKey): Delta | null {
  let value = [...(chart.value ?? [])]
    .filter((p) => p.y != null)
    .sort((a, b) => a.x.localeCompare(b.x))
  // Trim leading zero-value rows (parity with PortfolioChart) so Histórico
  // starts at the first day with a real position instead of a 0 € point.
  const firstPositive = value.findIndex((p) => p.y > 0)
  if (firstPositive > 0) value = value.slice(firstPositive)
  if (value.length < 2) return null

  const to = value[value.length - 1]
  let from: XY
  if (period === 'Histórico') {
    from = value[0]
  } else {
    const cutoff = PERIODS.find((p) => p.key === period)!.back(parseISO(to.x))
    from = pointAtOrBefore(value, cutoff)
  }
  if (from.x === to.x) from = value[value.length - 2]

  const invested = [...(chart.invested ?? [])].sort((a, b) => a.x.localeCompare(b.x))
  let flows = 0
  if (invested.length > 0) {
    const invFrom = pointAtOrBefore(invested, parseISO(from.x))
    const invTo = pointAtOrBefore(invested, parseISO(to.x))
    flows = invTo.y - invFrom.y
  }

  const diff = to.y - from.y
  return {
    from,
    to,
    diff,
    pct: from.y > 0 ? (diff / from.y) * 100 : null,
    flows,
    market: diff - flows,
  }
}

export function CapitalDelta({ chart }: { chart: PortfolioChart }) {
  const [period, setPeriod] = useState<PeriodKey>('Ayer')
  const delta = useMemo(() => computeDelta(chart, period), [chart, period])

  if (!delta) return null

  const Icon = delta.diff >= 0 ? TrendingUp : TrendingDown
  const hasFlows = Math.abs(delta.flows) >= 0.01

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-txt2">
          Variación de capital · desde {fmtDate(delta.from.x)}
        </div>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              aria-pressed={period === p.key}
              onClick={() => setPeriod(p.key)}
              className={`rounded-[var(--radius-card)] px-2.5 py-1 text-xs font-medium transition-colors ${
                period === p.key
                  ? 'bg-accent text-white'
                  : 'bg-card2 text-txt2 hover:text-txt'
              }`}
            >
              {p.key}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <div className={`flex items-center gap-2 text-2xl font-semibold tabular-nums ${signColor(delta.diff)}`}>
          <Icon className="h-5 w-5" />
          {`${delta.diff >= 0 ? '+' : ''}${fmtEur(delta.diff)}`}
        </div>
        <div className={`text-sm font-medium tabular-nums ${signColor(delta.pct)}`}>
          {`${delta.pct != null && delta.pct >= 0 ? '+' : ''}${fmtPct(delta.pct)}`}
        </div>
        <div className="text-xs text-txt2 tabular-nums">
          {fmtEur(delta.from.y)} → {fmtEur(delta.to.y)}
        </div>
      </div>

      {hasFlows && (
        <div className="mt-1.5 text-xs text-txt2 tabular-nums">
          Aportaciones netas en el periodo: {fmtEur(delta.flows)} · Variación de
          mercado (sin aportaciones):{' '}
          <span className={`font-medium ${signColor(delta.market)}`}>
            {`${delta.market >= 0 ? '+' : ''}${fmtEur(delta.market)}`}
          </span>
        </div>
      )}
    </Card>
  )
}
