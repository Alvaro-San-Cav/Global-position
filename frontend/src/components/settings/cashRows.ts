import { parseAmount } from '@/lib/format'

export interface CashRow {
  currency: string
  amount: string
}

export interface CashRowError {
  currency?: string
  amount?: string
}

/** Amount formatted ES-style (decimal comma, no grouping) so parseAmount round-trips it. */
export function fmtAmountInput(n: number): string {
  return n.toLocaleString('es-ES', { maximumFractionDigits: 8, useGrouping: false })
}

/** Is this row going to delete an existing currency (amount empty or 0)? */
export function removesCurrency(row: CashRow, existing: Set<string>): boolean {
  const cur = row.currency.trim().toUpperCase()
  if (!cur || !existing.has(cur)) return false
  const raw = row.amount.trim()
  return raw === '' || parseAmount(raw) === 0
}

export interface CashValidation {
  balances: Record<string, number>
  errors: Record<number, CashRowError>
  /** Existing currencies that will be removed because amount is empty/0. */
  removed: string[]
}

/** Validate rows and build the balances payload. Invalid rows are never dropped silently. */
export function validateCashRows(rows: CashRow[], existing: Set<string>): CashValidation {
  const balances: Record<string, number> = {}
  const errors: Record<number, CashRowError> = {}
  const removed: string[] = []
  const seen = new Set<string>()

  rows.forEach((r, i) => {
    const cur = r.currency.trim().toUpperCase()
    const raw = r.amount.trim()
    if (!cur && !raw) return // blank row
    if (!cur) {
      errors[i] = { currency: 'Indica la divisa.' }
      return
    }
    if (seen.has(cur)) {
      errors[i] = { currency: 'Divisa duplicada.' }
      return
    }
    seen.add(cur)
    if (raw === '') {
      if (existing.has(cur)) removed.push(cur)
      return
    }
    const amt = parseAmount(raw)
    if (Number.isNaN(amt)) {
      errors[i] = { amount: 'Importe no válido.' }
      return
    }
    if (amt === 0) {
      if (existing.has(cur)) removed.push(cur)
      return
    }
    balances[cur] = amt
  })
  return { balances, errors, removed }
}
