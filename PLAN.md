# Plan de migración: GlobalPosition.ipynb → Global-Position con frontend moderno

> **Fecha:** 2026-07-03
> **Objetivo:** Retirar definitivamente `GlobalPositionPersonal/GlobalPosition.ipynb` como herramienta de cálculo de posiciones y consolidar todo el flujo en `Global-Position`, sustituyendo la web actual (HTML único + vanilla JS + CDN) por un frontend moderno con build propio. Sin Streamlit y sin notebooks.

---

## 1. Diagnóstico del estado actual

### 1.1 Lo que ya está hecho (¡mucho!)

`Global-Position` **ya replica toda la lógica del notebook** en módulos Python testeados:

| Funcionalidad del notebook | Celda(s) | Equivalente en Global-Position | Estado |
|---|---|---|---|
| Ingesta Degiro + dedup (Date/ISIN/Qty/Price) | 3 | `src/loaders.py` | ✅ Mejorado (backup + log auditoría) |
| Lookup ticker por ISIN (API Yahoo) | 3 | `src/market_data.py` | ✅ |
| Fuente SAP vests (`sap_stock.csv`) | 3 | `sources.json` → `stock_sources` genérico | ✅ Generalizado |
| Descarga precios + FX y conversión a EUR | 7 | `src/market_data.py` con caché incremental | ✅ Mejorado |
| Ajustes NEPTF/PSH.L/GBX | 8 | `sources.json` → `price_adjustments`/`fx_adjustments` | ✅ Configurable |
| Detección y aplicación de splits (ops + yfinance post-tenencia) | 10 | `src/core.py` | ✅ |
| Valoración cartera acciones (qty acumulada × precio EUR) | 12 | `src/core.py` | ✅ |
| Gráficos evolución + composición | 15 | Dashboard web (`/api/dashboard`) | ✅ |
| Matriz de correlación | 17 | `server.py` + `web/index.html` | ✅ |
| Cartera crypto Binance (BTC/ETH) | 19, 21 | `src/loaders.py` + `sources.json` → `crypto_sources` | ✅ |
| Resumen consolidado (CAGR, TWR, pesos) | 23 | `main.py::_compute_metrics` + `src/core.py` | ✅ |
| Informe PDF + archivo histórico | 18, 25 | `src/reporter.py` → `output/` | ✅ |
| — (no existía en notebook) | — | Benchmark vs IWDA.AS + alfa | ✅ Extra |
| — (no existía en notebook) | — | Plusvalías FIFO (`src/tax.py`) | ✅ Extra |
| — (no existía en notebook) | — | 51 tests (unit + integración con mocks) | ✅ Extra |

**Datos:** `processing/operaciones.csv` (109 filas, hasta 2026-03-31) es idéntico al `operaciones.csv` del notebook. `processing/crypto.csv` está poblado. **No hay pérdida de datos al migrar.**

### 1.2 El gap real: el frontend

La web actual es `web/index.html`: un solo archivo con CSS/JS inline, Chart.js y Lucide por CDN. Funciona, pero:

- Sin sistema de componentes ni tipado → difícil de extender.
- Sin build: dependencias por CDN (requiere internet incluso en local).
- JS imperativo con manipulación DOM manual.
- Un archivo monolítico difícil de mantener a medida que crecen las páginas.

**El trabajo de esta migración es (a) modernizar el frontend y (b) formalizar el cutover del notebook.** El backend Python se conserva.

---

## 2. Decisión de stack

### 2.1 Recomendación

| Capa | Elección | Justificación |
|---|---|---|
| Backend | **FastAPI (se mantiene)** | Ya existe, moderno, async, OpenAPI gratis. Solo se endurece (Pydantic response models, prefijo `/api` ya presente). |
| Frontend | **React 19 + Vite + TypeScript** | Estándar de facto, ecosistema de charting maduro, tipado end-to-end contra la API. |
| Estilos | **Tailwind CSS v4** | Portar el dark theme actual (variables CSS ya definidas) es directo. |
| Componentes | **shadcn/ui** | Tablas, dialogs, tabs, toasts sin dependencia pesada; código copiado al repo. |
| Datos remotos | **TanStack Query** | Caché, revalidación, estados loading/error declarativos para los 16 endpoints. |
| Gráficos | **Recharts** (o mantener Chart.js vía `react-chartjs-2`) | Recharts = más idiomático React. Chart.js = migración 1:1 de los gráficos actuales. Decidir en Fase 2; default Recharts. |
| Routing | **React Router v7 (modo SPA)** | 6 páginas, sin SSR necesario. |
| Tests frontend | **Vitest + Testing Library** | Nativo de Vite. |
| Gestor JS | **pnpm** | Rápido, lockfile estricto. |

### 2.2 Alternativas descartadas

- **Streamlit / notebook** — excluidos por requisito.
- **Next.js** — SSR/RSC innecesarios para app local single-user; complica el deploy (Node en runtime). Vite genera estáticos que FastAPI ya sabe servir.
- **SvelteKit / Vue** — perfectamente válidos y más ligeros, pero menor ecosistema de componentes financieros/tablas; React maximiza mantenibilidad a largo plazo. Si prefieres Svelte, el plan es idéntico cambiando solo la Fase 2-3.
- **HTMX + Jinja** — mínimo cambio, pero no aporta tipado ni componentes; no cumple el espíritu de "framework moderno".

---

## 3. Arquitectura destino

```
Global-Position/
├── backend/                  # ← código Python actual reubicado
│   ├── main.py               # CLI (sin cambios funcionales)
│   ├── server.py             # FastAPI: API + servir frontend/dist
│   ├── sources.json
│   ├── requirements.txt
│   ├── src/                  # config, core, loaders, market_data, reporter, schemas, tax
│   └── tests/
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts        # proxy /api → localhost:8000 en dev
│   ├── src/
│   │   ├── api/              # cliente tipado (tipos generados de OpenAPI)
│   │   ├── components/       # ui/ (shadcn), charts/, layout/
│   │   ├── pages/            # Dashboard, Operations, Crypto, Tax, Import, Settings
│   │   ├── lib/              # formateadores €/%/fecha, utilidades
│   │   └── App.tsx
│   └── dist/                 # build de producción (gitignored)
├── input/  processing/  output/   # datos: SIN CAMBIOS de ubicación
├── PLAN.md
└── README.md
```

**Modos de ejecución:**
- **Desarrollo:** `uvicorn backend.server:app --reload` + `pnpm dev` (Vite, puerto 5173, proxy `/api`).
- **Producción/uso diario:** `pnpm build` una vez → `python backend/server.py` sirve `frontend/dist` en `http://localhost:8000`. Un solo proceso, como hoy.

---

## 4. Fases de ejecución

### Fase 0 — Preparación y congelación del notebook (~30 min)

1. Commit del estado actual de `Global-Position` (ya es repo git).
2. Verificar paridad de datos una última vez:
   - `GlobalPositionPersonal/operaciones.csv` vs `processing/operaciones.csv` (hoy: idénticos, 109 filas).
   - Reprocesar `GlobalPositionPersonal/binance.csv` (131 filas) por la CLI opción 3 y comparar balances BTC/ETH con la salida del notebook.
3. Ejecutar `python main.py` → opción 1 y comparar contra la última ejecución del notebook: capital aportado, valor actual, CAGR, TWR (acciones, crypto, total). Tolerancia: diferencias de céntimos por redondeo/fecha de precios.
4. Copiar `GlobalPositionPersonal/informes/` → `output/hist-inf/` (histórico de PDFs).
5. Marcar el notebook como congelado: añadir celda 0 markdown "⚠️ DEPRECATED — usar Global-Position" (no borrar aún; se archiva en Fase 6).

**Criterio de salida:** métricas CLI ≡ métricas notebook documentadas en `docs/paridad.md` (tabla antes/después).

### Fase 1 — Endurecimiento de la API (~½ día)

1. Reestructurar a `backend/` (mover `main.py`, `server.py`, `src/`, `tests/`, `sources.json`, `requirements.txt`; rutas de datos en `src/config.py` apuntan a `../input`, `../processing`, `../output` o mejor: raíz del repo detectada).
2. Definir **Pydantic response models** para cada endpoint (hoy devuelven dicts ad-hoc):
   - `GET /api/dashboard` → `DashboardResponse` (kpis, series evolución, composición, benchmark, correlación).
   - `GET/POST /api/operations`, `GET/POST /api/crypto`, `GET /api/tax`, `GET/POST /api/sources`, `POST /api/upload`, `GET /api/source-data`, `GET /api/pending-files`, `GET /api/source-files`, `DELETE /api/pending-files/{filename}`, `GET /api/invalidate`.
3. Reactivar `docs_url="/api/docs"` (hoy deshabilitado) → OpenAPI para generar tipos TS.
4. `CORSMiddleware` solo para origen `http://localhost:5173` en modo dev.
5. Añadir `GET /api/health` y `GET /api/report/pdf` (descarga del último PDF) si no existen.
6. Tests: los 51 existentes deben seguir en verde tras la reubicación; añadir tests de contrato por endpoint (schemas válidos con datos de fixtures).

**Criterio de salida:** `pytest` verde, `/api/docs` muestra esquemas completos, `web/index.html` viejo sigue funcionando (aún no se toca).

### Fase 2 — Scaffold del frontend (~½ día)

1. `pnpm create vite frontend --template react-ts`.
2. Tailwind v4 + shadcn/ui init. Portar el theme dark actual: las variables `--bg`, `--card`, `--accent`, `--green`… de `web/index.html` se trasladan tal cual a tokens Tailwind (continuidad visual).
3. TanStack Query + React Router: layout con sidebar (mismas 6 secciones actuales) y rutas:
   `/` (Dashboard), `/operaciones`, `/crypto`, `/fiscalidad`, `/importar`, `/ajustes`.
4. Cliente API tipado: `openapi-typescript` genera `src/api/schema.d.ts` desde `http://localhost:8000/openapi.json` (script `pnpm gen:api`); wrapper fetch fino en `src/api/client.ts`.
5. `vite.config.ts` con proxy `/api` → `:8000`.
6. Utilidades de formato: `fmtEur`, `fmtPct`, `fmtDate` (locale `es-ES`) — hoy repetidas por todo el JS.

**Criterio de salida:** `pnpm dev` levanta shell con navegación, tema dark aplicado, `GET /api/dashboard` tipado consumido en una página de prueba.

### Fase 3 — Migración página a página (~2-3 días, el grueso)

Orden por valor/uso. Cada página: componente(s) + query tipada + estados loading/error + test de render con mock.

| # | Página | Endpoints | Componentes clave |
|---|---|---|---|
| 3.1 | **Dashboard** | `/api/dashboard`, `/api/invalidate` | KPICards (capital, valor, plusvalía, rentabilidad, CAGR, TWR, alfa), EvolutionChart (valor vs aportado, área plusvalía), BenchmarkChart, CompositionDonut (umbral 2% → "Otros"), CorrelationHeatmap, botón "Refrescar precios" (invalidate + refetch) |
| 3.2 | **Operaciones** | `/api/operations` (GET/POST) | DataTable shadcn con sort/filtro por ticker, moneda, rango fechas, búsqueda libre; paginación client-side (≈100 filas) |
| 3.3 | **Crypto** | `/api/crypto` (GET/POST) | Tabla transacciones + tarjetas de balance por moneda con valor EUR actual |
| 3.4 | **Fiscalidad** | `/api/tax` | Resumen FIFO por año fiscal y ticker (tabla agrupada), botón exportar CSV |
| 3.5 | **Importar** | `/api/upload`, `/api/pending-files`, `/api/source-files`, `DELETE /api/pending-files/{f}` | Dropzone drag&drop, lista de pendientes con acción procesar/borrar, feedback del log de ingesta |
| 3.6 | **Ajustes** | `/api/sources` (GET/POST), `/api/source-data` | Editor de `sources.json` por formularios (stock/crypto sources, benchmark, ajustes precio/FX) + vista JSON raw con validación |

Notas:
- El JS actual de `web/index.html` es la **especificación funcional**: replicar comportamiento, no reescribir de memoria.
- Gráficos: portar configuraciones Chart.js existentes a Recharts uno a uno, comparando visualmente contra la web vieja (correr ambas en paralelo durante esta fase).

**Criterio de salida:** paridad funcional total con `web/index.html` verificada página a página con datos reales.

### Fase 4 — Integración de build y single-command (~½ día)

1. `pnpm build` → `frontend/dist`.
2. `server.py`: montar `StaticFiles(directory="frontend/dist")` con fallback SPA (el catch-all `/{path:path}` actual ya apunta bien; cambiar directorio).
3. Scripts de conveniencia en la raíz:
   - `run.ps1` / `Makefile`: `dev` (backend+frontend concurrentes), `build`, `serve`, `test`.
4. `.gitignore`: `frontend/node_modules`, `frontend/dist`, cachés.

**Criterio de salida:** `python backend/server.py` sirve la app nueva completa en `:8000` sin Node en runtime.

### Fase 5 — Calidad (~½ día)

1. Frontend: Vitest para formateadores y componentes críticos (KPICards, DataTable con filtros); `pnpm gen:api` en CI-local para detectar drift de contrato.
2. Backend: mantener 51 tests + los de contrato de Fase 1.
3. Opcional: 2-3 flujos E2E con Playwright (cargar dashboard, filtrar operaciones, subir CSV de fixture).
4. Lint/format: `ruff` (backend), `eslint + prettier` (frontend).

### Fase 6 — Cutover y retirada del notebook (~1 h)

1. Borrar `web/index.html` (queda en historia git).
2. Actualizar `README.md`: nueva estructura, comandos dev/build, flujo de uso diario.
3. Archivar `GlobalPositionPersonal/`:
   - Mover `GlobalPosition.ipynb` y CSVs históricos a `Global-Position/docs/archive/notebook/` (o a un zip fuera del repo). **No borrar sin confirmar** que Fase 0 documentó la paridad.
   - `hist_data_globlapos/` y `qty_acumulada.csv`: revisar si aportan algo no regenerable; si no, archivar igual.
4. Commit final + tag `v2.0.0`.

**Flujo de uso diario resultante:**
```
Descargar CSV Degiro/Binance → arrastrar a "Importar" en la web
→ Dashboard se actualiza (caché incremental de precios)
→ PDF/fiscalidad bajo demanda desde la web
```

---

## 5. Riesgos y mitigaciones

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Discrepancia de métricas notebook vs backend (fechas de precio, ffill, redondeos) | Media | Fase 0 documenta paridad ANTES de tocar nada; cualquier delta se investiga ahí, no después |
| Regresión visual/funcional al portar gráficos | Media | Web vieja y nueva conviven durante Fase 3; comparación lado a lado con datos reales |
| Drift entre API y tipos TS | Baja | Tipos generados de OpenAPI, regenerables con un comando; test de contrato en backend |
| yfinance rompe (rate limit, cambios API) | Media (ya existente) | Caché incremental ya lo amortigua; fuera de alcance de esta migración |
| Reubicación a `backend/` rompe rutas relativas de datos | Media | `src/config.py` centraliza rutas — un solo punto de cambio; tests de integración lo cubren |
| Scope creep (features nuevas durante la migración) | Alta | Regla: Fases 1-4 = paridad estricta. Ideas nuevas → sección 7 |

---

## 6. Estimación total

| Fase | Esfuerzo |
|---|---|
| 0. Preparación y paridad | 0.5 día |
| 1. API hardening | 0.5 día |
| 2. Scaffold frontend | 0.5 día |
| 3. Páginas (×6) | 2–3 días |
| 4. Build/integración | 0.5 día |
| 5. Calidad | 0.5 día |
| 6. Cutover | 0.25 día |
| **Total** | **≈ 5–6 días de trabajo efectivo** |

---

## 7. Backlog post-migración (NO incluir en la migración)

- Rebalanceo objetivo: pesos deseados por activo y sugerencias de compra.
- Dividendos: ingesta y tracking (Degiro los exporta).
- Alertas (precio objetivo, drift de asset allocation).
- Multi-benchmark y comparación por periodos.
- Vista móvil optimizada / PWA.
- Snapshot diario automático (tarea programada) para históricos sin recálculo.
- Reemplazar PDF matplotlib por render del propio frontend (print CSS o Playwright PDF).

---

## 8. Checklist de aceptación final

- [ ] `docs/paridad.md` con métricas notebook vs sistema (Fase 0)
- [ ] `pytest` verde (51+ tests) tras reestructuración
- [ ] `/api/docs` operativo con schemas Pydantic completos
- [ ] 6 páginas con paridad funcional vs `web/index.html`
- [ ] `python backend/server.py` sirve la app buildada en `:8000` sin Node
- [ ] `pnpm test` verde
- [ ] README actualizado
- [ ] Notebook archivado, `GlobalPositionPersonal/` vaciada o archivada
- [ ] Tag `v2.0.0`
