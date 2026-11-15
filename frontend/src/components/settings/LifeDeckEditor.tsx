import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, Plug, Save, UploadCloud } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiGet, apiPost } from '@/api/client'
import { Toggle } from './Toggle'

interface LifeDeckSettings {
  enabled: boolean
  url: string
  has_token: boolean
  last_push_at: string | null
  last_error: string | null
  auto_supported?: boolean
  auto_enabled?: boolean
  auto_minutes?: number
  last_auto_at?: string | null
  last_auto_error?: string | null
}

const INTERVALS = [15, 30, 60, 120] as const

interface Result {
  ok: boolean
  message: string
}

const KEY = ['lifedeck'] as const

function when(iso: string | null): string {
  if (!iso) return 'nunca'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
}

/** Ajustes › LifeDeck: URL + token (el de PersAcc) y subida del resumen de patrimonio. */
export function LifeDeckEditor() {
  const qc = useQueryClient()
  const q = useQuery<LifeDeckSettings>({ queryKey: KEY, queryFn: () => apiGet('/api/lifedeck') })
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    if (!q.data) return
    setUrl(q.data.url || 'https://life-deck-one.vercel.app')
    setEnabled(q.data.enabled)
  }, [q.data])

  const save = useMutation({
    mutationFn: () => apiPost<LifeDeckSettings>('/api/lifedeck', { url, token, enabled }),
    onSuccess: (d) => {
      qc.setQueryData(KEY, d)
      setToken('')
      toast.success('Ajustes de LifeDeck guardados')
    },
    onError: (e: Error) => toast.error('No se pudo guardar', { description: e.message }),
  })
  const test = useMutation({
    mutationFn: () => apiPost<Result>('/api/lifedeck/test'),
    onSuccess: (r) => (r.ok ? toast.success(r.message) : toast.error(r.message)),
    onError: (e: Error) => toast.error(e.message),
  })
  const push = useMutation({
    mutationFn: () => apiPost<Result>('/api/lifedeck/push'),
    onSuccess: (r) => toast.success(r.message),
    onError: (e: Error) => toast.error('No se pudo subir', { description: e.message }),
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })

  const auto = useMutation({
    mutationFn: (body: { enabled: boolean; minutes?: number }) => apiPost<LifeDeckSettings>('/api/lifedeck/auto', body),
    onSuccess: (d, body) => {
      qc.setQueryData(KEY, d)
      toast.success(
        body.enabled
          ? `Actualizando en segundo plano cada ${body.minutes ?? d.auto_minutes} min (aunque cierres Global Position)`
          : 'Actualización en segundo plano desactivada',
      )
    },
    onError: (e: Error) => toast.error('No se pudo cambiar', { description: e.message }),
  })

  const s = q.data
  const minutes = s?.auto_minutes ?? 30
  const dirty = Boolean(s && (url !== s.url || enabled !== s.enabled || token.trim()))

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>LifeDeck</CardTitle>
        <div className="flex items-center gap-2 text-sm text-txt2">
          Subir tras cada análisis
          <Toggle checked={enabled} onChange={setEnabled} label="Subir automáticamente a LifeDeck" />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-txt2">
          Envía a LifeDeck un resumen del patrimonio (totales, reparto por clases, activos principales y la evolución
          reducida) para verlo en el móvil. No se envían operaciones. Usa el mismo token que PersAcc: LifeDeck › Ajustes ›
          Conexión con PersAcc.
        </p>
        {q.isError && (
          <p role="alert" className="text-sm text-red">
            El servidor no responde a /api/lifedeck: cierra Global Position del todo (o ejecuta launch-app.ps1 -Stop) y
            vuelve a abrirlo para cargar la versión nueva.
          </p>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="ld-url">URL de LifeDeck</Label>
            <Input id="ld-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ld-token">Token</Label>
            <Input
              id="ld-token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={s?.has_token ? '•••••••• (guardado; escribe para cambiarlo)' : 'Pega el token'}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
            <Save className="h-4 w-4" /> Guardar
          </Button>
          <Button variant="outline" onClick={() => test.mutate()} disabled={test.isPending || !s?.has_token}>
            <Plug className="h-4 w-4" /> Probar conexión
          </Button>
          <Button variant="outline" onClick={() => push.mutate()} disabled={push.isPending || !s?.has_token}>
            <UploadCloud className="h-4 w-4" /> {push.isPending ? 'Subiendo…' : 'Subir ahora'}
          </Button>
        </div>
        <p className="text-xs text-txt2">
          Última subida: {when(s?.last_push_at ?? null)}
          {s?.last_error ? <span className="ml-2 text-red">· {s.last_error}</span> : null}
        </p>

        {s?.auto_supported !== false && (
          <div className="space-y-2 rounded-md border border-border-subtle p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Clock className="h-4 w-4" /> Actualizar en segundo plano
              </div>
              <div className="flex items-center gap-2 text-sm text-txt2">
                cada
                <select
                  aria-label="Intervalo de actualización"
                  className="h-8 rounded-md border border-border-subtle bg-card px-2 text-sm"
                  value={minutes}
                  disabled={auto.isPending}
                  onChange={(e) => {
                    const m = Number(e.target.value)
                    if (s?.auto_enabled) auto.mutate({ enabled: true, minutes: m })
                    else qc.setQueryData<LifeDeckSettings>(KEY, (old) => (old ? { ...old, auto_minutes: m } : old))
                  }}
                >
                  {INTERVALS.map((m) => (
                    <option key={m} value={m}>
                      {m < 60 ? `${m} min` : `${m / 60} h`}
                    </option>
                  ))}
                </select>
                <Toggle
                  checked={Boolean(s?.auto_enabled)}
                  onChange={(v) => auto.mutate(v ? { enabled: true, minutes } : { enabled: false })}
                  label="Actualizar en segundo plano"
                />
              </div>
            </div>
            <p className="text-xs text-txt2">
              Crea una tarea en el Programador de tareas de Windows que, con el PC encendido y tu sesión iniciada, recalcula el
              patrimonio con precios frescos y lo sube a LifeDeck, aunque no abras Global Position. Los fondos solo cambian
              una vez al día; acciones, ETF y cripto, durante la sesión.
            </p>
            {s?.auto_enabled && (
              <p className="text-xs text-txt2">
                Última ejecución: {when(s.last_auto_at ?? null)}
                {s.last_auto_error ? <span className="ml-2 text-red">· {s.last_auto_error}</span> : null}
              </p>
            )}
            {!s?.has_token && <p className="text-xs text-txt2">Guarda antes la URL y el token.</p>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
