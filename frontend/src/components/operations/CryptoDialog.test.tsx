import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const updateMutate = vi.fn().mockResolvedValue({})
const deleteMutate = vi.fn().mockResolvedValue({})
const addMutate = vi.fn().mockResolvedValue({})

vi.mock('@/api/queries', () => ({
  useAddCrypto: () => ({ mutateAsync: addMutate, isPending: false }),
  useUpdateCrypto: () => ({ mutateAsync: updateMutate, isPending: false }),
  useDeleteCrypto: () => ({ mutateAsync: deleteMutate, isPending: false }),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { CryptoDialog } from './CryptoDialog'

const op = {
  id: 3,
  fingerprint: 'abc123',
  Date: '2026-02-03 10:11:12',
  Coin: 'BTC',
  Quantity: 0.5,
  Product: 'Bitcoin',
  ticker: 'BTC-EUR',
}

function openEdit() {
  render(<CryptoDialog operation={op} />)
  fireEvent.click(screen.getByLabelText('Editar movimiento'))
}

describe('CryptoDialog (edit)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('prefills, keeps seconds and associates labels', () => {
    openEdit()
    expect((screen.getByLabelText('Fecha y hora *') as HTMLInputElement).value).toMatch(
      /^2026-02-03T10:11:12/,
    )
    expect(screen.getByLabelText('Coin *')).toHaveValue('BTC')
  })

  it('submits with Enter-style form submit and forwards fingerprint', async () => {
    openEdit()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(updateMutate).toHaveBeenCalled())
    const arg = updateMutate.mock.calls[0][0]
    expect(arg.id).toBe(3)
    expect(arg.fingerprint).toBe('abc123')
    expect(arg.body.Date).toBe('2026-02-03 10:11:12')
    expect(arg.body.ticker).toBe('BTC-EUR')
  })

  it('omits stale ticker when the coin changed', async () => {
    openEdit()
    fireEvent.change(screen.getByLabelText('Coin *'), { target: { value: 'eth' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(updateMutate).toHaveBeenCalled())
    const body = updateMutate.mock.calls[0][0].body
    expect(body.Coin).toBe('ETH')
    expect(body).not.toHaveProperty('ticker')
  })

  it('deletes with fingerprint after confirmation', async () => {
    openEdit()
    fireEvent.click(screen.getByRole('button', { name: /Eliminar/ }))
    fireEvent.click(screen.getByRole('button', { name: /Confirmar eliminación/ }))
    await waitFor(() => expect(deleteMutate).toHaveBeenCalledWith({ id: 3, fingerprint: 'abc123' }))
  })
})
