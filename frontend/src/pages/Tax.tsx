import { useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '@/components/ui/tabs'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select'
import { fmtEur, fmtNum, fmtDate, signColor } from '@/lib/format'
import { useTax } from '@/api/queries'

/**
 * Local row shapes describing the exact keys observed from GET /api/tax.
 * The API returns Record<string, unknown>[]; these interfaces document the
 * columns, but every field is read defensively (String()/Number()) because
 * pandas emits dynamic keys.
 */
// Observed `gains` columns (documented; read defensively at runtime):
// ticker, fecha_venta, qty_vendida, precio_venta_eur, coste_base_eur,
// plusvalia_eur, annyo.

const ALL_YEARS = '__all__'

/** Read a numeric field from a dynamic row, tolerating null/undefined. */
function num(row: Record<string, unknown>, key: string): number {
  return Number(row[key])
}

/** Read a string field from a dynamic row. */
function str(row: Record<string, unknown>, key: string): string {
  const v = row[key]
  return v == null ? '—' : String(v)
}

/** Build a CSV from the raw gains rows and trigger a client-side download. */
function downloadTaxCsv(gains: Record<string, unknown>[]): void {
  if (!gains.length) return
  const keys = Object.keys(gains[0])
  const csv = [
    keys.join(','),
    ...gains.map((r) =>
      keys.map((k) => `"${r[k] ?? ''}"`).join(','),
    ),
  ].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'plusvalias_fifo.csv'
  a.click()
  URL.revokeObjectURL(url)
  toast.success('CSV descargado')
}

export function Tax() {
  const { data, isLoading } = useTax()
  const [year, setYear] = useState<string>(ALL_YEARS)

  const gains = data?.gains ?? []
  const annual = data?.annual ?? []
  const byTicker = data?.by_ticker ?? []

  // Distinct fiscal years present in the sales detail, descending.
  const years = useMemo(() => {
    const set = new Set<string>()
    for (const r of gains) {
      const y = r.annyo != null ? String(r.annyo) : r.fecha_venta != null ? String(r.fecha_venta).slice(0, 4) : ''
      if (y) set.add(y)
    }
    return Array.from(set).sort((a, b) => Number(b) - Number(a))
  }, [gains])

  const filteredGains = useMemo(() => {
    if (year === ALL_YEARS) return gains
    return gains.filter((r) => {
      const y = r.annyo != null ? String(r.annyo) : String(r.fecha_venta ?? '').slice(0, 4)
      return y === year
    })
  }, [gains, year])

  if (isLoading) {
    return (
      <div>
        <PageHeader
          title="Fiscalidad"
          subtitle="Plusvalías y minusvalías por criterio FIFO."
        />
        <div className="rounded-[var(--radius-card-lg)] border border-border-subtle bg-card p-8 text-sm text-txt2">
          <p className="mb-4">Calculando plusvalías (puede tardar)…</p>
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-3/4" />
          </div>
        </div>
      </div>
    )
  }

  if (!gains.length) {
    return (
      <div>
        <PageHeader
          title="Fiscalidad"
          subtitle="Plusvalías y minusvalías por criterio FIFO."
        />
        <div className="rounded-[var(--radius-card-lg)] border border-border-subtle bg-card p-8 text-center text-sm text-txt2">
          No hay ventas registradas
        </div>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Fiscalidad"
        subtitle="Plusvalías y minusvalías por criterio FIFO."
        actions={
          <Button variant="outline" onClick={() => downloadTaxCsv(gains)}>
            <Download />
            Exportar CSV
          </Button>
        }
      />

      <Tabs defaultValue="annual">
        <TabsList>
          <TabsTrigger value="annual">Por año</TabsTrigger>
          <TabsTrigger value="ticker">Por ticker</TabsTrigger>
          <TabsTrigger value="detail">Detalle ventas</TabsTrigger>
        </TabsList>

        {/* ── Por año ──────────────────────────────────────────── */}
        <TabsContent value="annual">
          <div className="rounded-[var(--radius-card-lg)] border border-border-subtle bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Año</TableHead>
                  <TableHead className="text-right">Plusvalía neta</TableHead>
                  <TableHead className="text-right">Ganancias</TableHead>
                  <TableHead className="text-right">Pérdidas</TableHead>
                  <TableHead className="text-right">Nº ventas</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {annual.map((r, i) => {
                  const pv = num(r, 'plusvalia_total_eur')
                  return (
                    <TableRow key={`${str(r, 'annyo')}-${i}`}>
                      <TableCell className="font-medium text-txt">{str(r, 'annyo')}</TableCell>
                      <TableCell className={`text-right tabular-nums ${signColor(pv)}`}>
                        {fmtEur(pv)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-green">
                        {fmtEur(num(r, 'plusvalias_eur'))}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-red">
                        {fmtEur(num(r, 'minusvalias_eur'))}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-txt2">
                        {fmtNum(num(r, 'n_ventas'), 0)}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        {/* ── Por ticker ───────────────────────────────────────── */}
        <TabsContent value="ticker">
          <div className="rounded-[var(--radius-card-lg)] border border-border-subtle bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Año</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead className="text-right">Plusvalía</TableHead>
                  <TableHead className="text-right">Nº ventas</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {byTicker.map((r, i) => {
                  const pv = num(r, 'plusvalia_eur')
                  return (
                    <TableRow key={`${str(r, 'ticker')}-${str(r, 'annyo')}-${i}`}>
                      <TableCell className="text-txt2 tabular-nums">{str(r, 'annyo')}</TableCell>
                      <TableCell>
                        <Badge variant="accent">{str(r, 'ticker')}</Badge>
                      </TableCell>
                      <TableCell className={`text-right tabular-nums ${signColor(pv)}`}>
                        {fmtEur(pv)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-txt2">
                        {fmtNum(num(r, 'n_ventas'), 0)}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        {/* ── Detalle ventas ───────────────────────────────────── */}
        <TabsContent value="detail">
          <div className="mb-3 flex items-center gap-2">
            <span className="text-xs text-txt2">Año fiscal:</span>
            <Select value={year} onValueChange={setYear}>
              <SelectTrigger className="h-8 w-40 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_YEARS}>Todos</SelectItem>
                {years.map((y) => (
                  <SelectItem key={y} value={y}>
                    {y}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="rounded-[var(--radius-card-lg)] border border-border-subtle bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fecha venta</TableHead>
                  <TableHead>Ticker</TableHead>
                  <TableHead className="text-right">Cantidad</TableHead>
                  <TableHead className="text-right">Precio venta</TableHead>
                  <TableHead className="text-right">Coste base</TableHead>
                  <TableHead className="text-right">Plusvalía</TableHead>
                  <TableHead>Año</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredGains.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-6 text-center text-txt2">
                      No hay ventas para el año seleccionado.
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredGains.map((r, i) => {
                    const pv = num(r, 'plusvalia_eur')
                    return (
                      <TableRow key={`${str(r, 'ticker')}-${str(r, 'fecha_venta')}-${i}`}>
                        <TableCell className="tabular-nums text-txt2">
                          {fmtDate(str(r, 'fecha_venta'))}
                        </TableCell>
                        <TableCell>
                          <Badge variant="accent">{str(r, 'ticker')}</Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtNum(num(r, 'qty_vendida'))}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtEur(num(r, 'precio_venta_eur'))}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtEur(num(r, 'coste_base_eur'))}
                        </TableCell>
                        <TableCell className={`text-right tabular-nums ${signColor(pv)}`}>
                          {fmtEur(pv)}
                        </TableCell>
                        <TableCell className="tabular-nums text-txt2">{str(r, 'annyo')}</TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
