# Global Position - Frontend

SPA React 19 + Vite + TypeScript + Tailwind v4 (componentes shadcn/Radix,
TanStack Query, Recharts). Consume la API FastAPI de `../backend`.

## Requisitos

Node 20+ y pnpm (`corepack enable`). Instala dependencias con `pnpm install`.

## Scripts

| Comando | Acción |
|---------|--------|
| `pnpm dev` | Vite en `:5173` con proxy `/api` hacia `:8000` (necesita el backend levantado) |
| `pnpm build` | `tsc -b` + build de producción en `dist/` (lo sirve FastAPI) |
| `pnpm preview` | Sirve el build localmente |
| `pnpm test` | Vitest en modo watch (`pnpm test run` para una sola pasada) |
| `pnpm lint` | Oxlint |
| `pnpm format` | Prettier sobre `src/` |
| `pnpm gen:api` | Regenera `src/api/schema.d.ts` desde `http://localhost:8000/api/openapi.json` (backend levantado) |

## Estructura

```
src/
  api/          client.ts, queries.ts (hooks TanStack Query), types.ts, schema.d.ts (generado)
  components/   ui/ (shadcn), charts/, dashboard/, operations/, layout/
  pages/        Dashboard, Operations, Crypto, Tax, Objetivo, Import, Settings
  lib/          format.ts (es-ES), utils.ts, derivedTiles.ts
```

## Notas

- Tras cambiar endpoints o modelos Pydantic del backend, ejecuta `pnpm gen:api`.
- `dist/` y `node_modules/` están en `.gitignore`.
- Ver el [README principal](../README.md) para el flujo completo y el lanzador de escritorio.
