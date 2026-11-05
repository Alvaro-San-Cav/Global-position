import { useEffect, useState } from 'react'
import { Plus, Trash2, Wallet } from 'lucide-react'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useCash, useSaveCash } from '@/api/queries'
import { fmtEur } from '@/lib/format'
import {
  fmtAmountInput,
  removesCurrency,
  validateCashRows,
  type CashRow,
  type CashRowError,
} from '@/components/settings/cashRows'

/** Quick cash editor, opened from the dashboard. `trigger` is the button. */
export function CashDialog({ trigger }: { trigger: React.ReactNode }) {
  const { data } = useCash()
  const save = useSaveCash()
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<CashRow[]>([])
  const [errors, setErrors] = useState<Record<number, CashRowError>>({})

  const existing = new Set((data?.balances ?? []).map((b) => b.currency.toUpperCase()))

  // Reset the form from server state each time the dialog opens.
  useEffect(() => {
    if (!open) return
    setErrors({})
    setRows(
      data && data.balances.length
        ? data.balances.map((b) => ({ currency: b.currency, amount: fmtAmountInput(b.amount) }))
        : [{ currency: 'EUR', amount: '' }],
    )
  }, [open, data])

  function update(i: number, patch: Partial<CashRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
    setErrors((prev) => {
      if (!prev[i]) return prev
      const next = { ...prev }
      delete next[i]
      return next
    })
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
      toast.success('Efectivo actualizado', {
        description: removed.length
          ? `Eliminada(s) por importe 0: ${removed.join(', ')}`
          : undefined,
      })
      setOpen(false)
    } catch (e) {
      toast.error('No se pudo guardar', {
        description: e instanceof Error ? e.message : String(e),
      })
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wallet className="size-4 text-accent2" /> Efectivo en cuenta
          </DialogTitle>
          <DialogDescription>
            Saldo por divisa. Se convierte a EUR y suma al patrimonio total. No
            afecta a la plusvalía ni al TWR.
          </DialogDescription>
        </DialogHeader>

        <form
          id="cash-form"
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault()
            void persist()
          }}
        >
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
                  // oxlint-disable-next-line jsx-a11y/no-autofocus
                  autoFocus={i === 0}
                  onChange={(e) => update(i, { amount: e.target.value })}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))}
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
          <Button
            type="button"
            variant="subtle"
            size="sm"
            onClick={() => setRows((prev) => [...prev, { currency: '', amount: '' }])}
          >
            <Plus /> Añadir divisa
          </Button>
        </form>

        {data && (
          <div className="mt-2 flex items-center justify-between border-t border-border-subtle pt-3 text-sm">
            <span className="text-txt2">Total actual</span>
            <span className="font-semibold text-txt">{fmtEur(data.total_eur)}</span>
          </div>
        )}

        {data?.warning && (
          <p role="alert" className="text-xs text-amber-500">
            {data.warning}
          </p>
        )}

        <DialogFooter>
          <Button type="submit" form="cash-form" disabled={save.isPending}>
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
