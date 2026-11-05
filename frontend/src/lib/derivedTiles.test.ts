import { describe, it, expect } from 'vitest'
import { computeDerivedTiles, symbolMatches } from './derivedTiles'
import type { AssetSlice, ClassSlice, Metrics } from '@/api/types'

const metrics = { valor_actual_acciones: 1000, valor_actual_crypto: 500 } as Metrics

describe('symbolMatches', () => {
  it('matches exact and market suffix only', () => {
    expect(symbolMatches('SAP', 'SAP')).toBe(true)
    expect(symbolMatches('sap.de', 'SAP')).toBe(true)
    expect(symbolMatches('SAPPHIRE', 'SAP')).toBe(false)
    expect(symbolMatches('SAPR', 'SAP')).toBe(false)
    expect(symbolMatches(null, 'SAP')).toBe(false)
  })
})

describe('computeDerivedTiles', () => {
  const full: AssetSlice[] = [
    { name: 'SAP SE', symbol: 'SAP.DE', value: 200 },
    { name: 'Sapphire', symbol: 'SAPPHIRE', value: 50 },
    { name: 'Apple', symbol: 'AAPL', value: 750 },
  ]

  it('excludes only SAP and its market suffix', () => {
    const [tile] = computeDerivedTiles(metrics, full)
    expect(tile.value).toBe(800)
  })

  it('filters candidates by class when classes are given', () => {
    const classes: ClassSlice[] = [
      { name: 'Acciones', value: 950, pct: 90, members: [full[0], full[2]] },
      { name: 'Cripto', value: 50, pct: 10, members: [full[1]] },
    ]
    const [tile] = computeDerivedTiles(metrics, [...full, { name: 'SAP', symbol: 'SAP', value: 999 }], classes)
    // SAP (999) is not a member of any acciones class -> ignored; SAP.DE excluded.
    expect(tile.value).toBe(800)
  })

  it('returns null value without base metric', () => {
    const [tile] = computeDerivedTiles(null, full)
    expect(tile.value).toBeNull()
  })
})
