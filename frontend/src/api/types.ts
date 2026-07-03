/**
 * Domain types mirroring backend/src/api_models.py.
 * Hand-written (source of truth for components). The generated
 * schema.d.ts (pnpm gen:api) is kept alongside as an OpenAPI cross-check.
 */

export interface XY {
  x: string
  y: number
}

export interface Metrics {
  fecha_actual?: string | null
  dias_totales?: number | null
  anhos_totales?: number | null
  capital_total?: number | null
  valor_total?: number | null
  plusvalia_total?: number | null
  rentabilidad_total?: number | null
  cagr_total?: number | null
  twr_total_total?: number | null
  twr_total_anual?: number | null
  capital_aportado_acciones?: number | null
  valor_actual_acciones?: number | null
  plusvalia_acciones?: number | null
  rentabilidad_acciones?: number | null
  cagr_acciones?: number | null
  twr_acciones_total?: number | null
  twr_acciones_anual?: number | null
  peso_acciones?: number | null
  capital_aportado_crypto?: number | null
  valor_actual_crypto?: number | null
  plusvalia_crypto?: number | null
  rentabilidad_crypto?: number | null
  cagr_crypto?: number | null
  twr_cripto_total?: number | null
  twr_cripto_anual?: number | null
  peso_crypto?: number | null
  benchmark_ticker?: string | null
  benchmark_name?: string | null
  benchmark_total?: number | null
  benchmark_annual?: number | null
  [key: string]: number | string | null | undefined
}

export interface AssetSlice {
  name: string
  symbol: string
  value: number
}

export interface CryptoSlice extends AssetSlice {
  pct: number
}

export interface ClassSlice {
  name: string
  value: number
  pct: number
  members: AssetSlice[]
}

export interface AssetClassItem {
  symbol: string
  name: string
  auto: string
  override?: string | null
  effective: string
  kind: 'stock' | 'crypto'
}

export interface AssetClassesResponse {
  known_classes: string[]
  items: AssetClassItem[]
}

export interface CorrelationAsset {
  name: string
  symbol: string
  weight: number
}

export interface CorrelationPair {
  asset_1: string
  asset_2: string
  corr: number
}

export interface Correlation {
  threshold_pct: number
  assets: CorrelationAsset[]
  matrix: { labels: string[]; values: (number | null)[][] }
  top_positive: CorrelationPair[]
  top_negative: CorrelationPair[]
  history_days: number
  note: string
}

export interface PortfolioChart {
  value: XY[]
  invested: XY[]
  benchmark?: XY[] | null
}

export interface CryptoChart {
  value: XY[]
  invested: XY[]
}

export interface DashboardResponse {
  error?: string | null
  metrics?: Metrics | null
  has_crypto?: boolean | null
  portfolio_chart?: PortfolioChart | null
  composition?: AssetSlice[] | null
  composition_full?: AssetSlice[] | null
  portfolio_total_value?: number | null
  top_assets?: AssetSlice[] | null
  class_breakdown?: ClassSlice[] | null
  correlation?: Correlation | null
  crypto_chart?: CryptoChart | null
  crypto_breakdown?: CryptoSlice[] | null
  crypto_total_value?: number | null
  failed_tickers?: string[] | null
}

export interface Operation {
  Date: string
  Product?: string | null
  ticker?: string | null
  ISIN?: string | null
  Quantity?: number | null
  Price?: number | null
  Coin?: string | null
  Value?: number | null
}

export interface OperationCreate {
  Date: string
  Product: string
  ISIN: string
  Quantity: number
  Price: number
  Coin?: string
  ticker?: string
  Value?: number | null
}

export interface CryptoOperation {
  Date: string
  Product?: string | null
  Coin?: string | null
  Quantity?: number | null
  ticker?: string | null
  [key: string]: string | number | null | undefined
}

export interface CryptoOperationCreate {
  Date: string
  Coin: string
  Quantity: number
  Product?: string
  ticker?: string
}

export interface TaxResponse {
  gains: Record<string, unknown>[]
  annual: Record<string, unknown>[]
  by_ticker: Record<string, unknown>[]
}

export interface SourceFileInfo {
  file: string
  source: string
  enabled: boolean
}

export interface SourceDataEntry {
  date: string
  quantity: number
  price: number
  value: number
}

export interface SourceData {
  source: string
  file: string
  ticker?: string | null
  product?: string | null
  coin?: string | null
  total_qty?: number | null
  total_value?: number | null
  entries: SourceDataEntry[]
  error?: string | null
}

export interface ProcessResult {
  ok: boolean
  stock_added: number
  crypto_added: number
  files: string[]
  message: string
}

export interface ReportResult {
  ok: boolean
  file?: string | null
  message: string
}

/** sources.json shape (loose — the raw JSON editor handles unknown keys). */
export type SourcesConfig = Record<string, unknown>
