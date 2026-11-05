import { useMemo } from 'react'
import { AlertTriangle, PackageOpen } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useCash, useDashboard, useRebalance } from '@/api/queries'
import { fmtDate, fmtEur } from '@/lib/format'
import { computeDerivedTiles } from '@/lib/derivedTiles'
import { KpiGrid } from '@/components/dashboard/KpiGrid'
import { CapitalDelta } from '@/components/dashboard/CapitalDelta'
import { ClassBreakdown } from '@/components/dashboard/ClassBreakdown'
import { CryptoSection } from '@/components/dashboard/CryptoSection'
import { DashboardToolbar } from '@/components/dashboard/DashboardToolbar'
import { PortfolioChart } from '@/components/charts/PortfolioChart'
import { CompositionDonut } from '@/components/charts/CompositionDonut'
import { CorrelationHeatmap } from '@/components/charts/CorrelationHeatmap'

function LoadingState() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-[380px]" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Skeleton className="h-[320px]" />
        <Skeleton className="h-[320px]" />
      </div>
      <Skeleton className="h-[300px]" />
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <Card className="p-10 text-center">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-card2 text-txt2">
        <PackageOpen className="h-6 w-6" />
      </div>
      <div className="text-base font-semibold text-txt">Sin datos de cartera</div>
      <div className="mx-auto mt-1 max-w-md text-sm text-txt2">{message}</div>
      <div className="mt-4 text-sm text-txt2">
        Ve a{' '}
        <Link to="/importar" className="font-medium text-accent hover:underline">
          Importar
        </Link>{' '}
        para cargar tus operaciones.
      </div>
    </Card>
  )
}

export function Dashboard() {
  const { data, isLoading, isError, error } = useDashboard()
  const { data: cash } = useCash()
  const { data: rebalance } = useRebalance()

  // Prefer the fast /api/cash figure so edits reflect instantly; net worth is
  // computed client-side (invested value + cash) without waiting for the
  // slower dashboard price rebuild.
  const cashTotal = cash?.total_eur ?? data?.cash_total ?? 0
  const netWorth = (data?.portfolio_total_value ?? 0) + cashTotal

  // Merge cash into the class breakdown on the client so it appears instantly
  // when edited (the backend version only refreshes on a full price rebuild).
  // Percentages are recomputed over the invested total + cash.
  const classBreakdown = useMemo(() => {
    const base = (data?.class_breakdown ?? []).filter((c) => c.name !== 'Efectivo')
    const invested = base.reduce((a, c) => a + c.value, 0)
    const grand = invested + cashTotal
    if (grand <= 0) return base
    const out = base.map((c) => ({ ...c, pct: (c.value / grand) * 100 }))
    if (cashTotal > 0) {
      out.push({
        name: 'Efectivo',
        value: cashTotal,
        pct: (cashTotal / grand) * 100,
        members: (cash?.balances ?? []).map((b) => ({
          name: `Efectivo ${b.currency}`,
          symbol: b.currency,
          value: b.eur,
        })),
      })
    }
    return out.sort((a, b) => b.value - a.value)
  }, [data?.class_breakdown, cash?.balances, cashTotal])

  // Include cash as an "Efectivo" slice in the composition donut so the
  // percentages are computed over the full portfolio (invested + cash).
  const compositionTotal = (data?.portfolio_total_value ?? 0) + cashTotal
  const compositionWithCash = useMemo(() => {
    const base = data?.composition ?? []
    if (cashTotal <= 0) return base
    return [...base, { name: 'Efectivo', symbol: '', value: cashTotal }]
  }, [data?.composition, cashTotal])
  const topAssetsWithCash = useMemo(() => {
    const base = data?.top_assets ?? []
    if (cashTotal <= 0) return base
    return [...base, { name: 'Efectivo', symbol: '', value: cashTotal }].sort(
      (a, b) => b.value - a.value,
    )
  }, [data?.top_assets, cashTotal])

  // Tiles derivadas configurables (ver lib/derivedTiles), p. ej. "Valor sin SAP".
  const derivedTiles = useMemo(
    () => computeDerivedTiles(data?.metrics, data?.composition_full, data?.class_breakdown),
    [data?.metrics, data?.composition_full, data?.class_breakdown],
  )

  const subtitle = data?.metrics?.fecha_actual
    ? `Análisis a ${fmtDate(data.metrics.fecha_actual)}`
    : 'Posición global de la cartera'

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle={subtitle}
        actions={<DashboardToolbar />}
      />

      {isLoading && <LoadingState />}

      {!isLoading && isError && (
        <EmptyState message={(error as Error)?.message || 'No se pudo cargar el dashboard.'} />
      )}

      {!isLoading && !isError && data?.error && <EmptyState message={data.error} />}

      {!isLoading && !isError && data && !data.error && data.metrics && (
        <div className="space-y-4">
          {data.failed_tickers && data.failed_tickers.length > 0 && (
            <div className="flex items-start gap-2 rounded-[var(--radius-card)] border border-amber/40 bg-amber-dim px-4 py-3 text-sm text-amber">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                Sin precio de mercado: {data.failed_tickers.join(', ')}
              </span>
            </div>
          )}

          <KpiGrid metrics={data.metrics} derivedTiles={derivedTiles} />

          {data.portfolio_chart && <CapitalDelta chart={data.portfolio_chart} />}

          {cashTotal > 0 && (
            <div className="flex flex-wrap items-center gap-x-10 gap-y-3 rounded-[var(--radius-card)] border border-accent2/40 bg-accent2/10 px-6 py-5">
              <div className="flex flex-col">
                <span className="text-xs uppercase tracking-wide text-txt2">
                  Efectivo
                </span>
                <span className="text-2xl font-semibold text-txt">{fmtEur(cashTotal)}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs uppercase tracking-wide text-txt2">
                  Patrimonio total (inversión + efectivo)
                </span>
                <span className="text-3xl font-bold text-accent2">{fmtEur(netWorth)}</span>
              </div>
            </div>
          )}

          {data.portfolio_chart && (
            <Card>
              <CardHeader>
                <CardTitle>
                  Valor de cartera vs capital invertido
                  {data.metrics.benchmark_ticker ? ' vs benchmark' : ''}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <PortfolioChart
                  data={data.portfolio_chart}
                  benchmarkName={data.metrics.benchmark_name}
                />
              </CardContent>
            </Card>
          )}

          {classBreakdown.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Desglose por clase de activo</CardTitle>
              </CardHeader>
              <CardContent>
                <ClassBreakdown classes={classBreakdown} rebalance={rebalance} />
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {compositionWithCash.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Composición actual</CardTitle>
                </CardHeader>
                <CardContent>
                  <CompositionDonut
                    composition={compositionWithCash}
                    topAssets={topAssetsWithCash}
                    totalValue={compositionTotal}
                  />
                </CardContent>
              </Card>
            )}

            {data.has_crypto && (
              <Card>
                <CardHeader>
                  <CardTitle>Evolución crypto</CardTitle>
                </CardHeader>
                <CardContent>
                  <CryptoSection
                    chart={data.crypto_chart}
                    breakdown={data.crypto_breakdown}
                  />
                </CardContent>
              </Card>
            )}
          </div>

          {data.correlation && (
            <Card>
              <CardHeader>
                <CardTitle>Matriz de correlación de retornos diarios</CardTitle>
              </CardHeader>
              <CardContent>
                <CorrelationHeatmap correlation={data.correlation} />
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
