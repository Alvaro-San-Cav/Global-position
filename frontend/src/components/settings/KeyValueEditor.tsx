import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export interface KVRow {
  key: string
  value: string
}

/** Editable key-value table (add / edit / remove rows). Values kept as strings. */
export function KeyValueEditor({
  rows,
  onChange,
  keyLabel = 'Clave',
  valueLabel = 'Valor',
  valueType = 'text',
  keyPlaceholder,
  valuePlaceholder,
}: {
  rows: KVRow[]
  onChange: (rows: KVRow[]) => void
  keyLabel?: string
  valueLabel?: string
  valueType?: 'text' | 'number'
  keyPlaceholder?: string
  valuePlaceholder?: string
}) {
  function update(i: number, patch: Partial<KVRow>) {
    onChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }
  function remove(i: number) {
    onChange(rows.filter((_, idx) => idx !== i))
  }
  function add() {
    onChange([...rows, { key: '', value: '' }])
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_1fr_auto] gap-2 px-1 text-xs font-medium text-txt2">
        <span>{keyLabel}</span>
        <span>{valueLabel}</span>
        <span className="w-9" />
      </div>
      {rows.length === 0 && (
        <p className="px-1 py-2 text-sm text-txt2">Sin entradas.</p>
      )}
      {rows.map((row, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2">
          <Input
            value={row.key}
            placeholder={keyPlaceholder}
            onChange={(e) => update(i, { key: e.target.value })}
          />
          <Input
            value={row.value}
            type={valueType}
            placeholder={valuePlaceholder}
            onChange={(e) => update(i, { value: e.target.value })}
          />
          <Button
            variant="ghost"
            size="icon"
            type="button"
            aria-label="Eliminar fila"
            onClick={() => remove(i)}
          >
            <X />
          </Button>
        </div>
      ))}
      <Button variant="subtle" size="sm" type="button" onClick={add}>
        <Plus /> Añadir fila
      </Button>
    </div>
  )
}
