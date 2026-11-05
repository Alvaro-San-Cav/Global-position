import { useId, useRef, useState, type ReactNode } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { Metrics } from '@/api/types'
import type { DerivedTileValue } from '@/lib/derivedTiles'
import { fmtEur, fmtPct, signColor } from '@/lib/format'

export function InfoDot({ text }: { text: string }) {
  const id = useId()
  const tipRef = useRef<HTMLSpanElement>(null)
  const [shift, setShift] = useState(0)

  // Keep the tooltip inside the viewport (first/last grid columns).
  function clamp() {
    const el = tipRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const margin = 8
    setShift((cur) => {
      if (r.width === 0) return cur
      if (r.left < margin) return cur + (margin - r.left)
      if (r.right > window.innerWidth - margin) return cur - (r.right - (window.innerWidth - margin))
      return cur
    })
  }

  return (
    <span className="group relative inline-flex" onMouseEnter={clamp} onFocus={clamp}>
      <button
        type="button"
        aria-label="Más información"
        aria-describedby={id}
        className="flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-border-strong text-[9px] font-bold leading-none text-txt2 transition-colors hover:border-accent hover:text-accent focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      >
        <span aria-hidden="true">?</span>
      </button>
      <span
        ref={tipRef}
        id={id}
        role="tooltip"
        style={{ transform: `translateX(calc(-50% + ${shift}px))` }}
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 w-56 max-w-[calc(100vw-1rem)] rounded-md border border-border-strong bg-card3 p-2.5 text-xs font-normal leading-snug text-txt opacity-0 shadow-[var(--shadow-sm)] transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  )
}

function Kpi({
  label,
  value,
  sub,
  valueClass = 'text-txt',
  info,
}: {
  label: string
  value: string
  sub?: string
  valueClass?: string
  info?: string
}) {
  return (
    <Card className="overflow-visible p-4">
      <div className="flex items-center gap-1 text-xs text-txt2">
        <span>{label}</span>
        {info && <InfoDot text={info} />}
      </div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${valueClass}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-txt2 tabular-nums">{sub}</div>}
    </Card>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 mt-6 text-sm font-semibold text-txt">{children}</h2>
}

/** Explicaciones de fórmulas para los tooltips (?). */
const F = {
  valorTotal: 'Valor de mercado actual de todas las posiciones. Σ cantidad × precio actual × cambio a EUR.',
  capital: 'Dinero neto invertido: Σ (compras − ventas), cada una al tipo de cambio de su fecha.',
  plusvalia: 'Valor total − Capital aportado. Ganancia o pérdida acumulada (realizada + latente).',
  rentabilidad: 'Retorno simple: Plusvalía ÷ Capital aportado × 100. No tiene en cuenta cuándo aportaste.',
  cagr: 'Tasa compuesta anual: (Valor ÷ Capital)^(1÷años) − 1. Ignora el momento de las aportaciones.',
  twrAnual: 'Time-Weighted Return anualizado. Encadena los retornos diarios neutralizando entradas y salidas de capital: mide el rendimiento puro de la cartera.',
  twrTotal: 'Time-Weighted Return del periodo completo. Producto de (1 + retorno diario) − 1, aislando el efecto de aportaciones/retiradas.',
  bmTotal: 'Retorno total del índice de referencia en el mismo periodo (comprar y mantener).',
  bmAnual: 'Retorno anualizado del índice de referencia.',
  alfa: 'TWR anual − Benchmark anual. Exceso de rentabilidad frente al índice. Positivo = bates al mercado.',
  sleeveCapital: 'Capital neto invertido en este segmento (compras − ventas en EUR).',
  sleeveValor: 'Valor de mercado actual de las posiciones de este segmento.',
}

export function KpiGrid({
  metrics,
  derivedTiles = [],
}: {
  metrics: Metrics
  /** Tiles derivadas configurables (ver lib/derivedTiles). */
  derivedTiles?: DerivedTileValue[]
}) {
  const m = metrics
  const accionesDerived = derivedTiles.filter((t) => t.base === 'acciones')
  const cryptoDerived = derivedTiles.filter((t) => t.base === 'crypto')
  const hasBenchmark = !!m.benchmark_ticker
  const alfa =
    m.twr_total_anual != null && m.benchmark_annual != null
      ? m.twr_total_anual - m.benchmark_annual
      : null

  return (
    <section>
      {/* ── Total summary ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Valor total" value={fmtEur(m.valor_total)} valueClass="text-accent" info={F.valorTotal} />
        <Kpi label="Capital aportado" value={fmtEur(m.capital_total)} info={F.capital} />
        <Kpi
          label="Plusvalía"
          value={fmtEur(m.plusvalia_total)}
          sub={fmtPct(m.rentabilidad_total)}
          valueClass={signColor(m.plusvalia_total)}
          info={F.plusvalia}
        />
        <Kpi
          label="Rentabilidad"
          value={fmtPct(m.rentabilidad_total)}
          valueClass={signColor(m.rentabilidad_total)}
          info={F.rentabilidad}
        />
        <Kpi label="CAGR" value={fmtPct(m.cagr_total)} valueClass={signColor(m.cagr_total)} info={F.cagr} />
        <Kpi
          label="TWR anual"
          value={fmtPct(m.twr_total_anual)}
          valueClass={signColor(m.twr_total_anual)}
          info={F.twrAnual}
        />
      </div>

      {/* ── Benchmark ── */}
      {hasBenchmark && (
        <>
          <SectionTitle>vs {m.benchmark_name || m.benchmark_ticker}</SectionTitle>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Kpi label="Benchmark total" value={fmtPct(m.benchmark_total)} valueClass="text-amber" info={F.bmTotal} />
            <Kpi label="Benchmark anual" value={fmtPct(m.benchmark_annual)} valueClass="text-amber" info={F.bmAnual} />
            <Kpi
              label="Alfa (TWR − BM)"
              value={fmtPct(alfa)}
              valueClass={signColor(alfa)}
              info={F.alfa}
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
            <Kpi label="Capital" value={fmtEur(m.capital_aportado_acciones)} info={F.sleeveCapital} />
            <Kpi label="Valor" value={fmtEur(m.valor_actual_acciones)} valueClass="text-accent" info={F.sleeveValor} />
            {accionesDerived.map((t) => (
              <Kpi key={t.label} label={t.label} value={fmtEur(t.value)} valueClass={t.valueClass} info={t.info} />
            ))}
            <Kpi
              label="Plusvalía"
              value={fmtEur(m.plusvalia_acciones)}
              sub={fmtPct(m.rentabilidad_acciones)}
              valueClass={signColor(m.plusvalia_acciones)}
              info={F.plusvalia}
            />
            <Kpi label="CAGR" value={fmtPct(m.cagr_acciones)} valueClass={signColor(m.cagr_acciones)} info={F.cagr} />
            <Kpi
              label="TWR total"
              value={fmtPct(m.twr_acciones_total)}
              valueClass={signColor(m.twr_acciones_total)}
              info={F.twrTotal}
            />
            <Kpi
              label="TWR anual"
              value={fmtPct(m.twr_acciones_anual)}
              valueClass={signColor(m.twr_acciones_anual)}
              info={F.twrAnual}
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
            <Kpi label="Capital" value={fmtEur(m.capital_aportado_crypto)} info={F.sleeveCapital} />
            <Kpi label="Valor" value={fmtEur(m.valor_actual_crypto)} valueClass="text-amber" info={F.sleeveValor} />
            {cryptoDerived.map((t) => (
              <Kpi key={t.label} label={t.label} value={fmtEur(t.value)} valueClass={t.valueClass} info={t.info} />
            ))}
            <Kpi
              label="Plusvalía"
              value={fmtEur(m.plusvalia_crypto)}
              sub={fmtPct(m.rentabilidad_crypto)}
              valueClass={signColor(m.plusvalia_crypto)}
              info={F.plusvalia}
            />
            <Kpi label="CAGR" value={fmtPct(m.cagr_crypto)} valueClass={signColor(m.cagr_crypto)} info={F.cagr} />
            <Kpi
              label="TWR total"
              value={fmtPct(m.twr_cripto_total)}
              valueClass={signColor(m.twr_cripto_total)}
              info={F.twrTotal}
            />
            <Kpi
              label="TWR anual"
              value={fmtPct(m.twr_cripto_anual)}
              valueClass={signColor(m.twr_cripto_anual)}
              info={F.twrAnual}
            />
          </div>
        </Card>
      </div>
    </section>
  )
}
