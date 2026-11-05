import { cloneElement, useEffect, useId, useMemo, useState } from 'react'
import { Check, Flag } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useCash, useDashboard } from '@/api/queries'
import { fmtEur, fmtPct, parseAmount, parsePercent } from '@/lib/format'
import { MILESTONES, computeStage, fmtDuration, monthsToTarget } from '@/lib/milestones'
import { cn } from '@/lib/utils'

const STORAGE_KEY = 'gp.milestones.assumptions'

interface Assumptions {
  monthly: string
  returnPct: string
}

const DEFAULTS: Assumptions = { monthly: '500', returnPct: '7' }

function loadAssumptions(): Assumptions {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULTS
    const p = JSON.parse(raw) as Partial<Assumptions>
    return {
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

  const monthly = parseAmount(as.monthly)
  const returnPct = parsePercent(as.returnPct)
  const assumptionsOk = Number.isFinite(monthly) && monthly >= 0 && Number.isFinite(returnPct) && returnPct > -50

  const stage = useMemo(() => computeStage(netWorth), [netWorth])

  const eta = useMemo(
    () =>
      MILESTONES.map((m) =>
        assumptionsOk ? monthsToTarget(netWorth, monthly, returnPct, m.value) : null,
      ),
    [netWorth, monthly, returnPct, assumptionsOk],
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
                    <span>{stage.reached ? stage.reached.label : '0 €'}</span>
                    <span>
                      {fmtPct(stage.pctToNext, 1)} hacia {stage.next.label}
                    </span>
                  </div>
                  <progress
                    className="h-2.5 w-full appearance-none overflow-hidden rounded-full [&::-moz-progress-bar]:bg-accent [&::-webkit-progress-bar]:bg-card3 [&::-webkit-progress-value]:bg-accent"
                    aria-label={`Progreso hacia ${stage.next.label}`}
                    max={100}
                    value={Math.min(100, Math.max(0, stage.pctToNext))}
                  />
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
              <CardTitle>Supuestos de la proyección</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Aportación mensual (€)">
                  <Input
                    inputMode="decimal"
                    value={as.monthly}
                    onChange={(e) => setAs((a) => ({ ...a, monthly: e.target.value }))}
                  />
                </Field>
                <Field label="Rentabilidad anual esperada (%)" hint="Supuesto, no garantizado. Antes de impuestos e inflación.">
                  <Input
                    inputMode="decimal"
                    value={as.returnPct}
                    onChange={(e) => setAs((a) => ({ ...a, returnPct: e.target.value }))}
                  />
                </Field>
              </div>
              {!assumptionsOk && (
                <p role="alert" className="mt-2 text-xs text-amber">
                  Introduce una aportación (≥ 0) y una rentabilidad válidas para ver los plazos.
                </p>
              )}
            </CardContent>
          </Card>

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
