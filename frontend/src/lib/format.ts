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
