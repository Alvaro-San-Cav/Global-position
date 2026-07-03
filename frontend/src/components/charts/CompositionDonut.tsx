import { useMemo } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import type { AssetSlice } from '@/api/types'
import { fmtEur } from '@/lib/format'

const PIE_COLORS = [
  '#6366f1',
  '#8b5cf6',
  '#ec4899',
  '#f59e0b',
  '#10b981',
  '#06b6d4',
  '#3b82f6',
  '#a855f7',
  '#f43f5e',
  '#14b8a6',
  '#eab308',
  '#64748b',
]

function label(a: AssetSlice): string {
  const sym = (a.symbol || '').trim()
  if (sym && sym.toLowerCase() !== 'otros') return sym
  return (a.name || sym || '—').trim()
}

export function CompositionDonut({
  composition,
  topAssets,
  totalValue,
}: {
  composition: AssetSlice[]
  topAssets: AssetSlice[]
  totalValue: number
}) {
  const total = useMemo(
    () => totalValue || composition.reduce((a, b) => a + (b.value || 0), 0),
    [composition, totalValue],
  )

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const renderTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null
    const row = payload[0].payload as AssetSlice | undefined
    if (!row) return null
    const pct = total > 0 ? (row.value / total) * 100 : 0
    return (
      <div className="rounded-[8px] border border-border-strong bg-card2 px-3 py-2 text-xs text-txt">
        <div className="font-semibold">{row.name || label(row)}</div>
        <div className="text-txt2">
          {fmtEur(row.value)} · {pct.toFixed(1)}%
        </div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie
            data={composition}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius="92%"
            stroke="var(--card)"
            strokeWidth={1.2}
            isAnimationActive={false}
          >
            {composition.map((_, i) => (
              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip content={renderTooltip} />
        </PieChart>
      </ResponsiveContainer>

      <div className="min-w-0">
        <div className="mb-1 grid grid-cols-[minmax(0,1fr)_auto_auto] gap-x-4 border-b border-border-subtle pb-1 text-xs font-medium text-txt2">
          <div>Activo</div>
          <div className="text-right">%</div>
          <div className="text-right">Valor</div>
        </div>
        <div className="max-h-[240px] overflow-y-auto">
          {topAssets.length === 0 && (
            <div className="py-2 text-xs text-txt2">Sin datos de composición</div>
          )}
          {topAssets.map((a, i) => {
            const pct = total > 0 ? (a.value / total) * 100 : 0
            return (
              <div
                key={`${a.symbol}-${i}`}
                className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-4 py-1 text-xs"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: PIE_COLORS[i % PIE_COLORS.length] }}
                  />
                  <span className="truncate text-txt" title={a.name || label(a)}>
                    {a.name || label(a)}
                  </span>
                </div>
                <div className="text-right text-txt2">{pct.toFixed(2)}%</div>
                <div className="text-right tabular-nums text-txt">{fmtEur(a.value)}</div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
