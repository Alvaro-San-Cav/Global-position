import { useEffect, useMemo, useRef, useState } from 'react'
import { Plus, Trash2, Target, AlertTriangle, Save } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useAssetClasses,
  useRebalance,
  useSaveTarget,
  useTarget,
} from '@/api/queries'
import type { TargetConfig } from '@/api/types'
import { fmtEur, fmtPct, parsePercent } from '@/lib/format'
import { cn } from '@/lib/utils'

interface ClassRow {
  name: string
  pct: string
  min: string
  max: string
}

function num(s: string): number | null {
  const t = s.trim()
  if (t === '') return null
  const v = parsePercent(t)
  return Number.isNaN(v) ? null : v
}

export function Objetivo() {
  const { data: target } = useTarget()
  const { data: assetClasses } = useAssetClasses()
  const save = useSaveTarget()
  const rebalance = useRebalance()

  const [rows, setRows] = useState<ClassRow[]>([])
  const [band, setBand] = useState('')
  const [maxAsset, setMaxAsset] = useState('')
  const [cashPct, setCashPct] = useState('')
  const [cashAmount, setCashAmount] = useState('')

  // Seed once from server state; never overwrite what the user is typing.
  // Re-seed only when the server copy changed after our own save (updatedAt).
  const seeded = useRef(false)
  const reseedAfterSave = useRef(false)
  useEffect(() => {
    if (!target) return
    if (seeded.current && !reseedAfterSave.current) return
    const hasStored =
      Object.keys(target.targets ?? {}).length + Object.keys(target.class_limits ?? {}).length > 0
    if (!hasStored && !assetClasses) return // wait for known classes to seed empty form
    seeded.current = true
    reseedAfterSave.current = false
    const names = new Set<string>([
      ...Object.keys(target.targets ?? {}),
      ...Object.keys(target.class_limits ?? {}),
    ])
    if (names.size === 0 && assetClasses) {
      assetClasses.known_classes.forEach((c) => names.add(c))
    }
    setRows(
      [...names].map((name) => ({
        name,
        pct: target.targets?.[name] != null ? String(target.targets[name]) : '',
        min: target.class_limits?.[name]?.min != null ? String(target.class_limits[name]!.min) : '',
        max: target.class_limits?.[name]?.max != null ? String(target.class_limits[name]!.max) : '',
      })),
    )
    setBand(target.band_pct ? String(target.band_pct) : '')
    setMaxAsset(target.max_asset_pct != null ? String(target.max_asset_pct) : '')
    setCashPct(target.cash_buffer?.pct ? String(target.cash_buffer.pct) : '')
    setCashAmount(target.cash_buffer?.amount ? String(target.cash_buffer.amount) : '')
  }, [target, assetClasses])

  const sumPct = useMemo(
    () => rows.reduce((acc, r) => acc + (num(r.pct) ?? 0), 0),
    [rows],
  )

  // Every class the backend knows about, plus any legacy name already stored in
  // the config so an existing row never loses its own value from the dropdown.
  const classOptions = useMemo(() => {
    const known = assetClasses?.known_classes ?? []
    return [...new Set([...known, ...rows.map((r) => r.name).filter(Boolean)])]
  }, [assetClasses?.known_classes, rows])

  function updateRow(i: number, patch: Partial<ClassRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  async function persist() {
    const targets: Record<string, number> = {}
    const class_limits: TargetConfig['class_limits'] = {}
    for (const r of rows) {
      const name = r.name.trim()
      if (!name) continue
      const pct = num(r.pct)
      if (pct != null) targets[name] = pct
      const min = num(r.min)
      const max = num(r.max)
      if (min != null || max != null) class_limits[name] = { min, max }
    }
    const body: TargetConfig = {
      targets,
      band_pct: num(band) ?? 0,
      max_asset_pct: num(maxAsset),
      class_limits,
      cash_buffer: { pct: num(cashPct) ?? 0, amount: num(cashAmount) ?? 0 },
    }
    try {
      await save.mutateAsync(body)
      reseedAfterSave.current = true
      toast.success('Cartera objetivo guardada')
    } catch (e) {
      toast.error('No se pudo guardar', {
        description: e instanceof Error ? e.message : String(e),
      })
    }
  }

  // Targets don't have to add up to 100 — untargeted classes absorb the rest.
  // Only overshooting 100 is impossible.
  const sumOk = sumPct <= 100.01
  const untargeted = 100 - sumPct

  return (
    <div>
      <PageHeader
        title="Cartera objetivo"
        subtitle="Define tu cartera tipo y reglas de diversificación; el panel muestra qué hacer para cumplir vs lo que tienes (cartera + efectivo)."
        actions={
          <Button onClick={persist} disabled={save.isPending}>
            <Save /> Guardar
          </Button>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        {/* ── Editor ── */}
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="size-4 text-accent2" /> Objetivo por clase de activo
              </CardTitle>
            </CardHeader>
            <CardContent>
              {/* Header padding mirrors the controls' px-3 and the w-9 delete
                  button so every label sits over its own column. */}
              <div className="mb-2 grid grid-cols-[1.4fr_0.8fr_0.8fr_0.8fr_auto] items-center gap-2 text-[11px] font-medium uppercase text-txt3">
                <span className="pl-3">Clase</span>
                <span className="pr-3 text-right">Objetivo %</span>
                <span className="pr-3 text-right">Mín %</span>
                <span className="pr-3 text-right">Máx %</span>
                <span className="w-9" />
              </div>
              <div className="space-y-2">
                {rows.map((r, i) => (
                  <div
                    key={i}
                    className="grid grid-cols-[1.4fr_0.8fr_0.8fr_0.8fr_auto] items-center gap-2"
                  >
                    <Select
                      value={r.name || undefined}
                      onValueChange={(v) => updateRow(i, { name: v })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Elegir clase…" />
                      </SelectTrigger>
                      <SelectContent>
                        {classOptions
                          // Hide classes already taken by another row.
                          .filter(
                            (c) =>
                              c === r.name ||
                              !rows.some((o, oi) => oi !== i && o.name === c),
                          )
                          .map((c) => (
                            <SelectItem key={c} value={c}>
                              {c}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                    <Input
                      className="text-right"
                      inputMode="decimal"
                      value={r.pct}
                      placeholder="0"
                      onChange={(e) => updateRow(i, { pct: e.target.value })}
                    />
                    <Input
                      className="text-right"
                      inputMode="decimal"
                      value={r.min}
                      placeholder="—"
                      onChange={(e) => updateRow(i, { min: e.target.value })}
                    />
                    <Input
                      className="text-right"
                      inputMode="decimal"
                      value={r.max}
                      placeholder="—"
                      onChange={(e) => updateRow(i, { max: e.target.value })}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))}
                      aria-label="Eliminar clase"
                    >
                      <Trash2 />
                    </Button>
                  </div>
                ))}
              </div>

              <div className="mt-3 flex items-center justify-between">
                <Button
                  variant="subtle"
                  size="sm"
                  disabled={
                    rows.some((r) => !r.name) ||
                    classOptions.every((c) => rows.some((r) => r.name === c))
                  }
                  onClick={() => setRows((prev) => [...prev, { name: '', pct: '', min: '', max: '' }])}
                >
                  <Plus /> Añadir clase
                </Button>
                <span
                  className={cn(
                    'text-sm font-medium tabular-nums',
                    sumOk ? 'text-green' : 'text-amber',
                  )}
                >
                  Suma: {fmtPct(sumPct, 1)}
                </span>
              </div>
              {sumPct > 0 && untargeted > 0.01 && (
                <p className="mt-2 text-[11px] text-txt3">
                  El resto ({fmtPct(untargeted, 1)}) queda sin objetivo.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Reglas de diversificación</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Field
                label="Banda de tolerancia ±%"
                hint="Margen antes de marcar que hay que rebalancear."
                value={band}
                onChange={setBand}
                placeholder="5"
              />
              <Field
                label="Peso máx. por activo %"
                hint="Ningún activo individual supera este % del patrimonio."
                value={maxAsset}
                onChange={setMaxAsset}
                placeholder="10"
              />
              <div className="grid grid-cols-2 gap-3">
                <Field
                  label="Colchón efectivo %"
                  value={cashPct}
                  onChange={setCashPct}
                  placeholder="5"
                />
                <Field
                  label="Colchón efectivo €"
                  value={cashAmount}
                  onChange={setCashAmount}
                  placeholder="0"
                />
              </div>
              <p className="text-[11px] text-txt3">
                Se exige el mayor de los dos (porcentaje o importe fijo).
              </p>
            </CardContent>
          </Card>
        </div>

        {/* ── Panel de control ── */}
        <ControlPanel rebalance={rebalance} />
      </div>
    </div>
  )
}

function Field({
  label,
  hint,
  value,
  onChange,
  placeholder,
}: {
  label: string
  hint?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-sm text-txt">{label}</span>
      </div>
      <Input
        inputMode="decimal"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <p className="mt-1 text-[11px] text-txt3">{hint}</p>}
    </div>
  )
}

function statusBadge(status: string) {
  if (status === 'comprar') return <Badge variant="green">Comprar</Badge>
  if (status === 'vender') return <Badge variant="red">Vender</Badge>
  if (status === 'sin_objetivo') return <Badge variant="default">Sin objetivo</Badge>
  return <Badge variant="default">OK</Badge>
}

function ControlPanel({
  rebalance,
}: {
  rebalance: ReturnType<typeof useRebalance>
}) {
  const data = rebalance.data

  return (
    <Card className="self-start">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Panel de control</span>
          {data && (
            <span className="text-xs font-normal text-txt2">
              Patrimonio {fmtEur(data.net_worth)}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {rebalance.isLoading && <p className="text-sm text-txt2">Calculando…</p>}
        {rebalance.isError && (
          <p className="text-sm text-red">
            No se pudo calcular. ¿Hay operaciones cargadas?
          </p>
        )}
        {data && !data.configured && (
          <p className="text-sm text-txt2">
            Define los objetivos por clase y pulsa «Guardar» para ver el plan.
          </p>
        )}

        {data && data.configured && (
          <>
            {data.note && (
              <p className="mb-3 rounded-[var(--radius-card)] bg-amber-dim px-3 py-2 text-xs text-amber">
                {data.note}
              </p>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle text-[11px] uppercase text-txt3">
                    <th className="py-2 text-left font-medium">Clase</th>
                    <th className="py-2 text-right font-medium">Obj.</th>
                    <th className="py-2 text-right font-medium">Actual</th>
                    <th className="py-2 text-right font-medium">Desv.</th>
                    <th className="py-2 text-right font-medium">Acción €</th>
                    <th className="py-2 text-right font-medium">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => (
                    <tr key={r.asset_class} className="border-b border-border-subtle/50">
                      <td className="py-2 text-txt">{r.asset_class}</td>
                      <td className="py-2 text-right tabular-nums text-txt2">
                        {r.has_target ? fmtPct(r.target_pct ?? 0, 1) : '—'}
                      </td>
                      <td className="py-2 text-right tabular-nums text-txt2">
                        {fmtPct(r.actual_pct, 1)}
                      </td>
                      <td
                        className={cn(
                          'py-2 text-right tabular-nums',
                          r.within_band
                            ? 'text-txt3'
                            : (r.drift_pct ?? 0) > 0
                              ? 'text-red'
                              : 'text-amber',
                        )}
                      >
                        {r.has_target
                          ? `${(r.drift_pct ?? 0) > 0 ? '+' : ''}${fmtPct(r.drift_pct ?? 0, 1)}`
                          : '—'}
                      </td>
                      <td
                        className={cn(
                          'py-2 text-right tabular-nums font-medium',
                          !r.has_target || r.status === 'ok'
                            ? 'text-txt3'
                            : (r.action_eur ?? 0) > 0
                              ? 'text-green'
                              : 'text-red',
                        )}
                      >
                        {!r.has_target || r.status === 'ok'
                          ? '—'
                          : `${(r.action_eur ?? 0) > 0 ? '+' : ''}${fmtEur(r.action_eur ?? 0)}`}
                      </td>
                      <td className="py-2 text-right">{statusBadge(r.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Violations */}
            <div className="mt-4">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-txt">
                <AlertTriangle className="size-4 text-amber" /> Reglas
                {data.violations.length === 0 && (
                  <Badge variant="green" className="ml-1">
                    Todo en regla
                  </Badge>
                )}
              </h3>
              {data.violations.length > 0 ? (
                <ul className="space-y-1.5">
                  {data.violations.map((v, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 rounded-[var(--radius-card)] bg-red-dim/60 px-3 py-2 text-xs text-txt"
                    >
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-red" />
                      <span>{v.message}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-txt3">
                  Ninguna regla de diversificación incumplida.
                </p>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
