import { useEffect, useMemo, useState } from 'react'
import { Save, Search } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAssetClasses, useSources, useSaveSources } from '@/api/queries'
import type { SourcesConfig } from '@/api/types'

const AUTO = '__auto__'

export function AssetClassEditor() {
  const { data, isLoading, isError } = useAssetClasses()
  const { data: sources } = useSources()
  const save = useSaveSources()

  // Local override map keyed by UPPER symbol. Initialised from the server view.
  const [overrides, setOverrides] = useState<Record<string, string>>({})
  const [filter, setFilter] = useState('')

  useEffect(() => {
    if (!data) return
    const init: Record<string, string> = {}
    for (const it of data.items) {
      if (it.override) init[it.symbol.toUpperCase()] = it.override
    }
    setOverrides(init)
  }, [data])

  const classOptions = data?.known_classes ?? []

  const items = useMemo(() => {
    const q = filter.trim().toLowerCase()
    const list = data?.items ?? []
    if (!q) return list
    return list.filter(
      (it) =>
        it.symbol.toLowerCase().includes(q) ||
        it.name.toLowerCase().includes(q) ||
        it.effective.toLowerCase().includes(q),
    )
  }, [data, filter])

  const dirty = useMemo(() => {
    if (!data) return false
    const original: Record<string, string> = {}
    for (const it of data.items) if (it.override) original[it.symbol.toUpperCase()] = it.override
    const a = JSON.stringify(original, Object.keys(original).sort())
    const b = JSON.stringify(overrides, Object.keys(overrides).sort())
    return a !== b
  }, [data, overrides])

  function setOverride(symbol: string, value: string) {
    const up = symbol.toUpperCase()
    setOverrides((prev) => {
      const next = { ...prev }
      if (value === AUTO) delete next[up]
      else next[up] = value
      return next
    })
  }

  async function persist() {
    // Preserve the whole sources.json; only replace asset_classes.
    const base: SourcesConfig = sources ? structuredClone(sources) : {}
    const prevAc = (base.asset_classes as Record<string, unknown>) ?? {}
    const nextAc: Record<string, unknown> = {}
    if (typeof prevAc._comment === 'string') nextAc._comment = prevAc._comment
    for (const [k, v] of Object.entries(overrides)) nextAc[k] = v
    base.asset_classes = nextAc
    try {
      await save.mutateAsync(base)
      toast.success('Clases guardadas', {
        description: 'Los cambios aplican al recalcular el dashboard.',
      })
    } catch (e) {
      toast.error('No se pudo guardar', {
        description: e instanceof Error ? e.message : String(e),
      })
    }
  }

  if (isLoading) {
    return <p className="text-sm text-txt2">Cargando activos…</p>
  }
  if (isError || !data) {
    return <p className="text-sm text-red">No se pudieron cargar los activos.</p>
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-txt2">
        Clase de cada activo. Por defecto se deduce automáticamente del nombre;
        elige una clase en el desplegable para fijarla (gana sobre la detección).
        Vuelve a «Automático» para quitar el override.
      </p>

      <div className="relative max-w-xs">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-txt3" />
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Buscar ticker, nombre o clase…"
          className="pl-9"
        />
      </div>

      <div className="overflow-hidden rounded-[var(--radius-card-lg)] border border-border-subtle bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Activo</TableHead>
              <TableHead>Ticker</TableHead>
              <TableHead>Clase actual</TableHead>
              <TableHead className="w-56">Fijar clase</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((it) => {
              const up = it.symbol.toUpperCase()
              const current = overrides[up] ?? it.auto
              const isOverride = up in overrides
              return (
                <TableRow key={up}>
                  <TableCell className="max-w-[280px] truncate text-txt" title={it.name}>
                    {it.name}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-txt2">{it.symbol}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="text-txt">{current}</span>
                      <Badge variant={isOverride ? 'accent' : 'default'}>
                        {isOverride ? 'fijada' : 'auto'}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Select
                      value={overrides[up] ?? AUTO}
                      onValueChange={(v) => setOverride(it.symbol, v)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={AUTO}>Automático ({it.auto})</SelectItem>
                        {classOptions.map((c) => (
                          <SelectItem key={c} value={c}>
                            {c}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                </TableRow>
              )
            })}
            {items.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-sm text-txt2">
                  Sin activos que coincidan.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={persist} disabled={save.isPending || !dirty}>
          <Save /> Guardar clases
        </Button>
        {dirty && <span className="text-xs text-amber">Hay cambios sin guardar.</span>}
      </div>
    </div>
  )
}
