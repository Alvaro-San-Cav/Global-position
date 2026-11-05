import {
  useQuery,
  useMutation,
  useQueryClient,
  type QueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query'
import { apiGet, apiPost, apiPut, apiDelete, apiUpload } from './client'
import type {
  AssetClassesResponse,
  CashResponse,
  CryptoOperation,
  CryptoOperationCreate,
  DashboardResponse,
  Operation,
  OperationCreate,
  ProcessCommit,
  ProcessPreview,
  ProcessResult,
  RebalanceResponse,
  ReportResult,
  SourceData,
  SourceFileContent,
  SourceFileInfo,
  SourcesConfig,
  TargetConfig,
  TaxResponse,
} from './types'

export const qk = {
  dashboard: ['dashboard'] as const,
  operations: ['operations'] as const,
  crypto: ['crypto'] as const,
  tax: ['tax'] as const,
  sources: ['sources'] as const,
  assetClasses: ['asset-classes'] as const,
  cash: ['cash'] as const,
  pending: ['pending-files'] as const,
  sourceFiles: ['source-files'] as const,
  sourceData: ['source-data'] as const,
  target: ['target'] as const,
  rebalance: ['rebalance'] as const,
}

/**
 * Invalidate every query derived from portfolio data (operations, crypto,
 * cash, sources, process...). Call after ANY mutation that may change them.
 * Pass `{ dashboard: false }` when the dashboard cache was already set.
 */
export function invalidatePortfolio(
  qc: QueryClient,
  opts: { dashboard?: boolean } = {},
) {
  const keys = [
    qk.rebalance,
    qk.tax,
    qk.operations,
    qk.crypto,
    qk.cash,
    qk.sourceData,
    ...(opts.dashboard === false ? [] : [qk.dashboard]),
  ]
  for (const queryKey of keys) qc.invalidateQueries({ queryKey })
}

export function fingerprintQuery(fp: string | null | undefined): string {
  return fp ? `?fingerprint=${encodeURIComponent(fp)}` : ''
}

// ── Queries ────────────────────────────────────────────────────────────

export function useDashboard(
  opts?: Partial<UseQueryOptions<DashboardResponse>>,
) {
  return useQuery<DashboardResponse>({
    queryKey: qk.dashboard,
    queryFn: () => apiGet<DashboardResponse>('/api/dashboard'),
    staleTime: 5 * 60 * 1000,
    ...opts,
  })
}

export function useOperations() {
  return useQuery<Operation[]>({
    queryKey: qk.operations,
    queryFn: () => apiGet<Operation[]>('/api/operations'),
  })
}

export function useCrypto() {
  return useQuery<CryptoOperation[]>({
    queryKey: qk.crypto,
    queryFn: () => apiGet<CryptoOperation[]>('/api/crypto'),
  })
}

export function useTax() {
  return useQuery<TaxResponse>({
    queryKey: qk.tax,
    queryFn: () => apiGet<TaxResponse>('/api/tax'),
    staleTime: 10 * 60 * 1000,
  })
}

export function useSources() {
  return useQuery<SourcesConfig>({
    queryKey: qk.sources,
    queryFn: () => apiGet<SourcesConfig>('/api/sources'),
  })
}

export function useAssetClasses() {
  return useQuery<AssetClassesResponse>({
    queryKey: qk.assetClasses,
    queryFn: () => apiGet<AssetClassesResponse>('/api/asset-classes'),
  })
}

export function useCash() {
  return useQuery<CashResponse>({
    queryKey: qk.cash,
    queryFn: () => apiGet<CashResponse>('/api/cash'),
  })
}

export function useSaveCash() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (balances: Record<string, number>) =>
      apiPost<CashResponse>('/api/cash', { balances }),
    onSuccess: () => invalidatePortfolio(qc),
  })
}

export function usePendingFiles() {
  return useQuery<string[]>({
    queryKey: qk.pending,
    queryFn: () => apiGet<string[]>('/api/pending-files'),
  })
}

export function useSourceFiles() {
  return useQuery<SourceFileInfo[]>({
    queryKey: qk.sourceFiles,
    queryFn: () => apiGet<SourceFileInfo[]>('/api/source-files'),
  })
}

export function useSourceData() {
  return useQuery<SourceData[]>({
    queryKey: qk.sourceData,
    queryFn: () => apiGet<SourceData[]>('/api/source-data'),
  })
}

/** Raw CSV contents of a configured source file (enabled only when a name is set). */
export function useSourceFile(filename: string | null) {
  return useQuery<SourceFileContent>({
    queryKey: ['source-file', filename],
    queryFn: () =>
      apiGet<SourceFileContent>(`/api/source-file/${encodeURIComponent(filename as string)}`),
    enabled: filename !== null,
    staleTime: 0,
  })
}

export function useSaveSourceFile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SourceFileContent) =>
      apiPut<SourceFileContent>(
        `/api/source-file/${encodeURIComponent(body.file)}`,
        body,
      ),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['source-file', data.file] })
      qc.invalidateQueries({ queryKey: qk.sourceFiles })
      invalidatePortfolio(qc)
    },
  })
}

// ── Cartera objetivo (target portfolio) ──────────────────────────────────

export function useTarget() {
  return useQuery<TargetConfig>({
    queryKey: qk.target,
    queryFn: () => apiGet<TargetConfig>('/api/target'),
  })
}

export function useRebalance() {
  return useQuery<RebalanceResponse>({
    queryKey: qk.rebalance,
    queryFn: () => apiGet<RebalanceResponse>('/api/rebalance'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useSaveTarget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TargetConfig) => apiPost<TargetConfig>('/api/target', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.target })
      qc.invalidateQueries({ queryKey: qk.rebalance })
      qc.invalidateQueries({ queryKey: qk.sources })
    },
  })
}

// ── Mutations ──────────────────────────────────────────────────────────

export function useAddOperation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: OperationCreate) =>
      apiPost<{ ok: boolean; row: Operation }>('/api/operations', body),
    onSuccess: () => invalidatePortfolio(qc),
  })
}

export function useAddCrypto() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CryptoOperationCreate) =>
      apiPost<{ ok: boolean; row: CryptoOperation }>('/api/crypto', body),
    onSuccess: () => invalidatePortfolio(qc),
  })
}

export function useUpdateCrypto() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      body,
      fingerprint,
    }: {
      id: number
      body: CryptoOperationCreate
      fingerprint?: string | null
    }) =>
      apiPut<{ ok: boolean; row: CryptoOperation }>(
        `/api/crypto/${id}${fingerprintQuery(fingerprint)}`,
        body,
      ),
    onSuccess: () => invalidatePortfolio(qc),
  })
}

export function useDeleteCrypto() {
  const qc = useQueryClient()
  return useMutation({
    // Accepts a bare id (legacy) or { id, fingerprint }.
    mutationFn: (arg: number | { id: number; fingerprint?: string | null }) => {
      const { id, fingerprint } = typeof arg === 'number' ? { id: arg, fingerprint: null } : arg
      return apiDelete<{ ok: boolean; row: CryptoOperation }>(
        `/api/crypto/${id}${fingerprintQuery(fingerprint)}`,
      )
    },
    onSuccess: () => invalidatePortfolio(qc),
  })
}

export function useSaveSources() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SourcesConfig) => apiPost<{ ok: boolean }>('/api/sources', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.sources })
      qc.invalidateQueries({ queryKey: qk.assetClasses })
      qc.invalidateQueries({ queryKey: qk.target })
      invalidatePortfolio(qc)
    },
  })
}

export function useUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (files: File[]) => apiUpload<{ saved: string[] }>('/api/upload', files),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.pending })
      qc.invalidateQueries({ queryKey: qk.sourceFiles })
      qc.invalidateQueries({ queryKey: qk.sourceData })
    },
  })
}

export function useDeletePending() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (filename: string) =>
      apiDelete<{ ok: boolean }>(`/api/pending-files/${encodeURIComponent(filename)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.pending })
    },
  })
}

/** Preview what /api/process would add — no save, no delete. */
export function useProcessPreview() {
  return useMutation({
    mutationFn: () => apiPost<ProcessPreview>('/api/process/preview'),
  })
}

export function useProcess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<ProcessResult>('/api/process'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.pending })
      qc.invalidateQueries({ queryKey: qk.sourceFiles })
      invalidatePortfolio(qc)
    },
  })
}

/** Persist the (edited) preview rows the user confirmed. */
export function useProcessCommit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ProcessCommit) =>
      apiPost<ProcessResult>('/api/process/commit', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.pending })
      qc.invalidateQueries({ queryKey: qk.sourceFiles })
      invalidatePortfolio(qc)
    },
  })
}

/** Force a fresh dashboard build (re-download prices) and refetch. */
export function useRefreshDashboard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiGet<DashboardResponse>('/api/dashboard?refresh=true'),
    onSuccess: (data) => {
      qc.setQueryData(qk.dashboard, data)
      invalidatePortfolio(qc, { dashboard: false })
    },
  })
}

export function useGenerateReport() {
  return useMutation({
    mutationFn: () => apiPost<ReportResult>('/api/report/generate'),
  })
}
