import { addMonths, subMonths } from 'date-fns'

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

export interface SeriesPoint {
  x: string
  y: number
}

/**
 * Aportación mensual media a partir de la serie de capital aportado.
 * `windowMonths` = ventana reciente (p. ej. 12); null = todo el histórico.
 * Si el histórico es más corto que la ventana se usa todo lo disponible.
 * Devuelve null si hay menos de ~1 mes de datos. Puede ser negativa (retiradas netas).
 */
export function avgMonthlyContribution(
  invested: SeriesPoint[] | null | undefined,
  windowMonths: number | null,
): number | null {
  const pts = (invested ?? [])
    .filter((p) => Number.isFinite(p.y) && !Number.isNaN(Date.parse(p.x)))
    .sort((a, b) => Date.parse(a.x) - Date.parse(b.x))
  if (pts.length < 2) return null
  const last = pts[pts.length - 1]
  let start = pts[0]
  if (windowMonths !== null) {
    const cutoff = subMonths(new Date(last.x), windowMonths).getTime()
    const inside = pts.filter((p) => Date.parse(p.x) <= cutoff)
    if (inside.length) start = inside[inside.length - 1]
  }
  const months = (Date.parse(last.x) - Date.parse(start.x)) / (1000 * 60 * 60 * 24 * 30.4375)
  if (months < 1) return null
  return (last.y - start.y) / months
}

/**
 * Rentabilidad anualizada implícita en las series de valor y capital aportado
 * (Dietz modificado con flujos a mitad de periodo), para que la proyección sea
 * coherente con lo que se ve en el gráfico. null si hay <1 mes de datos.
 */
export function impliedAnnualReturn(
  value: SeriesPoint[] | null | undefined,
  invested: SeriesPoint[] | null | undefined,
  windowMonths: number | null,
): number | null {
  const clean = (s: SeriesPoint[] | null | undefined) =>
    (s ?? [])
      .filter((p) => Number.isFinite(p.y) && !Number.isNaN(Date.parse(p.x)))
      .sort((a, b) => Date.parse(a.x) - Date.parse(b.x))
  const v = clean(value)
  const inv = clean(invested)
  if (v.length < 2 || inv.length < 2) return null
  const endT = Date.parse(v[v.length - 1].x)
  const at = (s: SeriesPoint[], t: number, fromEnd = false) => {
    let pick = fromEnd ? s[s.length - 1] : s[0]
    for (const p of s) if (Date.parse(p.x) <= t) pick = p
    return pick
  }
  let startT = Date.parse(v[0].x)
  if (windowMonths !== null) {
    const cutoff = subMonths(new Date(endT), windowMonths).getTime()
    const inside = v.filter((p) => Date.parse(p.x) <= cutoff)
    if (inside.length) startT = Date.parse(inside[inside.length - 1].x)
  }
  const months = (endT - startT) / (1000 * 60 * 60 * 24 * 30.4375)
  if (months < 1) return null
  const v0 = at(v, startT).y
  const v1 = v[v.length - 1].y
  const flows = at(inv, endT, true).y - at(inv, startT).y
  const base = v0 + flows / 2
  if (!(base > 0)) return null
  const r = (v1 - v0 - flows) / base
  if (r <= -1) return null
  return (Math.pow(1 + r, 12 / months) - 1) * 100
}

export interface ProjectionPoint {
  /** Fecha ISO (yyyy-MM-dd). */
  x: string
  /** Patrimonio proyectado. */
  proj: number
  /** Capital aportado proyectado (base + aportaciones futuras). */
  contrib: number
}

/**
 * Curva mensual de patrimonio proyectado desde `current` con aportación y
 * rentabilidad constantes. Corta al superar `target` o a los `maxYears`.
 * El primer punto es el estado actual (mes 0).
 */
export function projectionCurve(
  current: number,
  invested: number,
  monthly: number,
  annualReturnPct: number,
  from: Date,
  target = 1_000_000,
  maxYears = 40,
): ProjectionPoint[] {
  if (![current, invested, monthly, annualReturnPct].every(Number.isFinite)) return []
  const rate = Math.pow(1 + annualReturnPct / 100, 1 / 12) - 1
  const iso = (m: number) => addMonths(from, m).toISOString().slice(0, 10)
  const out: ProjectionPoint[] = [{ x: iso(0), proj: current, contrib: invested }]
  let v = current
  let c = invested
  for (let m = 1; m <= maxYears * 12; m++) {
    v = v * (1 + rate) + monthly
    c += monthly
    out.push({ x: iso(m), proj: v, contrib: c })
    if (v >= target) break
  }
  return out
}
