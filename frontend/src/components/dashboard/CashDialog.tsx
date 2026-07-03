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

interface Row {
  currency: string
  amount: string
}

/** Quick cash editor, opened from the dashboard. `trigger` is the button. */
export function CashDialog({ trigger }: { trigger: React.ReactNode }) {
  const { data } = useCash()
  const save = useSaveCash()
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<Row[]>([])

  // Reset the form from server state each time the dialog opens.
  useEffect(() => {
    if (!open) return
    setRows(
      data && data.balances.length
        ? data.balances.map((b) => ({ currency: b.currency, amount: String(b.amount) }))
        : [{ currency: 'EUR', amount: '' }],
    )
  }, [open, data])

  function update(i: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  async function persist() {
    const balances: Record<string, number> = {}
    for (const r of rows) {
      const cur = r.currency.trim().toUpperCase()
      const amt = parseFloat(r.amount)
      if (cur && !Number.isNaN(amt) && amt !== 0) balances[cur] = amt
    }
    try {
      await save.mutateAsync(balances)
      toast.success('Efectivo actualizado')
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

        <div className="space-y-2">
          {rows.map((r, i) => (
            <div key={i} className="grid grid-cols-[1fr_1.4fr_auto] items-center gap-2">
              <Input
                value={r.currency}
                placeholder="EUR"
                onChange={(e) => update(i, { currency: e.target.value.toUpperCase() })}
              />
              <Input
                type="number"
                step="0.01"
                value={r.amount}
                placeholder="0.00"
                autoFocus={i === 0}
                onChange={(e) => update(i, { amount: e.target.value })}
              />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))}
                aria-label="Eliminar"
              >
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button
            variant="subtle"
            size="sm"
            onClick={() => setRows((prev) => [...prev, { currency: '', amount: '' }])}
          >
            <Plus /> Añadir divisa
          </Button>
        </div>

        {data && (
          <div className="mt-2 flex items-center justify-between border-t border-border-subtle pt-3 text-sm">
            <span className="text-txt2">Total actual</span>
            <span className="font-semibold text-txt">{fmtEur(data.total_eur)}</span>
          </div>
        )}

        <DialogFooter>
          <Button onClick={persist} disabled={save.isPending}>
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
