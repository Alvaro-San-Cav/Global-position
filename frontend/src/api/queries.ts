import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query'
import { apiGet, apiPost, apiDelete, apiUpload } from './client'
import type {
  AssetClassesResponse,
  CryptoOperation,
  CryptoOperationCreate,
  DashboardResponse,
  Operation,
  OperationCreate,
  ProcessResult,
  ReportResult,
  SourceData,
  SourceFileInfo,
  SourcesConfig,
  TaxResponse,
} from './types'

export const qk = {
  dashboard: ['dashboard'] as const,
  operations: ['operations'] as const,
  crypto: ['crypto'] as const,
  tax: ['tax'] as const,
  sources: ['sources'] as const,
  assetClasses: ['asset-classes'] as const,
  pending: ['pending-files'] as const,
  sourceFiles: ['source-files'] as const,
  sourceData: ['source-data'] as const,
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

// ── Mutations ──────────────────────────────────────────────────────────

export function useAddOperation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: OperationCreate) =>
      apiPost<{ ok: boolean; row: Operation }>('/api/operations', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.operations })
      qc.invalidateQueries({ queryKey: qk.dashboard })
    },
  })
}

export function useAddCrypto() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CryptoOperationCreate) =>
      apiPost<{ ok: boolean; row: CryptoOperation }>('/api/crypto', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.crypto })
      qc.invalidateQueries({ queryKey: qk.dashboard })
    },
  })
}

export function useSaveSources() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SourcesConfig) => apiPost<{ ok: boolean }>('/api/sources', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.sources })
      qc.invalidateQueries({ queryKey: qk.dashboard })
      qc.invalidateQueries({ queryKey: qk.assetClasses })
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

export function useProcess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<ProcessResult>('/api/process'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.pending })
      qc.invalidateQueries({ queryKey: qk.operations })
      qc.invalidateQueries({ queryKey: qk.crypto })
      qc.invalidateQueries({ queryKey: qk.dashboard })
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
    },
  })
}

export function useGenerateReport() {
  return useMutation({
    mutationFn: () => apiPost<ReportResult>('/api/report/generate'),
  })
}
