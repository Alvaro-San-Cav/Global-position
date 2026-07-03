import { useMemo, useState } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type ColumnDef } from '@/components/DataTable'
import { OperationDialog } from '@/components/operations/OperationDialog'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { TableCell, TableFooter, TableRow } from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useOperations } from '@/api/queries'
import type { Operation } from '@/api/types'
import { fmtDate, fmtEur, fmtNum, signColor } from '@/lib/format'
import { cn } from '@/lib/utils'

const ALL = '__all__'

export function Operations() {
  const { data, isLoading, isError } = useOperations()
  const rows = useMemo(() => data ?? [], [data])

  const [ticker, setTicker] = useState(ALL)
  const [coin, setCoin] = useState(ALL)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [search, setSearch] = useState('')

  const tickers = useMemo(
    () =>
      [...new Set(rows.map((r) => r.ticker).filter(Boolean))].sort() as string[],
    [rows],
  )
  const coins = useMemo(
    () =>
      [...new Set(rows.map((r) => r.Coin).filter(Boolean))].sort() as string[],
    [rows],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (ticker !== ALL && r.ticker !== ticker) return false
      if (coin !== ALL && r.Coin !== coin) return false
      const d = (r.Date ?? '').slice(0, 10)
      if (from && d < from) return false
      if (to && d > to) return false
      if (q) {
        const hay = `${r.Product ?? ''} ${r.ISIN ?? ''} ${r.ticker ?? ''}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [rows, ticker, coin, from, to, search])

  const visibleSum = useMemo(
    () => filtered.reduce((acc, r) => acc + (r.Value ?? 0), 0),
    [filtered],
  )

  const clear = () => {
    setTicker(ALL)
    setCoin(ALL)
    setFrom('')
    setTo('')
    setSearch('')
  }

  const columns: ColumnDef<Operation>[] = [
    {
      key: 'Date',
      header: 'Fecha',
      sortable: true,
      sortValue: (r) => r.Date ?? '',
      render: (r) => <span className="tabular-nums">{fmtDate(r.Date)}</span>,
    },
    {
      key: 'Product',
      header: 'Producto',
      sortable: true,
      sortValue: (r) => r.Product ?? '',
      render: (r) => (
        <span
          className="block max-w-[220px] truncate font-medium text-txt"
          title={r.Product ?? ''}
        >
          {r.Product || '—'}
        </span>
      ),
    },
    {
      key: 'ticker',
      header: 'Ticker',
      sortable: true,
      sortValue: (r) => r.ticker ?? '',
      render: (r) =>
        r.ticker ? <Badge variant="accent">{r.ticker}</Badge> : '—',
    },
    {
      key: 'ISIN',
      header: 'ISIN',
      sortable: true,
      sortValue: (r) => r.ISIN ?? '',
      render: (r) => (
        <span className="tabular-nums text-xs text-txt3">{r.ISIN || '—'}</span>
      ),
    },
    {
      key: 'Quantity',
      header: 'Cantidad',
      sortable: true,
      align: 'right',
      sortValue: (r) => r.Quantity ?? 0,
      cellClassName: (r) => cn('tabular-nums', signColor(r.Quantity)),
      render: (r) => fmtNum(r.Quantity),
    },
    {
      key: 'Price',
      header: 'Precio',
      sortable: true,
      align: 'right',
      sortValue: (r) => r.Price ?? 0,
      cellClassName: 'tabular-nums',
      render: (r) => fmtNum(r.Price),
    },
    {
      key: 'Coin',
      header: 'Moneda',
      sortable: true,
      sortValue: (r) => r.Coin ?? '',
      render: (r) => (r.Coin ? <Badge variant="amber">{r.Coin}</Badge> : '—'),
    },
    {
      key: 'Value',
      header: 'Valor',
      sortable: true,
      align: 'right',
      sortValue: (r) => r.Value ?? 0,
      cellClassName: (r) => cn('tabular-nums font-medium', signColor(r.Value)),
      render: (r) => fmtNum(r.Value),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Operaciones"
        subtitle="Compras y ventas registradas."
        actions={<OperationDialog />}
      />

      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-[var(--radius-card-lg)] border border-border-subtle bg-card p-4">
        <FilterSelect
          label="Ticker"
          value={ticker}
          onChange={setTicker}
          options={tickers}
          allLabel="Todos"
        />
        <FilterSelect
          label="Moneda"
          value={coin}
          onChange={setCoin}
          options={coins}
          allLabel="Todas"
        />
        <div className="flex flex-col gap-1">
          <Label>Desde</Label>
          <Input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="w-[150px]"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Hasta</Label>
          <Input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="w-[150px]"
          />
        </div>
        <div className="flex flex-1 flex-col gap-1">
          <Label>Buscar</Label>
          <Input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Producto / ISIN / Ticker…"
            className="min-w-[190px]"
          />
        </div>
        <Button variant="ghost" onClick={clear}>
          Limpiar
        </Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-txt2">Cargando operaciones…</p>
      ) : isError ? (
        <p className="text-sm text-red">No se pudieron cargar las operaciones.</p>
      ) : (
        <DataTable
          columns={columns}
          rows={filtered}
          defaultSort={{ key: 'Date', dir: 'desc' }}
          getRowKey={(r, i) => `${r.Date}-${r.ISIN ?? ''}-${i}`}
          emptyMessage="No hay operaciones para los filtros seleccionados."
          footer={
            <TableFooter>
              <TableRow>
                <TableCell colSpan={7} className="text-txt2">
                  {filtered.length}{' '}
                  {filtered.length === 1 ? 'operación' : 'operaciones'}
                </TableCell>
                <TableCell
                  className={cn(
                    'text-right tabular-nums',
                    signColor(visibleSum),
                  )}
                >
                  {fmtEur(visibleSum)}
                </TableCell>
              </TableRow>
            </TableFooter>
          }
        />
      )}
    </div>
  )
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: string[]
  allLabel: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-[140px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>{allLabel}</SelectItem>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
