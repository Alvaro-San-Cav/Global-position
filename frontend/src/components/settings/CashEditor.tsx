import { useEffect, useState } from 'react'
import { Plus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCash, useSaveCash } from '@/api/queries'
import { fmtEur } from '@/lib/format'
import {
  fmtAmountInput,
  removesCurrency,
  validateCashRows,
  type CashRow,
  type CashRowError,
} from './cashRows'

export function CashEditor() {
  const { data, isLoading, isError } = useCash()
  const save = useSaveCash()
  const [rows, setRows] = useState<CashRow[]>([])
  const [errors, setErrors] = useState<Record<number, CashRowError>>({})

  const existing = new Set((data?.balances ?? []).map((b) => b.currency.toUpperCase()))

  useEffect(() => {
    if (!data) return
    setErrors({})
    setRows(
      data.balances.length
        ? data.balances.map((b) => ({ currency: b.currency, amount: fmtAmountInput(b.amount) }))
        : [{ currency: 'EUR', amount: '' }],
    )
  }, [data])

  function update(i: number, patch: Partial<CashRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
    setErrors((prev) => {
      if (!prev[i]) return prev
      const next = { ...prev }
      delete next[i]
      return next
    })
  }
  function addRow() {
    setRows((prev) => [...prev, { currency: '', amount: '' }])
  }
  function removeRow(i: number) {
    setRows((prev) => prev.filter((_, idx) => idx !== i))
    setErrors({})
  }

  async function persist() {
    const { balances, errors: errs, removed } = validateCashRows(rows, existing)
    if (Object.keys(errs).length > 0) {
      setErrors(errs)
      toast.error('Revisa los importes marcados', {
        description: 'Hay filas con divisa o importe no válidos; no se ha guardado nada.',
      })
      return
    }
    setErrors({})
    try {
      await save.mutateAsync(balances)
      toast.success('Efectivo guardado', {
        description: removed.length
          ? `Eliminada(s) por importe 0: ${removed.join(', ')}`
          : 'Aparece como clase «Efectivo» en el dashboard.',
      })
    } catch (e) {
      toast.error('No se pudo guardar', {
        description: e instanceof Error ? e.message : String(e),
      })
    }
  }

  if (isLoading) return <p className="text-sm text-txt2">Cargando…</p>
  if (isError) return <p className="text-sm text-red">No se pudo cargar el efectivo.</p>

  return (
    <div className="max-w-xl space-y-4">
      <p className="text-sm text-txt2">
        Saldo de efectivo en la cuenta, por divisa. Se convierte a EUR y se
        muestra como la clase «Efectivo» en el dashboard. No afecta a la
        plusvalía ni al TWR (el efectivo no tiene rendimiento de mercado).
      </p>

      <div className="space-y-2">
        <div className="grid grid-cols-[1fr_1.4fr_auto] gap-2 text-xs font-medium text-txt2">
          <span>Divisa</span>
          <span>Importe</span>
          <span />
        </div>
        {rows.map((r, i) => (
          <div key={i}>
            <div className="grid grid-cols-[1fr_1.4fr_auto] items-center gap-2">
              <Input
                value={r.currency}
                placeholder="EUR"
                aria-label={`Divisa ${i + 1}`}
                aria-invalid={errors[i]?.currency ? true : undefined}
                className={errors[i]?.currency ? 'border-red' : undefined}
                onChange={(e) => update(i, { currency: e.target.value.toUpperCase() })}
              />
              <Input
                type="text"
                inputMode="decimal"
                value={r.amount}
                placeholder="0,00"
                aria-label={`Importe ${i + 1}`}
                aria-invalid={errors[i]?.amount ? true : undefined}
                className={errors[i]?.amount ? 'border-red' : undefined}
                onChange={(e) => update(i, { amount: e.target.value })}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => removeRow(i)}
                aria-label="Eliminar"
              >
                <Trash2 />
              </Button>
            </div>
            {(errors[i]?.currency || errors[i]?.amount) && (
              <p role="alert" className="mt-1 text-xs text-red">
                {errors[i]?.currency ?? errors[i]?.amount}
              </p>
            )}
            {!errors[i] && removesCurrency(r, existing) && (
              <p className="mt-1 text-xs text-amber">
                Importe 0: esta divisa se eliminará al guardar.
              </p>
            )}
          </div>
        ))}
        <Button type="button" variant="subtle" size="sm" onClick={addRow}>
          <Plus /> Añadir divisa
        </Button>
      </div>

      <div className="flex items-center justify-between rounded-[var(--radius-card)] bg-card2 px-4 py-2">
        <Label>Total en EUR</Label>
        <span className="font-semibold text-txt">{fmtEur(data?.total_eur ?? 0)}</span>
      </div>

      <div className="flex items-center gap-3">
        <Button type="button" onClick={persist} disabled={save.isPending}>
          <Save /> Guardar efectivo
        </Button>
      </div>
    </div>
  )
}
