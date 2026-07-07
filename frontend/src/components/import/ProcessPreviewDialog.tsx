import { useEffect, useState } from 'react'
import { AlertTriangle, FileText, Trash2, Plus } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import type {
  ProcessPreview,
  PreviewFile,
  ProcessCommitFile,
  PreviewStockEntry,
  PreviewCryptoEntry,
} from '@/api/types'

/** Editable working copy of a file's rows (all values as strings for inputs). */
interface EditFile {
  file: string
  kind: 'stock' | 'crypto'
  source?: string | null
  duplicates: number
  error?: string | null
  rows: Record<string, string>[]
}

const STOCK_COLS: { key: string; label: string; className?: string }[] = [
  { key: 'date', label: 'Fecha' },
  { key: 'product', label: 'Producto' },
  { key: 'isin', label: 'ISIN' },
  { key: 'quantity', label: 'Cantidad' },
  { key: 'price', label: 'Precio' },
  { key: 'coin', label: 'Moneda' },
  { key: 'value', label: 'Valor' },
]

const CRYPTO_COLS: { key: string; label: string }[] = [
  { key: 'date', label: 'Fecha' },
  { key: 'coin', label: 'Moneda' },
  { key: 'quantity', label: 'Cantidad' },
  { key: 'ticker', label: 'Ticker' },
]

function str(v: unknown): string {
  return v === null || v === undefined ? '' : String(v)
}

function toEditFiles(preview: ProcessPreview | null): EditFile[] {
  if (!preview) return []
  return preview.files.map((f: PreviewFile) => ({
    file: f.file,
    kind: f.kind,
    source: f.source,
    duplicates: f.duplicates,
    error: f.error,
    rows: (f.entries ?? []).map((e) => {
      const cols = f.kind === 'crypto' ? CRYPTO_COLS : STOCK_COLS
      const row: Record<string, string> = {}
      for (const c of cols) row[c.key] = str((e as unknown as Record<string, unknown>)[c.key])
      return row
    }),
  }))
}

interface ProcessPreviewDialogProps {
  preview: ProcessPreview | null
  onOpenChange: (open: boolean) => void
  onConfirm: (files: ProcessCommitFile[]) => void
  busy?: boolean
}

/**
 * Editable confirmation preview shown before committing new transactions.
 * The user can edit any field, delete rows, or add rows; on confirm the exact
 * edited rows are sent to the backend (nothing is saved until "Confirmar").
 */
export function ProcessPreviewDialog({
  preview,
  onOpenChange,
  onConfirm,
  busy = false,
}: ProcessPreviewDialogProps) {
  const [files, setFiles] = useState<EditFile[]>([])

  useEffect(() => {
    setFiles(toEditFiles(preview))
  }, [preview])

  const totalNew = files.reduce((a, f) => a + f.rows.length, 0)
  const totalDup = files.reduce((a, f) => a + f.duplicates, 0)
  const nothingNew = totalNew === 0

  function setCell(fi: number, ri: number, key: string, value: string) {
    setFiles((prev) =>
      prev.map((f, i) =>
        i !== fi
          ? f
          : { ...f, rows: f.rows.map((r, j) => (j === ri ? { ...r, [key]: value } : r)) },
      ),
    )
  }

  function deleteRow(fi: number, ri: number) {
    setFiles((prev) =>
      prev.map((f, i) =>
        i !== fi ? f : { ...f, rows: f.rows.filter((_, j) => j !== ri) },
      ),
    )
  }

  function addRow(fi: number) {
    setFiles((prev) =>
      prev.map((f, i) => {
        if (i !== fi) return f
        const cols = f.kind === 'crypto' ? CRYPTO_COLS : STOCK_COLS
        const empty: Record<string, string> = {}
        for (const c of cols) empty[c.key] = ''
        // Prepend so the new (empty) row appears at the top, ready to edit.
        return { ...f, rows: [empty, ...f.rows] }
      }),
    )
  }

  function handleConfirm() {
    const payload: ProcessCommitFile[] = files
      .filter((f) => !f.error && f.rows.length > 0)
      .map((f) => ({
        file: f.file,
        kind: f.kind,
        entries: f.rows.map((r) =>
          f.kind === 'crypto'
            ? ({
                date: r.date,
                coin: r.coin,
                quantity: Number(r.quantity) || 0,
                ticker: r.ticker,
              } as PreviewCryptoEntry)
            : ({
                date: r.date,
                product: r.product,
                isin: r.isin,
                quantity: r.quantity === '' ? null : Number(r.quantity),
                price: r.price === '' ? null : Number(r.price),
                coin: r.coin,
                value: r.value === '' ? null : Number(r.value),
              } as PreviewStockEntry),
        ),
      }))
    onConfirm(payload)
  }

  return (
    <Dialog open={preview !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>Previsualizar y editar antes de guardar</DialogTitle>
          <DialogDescription>
            {nothingNew ? (
              'No hay transacciones nuevas para añadir.'
            ) : (
              <>
                Se guardarán{' '}
                <span className="font-medium text-txt">{totalNew}</span>{' '}
                transacción(es)
                {totalDup > 0 && (
                  <>
                    {' '}
                    (<span className="text-txt2">{totalDup} duplicada(s) omitida(s)</span>)
                  </>
                )}
                . Edita, borra o añade filas; nada se guarda hasta que confirmes.
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
          {files.map((f, fi) => (
            <FileEditor
              key={`${f.kind}-${f.file}`}
              file={f}
              onCell={(ri, key, value) => setCell(fi, ri, key, value)}
              onDelete={(ri) => deleteRow(fi, ri)}
              onAdd={() => addRow(fi)}
            />
          ))}
        </div>

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" size="sm" disabled={busy}>
              Cancelar
            </Button>
          </DialogClose>
          <Button size="sm" disabled={busy || nothingNew} onClick={handleConfirm}>
            {busy ? 'Guardando…' : `Confirmar y guardar (${totalNew})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function FileEditor({
  file,
  onCell,
  onDelete,
  onAdd,
}: {
  file: EditFile
  onCell: (ri: number, key: string, value: string) => void
  onDelete: (ri: number) => void
  onAdd: () => void
}) {
  const cols = file.kind === 'crypto' ? CRYPTO_COLS : STOCK_COLS

  return (
    <div className="rounded-[var(--radius-card)] border border-border-subtle bg-card2">
      <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle px-3 py-2 text-sm">
        <FileText className="size-3.5 shrink-0 text-txt3" />
        <span className="font-medium text-txt">{file.file}</span>
        <Badge variant="accent">{file.kind === 'crypto' ? 'Crypto' : 'Acciones'}</Badge>
        {file.error ? (
          <Badge variant="red">Error</Badge>
        ) : (
          <>
            <Badge variant="green">{file.rows.length} a guardar</Badge>
            {file.duplicates > 0 && (
              <Badge variant="red">{file.duplicates} duplicada(s)</Badge>
            )}
          </>
        )}
      </div>

      <div className="px-3 py-2">
        {file.error ? (
          <div className="flex items-start gap-2 text-sm text-red">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{file.error}</span>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    {cols.map((c) => (
                      <TableHead key={c.key}>{c.label}</TableHead>
                    ))}
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {file.rows.map((row, ri) => (
                    <TableRow key={ri}>
                      {cols.map((c) => (
                        <TableCell key={c.key} className="p-1">
                          <Input
                            value={row[c.key] ?? ''}
                            onChange={(e) => onCell(ri, c.key, e.target.value)}
                            className="h-8 text-xs tabular-nums"
                          />
                        </TableCell>
                      ))}
                      <TableCell className="p-1 text-center">
                        <button
                          type="button"
                          onClick={() => onDelete(ri)}
                          title="Eliminar fila"
                          aria-label={`Eliminar fila ${ri + 1}`}
                          className="rounded p-1 text-txt3 transition-colors hover:bg-red-dim hover:text-red"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <div className="mt-2">
              <Button variant="outline" size="sm" onClick={onAdd}>
                <Plus className="size-3.5" /> Añadir fila
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
