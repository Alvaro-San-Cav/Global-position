import { cloneElement, useId, useState, type ReactElement, type ReactNode } from 'react'
import { Plus, Pencil, Trash2 } from 'lucide-react'
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
import { useAddCrypto, useUpdateCrypto, useDeleteCrypto } from '@/api/queries'
import type { CryptoOperation, CryptoOperationCreate } from '@/api/types'

/** Local datetime "YYYY-MM-DDTHH:MM" for a datetime-local default. */
const nowLocal = () =>
  new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)

/** API date "YYYY-MM-DD HH:MM[:SS]" → datetime-local, keeping seconds if present. */
const toLocalInput = (raw: string | null | undefined): string => {
  if (!raw) return nowLocal()
  const [date, time] = raw.split(/[ T]/)
  if (!date) return nowLocal()
  const t = time ?? '00:00'
  return `${date}T${/^\d{2}:\d{2}:\d{2}/.test(t) ? t.slice(0, 8) : t.slice(0, 5)}`
}

/** True when a datetime-local value carries seconds. */
const hasSeconds = (v: string) => /T\d{2}:\d{2}:\d{2}/.test(v)

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

const fromOperation = (op: CryptoOperation): FormState => ({
  Date: toLocalInput(op.Date),
  Coin: op.Coin ?? '',
  Quantity: op.Quantity != null ? String(op.Quantity) : '',
  Product: op.Product ?? '',
  ticker: op.ticker ?? '',
})

/**
 * Add or edit a crypto movement. Pass `operation` (with a numeric `id`) to edit
 * an existing row; omit it to add a new one. Edit mode also allows deletion.
 */
export function CryptoDialog({ operation }: { operation?: CryptoOperation }) {
  const isEdit = operation != null && operation.id != null
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(empty)
  const [confirmDelete, setConfirmDelete] = useState(false)
  // Coin/ticker the row had when the dialog opened (to detect a stale ticker).
  const [orig, setOrig] = useState<{ Coin: string; ticker: string }>({ Coin: '', ticker: '' })
  const add = useAddCrypto()
  const update = useUpdateCrypto()
  const del = useDeleteCrypto()

  // Reset the form whenever the dialog opens (fresh for add, prefilled for edit).
  function onOpenChange(next: boolean) {
    if (next) {
      const f = isEdit ? fromOperation(operation!) : empty()
      setForm(f)
      setOrig({ Coin: f.Coin.trim().toUpperCase(), ticker: f.ticker.trim() })
      setConfirmDelete(false)
    }
    setOpen(next)
  }

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
    const coin = form.Coin.trim().toUpperCase()
    // If the coin changed but the ticker is still the old one, it is stale:
    // omit it so the backend resolves it automatically.
    const staleTicker =
      isEdit && coin !== orig.Coin && form.ticker.trim() === orig.ticker
    // API expects "YYYY-MM-DD HH:MM"; datetime-local yields "YYYY-MM-DDTHH:MM".
    const body: CryptoOperationCreate = {
      Date: form.Date.replace('T', ' '),
      Coin: coin,
      Quantity: Number(form.Quantity),
      ...(form.Product.trim() ? { Product: form.Product.trim() } : {}),
      ...(form.ticker.trim() && !staleTicker ? { ticker: form.ticker.trim() } : {}),
    }
    try {
      if (isEdit) {
        await update.mutateAsync({
          id: operation!.id!,
          body,
          fingerprint: operation!.fingerprint,
        })
        toast.success('Movimiento crypto actualizado.')
      } else {
        await add.mutateAsync(body)
        toast.success('Movimiento crypto guardado.')
        setForm(empty())
      }
      setOpen(false)
    } catch (e) {
      toast.error(`Error al guardar: ${(e as Error).message}`)
    }
  }

  async function remove() {
    try {
      await del.mutateAsync({ id: operation!.id!, fingerprint: operation!.fingerprint })
      toast.success('Movimiento crypto eliminado.')
      setOpen(false)
    } catch (e) {
      toast.error(`Error al eliminar: ${(e as Error).message}`)
    }
  }

  const pending = add.isPending || update.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        {isEdit ? (
          <Button variant="ghost" size="icon" aria-label="Editar movimiento">
            <Pencil />
          </Button>
        ) : (
          <Button>
            <Plus />
            Añadir movimiento
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? 'Editar movimiento crypto' : 'Nuevo movimiento crypto'}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Modifica los datos de esta entrada de criptomoneda.'
              : 'Registra una entrada manual de criptomoneda.'}
          </DialogDescription>
        </DialogHeader>

        <form
          id="crypto-form"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
          className="grid grid-cols-2 gap-3"
        >
          <Field label="Fecha y hora *" className="col-span-2">
            <Input
              type="datetime-local"
              step={hasSeconds(form.Date) ? 1 : undefined}
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
          <Field label="Ticker" hint={<p className="mt-1 text-xs text-txt3">Vacío = automático.</p>}>
            <Input
              value={form.ticker}
              onChange={(e) => set('ticker', e.target.value)}
              placeholder="Automático"
            />
          </Field>
        </form>

        <DialogFooter className="sm:justify-between">
          {isEdit ? (
            confirmDelete ? (
              <Button
                variant="danger"
                type="button"
                onClick={() => void remove()}
                disabled={del.isPending}
              >
                <Trash2 />
                {del.isPending ? 'Eliminando…' : '¿Confirmar eliminación?'}
              </Button>
            ) : (
              <Button
                variant="ghost"
                type="button"
                className="text-red hover:text-red"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 />
                Eliminar
              </Button>
            )
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button
              variant="outline"
              type="button"
              onClick={() => setOpen(false)}
            >
              Cancelar
            </Button>
            <Button type="submit" form="crypto-form" disabled={pending}>
              {pending
                ? 'Guardando…'
                : isEdit
                  ? 'Guardar cambios'
                  : 'Guardar movimiento'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Field({
  label,
  children,
  className,
  hint,
}: {
  label: string
  children: ReactElement<{ id?: string }>
  className?: string
  hint?: ReactNode
}) {
  const id = useId()
  return (
    <div className={className}>
      <Label htmlFor={id} className="mb-1 block">
        {label}
      </Label>
      {cloneElement(children, { id })}
      {hint}
    </div>
  )
}
