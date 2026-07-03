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
import { useAddCrypto } from '@/api/queries'
import type { CryptoOperationCreate } from '@/api/types'

/** Local datetime "YYYY-MM-DDTHH:MM" for a datetime-local default. */
const nowLocal = () =>
  new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)

interface FormState {
  Date: string
  Coin: string
  Quantity: string
  Product: string
  ticker: string
}

const empty = (): FormState => ({
  Date: nowLocal(),
  Coin: '',
  Quantity: '',
  Product: '',
  ticker: '',
})

export function CryptoDialog() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(empty)
  const add = useAddCrypto()

  function set<K extends keyof FormState>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function validate(): string | null {
    if (!form.Date) return 'La fecha es obligatoria.'
    if (!form.Coin.trim()) return 'La moneda (Coin) es obligatoria.'
    const qty = Number(form.Quantity)
    if (!form.Quantity.trim() || Number.isNaN(qty) || qty <= 0)
      return 'La cantidad debe ser un número mayor que 0.'
    return null
  }

  async function submit() {
    const err = validate()
    if (err) {
      toast.error(err)
      return
    }
    // API expects "YYYY-MM-DD HH:MM"; datetime-local yields "YYYY-MM-DDTHH:MM".
    const body: CryptoOperationCreate = {
      Date: form.Date.replace('T', ' '),
      Coin: form.Coin.trim().toUpperCase(),
      Quantity: Number(form.Quantity),
      ...(form.Product.trim() ? { Product: form.Product.trim() } : {}),
      ...(form.ticker.trim() ? { ticker: form.ticker.trim() } : {}),
    }
    try {
      await add.mutateAsync(body)
      toast.success('Movimiento crypto guardado.')
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
          Añadir movimiento
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo movimiento crypto</DialogTitle>
          <DialogDescription>
            Registra una entrada manual de criptomoneda.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
          className="grid grid-cols-2 gap-3"
        >
          <Field label="Fecha y hora *" className="col-span-2">
            <Input
              type="datetime-local"
              value={form.Date}
              onChange={(e) => set('Date', e.target.value)}
            />
          </Field>
          <Field label="Coin *">
            <Input
              value={form.Coin}
              onChange={(e) => set('Coin', e.target.value)}
              placeholder="BTC"
            />
          </Field>
          <Field label="Cantidad *">
            <Input
              type="number"
              step="any"
              value={form.Quantity}
              onChange={(e) => set('Quantity', e.target.value)}
              placeholder="0.01"
            />
          </Field>
          <Field label="Producto">
            <Input
              value={form.Product}
              onChange={(e) => set('Product', e.target.value)}
              placeholder="Opcional"
            />
          </Field>
          <Field label="Ticker">
            <Input
              value={form.ticker}
              onChange={(e) => set('ticker', e.target.value)}
              placeholder="Opcional"
            />
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
            {add.isPending ? 'Guardando…' : 'Guardar movimiento'}
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
