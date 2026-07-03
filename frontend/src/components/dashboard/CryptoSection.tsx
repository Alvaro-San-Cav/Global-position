import { useMemo } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { CryptoChart, CryptoSlice } from '@/api/types'
import { fmtDate, fmtEur, fmtPct } from '@/lib/format'

interface Row {
  x: string
  value: number | null
  invested: number | null
}

function mergeSeries(chart: CryptoChart): Row[] {
  const byDate = new Map<string, Row>()
  const ensure = (x: string): Row => {
    let r = byDate.get(x)
    if (!r) {
      r = { x, value: null, invested: null }
      byDate.set(x, r)
    }
    return r
  }
  for (const p of chart.value ?? []) ensure(p.x).value = p.y
  for (const p of chart.invested ?? []) ensure(p.x).invested = p.y
  const rows = [...byDate.values()].sort((a, b) => a.x.localeCompare(b.x))
  const firstPositive = rows.findIndex((r) => (r.value ?? 0) > 0)
  return firstPositive > 0 ? rows.slice(firstPositive) : rows
}

export function CryptoSection({
  chart,
  breakdown,
}: {
  chart: CryptoChart | null | undefined
  breakdown: CryptoSlice[] | null | undefined
}) {
  const rows = useMemo(() => (chart ? mergeSeries(chart) : []), [chart])

  return (
    <div>
      {rows.length > 0 && (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
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
            <Line
              type="monotone"
              dataKey="value"
              name="Valor crypto"
              stroke="#10b981"
              strokeWidth={2.5}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="invested"
              name="Capital aportado"
              stroke="#34d399"
              strokeWidth={1.8}
              strokeDasharray="6 4"
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {breakdown && breakdown.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {breakdown.map((c) => (
            <div
              key={c.symbol}
              className="flex items-center gap-2 rounded-full bg-card2 px-3 py-1 text-xs"
            >
              <span className="font-semibold text-txt">{c.symbol}</span>
              <span className="text-txt2">{fmtEur(c.value)}</span>
              <span className="text-amber">{fmtPct(c.pct)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
