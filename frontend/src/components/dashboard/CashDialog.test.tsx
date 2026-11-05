import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const saveMutate = vi.fn().mockResolvedValue({})
// Stable reference, like react-query's structural sharing.
const cashData = {
  balances: [{ currency: 'EUR', amount: 1234.567, eur: 1234.567 }],
  total_eur: 1234.567,
}
vi.mock('@/api/queries', () => ({
  useCash: () => ({ data: cashData }),
  useSaveCash: () => ({ mutateAsync: saveMutate, isPending: false }),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { CashDialog } from './CashDialog'

function open() {
  render(<CashDialog trigger={<button>abrir</button>} />)
  fireEvent.click(screen.getByText('abrir'))
}

describe('CashDialog', () => {
  beforeEach(() => vi.clearAllMocks())

  it('preloads ES-formatted amount and round-trips it without 1000x error', async () => {
    open()
    expect(screen.getByLabelText('Importe 1')).toHaveValue('1234,567')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(saveMutate).toHaveBeenCalledWith({ EUR: 1234.567 }))
  })

  it('does not save and flags the field when the amount is invalid', async () => {
    open()
    fireEvent.change(screen.getByLabelText('Importe 1'), { target: { value: 'abc' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Importe no válido')
    expect(saveMutate).not.toHaveBeenCalled()
  })

  it('warns that amount 0 removes an existing currency', () => {
    open()
    fireEvent.change(screen.getByLabelText('Importe 1'), { target: { value: '0' } })
    expect(screen.getByText(/se eliminará al guardar/)).toBeInTheDocument()
  })
})
