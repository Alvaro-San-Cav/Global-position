import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, Save } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/PageHeader'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { useSources, useSaveSources } from '@/api/queries'
import type { SourcesConfig } from '@/api/types'
import { KeyValueEditor, type KVRow } from '@/components/settings/KeyValueEditor'
import { Toggle } from '@/components/settings/Toggle'
import { AssetClassEditor } from '@/components/settings/AssetClassEditor'
import { CashEditor } from '@/components/settings/CashEditor'

const SAVE_NOTE = 'Los cambios aplican al recalcular el dashboard.'

// ── helpers to convert a plain object <-> editable KV rows ──────────────
function objToRows(obj: Record<string, unknown> | undefined): KVRow[] {
  if (!obj) return []
  return Object.entries(obj)
    .filter(([k]) => k !== '_comment')
    .map(([key, value]) => ({ key, value: String(value ?? '') }))
}

/** Rebuild an object from rows, preserving any `_comment` from the original. */
function rowsToObj(
  rows: KVRow[],
  original: Record<string, unknown> | undefined,
  numeric: boolean,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const { key, value } of rows) {
    const k = key.trim()
    if (!k) continue
    if (numeric) {
      const n = parseFloat(value)
      out[k] = Number.isNaN(n) ? value : n
    } else {
      out[k] = value
    }
  }
  if (original && typeof original._comment === 'string') {
    out._comment = original._comment
  }
  return out
}

export function Settings() {
  const { data, isLoading, isError } = useSources()
  const save = useSaveSources()

  // Local editable draft, synced whenever fresh server data arrives.
  const [draft, setDraft] = useState<SourcesConfig | null>(null)
  const [jsonText, setJsonText] = useState('')
  const [jsonError, setJsonError] = useState<string | null>(null)

  useEffect(() => {
    if (data) {
      setDraft(structuredClone(data))
      setJsonText(JSON.stringify(data, null, 2))
      setJsonError(null)
    }
  }, [data])

  const stockSources = (draft?.stock_sources as any[]) ?? []
  const cryptoSources = (draft?.crypto_sources as any[]) ?? []
  const benchmark = (draft?.benchmark as Record<string, unknown>) ?? {}

  const priceRows = useMemo(
    () => objToRows(draft?.price_adjustments as Record<string, unknown>),
    [draft],
  )
  const fxRows = useMemo(
    () => objToRows(draft?.fx_adjustments as Record<string, unknown>),
    [draft],
  )

  // Patch a single top-level key of the draft, keeping everything else intact.
  function patchDraft(patch: Partial<SourcesConfig>) {
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  function updateSource(kind: 'stock' | 'crypto', index: number, patch: Record<string, unknown>) {
    const key = kind === 'stock' ? 'stock_sources' : 'crypto_sources'
    const list = ((draft?.[key] as any[]) ?? []).map((s, i) =>
      i === index ? { ...s, ...patch } : s,
    )
    patchDraft({ [key]: list } as Partial<SourcesConfig>)
  }

  // Always builds the payload from the FULL draft so unknown keys are preserved.
  async function persist(next: SourcesConfig) {
    try {
      await save.mutateAsync(next)
      setDraft(structuredClone(next))
      setJsonText(JSON.stringify(next, null, 2))
      setJsonError(null)
      toast.success('Configuración guardada', { description: SAVE_NOTE })
    } catch (e) {
      toast.error('No se pudo guardar', {
        description: e instanceof Error ? e.message : String(e),
      })
    }
  }

  function saveDraft() {
    if (!draft) return
    void persist(draft)
  }

  function savePriceFx() {
    if (!draft) return
    const next: SourcesConfig = {
      ...draft,
      price_adjustments: rowsToObj(
        priceRows,
        draft.price_adjustments as Record<string, unknown>,
        true,
      ),
      fx_adjustments: rowsToObj(
        fxRows,
        draft.fx_adjustments as Record<string, unknown>,
        true,
      ),
    }
    void persist(next)
  }

  function saveJson() {
    let parsed: SourcesConfig
    try {
      parsed = JSON.parse(jsonText)
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'JSON inválido')
      return
    }
    setJsonError(null)
    void persist(parsed)
  }

  if (isError && !draft) {
    return (
      <div>
        <PageHeader title="Ajustes" subtitle="Configuración de fuentes y cálculos." />
        <div className="rounded-[var(--radius-card-lg)] border border-border-subtle bg-card p-8 text-sm text-red">
          No se pudo cargar la configuración.
        </div>
      </div>
    )
  }

  if (isLoading || !draft) {
    return (
      <div>
        <PageHeader title="Ajustes" subtitle="Configuración de fuentes y cálculos." />
        <div className="rounded-[var(--radius-card-lg)] border border-border-subtle bg-card p-8 text-sm text-txt2">
          Cargando configuración…
        </div>
      </div>
    )
  }

  const saving = save.isPending
  const saveBtn = (onClick: () => void, disabled = false) => (
    <Button onClick={onClick} disabled={saving || disabled}>
      <Save /> Guardar
    </Button>
  )

  return (
    <div>
      <PageHeader
        title="Ajustes"
        subtitle="Configuración de fuentes, benchmark y ajustes de precio/FX."
      />

      <Tabs defaultValue="fuentes">
        <TabsList>
          <TabsTrigger value="fuentes">Fuentes</TabsTrigger>
          <TabsTrigger value="clases">Clases de activo</TabsTrigger>
          <TabsTrigger value="efectivo">Efectivo</TabsTrigger>
          <TabsTrigger value="benchmark">Benchmark</TabsTrigger>
          <TabsTrigger value="ajustes">Ajustes precio/FX</TabsTrigger>
          <TabsTrigger value="json">JSON</TabsTrigger>
        </TabsList>

        {/* ── Fuentes ─────────────────────────────────────────────── */}
        <TabsContent value="fuentes" className="space-y-4">
          <p className="text-sm text-txt2">
            Fuentes de acciones y crypto. Los campos avanzados (buy_operations,
            coins…) se editan en la pestaña JSON.
          </p>

          <div>
            <h2 className="mb-2 text-sm font-semibold text-txt">Acciones</h2>
            <div className="space-y-3">
              {stockSources.length === 0 && (
                <p className="text-sm text-txt2">Sin fuentes de acciones.</p>
              )}
              {stockSources.map((src, i) => (
                <SourceCard
                  key={i}
                  src={src}
                  onToggle={(v) => updateSource('stock', i, { enabled: v })}
                  onField={(patch) => updateSource('stock', i, patch)}
                  onColumnMap={(m) => updateSource('stock', i, { column_map: m })}
                  onDefaults={(m) => updateSource('stock', i, { defaults: m })}
                />
              ))}
            </div>
          </div>

          <div>
            <h2 className="mb-2 text-sm font-semibold text-txt">Crypto</h2>
            <div className="space-y-3">
              {cryptoSources.length === 0 && (
                <p className="text-sm text-txt2">Sin fuentes de crypto.</p>
              )}
              {cryptoSources.map((src, i) => (
                <SourceCard
                  key={i}
                  src={src}
                  onToggle={(v) => updateSource('crypto', i, { enabled: v })}
                  onField={(patch) => updateSource('crypto', i, patch)}
                  onColumnMap={(m) => updateSource('crypto', i, { column_map: m })}
                  onDefaults={(m) => updateSource('crypto', i, { defaults: m })}
                />
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {saveBtn(saveDraft)}
            <span className="text-xs text-txt2">{SAVE_NOTE}</span>
          </div>
        </TabsContent>

        {/* ── Clases de activo ────────────────────────────────────── */}
        <TabsContent value="clases">
          <AssetClassEditor />
        </TabsContent>

        {/* ── Efectivo ────────────────────────────────────────────── */}
        <TabsContent value="efectivo">
          <CashEditor />
        </TabsContent>

        {/* ── Benchmark ───────────────────────────────────────────── */}
        <TabsContent value="benchmark" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Benchmark de referencia</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="bench-ticker">Ticker</Label>
                <Input
                  id="bench-ticker"
                  value={String(benchmark.ticker ?? '')}
                  placeholder="IWDA.AS"
                  onChange={(e) =>
                    patchDraft({
                      benchmark: { ...benchmark, ticker: e.target.value },
                    })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="bench-name">Nombre</Label>
                <Input
                  id="bench-name"
                  value={String(benchmark.name ?? '')}
                  placeholder="MSCI World (IWDA)"
                  onChange={(e) =>
                    patchDraft({
                      benchmark: { ...benchmark, name: e.target.value },
                    })
                  }
                />
              </div>
            </CardContent>
          </Card>
          <div className="flex items-center gap-3">
            {saveBtn(saveDraft)}
            <span className="text-xs text-txt2">{SAVE_NOTE}</span>
          </div>
        </TabsContent>

        {/* ── Ajustes precio/FX ───────────────────────────────────── */}
        <TabsContent value="ajustes" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Ajustes de precio por ticker</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-xs text-txt2">
                Divisor aplicado al precio descargado (p. ej. NEPTF viene en
                milésimas → 1000).
              </p>
              <KeyValueEditor
                rows={priceRows}
                onChange={(rows) =>
                  patchDraft({
                    price_adjustments: rowsToObj(
                      rows,
                      draft.price_adjustments as Record<string, unknown>,
                      true,
                    ),
                  })
                }
                keyLabel="Ticker"
                valueLabel="Divisor"
                valueType="number"
                keyPlaceholder="NEPTF"
                valuePlaceholder="1000"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Ajustes de tipo de cambio (FX)</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-xs text-txt2">
                Divisor aplicado al tipo de cambio (p. ej. GBX viene en peniques
                → 100).
              </p>
              <KeyValueEditor
                rows={fxRows}
                onChange={(rows) =>
                  patchDraft({
                    fx_adjustments: rowsToObj(
                      rows,
                      draft.fx_adjustments as Record<string, unknown>,
                      true,
                    ),
                  })
                }
                keyLabel="Moneda"
                valueLabel="Divisor"
                valueType="number"
                keyPlaceholder="GBX"
                valuePlaceholder="100"
              />
            </CardContent>
          </Card>

          <div className="flex items-center gap-3">
            {saveBtn(savePriceFx)}
            <span className="text-xs text-txt2">{SAVE_NOTE}</span>
          </div>
        </TabsContent>

        {/* ── JSON ────────────────────────────────────────────────── */}
        <TabsContent value="json" className="space-y-3">
          <p className="text-sm text-txt2">
            Editor directo de <code className="text-txt">sources.json</code>. Se
            valida antes de guardar.
          </p>
          <textarea
            value={jsonText}
            spellCheck={false}
            onChange={(e) => {
              setJsonText(e.target.value)
              if (jsonError) setJsonError(null)
            }}
            className="h-[480px] w-full rounded-[var(--radius-card)] border border-border-strong bg-bg2 p-3 font-mono text-xs text-txt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          />
          {jsonError && (
            <div className="flex items-start gap-2 text-sm text-red">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <span>JSON inválido: {jsonError}</span>
            </div>
          )}
          <div className="flex items-center gap-3">
            {saveBtn(saveJson)}
            <span className="text-xs text-txt2">{SAVE_NOTE}</span>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ── Source card ───────────────────────────────────────────────────────
function SourceCard({
  src,
  onToggle,
  onField,
  onColumnMap,
  onDefaults,
}: {
  src: Record<string, unknown>
  onToggle: (v: boolean) => void
  onField: (patch: Record<string, unknown>) => void
  onColumnMap: (map: Record<string, unknown>) => void
  onDefaults: (map: Record<string, unknown>) => void
}) {
  const enabled = Boolean(src.enabled)
  const columnMap = (src.column_map as Record<string, unknown>) ?? {}
  const defaults = (src.defaults as Record<string, unknown>) ?? {}

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <CardTitle>{String(src.name ?? 'Sin nombre')}</CardTitle>
          <Badge variant={enabled ? 'green' : 'default'}>
            {enabled ? 'Activa' : 'Inactiva'}
          </Badge>
        </div>
        <Toggle checked={enabled} onChange={onToggle} label="Habilitada" />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Nombre</Label>
            <Input
              value={String(src.name ?? '')}
              onChange={(e) => onField({ name: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Patrón de archivo</Label>
            <Input
              value={String(src.file_pattern ?? '')}
              placeholder="sap*.csv"
              onChange={(e) => onField({ file_pattern: e.target.value })}
            />
          </div>
        </div>

        <div>
          <Label className="mb-2 block">column_map</Label>
          <KeyValueEditor
            rows={objToRows(columnMap)}
            onChange={(rows) => onColumnMap(rowsToObj(rows, columnMap, false))}
            keyLabel="Campo interno"
            valueLabel="Columna CSV"
          />
        </div>

        <div>
          <Label className="mb-2 block">defaults</Label>
          <KeyValueEditor
            rows={objToRows(defaults)}
            onChange={(rows) => onDefaults(rowsToObj(rows, defaults, false))}
            keyLabel="Campo"
            valueLabel="Valor"
          />
        </div>
      </CardContent>
    </Card>
  )
}
