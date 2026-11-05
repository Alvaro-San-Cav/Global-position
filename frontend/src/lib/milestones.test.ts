import { describe, expect, it } from 'vitest'
import { computeStage, fmtDuration, monthsToTarget } from './milestones'

describe('computeStage', () => {
  it('sin patrimonio: sin hito alcanzado, siguiente 1.000', () => {
    const s = computeStage(0)
    expect(s.reached).toBeNull()
    expect(s.next?.value).toBe(1000)
    expect(s.pctToNext).toBe(0)
    expect(s.remaining).toBe(1000)
  })

  it('NaN y null se tratan como 0', () => {
    expect(computeStage(NaN).next?.value).toBe(1000)
    expect(computeStage(null).next?.value).toBe(1000)
  })

  it('entre hitos calcula el progreso relativo', () => {
    const s = computeStage(30_000) // entre 25k y 50k
    expect(s.reached?.value).toBe(25_000)
    expect(s.next?.value).toBe(50_000)
    expect(s.pctToNext).toBeCloseTo(20, 5)
    expect(s.remaining).toBe(20_000)
  })

  it('exactamente en un hito cuenta como alcanzado', () => {
    const s = computeStage(100_000)
    expect(s.reached?.value).toBe(100_000)
    expect(s.next?.value).toBe(250_000)
    expect(s.pctToNext).toBe(0)
  })

  it('superado el millón no hay siguiente', () => {
    const s = computeStage(1_200_000)
    expect(s.reached?.value).toBe(1_000_000)
    expect(s.next).toBeNull()
    expect(s.pctToNext).toBe(100)
  })
})

describe('monthsToTarget', () => {
  it('ya alcanzado -> 0', () => {
    expect(monthsToTarget(2000, 100, 5, 1000)).toBe(0)
  })

  it('sin rentabilidad es lineal', () => {
    expect(monthsToTarget(0, 100, 0, 1000)).toBe(10)
  })

  it('con rentabilidad tarda menos que sin ella', () => {
    const sin = monthsToTarget(10_000, 500, 0, 100_000) as number
    const con = monthsToTarget(10_000, 500, 7, 100_000) as number
    expect(con).toBeLessThan(sin)
  })

  it('sin aportación ni rentabilidad no llega nunca', () => {
    expect(monthsToTarget(1000, 0, 0, 5000)).toBeNull()
  })

  it('entradas no finitas -> null', () => {
    expect(monthsToTarget(NaN, 100, 5, 1000)).toBeNull()
  })
})

describe('fmtDuration', () => {
  it('formatea años y meses', () => {
    expect(fmtDuration(0)).toBe('ya alcanzado')
    expect(fmtDuration(1)).toBe('1 mes')
    expect(fmtDuration(12)).toBe('1 año')
    expect(fmtDuration(27)).toBe('2 años y 3 meses')
    expect(fmtDuration(null)).toBe('más de 80 años')
  })
})
