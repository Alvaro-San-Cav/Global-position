import { useState, type ReactNode } from 'react'
import { Plus } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAddOperation } from '@/api/queries'
import type { OperationCreate } from '@/api/types'

const today = () => new Date().toISOString().slice(0, 10)

interface FormState {
  Date: string
  Product: string
  ticker: string
  ISIN: string
  Quantity: string
  Price: string
  Coin: string
  Value: string
}

const empty = (): FormState => ({
  Date: today(),
  Product: '',
  ticker: '',
  ISIN: '',
  Quantity: '',
  Price: '',
  Coin: 'EUR',
  Value: '',
})

export function OperationDialog() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(empty)
  const add = useAddOperation()

  function set<K extends keyof FormState>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function validate(): string | null {
    if (!form.Date) return 'La fecha es obligatoria.'
    if (!form.Product.trim()) return 'El producto es obligatorio.'
    if (!form.ISIN.trim()) return 'El ISIN es obligatorio.'
    const qty = Number(form.Quantity)
    if (!form.Quantity.trim() || Number.isNaN(qty) || qty === 0)
      return 'La cantidad debe ser un número distinto de 0.'
    const price = Number(form.Price)
    if (!form.Price.trim() || Number.isNaN(price))
      return 'El precio debe ser numérico.'
    if (form.Value.trim() && Number.isNaN(Number(form.Value)))
      return 'El valor debe ser numérico.'
    return null
  }

  async function submit() {
    const err = validate()
    if (err) {
      toast.error(err)
      return
    }
    const body: OperationCreate = {
      Date: form.Date,
      Product: form.Product.trim(),
      ISIN: form.ISIN.trim(),
      Quantity: Number(form.Quantity),
      Price: Number(form.Price),
      Coin: form.Coin.trim() || 'EUR',
      ...(form.ticker.trim() ? { ticker: form.ticker.trim() } : {}),
      ...(form.Value.trim() ? { Value: Number(form.Value) } : {}),
    }
    try {
      await add.mutateAsync(body)
      toast.success('Operación guardada.')
      setForm(empty())
      setOpen(false)
    } catch (e) {
      toast.error(`Error al guardar: ${(e as Error).message}`)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus />
          Añadir operación
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva operación manual</DialogTitle>
          <DialogDescription>
            Registra una compra o venta. Usa cantidad negativa para ventas.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
          className="grid grid-cols-2 gap-3"
        >
          <Field label="Fecha *">
            <Input
              type="date"
              value={form.Date}
              onChange={(e) => set('Date', e.target.value)}
            />
          </Field>
          <Field label="Moneda">
            <Input
              value={form.Coin}
              onChange={(e) => set('Coin', e.target.value)}
              placeholder="EUR"
            />
          </Field>
          <Field label="Producto *" className="col-span-2">
            <Input
              value={form.Product}
              onChange={(e) => set('Product', e.target.value)}
              placeholder="Nombre del producto"
            />
          </Field>
          <Field label="ISIN *">
            <Input
              value={form.ISIN}
              onChange={(e) => set('ISIN', e.target.value)}
              placeholder="ISIN"
            />
          </Field>
          <Field label="Ticker">
            <Input
              value={form.ticker}
              onChange={(e) => set('ticker', e.target.value)}
              placeholder="Opcional"
            />
          </Field>
          <Field label="Cantidad *">
            <Input
              type="number"
              step="any"
              value={form.Quantity}
              onChange={(e) => set('Quantity', e.target.value)}
              placeholder="Ej: 1 o -1"
            />
          </Field>
          <Field label="Precio *">
            <Input
              type="number"
              step="any"
              value={form.Price}
              onChange={(e) => set('Price', e.target.value)}
              placeholder="Ej: 123.45"
            />
          </Field>
          <Field label="Valor (€)" className="col-span-2">
            <Input
              type="number"
              step="any"
              value={form.Value}
              onChange={(e) => set('Value', e.target.value)}
              placeholder="Auto si se deja vacío"
            />
            <p className="mt-1 text-xs text-txt3">
              Se calcula como ±Cantidad×Precio si se deja vacío.
            </p>
          </Field>
        </form>

        <DialogFooter>
          <Button
            variant="outline"
            type="button"
            onClick={() => setOpen(false)}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={() => void submit()}
            disabled={add.isPending}
          >
            {add.isPending ? 'Guardando…' : 'Guardar operación'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Field({
  label,
  children,
  className,
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={className}>
      <Label className="mb-1 block">{label}</Label>
      {children}
    </div>
  )
}
