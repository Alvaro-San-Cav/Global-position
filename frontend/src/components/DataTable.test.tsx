import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { DataTable, type ColumnDef } from './DataTable'

interface Row {
  ticker: string
  value: number
}

const rows: Row[] = [
  { ticker: 'AAPL', value: 300 },
  { ticker: 'NVDA', value: 100 },
  { ticker: 'MSFT', value: 200 },
]

const columns: ColumnDef<Row>[] = [
  { key: 'ticker', header: 'Ticker', render: (r) => r.ticker, sortable: true },
  {
    key: 'value',
    header: 'Valor',
    render: (r) => String(r.value),
    sortValue: (r) => r.value,
    sortable: true,
  },
]

function bodyOrder(): string[] {
  const table = screen.getByRole('table')
  const bodyRows = within(table).getAllByRole('row').slice(1) // skip header
  return bodyRows.map((tr) => within(tr).getAllByRole('cell')[0].textContent ?? '')
}

describe('DataTable', () => {
  it('renders all rows', () => {
    render(<DataTable columns={columns} rows={rows} />)
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('NVDA')).toBeInTheDocument()
    expect(screen.getByText('MSFT')).toBeInTheDocument()
  })

  it('sorts by value descending then ascending on header clicks', () => {
    render(<DataTable columns={columns} rows={rows} />)
    const valueHeader = screen.getByText('Valor')
    fireEvent.click(valueHeader) // desc → 300,200,100
    expect(bodyOrder()).toEqual(['AAPL', 'MSFT', 'NVDA'])
    fireEvent.click(valueHeader) // asc → 100,200,300
    expect(bodyOrder()).toEqual(['NVDA', 'MSFT', 'AAPL'])
  })

  it('shows empty message when no rows', () => {
    render(<DataTable columns={columns} rows={[]} emptyMessage="Vacío" />)
    expect(screen.getByText('Vacío')).toBeInTheDocument()
  })
})
