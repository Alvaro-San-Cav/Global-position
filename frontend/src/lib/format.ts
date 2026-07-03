import { format, parseISO } from 'date-fns'

type Num = number | null | undefined

export function fmtEur(v: Num, dec = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('es-ES', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })
}

export function fmtPct(v: Num, dec = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${v.toLocaleString('es-ES', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })} %`
}

export function fmtNum(v: Num, dec = 2): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('es-ES', {
    minimumFractionDigits: 0,
    maximumFractionDigits: dec,
  })
}

/** "2026-07-03" or "2026-07-03 12:30" → "03/07/2026" (date part only). */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return format(parseISO(iso.slice(0, 10)), 'dd/MM/yyyy')
  } catch {
    return iso
  }
}

/** Colour token by sign, for gains/losses. */
export function signColor(v: Num): string {
  if (v == null) return 'text-txt2'
  return v >= 0 ? 'text-green' : 'text-red'
}

/**
 * Parse a human-typed amount into a number, tolerant of ES/EU and EN formats.
 * "7.248,83" → 7248.83 · "7,248.83" → 7248.83 · "1.000" → 1000 · "12,5" → 12.5
 *
 * Rule: when both separators appear, the LAST one is the decimal separator.
 * With a single "." and 3 trailing digits it is treated as a thousands
 * separator (ES convention, e.g. "1.000"); otherwise as decimal.
 */
export function parseAmount(raw: string | number | null | undefined): number {
  if (raw == null) return NaN
  if (typeof raw === 'number') return raw
  let s = raw.trim().replace(/[^\d.,-]/g, '')
  if (!s) return NaN

  const lastComma = s.lastIndexOf(',')
  const lastDot = s.lastIndexOf('.')
  let decimalSep: ',' | '.' | '' = ''

  if (lastComma >= 0 && lastDot >= 0) {
    decimalSep = lastComma > lastDot ? ',' : '.'
  } else if (lastComma >= 0) {
    decimalSep = s.indexOf(',') === lastComma ? ',' : '' // single → decimal, many → thousands
  } else if (lastDot >= 0) {
    const after = s.length - lastDot - 1
    const onlyOne = s.indexOf('.') === lastDot
    decimalSep = onlyOne && after > 0 && after <= 2 ? '.' : ''
  }

  if (decimalSep === ',') {
    s = s.replace(/\./g, '').replace(',', '.')
  } else if (decimalSep === '.') {
    s = s.replace(/,/g, '')
    const parts = s.split('.')
    const dec = parts.pop()
    s = parts.join('') + '.' + dec
  } else {
    s = s.replace(/[.,]/g, '')
  }

  return parseFloat(s)
}
