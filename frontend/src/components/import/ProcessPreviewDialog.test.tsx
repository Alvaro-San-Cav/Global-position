import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ProcessPreviewDialog } from './ProcessPreviewDialog'
import type { ProcessPreview } from '@/api/types'

const cryptoPreview: ProcessPreview = {
  total_new: 1,
  total_duplicates: 0,
  files: [
    {
      file: 'c.csv',
      kind: 'crypto',
      rows_read: 1,
      new: 1,
      duplicates: 0,
      entries: [{ date: '2026-01-01 10:00', coin: 'BTC', quantity: 1, ticker: 'BTC-EUR' }],
    },
  ],
}

const stockPreview: ProcessPreview = {
  total_new: 1,
  total_duplicates: 0,
  files: [
    {
      file: 's.csv',
      kind: 'stock',
      rows_read: 1,
      new: 1,
      duplicates: 0,
      entries: [
        { date: '2026-01-01', product: 'X', isin: 'DE1', quantity: 2, price: 10, coin: 'EUR', value: 20 },
      ],
    },
  ],
}

const confirmBtn = () => screen.getByRole('button', { name: /Confirmar y guardar/ })

describe('ProcessPreviewDialog', () => {
  it('parses ES decimals on confirm (crypto)', () => {
    const onConfirm = vi.fn()
    render(<ProcessPreviewDialog preview={cryptoPreview} onOpenChange={() => {}} onConfirm={onConfirm} />)
    fireEvent.change(screen.getByLabelText('Cantidad fila 1'), { target: { value: '1,5' } })
    fireEvent.click(confirmBtn())
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onConfirm.mock.calls[0][0][0].entries[0].quantity).toBe(1.5)
  })

  it('blocks confirm and flags the cell when a number is invalid', () => {
    const onConfirm = vi.fn()
    render(<ProcessPreviewDialog preview={stockPreview} onOpenChange={() => {}} onConfirm={onConfirm} />)
    fireEvent.change(screen.getByLabelText('Precio fila 1'), { target: { value: 'abc' } })
    expect(confirmBtn()).toBeDisabled()
    expect(screen.getByLabelText('Precio fila 1')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toBeInTheDocument()
    fireEvent.click(confirmBtn())
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('rejects empty or zero crypto quantity', () => {
    render(<ProcessPreviewDialog preview={cryptoPreview} onOpenChange={() => {}} onConfirm={() => {}} />)
    const q = screen.getByLabelText('Cantidad fila 1')
    fireEvent.change(q, { target: { value: '' } })
    expect(confirmBtn()).toBeDisabled()
    fireEvent.change(q, { target: { value: '0' } })
    expect(confirmBtn()).toBeDisabled()
    fireEvent.change(q, { target: { value: '0,5' } })
    expect(confirmBtn()).toBeEnabled()
  })

  it('allows empty optional stock numbers as null', () => {
    const onConfirm = vi.fn()
    render(<ProcessPreviewDialog preview={stockPreview} onOpenChange={() => {}} onConfirm={onConfirm} />)
    fireEvent.change(screen.getByLabelText('Valor fila 1'), { target: { value: '' } })
    fireEvent.click(confirmBtn())
    expect(onConfirm.mock.calls[0][0][0].entries[0].value).toBeNull()
  })
})
