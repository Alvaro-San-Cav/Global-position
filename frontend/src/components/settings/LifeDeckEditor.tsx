import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plug, Save, UploadCloud } from 'lucide-react'
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
}

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

  const s = q.data
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
      </CardContent>
    </Card>
  )
}
