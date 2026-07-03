import { describe, it, expect } from 'vitest'
import { fmtEur, fmtPct, fmtNum, fmtDate, signColor, parseAmount } from './format'

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

describe('parseAmount', () => {
  it('parses ES format (dot thousands, comma decimal)', () => {
    expect(parseAmount('7.248,83')).toBe(7248.83)
    expect(parseAmount('1.234.567,89')).toBe(1234567.89)
    expect(parseAmount('12,5')).toBe(12.5)
  })
  it('parses EN format (comma thousands, dot decimal)', () => {
    expect(parseAmount('7,248.83')).toBe(7248.83)
    expect(parseAmount('1,000,000')).toBe(1000000)
    expect(parseAmount('1234.5')).toBe(1234.5)
  })
  it('treats a lone dot with 3 trailing digits as thousands (ES)', () => {
    expect(parseAmount('1.000')).toBe(1000)
    expect(parseAmount('1.000.000')).toBe(1000000)
  })
  it('handles plain numbers, currency symbols and negatives', () => {
    expect(parseAmount('1234')).toBe(1234)
    expect(parseAmount('€7.248,83')).toBe(7248.83)
    expect(parseAmount('-50,25')).toBe(-50.25)
    expect(parseAmount(4000)).toBe(4000)
  })
  it('returns NaN for empty/garbage', () => {
    expect(Number.isNaN(parseAmount(''))).toBe(true)
    expect(Number.isNaN(parseAmount(null))).toBe(true)
  })
})
