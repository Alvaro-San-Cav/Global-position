import { useMemo, useState } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type ColumnDef } from '@/components/DataTable'
import { CryptoDialog } from '@/components/operations/CryptoDialog'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useCrypto, useDashboard } from '@/api/queries'
import type { CryptoOperation, CryptoSlice } from '@/api/types'
import { fmtEur, fmtNum } from '@/lib/format'
import { cn } from '@/lib/utils'

const ALL = '__all__'

/** "YYYY-MM-DD HH:MM" → "DD/MM/YYYY HH:MM" (keeps time, unlike fmtDate). */
function fmtDateTime(raw: string | null | undefined): string {
  if (!raw) return '—'
  const [date, time] = raw.split(/[ T]/)
  const parts = date?.split('-')
  if (!parts || parts.length !== 3) return raw
  const [y, m, d] = parts
  return time ? `${d}/${m}/${y} ${time.slice(0, 5)}` : `${d}/${m}/${y}`
}

export function Crypto() {
  const { data, isLoading, isError } = useCrypto()
  const dashboard = useDashboard()
  const rows = useMemo(() => data ?? [], [data])

  const [coin, setCoin] = useState(ALL)

  const coins = useMemo(
    () =>
      [...new Set(rows.map((r) => r.Coin).filter(Boolean))].sort() as string[],
    [rows],
  )

  const filtered = useMemo(
    () => (coin === ALL ? rows : rows.filter((r) => r.Coin === coin)),
    [rows, coin],
  )

  // Net balance per coin (client-side sum of Quantity).
  const balances = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of rows) {
      const c = r.Coin
      if (!c) continue
      map.set(c, (map.get(c) ?? 0) + (r.Quantity ?? 0))
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1])
  }, [rows])

  // symbol → EUR value from the dashboard breakdown.
  const eurBySymbol = useMemo(() => {
    const map = new Map<string, number>()
    for (const s of dashboard.data?.crypto_breakdown ?? ([] as CryptoSlice[])) {
      if (s.symbol) map.set(s.symbol.toUpperCase(), s.value)
    }
    return map
  }, [dashboard.data])

  const columns = useMemo<ColumnDef<CryptoOperation>[]>(() => [
    {
      key: 'Date',
      header: 'Fecha',
      sortable: true,
      sortValue: (r) => r.Date ?? '',
      render: (r) => (
        <span className="tabular-nums">{fmtDateTime(r.Date)}</span>
      ),
    },
    {
      key: 'Coin',
      header: 'Coin',
      sortable: true,
      sortValue: (r) => r.Coin ?? '',
      render: (r) => (r.Coin ? <Badge variant="amber">{r.Coin}</Badge> : '—'),
    },
    {
      key: 'Quantity',
      header: 'Cantidad',
      sortable: true,
      align: 'right',
      sortValue: (r) => r.Quantity ?? 0,
      cellClassName: 'tabular-nums',
      render: (r) => fmtNum(r.Quantity, 8),
    },
    {
      key: 'Product',
      header: 'Producto',
      sortable: true,
      sortValue: (r) => r.Product ?? '',
      render: (r) => <span className="text-txt">{r.Product || '—'}</span>,
    },
    {
      key: 'ticker',
      header: 'Ticker',
      sortable: true,
      sortValue: (r) => r.ticker ?? '',
      render: (r) => r.ticker || '—',
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (r) =>
        r.id != null ? (
          <div className="flex justify-end">
            <CryptoDialog operation={r} />
          </div>
        ) : null,
    },
  ], [])

  return (
    <div>
      <PageHeader
        title="Crypto"
        subtitle="Movimientos y balance por criptomoneda."
        actions={<CryptoDialog />}
      />

      {balances.length > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {balances.map(([c, qty]) => {
            const eur = eurBySymbol.get(c.toUpperCase())
            return (
              <Card key={c}>
                <CardContent className="pt-4">
                  <div className="flex items-center justify-between">
                    <Badge variant="amber">{c}</Badge>
                    {eur != null && (
                      <span className="text-xs text-txt2">{fmtEur(eur)}</span>
                    )}
                  </div>
                  <p
                    className={cn(
                      'mt-2 text-lg font-semibold tabular-nums',
                      qty >= 0 ? 'text-txt' : 'text-red',
                    )}
                  >
                    {fmtNum(qty, 8)}
                  </p>
                  <p className="text-xs text-txt3">Balance neto</p>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-[var(--radius-card-lg)] border border-border-subtle bg-card p-4">
        <div className="flex flex-col gap-1">
          <Label>Moneda</Label>
          <Select value={coin} onValueChange={setCoin}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Todas</SelectItem>
              {coins.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <span className="pb-2 text-xs text-txt2">
          {filtered.length}{' '}
          {filtered.length === 1 ? 'transacción' : 'transacciones'}
        </span>
      </div>

      {isLoading ? (
        <p className="text-sm text-txt2">Cargando movimientos…</p>
      ) : isError ? (
        <p className="text-sm text-red">
          No se pudieron cargar los movimientos.
        </p>
      ) : (
        <DataTable
          columns={columns}
          rows={filtered}
          defaultSort={{ key: 'Date', dir: 'desc' }}
          getRowKey={(r, i) => `${r.Date}-${r.Coin ?? ''}-${i}`}
          emptyMessage="No hay movimientos para el filtro seleccionado."
        />
      )}
    </div>
  )
}
