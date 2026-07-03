import { useMemo, useState, type ReactNode } from 'react'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

export type Align = 'left' | 'right' | 'center'

export interface ColumnDef<T> {
  /** Unique key. Used for sorting via `sortValue` (falls back to `row[key]`). */
  key: string
  header: ReactNode
  /** Custom cell renderer. Defaults to `String(row[key])`. */
  render?: (row: T) => ReactNode
  /** Value used for client-side sorting. Defaults to `row[key]`. */
  sortValue?: (row: T) => string | number | null | undefined
  sortable?: boolean
  align?: Align
  /** Extra classes for the cells in this column. */
  cellClassName?: string | ((row: T) => string)
}

interface SortState {
  key: string
  dir: 'asc' | 'desc'
}

const alignClass: Record<Align, string> = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
}

function compare(a: unknown, b: unknown): number {
  const an = a == null || a === ''
  const bn = b == null || b === ''
  if (an && bn) return 0
  if (an) return -1
  if (bn) return 1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), 'es', { numeric: true })
}

export function DataTable<T extends object>({
  columns,
  rows,
  defaultSort,
  getRowKey,
  rowClassName,
  emptyMessage = 'No hay datos para mostrar.',
  footer,
}: {
  columns: ColumnDef<T>[]
  rows: T[]
  defaultSort?: SortState
  getRowKey?: (row: T, index: number) => string | number
  rowClassName?: (row: T) => string
  emptyMessage?: string
  footer?: ReactNode
}) {
  const [sort, setSort] = useState<SortState | null>(defaultSort ?? null)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = columns.find((c) => c.key === sort.key)
    if (!col) return rows
    const valueOf = (row: T) =>
      col.sortValue
        ? col.sortValue(row)
        : (row as Record<string, unknown>)[col.key]
    const out = [...rows].sort((a, b) => compare(valueOf(a), valueOf(b)))
    if (sort.dir === 'desc') out.reverse()
    return out
  }, [rows, sort, columns])

  function toggleSort(key: string) {
    setSort((prev) => {
      if (prev?.key === key) {
        return { key, dir: prev.dir === 'desc' ? 'asc' : 'desc' }
      }
      return { key, dir: 'desc' }
    })
  }

  return (
    <div className="overflow-hidden rounded-[var(--radius-card-lg)] border border-border-subtle bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((col) => {
              const active = sort?.key === col.key
              return (
                <TableHead
                  key={col.key}
                  className={cn(col.align && alignClass[col.align])}
                >
                  {col.sortable ? (
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      className={cn(
                        'inline-flex items-center gap-1 font-semibold text-txt2 transition-colors hover:text-txt',
                        col.align === 'right' && 'flex-row-reverse',
                        active && 'text-txt',
                      )}
                    >
                      {col.header}
                      {active ? (
                        sort?.dir === 'desc' ? (
                          <ArrowDown className="size-3" />
                        ) : (
                          <ArrowUp className="size-3" />
                        )
                      ) : (
                        <ChevronsUpDown className="size-3 text-txt3" />
                      )}
                    </button>
                  ) : (
                    col.header
                  )}
                </TableHead>
              )
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={columns.length}
                className="py-10 text-center text-sm text-txt2"
              >
                {emptyMessage}
              </TableCell>
            </TableRow>
          ) : (
            sorted.map((row, i) => (
              <TableRow
                key={getRowKey ? getRowKey(row, i) : i}
                className={rowClassName?.(row)}
              >
                {columns.map((col) => {
                  const extra =
                    typeof col.cellClassName === 'function'
                      ? col.cellClassName(row)
                      : col.cellClassName
                  return (
                    <TableCell
                      key={col.key}
                      className={cn(
                        col.align && alignClass[col.align],
                        extra,
                      )}
                    >
                      {col.render
                        ? col.render(row)
                        : String(
                            (row as Record<string, unknown>)[col.key] ?? '—',
                          )}
                    </TableCell>
                  )
                })}
              </TableRow>
            ))
          )}
        </TableBody>
        {footer}
      </Table>
    </div>
  )
}
