import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Plus, Trash2, Loader2 } from 'lucide-react'
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
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import { useSourceFile, useSaveSourceFile } from '@/api/queries'
import { ApiError } from '@/api/client'

interface SourceFileEditorProps {
  /** Filename to edit, or null when closed. */
  filename: string | null
  title?: string
  onOpenChange: (open: boolean) => void
}

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error) return e.message
  return 'Error desconocido'
}

/**
 * Raw-CSV editor for a configured source file (e.g. sap_stock.csv).
 * Loads the file on open, lets the user edit/add/delete rows, and saves
 * back via PUT (the backend keeps a dated backup before overwriting).
 */
export function SourceFileEditor({
  filename,
  title,
  onOpenChange,
}: SourceFileEditorProps) {
  const query = useSourceFile(filename)
  const save = useSaveSourceFile()

  const [columns, setColumns] = useState<string[]>([])
  const [rows, setRows] = useState<string[][]>([])

  // Reset local edit state whenever a freshly-loaded file arrives.
  useEffect(() => {
    if (query.data) {
      setColumns(query.data.columns)
      setRows(query.data.rows.map((r) => [...r]))
    }
  }, [query.data])

  function setCell(ri: number, ci: number, value: string) {
    setRows((prev) => {
      const next = prev.map((r) => [...r])
      next[ri][ci] = value
      return next
    })
  }

  function addRow() {
    // Prepend so the new (empty) row appears at the top, ready to edit.
    setRows((prev) => [columns.map(() => ''), ...prev])
  }

  function deleteRow(ri: number) {
    setRows((prev) => prev.filter((_, i) => i !== ri))
  }

  async function handleSave() {
    if (!filename) return
    try {
      await save.mutateAsync({ file: filename, columns, rows })
      toast.success(`"${filename}" guardado (${rows.length} filas)`)
      onOpenChange(false)
    } catch (e) {
      toast.error(`Error al guardar: ${errMsg(e)}`)
    }
  }

  return (
    <Dialog open={filename !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Editar {title || filename}</DialogTitle>
          <DialogDescription>
            Edición directa del CSV fuente. Se crea una copia de seguridad
            antes de sobrescribir. Los cambios se reflejan al recargar el panel.
          </DialogDescription>
        </DialogHeader>

        {query.isLoading ? (
          <div className="flex items-center gap-2 py-8 text-sm text-txt2">
            <Loader2 className="size-4 animate-spin" /> Cargando archivo…
          </div>
        ) : query.isError ? (
          <p className="py-6 text-sm text-red">{errMsg(query.error)}</p>
        ) : (
          <>
            <div className="max-h-[55vh] overflow-auto rounded-[var(--radius-card)] border border-border-subtle">
              <Table>
                <TableHeader>
                  <TableRow>
                    {columns.map((c) => (
                      <TableHead key={c}>{c}</TableHead>
                    ))}
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row, ri) => (
                    <TableRow key={ri}>
                      {row.map((cell, ci) => (
                        <TableCell key={ci} className="p-1">
                          <Input
                            value={cell}
                            onChange={(e) => setCell(ri, ci, e.target.value)}
                            className="h-8 text-xs tabular-nums"
                          />
                        </TableCell>
                      ))}
                      <TableCell className="p-1 text-center">
                        <button
                          type="button"
                          onClick={() => deleteRow(ri)}
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

            <div className="mt-2 flex items-center justify-between">
              <Button variant="outline" size="sm" onClick={addRow}>
                <Plus className="size-3.5" /> Añadir fila
              </Button>
              <span className="text-xs text-txt3">{rows.length} fila(s)</span>
            </div>
          </>
        )}

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" size="sm" disabled={save.isPending}>
              Cancelar
            </Button>
          </DialogClose>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={save.isPending || query.isLoading || query.isError}
          >
            {save.isPending ? 'Guardando…' : 'Guardar cambios'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
