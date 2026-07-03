import { describe, it, expect } from 'vitest'
import { fmtEur, fmtPct, fmtNum, fmtDate, signColor } from './format'

describe('fmtEur', () => {
  it('formats euros in es-ES', () => {
    // Thousands separator is optional: jsdom's ICU may omit grouping.
    expect(fmtEur(1234.5)).toContain('€')
    expect(fmtEur(1234.5)).toMatch(/1\.?234,50/)
  })
  it('handles null/undefined/NaN', () => {
    expect(fmtEur(null)).toBe('—')
    expect(fmtEur(undefined)).toBe('—')
    expect(fmtEur(NaN)).toBe('—')
  })
  it('handles zero and negatives', () => {
    expect(fmtEur(0)).toContain('0,00')
    expect(fmtEur(-50)).toContain('-')
  })
})

describe('fmtPct', () => {
  it('appends % sign', () => {
    expect(fmtPct(12.345)).toBe('12,35 %')
  })
  it('handles null', () => {
    expect(fmtPct(null)).toBe('—')
  })
})

describe('fmtNum', () => {
  it('formats without currency', () => {
    expect(fmtNum(1000)).toMatch(/1\.?000/)
    expect(fmtNum(null)).toBe('—')
  })
})

describe('fmtDate', () => {
  it('formats ISO date to dd/MM/yyyy', () => {
    expect(fmtDate('2026-07-03')).toBe('03/07/2026')
  })
  it('trims datetime to date part', () => {
    expect(fmtDate('2026-07-03 12:30')).toBe('03/07/2026')
  })
  it('handles empty', () => {
    expect(fmtDate('')).toBe('—')
    expect(fmtDate(null)).toBe('—')
  })
})

describe('signColor', () => {
  it('green for >=0, red for <0', () => {
    expect(signColor(10)).toBe('text-green')
    expect(signColor(0)).toBe('text-green')
    expect(signColor(-1)).toBe('text-red')
    expect(signColor(null)).toBe('text-txt2')
  })
})
