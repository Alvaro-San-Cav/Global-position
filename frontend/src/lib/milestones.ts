/**
 * Hitos patrimoniales de 0 a 1 M€ y proyección simple al siguiente hito.
 * Las etapas y descripciones son orientativas (texto propio), no asesoramiento.
 */

export interface Milestone {
  value: number
  label: string
  stage: string
  focus: string
}

export const MILESTONES: Milestone[] = [
  {
    value: 1_000,
    label: '1.000 €',
    stage: 'Arranque',
    focus: 'Crear el hábito de ahorrar y un primer colchón. El mayor motor es la tasa de ahorro.',
  },
  {
    value: 10_000,
    label: '10.000 €',
    stage: 'Colchón y primeras inversiones',
    focus: 'Fondo de emergencia cubierto y primera cartera diversificada y barata.',
  },
  {
    value: 25_000,
    label: '25.000 €',
    stage: 'Hábito consolidado',
    focus: 'Aportaciones automáticas. Las caídas del mercado empiezan a notarse en euros.',
  },
  {
    value: 50_000,
    label: '50.000 €',
    stage: 'El interés compuesto se nota',
    focus: 'La rentabilidad anual ya puede igualar varios meses de aportación.',
  },
  {
    value: 100_000,
    label: '100.000 €',
    stage: 'Primer gran hito',
    focus: 'Las rentabilidades pesan más que las aportaciones. Importan comisiones y fiscalidad.',
  },
  {
    value: 250_000,
    label: '250.000 €',
    stage: 'Aceleración',
    focus: 'Un año normal de mercado puede aportar más que tu ahorro anual. Control del riesgo.',
  },
  {
    value: 500_000,
    label: '500.000 €',
    stage: 'Medio camino',
    focus: 'Rebalanceo y fiscalidad cobran peso. Conviene decidir riesgo y concentración.',
  },
  {
    value: 1_000_000,
    label: '1.000.000 €',
    stage: 'Millón',
    focus: 'Pasar de acumular a preservar y planificar la retirada de capital.',
  },
]

export interface StageInfo {
  /** Último hito alcanzado (null si aún no se llegó al primero). */
  reached: Milestone | null
  /** Siguiente hito (null si ya se superó el último). */
  next: Milestone | null
  /** Progreso 0..100 entre el hito anterior (o 0) y el siguiente. */
  pctToNext: number
  /** Cuánto falta para el siguiente hito, en €. */
  remaining: number
}

export function computeStage(netWorth: number | null | undefined): StageInfo {
  const nw = Number.isFinite(netWorth) ? Math.max(0, netWorth as number) : 0
  let reached: Milestone | null = null
  let next: Milestone | null = null
  for (const m of MILESTONES) {
    if (nw >= m.value) reached = m
    else {
      next = m
      break
    }
  }
  if (!next) return { reached, next: null, pctToNext: 100, remaining: 0 }
  const from = reached?.value ?? 0
  const pctToNext = ((nw - from) / (next.value - from)) * 100
  return { reached, next, pctToNext, remaining: next.value - nw }
}

/**
 * Meses hasta alcanzar `target` capitalizando mensualmente.
 * Devuelve 0 si ya se alcanzó y null si no se alcanza en `maxYears`.
 */
export function monthsToTarget(
  current: number,
  monthlyContribution: number,
  annualReturnPct: number,
  target: number,
  maxYears = 80,
): number | null {
  if (![current, monthlyContribution, annualReturnPct, target].every(Number.isFinite)) return null
  if (current >= target) return 0
  const monthlyRate = Math.pow(1 + annualReturnPct / 100, 1 / 12) - 1
  let value = current
  const maxMonths = maxYears * 12
  for (let m = 1; m <= maxMonths; m++) {
    value = value * (1 + monthlyRate) + monthlyContribution
    if (value >= target) return m
  }
  return null
}

export function fmtDuration(months: number | null): string {
  if (months === null) return 'más de 80 años'
  if (months === 0) return 'ya alcanzado'
  const y = Math.floor(months / 12)
  const m = months % 12
  const parts: string[] = []
  if (y > 0) parts.push(`${y} ${y === 1 ? 'año' : 'años'}`)
  if (m > 0) parts.push(`${m} ${m === 1 ? 'mes' : 'meses'}`)
  return parts.join(' y ')
}
