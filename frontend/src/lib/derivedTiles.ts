import type { AssetSlice, ClassSlice, Metrics } from '@/api/types'
import { fmtEur } from '@/lib/format'

/**
 * Tiles derivadas configurables: parten de una métrica base (p. ej. el valor
 * actual de acciones) y le restan el valor de los activos cuyo símbolo coincide
 * con alguno de `excludeSymbols` (igualdad exacta o con sufijo de mercado:
 * «SAP» casa con SAP y SAP.DE, pero no con SAPPHIRE). Sirven para montar vistas personales del
 * estilo "valor de acciones sin SAP" sin tocar los componentes.
 *
 * Para añadir otra tile, mete una entrada más en DERIVED_TILES.
 */
export interface DerivedTileConfig {
  /** Etiqueta mostrada en la tile. */
  label: string
  /** Métrica base de la que se resta. */
  base: 'acciones' | 'crypto' | 'total'
  /** Símbolos (exactos o con sufijo de mercado «.XX», case-insensitive) a excluir. */
  excludeSymbols: string[]
  /** Clase de color del valor (por defecto text-accent). */
  valueClass?: string
  /**
   * Texto del tooltip (?). Si se omite, se genera dinámicamente a partir de
   * `base`, `excludeSymbols` y el importe realmente excluido.
   */
  info?: string
}

/** Config personal — edítala para montar otras tiles parecidas. */
export const DERIVED_TILES: DerivedTileConfig[] = [
  {
    label: 'Valor sin SAP',
    base: 'acciones',
    excludeSymbols: ['SAP'],
    valueClass: 'text-accent',
  },
]

const BASE_METRIC: Record<DerivedTileConfig['base'], keyof Metrics> = {
  acciones: 'valor_actual_acciones',
  crypto: 'valor_actual_crypto',
  total: 'valor_total',
}

const BASE_LABEL: Record<DerivedTileConfig['base'], string> = {
  acciones: 'acciones',
  crypto: 'cripto',
  total: 'la cartera',
}

/** Construye el texto del tooltip en función de la config y el importe excluido. */
function buildInfo(t: DerivedTileConfig, excluded: number): string {
  const syms = t.excludeSymbols.join(', ')
  const plural = t.excludeSymbols.length > 1
  return (
    `Valor de mercado de ${BASE_LABEL[t.base]} excluyendo las posiciones ` +
    `cuyo símbolo es ${syms} (−${fmtEur(excluded)} ` +
    `en ${plural ? 'esos activos' : 'ese activo'}).`
  )
}

export interface DerivedTileValue {
  label: string
  base: DerivedTileConfig['base']
  value: number | null
  valueClass: string
  info?: string
}

/** ¿El símbolo coincide exactamente o con sufijo de mercado (SAP, SAP.DE)? */
export function symbolMatches(symbol: string | null | undefined, target: string): boolean {
  const sym = (symbol ?? '').trim().toUpperCase()
  const t = target.trim().toUpperCase()
  if (!sym || !t) return false
  return sym === t || sym.startsWith(`${t}.`)
}

const CRYPTO_CLASS = 'Cripto'
const NON_STOCK_CLASSES = new Set([CRYPTO_CLASS, 'Efectivo'])

/** Resuelve el valor de cada tile derivada a partir de metrics + composition_full. */
export function computeDerivedTiles(
  metrics: Metrics | null | undefined,
  compositionFull: AssetSlice[] | null | undefined,
  /** Desglose por clase (opcional): permite filtrar los activos según `base`. */
  classes?: ClassSlice[] | null,
): DerivedTileValue[] {
  const full = compositionFull ?? []
  return DERIVED_TILES.map((t) => {
    let candidates = full
    if (classes && classes.length > 0 && t.base !== 'total') {
      const allowed = new Set<string>()
      for (const c of classes) {
        const isCrypto = c.name === CRYPTO_CLASS
        const keep = t.base === 'crypto' ? isCrypto : !NON_STOCK_CLASSES.has(c.name)
        if (keep) for (const m of c.members) allowed.add(m.symbol.toUpperCase())
      }
      candidates = full.filter((a) => allowed.has((a.symbol ?? '').toUpperCase()))
    }
    const base = metrics?.[BASE_METRIC[t.base]]
    const baseNum = typeof base === 'number' ? base : null
    const excluded = candidates
      .filter((a) => t.excludeSymbols.some((p) => symbolMatches(a.symbol, p)))
      .reduce((s, a) => s + a.value, 0)
    const info = t.info ?? buildInfo(t, excluded)
    if (baseNum == null) {
      return { label: t.label, base: t.base, value: null, valueClass: t.valueClass ?? 'text-accent', info }
    }
    return {
      label: t.label,
      base: t.base,
      value: baseNum - excluded,
      valueClass: t.valueClass ?? 'text-accent',
      info,
    }
  })
}
