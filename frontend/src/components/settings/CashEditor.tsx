import { useEffect, useState } from 'react'
import { Plus, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCash, useSaveCash } from '@/api/queries'
import { fmtEur } from '@/lib/format'

interface Row {
  currency: string
  amount: string
}

export function CashEditor() {
  const { data, isLoading, isError } = useCash()
  const save = useSaveCash()
  const [rows, setRows] = useState<Row[]>([])

  useEffect(() => {
    if (!data) return
    setRows(
      data.balances.length
        ? data.balances.map((b) => ({ currency: b.currency, amount: String(b.amount) }))
        : [{ currency: 'EUR', amount: '' }],
    )
  }, [data])

  function update(i: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }
  function addRow() {
    setRows((prev) => [...prev, { currency: '', amount: '' }])
  }
  function removeRow(i: number) {
    setRows((prev) => prev.filter((_, idx) => idx !== i))
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
      toast.success('Efectivo guardado', {
        description: 'Aparece como clase «Efectivo» en el dashboard.',
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
              onChange={(e) => update(i, { amount: e.target.value })}
            />
            <Button variant="ghost" size="icon" onClick={() => removeRow(i)} aria-label="Eliminar">
              <Trash2 />
            </Button>
          </div>
        ))}
        <Button variant="subtle" size="sm" onClick={addRow}>
          <Plus /> Añadir divisa
        </Button>
      </div>

      <div className="flex items-center justify-between rounded-[var(--radius-card)] bg-card2 px-4 py-2">
        <Label>Total en EUR</Label>
        <span className="font-semibold text-txt">{fmtEur(data?.total_eur ?? 0)}</span>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={persist} disabled={save.isPending}>
          <Save /> Guardar efectivo
        </Button>
      </div>
    </div>
  )
}
