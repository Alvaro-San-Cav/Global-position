import { useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { parseISO, subYears } from 'date-fns'
import type { PortfolioChart as PortfolioChartData } from '@/api/types'
import { fmtEur, fmtDate } from '@/lib/format'

type Range = '1A' | '3A' | '5A' | 'Todo'

const RANGES: { key: Range; years: number | null }[] = [
  { key: '1A', years: 1 },
  { key: '3A', years: 3 },
  { key: '5A', years: 5 },
  { key: 'Todo', years: null },
]

interface Row {
  x: string
  value: number | null
  invested: number | null
  benchmark: number | null
  /** Green band between value and invested when value >= invested. */
  gain: [number, number] | null
}

/** Merge the three parallel {x,y} series into one row-per-date dataset. */
function mergeSeries(data: PortfolioChartData): Row[] {
  const byDate = new Map<string, Row>()
  const ensure = (x: string): Row => {
    let r = byDate.get(x)
    if (!r) {
      r = { x, value: null, invested: null, benchmark: null, gain: null }
      byDate.set(x, r)
    }
    return r
  }
  for (const p of data.value ?? []) ensure(p.x).value = p.y
  for (const p of data.invested ?? []) ensure(p.x).invested = p.y
  for (const p of data.benchmark ?? []) ensure(p.x).benchmark = p.y

  const rows = [...byDate.values()].sort((a, b) => a.x.localeCompare(b.x))
  // Trim leading rows where the portfolio value is still zero (parity with legacy).
  const firstPositive = rows.findIndex((r) => (r.value ?? 0) > 0)
  const trimmed = firstPositive > 0 ? rows.slice(firstPositive) : rows
  for (const r of trimmed) {
    if (r.value != null && r.invested != null && r.value >= r.invested) {
      r.gain = [r.invested, r.value]
    }
  }
  return trimmed
}

/** Benchmark is only meaningful if it has >1 distinct value. */
function benchmarkIsValid(rows: Row[]): boolean {
  const vals = new Set<string>()
  for (const r of rows) if (r.benchmark != null) vals.add(r.benchmark.toFixed(4))
  return vals.size > 1
}

export function PortfolioChart({
  data,
  benchmarkName,
}: {
  data: PortfolioChartData
  benchmarkName?: string | null
}) {
  const [range, setRange] = useState<Range>('Todo')
  const rows = useMemo(() => mergeSeries(data), [data])
  const showBenchmark = useMemo(() => benchmarkIsValid(rows), [rows])

  const filtered = useMemo(() => {
    const cfg = RANGES.find((r) => r.key === range)
    if (!cfg?.years || rows.length === 0) return rows
    const last = parseISO(rows[rows.length - 1].x)
    const cutoff = subYears(last, cfg.years)
    return rows.filter((r) => parseISO(r.x) >= cutoff)
  }, [rows, range])

  return (
    <div>
      <div className="mb-3 flex justify-end gap-1">
        {RANGES.map((r) => (
          <button
            key={r.key}
            type="button"
            aria-pressed={range === r.key}
            onClick={() => setRange(r.key)}
            className={`rounded-[var(--radius-card)] px-2.5 py-1 text-xs font-medium transition-colors ${
              range === r.key
                ? 'bg-accent text-white'
                : 'bg-card2 text-txt2 hover:text-txt'
            }`}
          >
            {r.key}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={filtered} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="pf-gain" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity={0.28} />
              <stop offset="100%" stopColor="#10b981" stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" strokeOpacity={0.4} vertical={false} />
          <XAxis
            dataKey="x"
            tickFormatter={(x: string) => fmtDate(x)}
            tick={{ fill: '#7d8fa8', fontSize: 11 }}
            minTickGap={48}
            axisLine={{ stroke: 'var(--border)' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#7d8fa8', fontSize: 11 }}
            tickFormatter={(v: number) => `€${v.toLocaleString('es-ES')}`}
            axisLine={false}
            tickLine={false}
            width={72}
          />
          <Tooltip
            labelFormatter={(x) => fmtDate(String(x))}
            formatter={(v, name) => [fmtEur(typeof v === 'number' ? v : undefined), name]}
            contentStyle={{
              background: 'var(--card2)',
              border: '1px solid var(--border2)',
              borderRadius: 8,
              color: 'var(--txt)',
              fontSize: 12,
            }}
          />
          {/* Green band between invested and value (only where value >= invested). */}
          <Area
            type="monotone"
            dataKey="gain"
            name="Plusvalía"
            stroke="none"
            fill="url(#pf-gain)"
            isAnimationActive={false}
            connectNulls={false}
            legendType="none"
            tooltipType="none"
          />
          <Line
            type="monotone"
            dataKey="value"
            name="Valor cartera"
            stroke="#6366f1"
            strokeWidth={2.5}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="invested"
            name="Capital invertido"
            stroke="#7d8fa8"
            strokeWidth={1.8}
            strokeDasharray="6 4"
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
          {showBenchmark && (
            <Line
              type="monotone"
              dataKey="benchmark"
              name={benchmarkName || 'Benchmark'}
              stroke="#fbbf24"
              strokeWidth={1.8}
              strokeDasharray="3 4"
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
