import { useMemo } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { subMonths } from 'date-fns'
import type { XY } from '@/api/types'
import { fmtDate, fmtEur } from '@/lib/format'
import { MILESTONES, type ProjectionPoint } from '@/lib/milestones'

interface Row {
  x: string
  hist: number | null
  proj: number | null
  contrib: number | null
}

const HISTORY_MONTHS = 24

function short(v: number): string {
  return v >= 1_000_000 ? `${v / 1_000_000} M` : `${v / 1000}k`
}

/** Histórico real (últimos 24 meses) + curva proyectada en un único dataset. */
export function MilestonesChart({
  history,
  cashOffset,
  projection,
}: {
  history: XY[] | null | undefined
  /** Efectivo actual, sumado al histórico (que solo recoge la cartera). */
  cashOffset: number
  projection: ProjectionPoint[]
}) {
  const rows = useMemo<Row[]>(() => {
    const byDate = new Map<string, Row>()
    const ensure = (x: string) => {
      let r = byDate.get(x)
      if (!r) {
        r = { x, hist: null, proj: null, contrib: null }
        byDate.set(x, r)
      }
      return r
    }
    const pts = (history ?? []).filter((p) => Number.isFinite(p.y) && !Number.isNaN(Date.parse(p.x)))
    const lastHist = pts.length ? new Date(pts[pts.length - 1].x) : null
    const cutoff = lastHist ? subMonths(lastHist, HISTORY_MONTHS).getTime() : 0
    for (const p of pts) if (Date.parse(p.x) >= cutoff) ensure(p.x).hist = p.y + cashOffset
    for (const p of projection) {
      const r = ensure(p.x)
      r.proj = p.proj
      r.contrib = p.contrib
    }
    return [...byDate.values()].sort((a, b) => a.x.localeCompare(b.x))
  }, [history, cashOffset, projection])

  const maxY = useMemo(
    () => Math.max(0, ...rows.map((r) => Math.max(r.hist ?? 0, r.proj ?? 0))),
    [rows],
  )
  const minY = useMemo(() => Math.min(...rows.map((r) => r.hist ?? r.proj ?? Infinity)), [rows])
  const lines = MILESTONES.filter((m) => m.value > minY && m.value <= maxY * 1.02)

  if (rows.length === 0) return null

  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
        <CartesianGrid stroke="var(--border)" strokeOpacity={0.4} vertical={false} />
        <XAxis
          dataKey="x"
          tickFormatter={(x: string) => fmtDate(x)}
          tick={{ fill: '#7d8fa8', fontSize: 11 }}
          minTickGap={56}
          axisLine={{ stroke: 'var(--border)' }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: '#7d8fa8', fontSize: 11 }}
          tickFormatter={(v: number) => `€${v.toLocaleString('es-ES')}`}
          axisLine={false}
          tickLine={false}
          width={80}
          domain={[0, 'auto']}
        />
        <Tooltip
          labelFormatter={(x) => fmtDate(String(x))}
          formatter={(v, name) => [fmtEur(typeof v === 'number' ? v : undefined, 0), name]}
          contentStyle={{
            background: 'var(--card2)',
            border: '1px solid var(--border2)',
            borderRadius: 8,
            color: 'var(--txt)',
            fontSize: 12,
          }}
        />
        {lines.map((m) => (
          <ReferenceLine
            key={m.value}
            y={m.value}
            stroke="var(--border2)"
            strokeDasharray="2 4"
            label={{ value: short(m.value), position: 'insideTopLeft', fill: '#7d8fa8', fontSize: 10 }}
          />
        ))}
        <Line
          type="monotone"
          dataKey="hist"
          name="Patrimonio real"
          stroke="#6366f1"
          strokeWidth={2.5}
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="proj"
          name="Patrimonio proyectado"
          stroke="#10b981"
          strokeWidth={2.5}
          strokeDasharray="6 4"
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="contrib"
          name="Capital aportado (proy.)"
          stroke="#7d8fa8"
          strokeWidth={1.6}
          strokeDasharray="3 4"
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
