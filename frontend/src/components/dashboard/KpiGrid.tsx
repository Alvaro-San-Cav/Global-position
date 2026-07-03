import type { ReactNode } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { Metrics } from '@/api/types'
import { fmtEur, fmtPct, signColor } from '@/lib/format'

function Kpi({
  label,
  value,
  sub,
  valueClass = 'text-txt',
}: {
  label: string
  value: string
  sub?: string
  valueClass?: string
}) {
  return (
    <Card className="p-4">
      <div className="text-xs text-txt2">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${valueClass}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-txt2 tabular-nums">{sub}</div>}
    </Card>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 mt-6 text-sm font-semibold text-txt">{children}</h2>
}

export function KpiGrid({ metrics }: { metrics: Metrics }) {
  const m = metrics
  const hasBenchmark = !!m.benchmark_ticker
  const alfa =
    m.twr_total_anual != null && m.benchmark_annual != null
      ? m.twr_total_anual - m.benchmark_annual
      : null

  return (
    <section>
      {/* ── Total summary ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Valor total" value={fmtEur(m.valor_total)} valueClass="text-accent" />
        <Kpi label="Capital aportado" value={fmtEur(m.capital_total)} />
        <Kpi
          label="Plusvalía"
          value={fmtEur(m.plusvalia_total)}
          sub={fmtPct(m.rentabilidad_total)}
          valueClass={signColor(m.plusvalia_total)}
        />
        <Kpi
          label="Rentabilidad"
          value={fmtPct(m.rentabilidad_total)}
          valueClass={signColor(m.rentabilidad_total)}
        />
        <Kpi label="CAGR" value={fmtPct(m.cagr_total)} valueClass={signColor(m.cagr_total)} />
        <Kpi
          label="TWR anual"
          value={fmtPct(m.twr_total_anual)}
          valueClass={signColor(m.twr_total_anual)}
        />
      </div>

      {/* ── Benchmark ── */}
      {hasBenchmark && (
        <>
          <SectionTitle>vs {m.benchmark_name || m.benchmark_ticker}</SectionTitle>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Kpi label="Benchmark total" value={fmtPct(m.benchmark_total)} valueClass="text-amber" />
            <Kpi label="Benchmark anual" value={fmtPct(m.benchmark_annual)} valueClass="text-amber" />
            <Kpi
              label="Alfa (TWR − BM)"
              value={fmtPct(alfa)}
              valueClass={signColor(alfa)}
            />
          </div>
        </>
      )}

      {/* ── Sleeves ── */}
      <SectionTitle>Desglose por activo</SectionTitle>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {/* Acciones */}
        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-semibold text-txt">Acciones / Renta Variable</span>
            <Badge variant="accent">{fmtPct(m.peso_acciones, 0)} cartera</Badge>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Kpi label="Capital" value={fmtEur(m.capital_aportado_acciones)} />
            <Kpi label="Valor" value={fmtEur(m.valor_actual_acciones)} valueClass="text-accent" />
            <Kpi
              label="Plusvalía"
              value={fmtEur(m.plusvalia_acciones)}
              sub={fmtPct(m.rentabilidad_acciones)}
              valueClass={signColor(m.plusvalia_acciones)}
            />
            <Kpi label="CAGR" value={fmtPct(m.cagr_acciones)} valueClass={signColor(m.cagr_acciones)} />
            <Kpi
              label="TWR total"
              value={fmtPct(m.twr_acciones_total)}
              valueClass={signColor(m.twr_acciones_total)}
            />
            <Kpi
              label="TWR anual"
              value={fmtPct(m.twr_acciones_anual)}
              valueClass={signColor(m.twr_acciones_anual)}
            />
          </div>
        </Card>

        {/* Crypto */}
        <Card className="p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-semibold text-txt">Criptomonedas</span>
            <Badge variant="amber">{fmtPct(m.peso_crypto, 0)} cartera</Badge>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Kpi label="Capital" value={fmtEur(m.capital_aportado_crypto)} />
            <Kpi label="Valor" value={fmtEur(m.valor_actual_crypto)} valueClass="text-amber" />
            <Kpi
              label="Plusvalía"
              value={fmtEur(m.plusvalia_crypto)}
              sub={fmtPct(m.rentabilidad_crypto)}
              valueClass={signColor(m.plusvalia_crypto)}
            />
            <Kpi label="CAGR" value={fmtPct(m.cagr_crypto)} valueClass={signColor(m.cagr_crypto)} />
            <Kpi
              label="TWR total"
              value={fmtPct(m.twr_cripto_total)}
              valueClass={signColor(m.twr_cripto_total)}
            />
            <Kpi
              label="TWR anual"
              value={fmtPct(m.twr_cripto_anual)}
              valueClass={signColor(m.twr_cripto_anual)}
            />
          </div>
        </Card>
      </div>
    </section>
  )
}
