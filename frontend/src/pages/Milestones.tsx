import { cloneElement, useEffect, useId, useMemo, useState } from 'react'
import { Check, Flag } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useCash, useDashboard } from '@/api/queries'
import { fmtEur, fmtPct, parseAmount, parsePercent } from '@/lib/format'
import {
  MILESTONES,
  avgMonthlyContribution,
  computeStage,
  fmtDuration,
  impliedAnnualReturn,
  monthsToTarget,
  projectionCurve,
} from '@/lib/milestones'
import { MilestonesChart } from '@/components/charts/MilestonesChart'
import { cn } from '@/lib/utils'

function shortLabel(v: number): string {
  return v >= 1_000_000 ? `${v / 1_000_000} M` : `${v / 1000}k`
}

const STORAGE_KEY = 'gp.milestones.assumptions'

type Mode = 'hist12' | 'histAll' | 'manual'

interface Assumptions {
  mode: Mode
  monthly: string
  returnPct: string
}

const DEFAULTS: Assumptions = { mode: 'hist12', monthly: '500', returnPct: '7' }

const MODES: { key: Mode; label: string }[] = [
  { key: 'hist12', label: 'Mi ritmo (últimos 12 meses)' },
  { key: 'histAll', label: 'Mi ritmo (todo el histórico)' },
  { key: 'manual', label: 'Manual' },
]

function loadAssumptions(): Assumptions {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULTS
    const p = JSON.parse(raw) as Partial<Assumptions>
    return {
      mode: p.mode === 'hist12' || p.mode === 'histAll' || p.mode === 'manual' ? p.mode : DEFAULTS.mode,
      monthly: typeof p.monthly === 'string' ? p.monthly : DEFAULTS.monthly,
      returnPct: typeof p.returnPct === 'string' ? p.returnPct : DEFAULTS.returnPct,
    }
  } catch {
    return DEFAULTS
  }
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactElement<{ id?: string }> }) {
  const id = useId()
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-xs font-medium text-txt2">
        {label}
      </label>
      {cloneElement(children, { id })}
      {hint && <p className="text-xs text-txt3">{hint}</p>}
    </div>
  )
}

export function Milestones() {
  const { data, isLoading, isError, error } = useDashboard()
  const { data: cash } = useCash()
  const [as, setAs] = useState<Assumptions>(loadAssumptions)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(as))
    } catch {
      /* almacenamiento no disponible: se ignora */
    }
  }, [as])

  const cashTotal = cash?.total_eur ?? data?.cash_total ?? 0
  const netWorth = (data?.portfolio_total_value ?? 0) + cashTotal
  const hasData = !!data && !data.error && !!data.metrics

  // Ritmo histórico: aportación media del capital aportado + rentabilidad anualizada (TWR).
  const histMonthly = useMemo(
    () =>
      as.mode === 'manual'
        ? null
        : avgMonthlyContribution(data?.portfolio_chart?.invested, as.mode === 'hist12' ? 12 : null),
    [as.mode, data?.portfolio_chart?.invested],
  )
  const histReturn = useMemo(
    () =>
      as.mode === 'manual'
        ? null
        : impliedAnnualReturn(
            data?.portfolio_chart?.value,
            data?.portfolio_chart?.invested,
            as.mode === 'hist12' ? 12 : null,
          ),
    [as.mode, data?.portfolio_chart?.value, data?.portfolio_chart?.invested],
  )
  const useHistory = as.mode !== 'manual' && histMonthly !== null && histReturn !== null

  const monthly = useHistory ? Math.max(0, histMonthly) : parseAmount(as.monthly)
  const returnPct = useHistory ? histReturn : parsePercent(as.returnPct)
  const assumptionsOk = Number.isFinite(monthly) && monthly >= 0 && Number.isFinite(returnPct) && returnPct > -50

  const stage = useMemo(() => computeStage(netWorth), [netWorth])

  const eta = useMemo(
    () =>
      MILESTONES.map((m) =>
        assumptionsOk ? monthsToTarget(netWorth, monthly, returnPct, m.value) : null,
      ),
    [netWorth, monthly, returnPct, assumptionsOk],
  )

  const investedSeries = data?.portfolio_chart?.invested
  const lastInvested = investedSeries?.length ? investedSeries[investedSeries.length - 1].y : netWorth
  const curve = useMemo(
    () =>
      assumptionsOk && netWorth < 1_000_000
        ? projectionCurve(netWorth, lastInvested + cashTotal, monthly, returnPct, new Date())
        : [],
    [assumptionsOk, netWorth, lastInvested, cashTotal, monthly, returnPct],
  )

  return (
    <div>
      <PageHeader
        title="Hitos"
        subtitle="De 0 a 1 M€: en qué etapa estás y cuánto falta para la siguiente"
      />

      {isLoading && <Skeleton className="h-64" />}

      {!isLoading && (isError || !hasData) && (
        <Card className="p-8 text-center text-sm text-txt2">
          {isError
            ? (error as Error)?.message || 'No se pudo cargar el patrimonio.'
            : data?.error || 'Sin datos de cartera: importa tus operaciones primero.'}
        </Card>
      )}

      {!isLoading && !isError && hasData && (
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <div className="text-xs text-txt2">Patrimonio actual (inversión + efectivo)</div>
                  <div className="text-2xl font-semibold text-txt">{fmtEur(netWorth, 0)}</div>
                </div>
                <div className="text-right text-sm text-txt2">
                  {stage.reached ? (
                    <>
                      Etapa: <span className="font-medium text-txt">{stage.reached.stage}</span>
                    </>
                  ) : (
                    'Aún no has llegado al primer hito'
                  )}
                </div>
              </div>

              {stage.next ? (
                <div>
                  <div className="mb-1 flex justify-between text-xs text-txt2">
                    <span>{fmtPct(stage.pctToNext, 0)} del tramo actual</span>
                    <span>Siguiente: {stage.next.label}</span>
                  </div>
                  <span className="sr-only">
                    {`Patrimonio ${fmtEur(netWorth, 0)} de 1.000.000 €. Siguiente hito: ${stage.next.label}`}
                  </span>
                  <div aria-hidden className="flex gap-1">
                    {MILESTONES.map((m, i) => {
                      const from = i === 0 ? 0 : MILESTONES[i - 1].value
                      const fill = Math.min(100, Math.max(0, ((netWorth - from) / (m.value - from)) * 100))
                      return (
                        <div key={m.value} className="min-w-0 flex-1">
                          <div className="h-2.5 overflow-hidden rounded-full bg-card3">
                            <div className="h-full rounded-full bg-accent" style={{ width: `${fill}%` }} />
                          </div>
                          <div className="mt-1 text-center text-[10px] text-txt3">{shortLabel(m.value)}</div>
                        </div>
                      )
                    })}
                  </div>
                  <div className="mt-1 text-xs text-txt2">
                    Te faltan <span className="font-medium text-txt">{fmtEur(stage.remaining, 0)}</span>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-green">Has superado el millón.</div>
              )}

              {stage.reached && (
                <p className="rounded-[var(--radius-card)] bg-card2 p-3 text-sm text-txt2">
                  {stage.reached.focus}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Ritmo para la proyección</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {MODES.map((m) => (
                  <button
                    key={m.key}
                    type="button"
                    aria-pressed={as.mode === m.key}
                    onClick={() => setAs((a) => ({ ...a, mode: m.key }))}
                    className={cn(
                      'rounded-[var(--radius-card)] border px-3 py-1.5 text-xs font-medium transition-colors',
                      as.mode === m.key
                        ? 'border-accent bg-accent/15 text-txt'
                        : 'border-border-subtle text-txt2 hover:text-txt',
                    )}
                  >
                    {m.label}
                  </button>
                ))}
              </div>

              {as.mode !== 'manual' && !useHistory && (
                <p role="alert" className="text-xs text-amber">
                  No hay histórico suficiente para estimar tu ritmo (mín. ~1 mes de aportaciones y
                  rentabilidad). Usa el modo manual.
                </p>
              )}

              {useHistory ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-[var(--radius-card)] bg-card2 p-3">
                    <div className="text-xs text-txt2">Aportación media</div>
                    <div className="text-lg font-semibold text-txt">{fmtEur(monthly, 0)}/mes</div>
                    {(histMonthly as number) < 0 && (
                      <div className="text-xs text-amber">Retiradas netas: se proyecta con 0 €.</div>
                    )}
                  </div>
                  <div className="rounded-[var(--radius-card)] bg-card2 p-3">
                    <div className="text-xs text-txt2">Rentabilidad anualizada (del gráfico)</div>
                    <div className="text-lg font-semibold text-txt">{fmtPct(returnPct)}</div>
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="Aportación mensual (€)">
                    <Input
                      inputMode="decimal"
                      value={as.monthly}
                      onChange={(e) => setAs((a) => ({ ...a, monthly: e.target.value }))}
                    />
                  </Field>
                  <Field label="Rentabilidad anual esperada (%)">
                    <Input
                      inputMode="decimal"
                      value={as.returnPct}
                      onChange={(e) => setAs((a) => ({ ...a, returnPct: e.target.value }))}
                    />
                  </Field>
                </div>
              )}

              <p className="text-xs text-txt3">
                La rentabilidad pasada no garantiza la futura. La aportación sale de la variación del
                capital aportado en el gráfico de la cartera; la rentabilidad, de la ganancia del mismo
                periodo descontando aportaciones, anualizada.
              </p>
              {as.mode === 'manual' && !assumptionsOk && (
                <p role="alert" className="text-xs text-amber">
                  Introduce una aportación (≥ 0) y una rentabilidad válidas para ver los plazos.
                </p>
              )}
            </CardContent>
          </Card>

          {curve.length > 1 && (
            <Card>
              <CardHeader>
                <CardTitle>Camino hacia 1 M€</CardTitle>
              </CardHeader>
              <CardContent>
                <MilestonesChart
                  history={data?.portfolio_chart?.value}
                  cashOffset={cashTotal}
                  projection={curve}
                />
                <p className="mt-2 text-xs text-txt3">
                  Parte de tu patrimonio actual y suma tu aportación mensual con la rentabilidad
                  elegida. El histórico (últimos 24 meses) incluye el efectivo actual como constante.
                </p>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Escalera de hitos</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-2">
                {MILESTONES.map((m, i) => {
                  const done = netWorth >= m.value
                  const isNext = stage.next?.value === m.value
                  return (
                    <li
                      key={m.value}
                      className={cn(
                        'flex items-start gap-3 rounded-[var(--radius-card)] border p-3',
                        isNext ? 'border-accent bg-card2' : 'border-border-subtle',
                      )}
                      aria-current={isNext ? 'step' : undefined}
                    >
                      <span
                        className={cn(
                          'mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full',
                          done ? 'bg-green-dim text-green' : isNext ? 'bg-accent/20 text-accent' : 'bg-card3 text-txt3',
                        )}
                      >
                        {done ? <Check className="size-3.5" aria-label="Alcanzado" /> : <Flag className="size-3.5" aria-hidden />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                          <span className="text-sm font-semibold text-txt">
                            {m.label} · {m.stage}
                          </span>
                          <span className="text-xs text-txt2">
                            {done ? 'Alcanzado' : assumptionsOk ? `≈ ${fmtDuration(eta[i])}` : '—'}
                          </span>
                        </div>
                        <p className="mt-0.5 text-xs text-txt2">{m.focus}</p>
                      </div>
                    </li>
                  )
                })}
              </ol>
              <p className="mt-3 text-xs text-txt3">
                Proyección simple con capitalización mensual y aportación constante. Orientativa; no es
                asesoramiento financiero.
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
