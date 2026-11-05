import { describe, expect, it } from 'vitest'
import {
  avgMonthlyContribution,
  computeStage,
  fmtDuration,
  impliedAnnualReturn,
  monthsToTarget,
  projectionCurve,
} from './milestones'

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

describe('impliedAnnualReturn', () => {
  const mk = (n: number, f: (i: number) => number) =>
    Array.from({ length: n }, (_, i) => ({
      x: new Date(Date.UTC(2024, 0, 1) + i * 30.4375 * 86400000).toISOString().slice(0, 10),
      y: f(i),
    }))

  it('sin rentabilidad ni aportaciones -> 0', () => {
    const v = mk(13, () => 1000)
    expect(impliedAnnualReturn(v, v, null)).toBeCloseTo(0, 5)
  })

  it('las aportaciones no cuentan como rentabilidad', () => {
    const inv = mk(13, (i) => 1000 + i * 100)
    expect(impliedAnnualReturn(inv, inv, null)).toBeCloseTo(0, 5)
  })

  it('un 10 % de ganancia en un año ≈ 10 % anual', () => {
    const v = mk(13, (i) => 1000 * (1 + (0.1 * i) / 12))
    const inv = mk(13, () => 1000)
    expect(impliedAnnualReturn(v, inv, null)).toBeCloseTo(10, 0)
  })

  it('pocos datos -> null', () => {
    expect(impliedAnnualReturn(null, null, 12)).toBeNull()
    expect(impliedAnnualReturn(mk(1, () => 1), mk(1, () => 1), 12)).toBeNull()
  })
})

describe('projectionCurve', () => {
  const from = new Date(Date.UTC(2026, 0, 1))

  it('empieza en el estado actual y es lineal sin rentabilidad', () => {
    const c = projectionCurve(1000, 800, 100, 0, from, 1500)
    expect(c[0]).toMatchObject({ proj: 1000, contrib: 800 })
    expect(c[c.length - 1].proj).toBe(1500)
    expect(c.length).toBe(6)
    expect(c[5].contrib).toBe(1300)
  })

  it('coincide con monthsToTarget', () => {
    const c = projectionCurve(10_000, 8_000, 500, 7, from, 100_000)
    expect(c.length - 1).toBe(monthsToTarget(10_000, 500, 7, 100_000))
  })

  it('entradas no finitas -> vacío', () => {
    expect(projectionCurve(NaN, 0, 1, 1, from)).toEqual([])
  })

  it('sin crecimiento corta en el máximo de años', () => {
    expect(projectionCurve(1000, 1000, 0, 0, from, 1_000_000, 2).length).toBe(25)
  })
})

describe('avgMonthlyContribution', () => {
  // 100 €/mes durante 24 meses (puntos mensuales ~ 30,4375 días)
  const series = Array.from({ length: 25 }, (_, i) => ({
    x: new Date(Date.UTC(2024, 0, 1) + i * 30.4375 * 86400000).toISOString().slice(0, 10),
    y: i * 100,
  }))

  it('histórico completo', () => {
    expect(avgMonthlyContribution(series, null)).toBeCloseTo(100, 0)
  })

  it('ventana reciente de 12 meses', () => {
    expect(avgMonthlyContribution(series, 12)).toBeCloseTo(100, 0)
  })

  it('la ventana capta un cambio de ritmo reciente', () => {
    const fast = series.map((p, i) => ({ ...p, y: i <= 12 ? i * 100 : 1200 + (i - 12) * 300 }))
    const recent = avgMonthlyContribution(fast, 12) as number
    const total = avgMonthlyContribution(fast, null) as number
    expect(recent).toBeGreaterThan(total)
  })

  it('ventana mayor que el histórico usa todo lo disponible', () => {
    expect(avgMonthlyContribution(series, 60)).toBeCloseTo(100, 0)
  })

  it('pocos datos o entradas vacías -> null', () => {
    expect(avgMonthlyContribution(null, 12)).toBeNull()
    expect(avgMonthlyContribution([{ x: '2025-01-01', y: 1 }], 12)).toBeNull()
    expect(
      avgMonthlyContribution(
        [
          { x: '2025-01-01', y: 0 },
          { x: '2025-01-10', y: 50 },
        ],
        null,
      ),
    ).toBeNull()
  })
})
