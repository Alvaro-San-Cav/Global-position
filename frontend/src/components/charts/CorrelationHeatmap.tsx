import type { Correlation, CorrelationPair } from '@/api/types'
import { Badge } from '@/components/ui/badge'

/** Interpolate cell background red(−1) → neutral(0) → green(+1). */
function cellBg(v: number): string {
  const a = Math.min(0.78, Math.max(0.1, 0.1 + Math.abs(v) * 0.68))
  return v >= 0 ? `rgba(16,185,129,${a})` : `rgba(248,113,113,${a})`
}

function cellText(v: number): string {
  return Math.abs(v) >= 0.45 ? '#ffffff' : '#e2e8f0'
}

function PairRow({ pair }: { pair: CorrelationPair }) {
  const v = Number(pair.corr)
  const valid = Number.isFinite(v)
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border-subtle py-1.5 text-xs last:border-0">
      <span className="truncate text-txt2" title={`${pair.asset_1} ↔ ${pair.asset_2}`}>
        {pair.asset_1} ↔ {pair.asset_2}
      </span>
      <span
        className={`shrink-0 tabular-nums font-medium ${
          !valid ? 'text-txt2' : v >= 0 ? 'text-green' : 'text-red'
        }`}
      >
        {valid ? v.toFixed(3) : '—'}
      </span>
    </div>
  )
}

export function CorrelationHeatmap({ correlation }: { correlation: Correlation }) {
  const labels = correlation.matrix?.labels ?? []
  const values = correlation.matrix?.values ?? []
  const hasMatrix = labels.length >= 2 && values.length === labels.length

  if (!hasMatrix) {
    return (
      <div className="py-6 text-center text-sm text-txt2">
        {correlation.note ||
          'Sin datos suficientes para construir la matriz de correlaciones.'}
      </div>
    )
  }

  const topPos = correlation.top_positive ?? []
  const topNeg = correlation.top_negative ?? []

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-txt2">
        <Badge variant="accent">Activos &gt; {correlation.threshold_pct.toFixed(2)}%</Badge>
        <span>
          Histórico usado: {correlation.history_days > 0 ? `${correlation.history_days} días` : 'n/d'}
        </span>
      </div>

      <div className="overflow-x-auto">
        <div
          className="grid gap-0.5 text-[11px]"
          style={{ gridTemplateColumns: `minmax(56px,auto) repeat(${labels.length}, minmax(40px,1fr))` }}
        >
          {/* Header row */}
          <div className="sticky left-0 z-10 bg-card p-1.5 font-medium text-txt2">Activo</div>
          {labels.map((sym) => (
            <div key={`h-${sym}`} className="p-1.5 text-center font-medium text-txt2" title={sym}>
              {sym}
            </div>
          ))}

          {/* Data rows */}
          {labels.map((rowSym, i) => (
            <div key={`r-${rowSym}`} className="contents">
              <div className="sticky left-0 z-10 bg-card p-1.5 font-medium text-txt2" title={rowSym}>
                {rowSym}
              </div>
              {labels.map((_, j) => {
                const raw = values[i]?.[j]
                const v = Number(raw)
                if (raw == null || !Number.isFinite(v)) {
                  return (
                    <div
                      key={`c-${i}-${j}`}
                      className="flex items-center justify-center rounded-[3px] bg-card2 p-1.5 text-txt2"
                    >
                      —
                    </div>
                  )
                }
                return (
                  <div
                    key={`c-${i}-${j}`}
                    className="flex items-center justify-center rounded-[3px] p-1.5 tabular-nums"
                    style={{ background: cellBg(v), color: cellText(v) }}
                  >
                    {v.toFixed(2)}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 md:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-semibold text-txt">Top más correlacionados</div>
          {topPos.length ? (
            topPos.map((p, i) => <PairRow key={i} pair={p} />)
          ) : (
            <div className="py-1.5 text-xs text-txt2">—</div>
          )}
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold text-txt">Menor correlación</div>
          {topNeg.length ? (
            topNeg.map((p, i) => <PairRow key={i} pair={p} />)
          ) : (
            <div className="py-1.5 text-xs text-txt2">—</div>
          )}
        </div>
      </div>
    </div>
  )
}
