import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import {
  FileText,
  Database,
  X,
  Play,
  Loader2,
  AlertTriangle,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { Dropzone } from '@/components/import/Dropzone'
import { ConfirmDeleteDialog } from '@/components/import/ConfirmDeleteDialog'
import {
  useUpload,
  usePendingFiles,
  useDeletePending,
  useSourceFiles,
  useSourceData,
  useProcess,
} from '@/api/queries'
import { fmtEur, fmtNum, fmtDate } from '@/lib/format'
import { ApiError } from '@/api/client'
import type { SourceData } from '@/api/types'

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error) return e.message
  return 'Error desconocido'
}

export function Import() {
  const upload = useUpload()
  const pending = usePendingFiles()
  const deletePending = useDeletePending()
  const sourceFiles = useSourceFiles()
  const sourceData = useSourceData()
  const process = useProcess()

  const [toDelete, setToDelete] = useState<string | null>(null)

  async function handleUpload(files: File[]) {
    try {
      const res = await upload.mutateAsync(files)
      toast.success(`${res.saved.length} archivo(s) guardado(s) en input/`)
    } catch (e) {
      toast.error(`Error al subir: ${errMsg(e)}`)
    }
  }

  async function handleDelete() {
    if (!toDelete) return
    try {
      await deletePending.mutateAsync(toDelete)
      toast.success(`Archivo "${toDelete}" eliminado`)
      setToDelete(null)
    } catch (e) {
      toast.error(`Error al eliminar: ${errMsg(e)}`)
    }
  }

  async function handleProcess() {
    try {
      const res = await process.mutateAsync()
      toast.success(res.message || 'Procesado correctamente')
    } catch (e) {
      toast.error(`Error al procesar: ${errMsg(e)}`)
    }
  }

  return (
    <div>
      <PageHeader
        title="Importar"
        subtitle="Sube CSV de transacciones, revisa los archivos fuente y procesa los pendientes."
        actions={
          <Button
            onClick={handleProcess}
            disabled={process.isPending}
          >
            {process.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Play />
            )}
            Procesar pendientes
          </Button>
        }
      />

      <div className="flex flex-col gap-6">
        {/* ── Dropzone ─────────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Importar transacciones</CardTitle>
            <CardDescription>
              Arrastra archivos CSV o haz clic para seleccionarlos. Se guardan
              en input/ como pendientes hasta que los proceses.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Dropzone onFiles={handleUpload} busy={upload.isPending} />
          </CardContent>
        </Card>

        {/* ── Archivos pendientes ──────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Archivos pendientes</CardTitle>
            <CardDescription>
              Transacciones nuevas esperando ser procesadas. Se eliminan
              automáticamente al procesar.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {pending.isLoading ? (
              <div className="flex flex-wrap gap-2">
                <Skeleton className="h-9 w-48" />
                <Skeleton className="h-9 w-40" />
              </div>
            ) : pending.isError ? (
              <p className="text-sm text-red">{errMsg(pending.error)}</p>
            ) : !pending.data || pending.data.length === 0 ? (
              <p className="text-sm text-txt3">
                No hay archivos pendientes en input/.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {pending.data.map((name) => (
                  <FileChip
                    key={name}
                    icon={<FileText className="size-3.5 text-txt3" />}
                    label={name}
                    onDelete={() => setToDelete(name)}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Archivos fuente ──────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Archivos fuente</CardTitle>
            <CardDescription>
              Archivos permanentes leídos en cada recarga según la configuración
              de Ajustes. No se eliminan al procesar.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {sourceFiles.isLoading ? (
              <div className="flex flex-wrap gap-2">
                <Skeleton className="h-9 w-56" />
                <Skeleton className="h-9 w-48" />
              </div>
            ) : sourceFiles.isError ? (
              <p className="text-sm text-red">{errMsg(sourceFiles.error)}</p>
            ) : !sourceFiles.data || sourceFiles.data.length === 0 ? (
              <p className="text-sm text-txt3">
                No hay archivos fuente en input/ — sube uno desde la zona de
                carga.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {sourceFiles.data.map((f) => (
                  <div
                    key={f.file}
                    className="flex items-center gap-2 rounded-[var(--radius-card)] border border-border-subtle bg-card2 px-3 py-2 text-sm text-txt"
                  >
                    <Database className="size-3.5 shrink-0 text-txt3" />
                    <span>{f.file}</span>
                    <Badge variant="accent">{f.source}</Badge>
                    <Badge variant={f.enabled ? 'green' : 'red'}>
                      {f.enabled ? 'Activo' : 'Inactivo'}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Datos de fuentes ─────────────────────────────────────── */}
        <div>
          <h2 className="mb-3 text-sm font-semibold text-txt2">
            Datos de fuentes
          </h2>
          {sourceData.isLoading ? (
            <div className="grid gap-4 md:grid-cols-2">
              <Skeleton className="h-64 w-full" />
              <Skeleton className="h-64 w-full" />
            </div>
          ) : sourceData.isError ? (
            <p className="text-sm text-red">{errMsg(sourceData.error)}</p>
          ) : !sourceData.data || sourceData.data.length === 0 ? (
            <p className="text-sm text-txt3">
              No hay datos de fuentes para mostrar.
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {sourceData.data.map((sd) => (
                <SourceDataCard key={`${sd.source}-${sd.file}`} data={sd} />
              ))}
            </div>
          )}
        </div>
      </div>

      <ConfirmDeleteDialog
        filename={toDelete}
        onOpenChange={(open) => {
          if (!open) setToDelete(null)
        }}
        onConfirm={handleDelete}
        busy={deletePending.isPending}
      />
    </div>
  )
}

function FileChip({
  icon,
  label,
  onDelete,
}: {
  icon: ReactNode
  label: string
  onDelete: () => void
}) {
  return (
    <div className="flex items-center gap-2 rounded-[var(--radius-card)] border border-border-subtle bg-card2 px-3 py-2 text-sm text-txt">
      {icon}
      <span>{label}</span>
      <button
        type="button"
        onClick={onDelete}
        title="Eliminar"
        aria-label={`Eliminar ${label}`}
        className="ml-1 flex items-center rounded p-0.5 text-txt3 transition-colors hover:bg-red-dim hover:text-red"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}

function SourceDataCard({ data }: { data: SourceData }) {
  const title = [data.source, data.ticker ?? data.product ?? data.coin]
    .filter(Boolean)
    .join(' · ')

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title || data.source}</CardTitle>
        <CardDescription>{data.file}</CardDescription>
      </CardHeader>
      <CardContent>
        {data.error ? (
          <div className="flex items-start gap-2 text-sm text-red">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{data.error}</span>
          </div>
        ) : data.entries.length === 0 ? (
          <p className="text-sm text-txt3">Sin movimientos.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fecha</TableHead>
                <TableHead className="text-right">Cantidad</TableHead>
                <TableHead className="text-right">Precio</TableHead>
                <TableHead className="text-right">Valor</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.entries.map((e, i) => (
                <TableRow key={`${e.date}-${i}`}>
                  <TableCell className="whitespace-nowrap text-txt2">
                    {fmtDate(e.date)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtNum(e.quantity, 6)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtNum(e.price, 4)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {fmtEur(e.value)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell className="text-txt2">Total</TableCell>
                <TableCell className="text-right tabular-nums">
                  {fmtNum(data.total_qty, 6)}
                </TableCell>
                <TableCell />
                <TableCell className="text-right tabular-nums">
                  {fmtEur(data.total_value)}
                </TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
