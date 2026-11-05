import { describe, it, expect, vi } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'
import { invalidatePortfolio, qk, fingerprintQuery } from './queries'

function fakeQc() {
  const calls: unknown[][] = []
  const qc = {
    invalidateQueries: vi.fn((o: { queryKey: unknown[] }) => {
      calls.push([...o.queryKey])
    }),
  } as unknown as QueryClient
  return { qc, calls }
}

describe('invalidatePortfolio', () => {
  it('invalidates all derived queries', () => {
    const { qc, calls } = fakeQc()
    invalidatePortfolio(qc)
    for (const k of [qk.dashboard, qk.rebalance, qk.tax, qk.operations, qk.crypto, qk.cash]) {
      expect(calls).toContainEqual([...k])
    }
  })
  it('can skip the dashboard', () => {
    const { qc, calls } = fakeQc()
    invalidatePortfolio(qc, { dashboard: false })
    expect(calls).not.toContainEqual([...qk.dashboard])
    expect(calls).toContainEqual([...qk.rebalance])
  })
})

describe('fingerprintQuery', () => {
  it('builds an encoded query string or empty', () => {
    expect(fingerprintQuery('a b')).toBe('?fingerprint=a%20b')
    expect(fingerprintQuery(null)).toBe('')
    expect(fingerprintQuery(undefined)).toBe('')
  })
})
