# Plan de implementación paso a paso — Migración frontend Global-Position

> **Documento ejecutable.** Destinado a ser implementado por un agente (Opus 4.8) sin contexto previo.
> Contexto estratégico y justificación del stack: ver [PLAN.md](PLAN.md).
> **Entorno:** Windows 11, PowerShell. Repo git en `C:\Proyectos\FIN\Global-Position` (este directorio).

---

## Reglas para el ejecutor

1. **Paridad estricta.** Fases 1–8 replican la funcionalidad existente. NO añadir features nuevas, NO "mejorar" cálculos financieros, NO tocar `src/core.py`, `src/tax.py`, `src/loaders.py`, `src/market_data.py` salvo lo indicado explícitamente.
2. **Un commit por etapa** con el mensaje indicado. No avanzar a la etapa siguiente si los criterios de verificación de la actual fallan.
3. **Tests siempre verdes.** Tras cada etapa que toque Python: `python -m pytest tests/ -v` (51 tests actuales deben pasar). Si un test falla por la reestructuración, arreglar el test/import, nunca la lógica.
4. La web vieja (`web/index.html`) **sigue funcionando hasta la Etapa 10**. Es la especificación funcional: ante cualquier duda de comportamiento, abrirla y replicar lo que hace.
5. Los endpoints con llamadas a yfinance (`/api/dashboard`, `/api/tax`) requieren red y tardan. Para verificación manual usar los datos reales ya presentes en `processing/`.
6. Código y comentarios de frontend en inglés; textos visibles de UI en español (como la web actual).

---

## Estado de partida (verificado 2026-07-03)

```
Global-Position/
├── main.py          # CLI, 492 líneas. Contiene _compute_metrics()
├── server.py        # FastAPI, 757 líneas, 16 endpoints bajo /api
├── sources.json     # Config fuentes/benchmark/ajustes
├── requirements.txt # pandas numpy yfinance matplotlib seaborn fastapi uvicorn[standard] python-multipart
├── input/           # CSVs fuente (sap_stock.csv)
├── processing/      # operaciones.csv (109 filas), crypto.csv (36 filas), cache/, backup/
├── output/          # PDFs e informes
├── src/             # config, schemas, loaders, market_data, core, tax, reporter
├── tests/           # 51 tests (test_logic, test_loaders, test_integration)
└── web/index.html   # SPA vanilla JS actual (a reemplazar)
```

Datos ya migrados y sincronizados con el notebook original. No hay migración de datos pendiente salvo lo indicado en Etapa 0.

---

## ETAPA 0 — Verificación de paridad y archivo histórico

**Objetivo:** dejar constancia documentada de que el sistema reproduce el notebook antes de tocar nada.

### Pasos

0.1. `git status` — confirmar árbol limpio. Si hay cambios sin commitear, commitearlos primero como `chore: estado previo a migración frontend`.

0.2. Ejecutar el pipeline completo:
```powershell
python main.py   # opción 1 (Run Analysis)
```
Capturar del output: `capital_total`, `valor_total`, `plusvalia_total`, `rentabilidad_total`, `cagr_total`, `twr_total_total`, `twr_total_anual`, y los bloques de acciones y crypto.

0.3. Crear `docs/paridad.md` con:
- Tabla de métricas capturadas en 0.2 con fecha de ejecución.
- Nota: el notebook `C:\Proyectos\FIN\GlobalPositionPersonal\GlobalPosition.ipynb` contiene la última ejecución con sus outputs guardados (celdas 15, 21, 23). Extraer de esos outputs las mismas métricas y anotarlas en una segunda columna. Diferencias esperables: céntimos por fecha de precio distinta. Si hay desviación >1% en alguna métrica, **PARAR y reportar** — no continuar la migración.

0.4. Copiar informes históricos del notebook:
```powershell
Copy-Item "C:\Proyectos\FIN\GlobalPositionPersonal\informes\*" -Destination "output\hist-inf\" -Recurse -Force
```

0.5. Commit: `docs: verificación de paridad con notebook y archivo de informes históricos`

### Verificación
- [ ] `docs/paridad.md` existe con ambas columnas rellenas
- [ ] `output/hist-inf/` contiene los PDFs del notebook
- [ ] Desviación de métricas <1%

---

## ETAPA 1 — Reestructuración a `backend/`

**Objetivo:** mover el código Python a `backend/` dejando los datos (`input/`, `processing/`, `output/`) en la raíz.

### Pasos

1.1. Mover con git para preservar historia:
```powershell
git mv main.py backend/main.py       # crear backend/ primero: New-Item -ItemType Directory backend
git mv server.py backend/server.py
git mv src backend/src
git mv tests backend/tests
git mv sources.json backend/sources.json
git mv requirements.txt backend/requirements.txt
```
(Si `git mv` a directorio nuevo falla, crear `backend/` y mover en dos pasos.)

1.2. Editar `backend/src/config.py`:
- `BASE_DIR` hoy es `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → tras el movimiento resolvería a `backend/`. Cambiar a:
```python
# Repo root: backend/src/config.py → tres niveles arriba
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```
- `SOURCES_FILE` debe apuntar al nuevo sitio: `os.path.join(BASE_DIR, "backend", "sources.json")`.
- `INPUT_DIR`, `PROCESSING_DIR`, `OUTPUT_DIR` NO cambian (siguen colgando de `BASE_DIR` = raíz del repo).

1.3. Refactor mínimo de import circular: `server.py` hace `from main import _compute_metrics`. Mover la función `_compute_metrics` de `backend/main.py` a `backend/src/core.py` renombrada `compute_metrics` (mismo cuerpo, sin cambios de lógica). Actualizar:
- `backend/main.py`: `from src.core import compute_metrics` (o `core.compute_metrics` si ya importa `core`), borrar la definición local, actualizar llamadas.
- `backend/server.py`: eliminar `from main import _compute_metrics`, usar `core.compute_metrics`.

1.4. Revisar rutas relativas restantes:
```powershell
# Desde la raíz del repo
Select-String -Path backend\*.py,backend\src\*.py -Pattern '"(input|processing|output|web)[/\\]|os\.path\.join\("' 
```
Toda referencia a datos debe pasar por `config.*`. `WEB_DIR` en `server.py` se corrige en Etapa 2.

1.5. Tests: `backend/tests/conftest.py` puede necesitar ajustar `sys.path`. Ejecutar desde `backend/`:
```powershell
cd backend; python -m pytest tests/ -v
```
Arreglar imports hasta verde (51/51).

1.6. Verificar CLI y server desde la raíz:
```powershell
python backend\main.py     # menú aparece, opción 5 sale
python backend\server.py   # levanta en :8000; web vieja aún rota (WEB_DIR) — se arregla en 2.1
```

1.7. Commit: `refactor: reestructura código Python bajo backend/, datos permanecen en raíz`

### Verificación
- [ ] 51 tests verdes
- [ ] `python backend\main.py` opción 1 corre completa y genera PDF en `output/`
- [ ] `git log --follow backend/src/core.py` muestra historia previa

---

## ETAPA 2 — Endurecimiento de la API

**Objetivo:** contratos Pydantic + OpenAPI para generar tipos TypeScript. Sin cambiar payloads.

### 2.1 Ajustes generales en `backend/server.py`

- `WEB_DIR = os.path.join(config.BASE_DIR, "web")` (temporal; en Etapa 9 pasa a `frontend/dist`).
- Reactivar docs: `app = FastAPI(title="Global Position", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)`.
- CORS para dev del frontend:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"], allow_headers=["*"])
```
- Añadir `GET /api/health` → `{"ok": True}`.
- Añadir `GET /api/report/pdf`: busca el `resumen_cartera_*.pdf` más reciente en `config.OUTPUT_DIR` y lo devuelve con `FileResponse` (404 si no hay). Añadir `POST /api/report/generate` que ejecute la generación del PDF (reutilizar la misma ruta de código que la opción 1 del CLI usa para `reporter`; si requiere pipeline completo, ejecutarlo y devolver `{"ok": True, "file": nombre}`).

### 2.2 Modelos Pydantic — crear `backend/src/api_models.py`

Definir EXACTAMENTE estos modelos (derivados del código actual; los payloads no cambian):

```python
from pydantic import BaseModel

class XY(BaseModel):
    x: str            # "YYYY-MM-DD"
    y: float

class Metrics(BaseModel):
    # Totales
    fecha_actual: str | None = None
    dias_totales: int | None = None
    anhos_totales: float | None = None
    capital_total: float | None = None
    valor_total: float | None = None
    plusvalia_total: float | None = None
    rentabilidad_total: float | None = None
    cagr_total: float | None = None
    twr_total_total: float | None = None
    twr_total_anual: float | None = None
    # Acciones
    capital_aportado_acciones: float | None = None
    valor_actual_acciones: float | None = None
    plusvalia_acciones: float | None = None
    rentabilidad_acciones: float | None = None
    cagr_acciones: float | None = None
    twr_acciones_total: float | None = None
    twr_acciones_anual: float | None = None
    peso_acciones: float | None = None
    # Crypto
    capital_aportado_crypto: float | None = None
    valor_actual_crypto: float | None = None
    plusvalia_crypto: float | None = None
    rentabilidad_crypto: float | None = None
    cagr_crypto: float | None = None
    twr_cripto_total: float | None = None
    twr_cripto_anual: float | None = None
    peso_crypto: float | None = None
    # Benchmark
    benchmark_ticker: str | None = None
    benchmark_name: str | None = None
    benchmark_total: float | None = None
    benchmark_annual: float | None = None

    model_config = {"extra": "allow"}   # _compute_metrics puede añadir claves

class AssetSlice(BaseModel):
    name: str
    symbol: str
    value: float

class CryptoSlice(AssetSlice):
    pct: float

class CorrelationAsset(BaseModel):
    name: str
    symbol: str
    weight: float

class CorrelationPair(BaseModel):
    asset_1: str
    asset_2: str
    corr: float

class CorrelationMatrix(BaseModel):
    labels: list[str]
    values: list[list[float | None]]

class Correlation(BaseModel):
    threshold_pct: float
    assets: list[CorrelationAsset]
    matrix: CorrelationMatrix
    top_positive: list[CorrelationPair]
    top_negative: list[CorrelationPair]
    history_days: int
    note: str

class PortfolioChart(BaseModel):
    value: list[XY]
    invested: list[XY]
    benchmark: list[XY] | None = None

class CryptoChart(BaseModel):
    value: list[XY]
    invested: list[XY]

class DashboardResponse(BaseModel):
    # `error` presente solo si no hay operaciones (comportamiento actual conservado)
    error: str | None = None
    metrics: Metrics | None = None
    has_crypto: bool | None = None
    portfolio_chart: PortfolioChart | None = None
    composition: list[AssetSlice] | None = None
    composition_full: list[AssetSlice] | None = None
    portfolio_total_value: float | None = None
    top_assets: list[AssetSlice] | None = None
    correlation: Correlation | None = None
    crypto_chart: CryptoChart | None = None
    crypto_breakdown: list[CryptoSlice] | None = None
    crypto_total_value: float | None = None
    failed_tickers: list[str] | None = None

class Operation(BaseModel):
    Date: str
    Product: str | None = None
    ticker: str | None = None
    ISIN: str | None = None
    Quantity: float | None = None
    Price: float | None = None
    Coin: str | None = None
    Value: float | None = None

class OperationCreate(BaseModel):
    Date: str
    Product: str
    ISIN: str
    Quantity: float
    Price: float
    Coin: str = "EUR"
    ticker: str = ""
    Value: float | None = None    # si falta: ±|Quantity×Price| (negativo en compra)

class CryptoOperation(BaseModel):
    Date: str
    Product: str | None = None
    Coin: str | None = None
    Quantity: float | None = None
    ticker: str | None = None
    model_config = {"extra": "allow"}

class CryptoOperationCreate(BaseModel):
    Date: str
    Coin: str
    Quantity: float               # > 0
    Product: str = ""
    ticker: str = ""

class TaxResponse(BaseModel):
    gains: list[dict]
    annual: list[dict]
    by_ticker: list[dict]

class OkResponse(BaseModel):
    ok: bool

class UploadResponse(BaseModel):
    saved: list[str]

class SourceFileInfo(BaseModel):
    file: str
    source: str
    enabled: bool

class SourceDataEntry(BaseModel):
    date: str
    quantity: float
    price: float
    value: float

class SourceData(BaseModel):
    source: str
    file: str
    ticker: str | None = None
    product: str | None = None
    coin: str | None = None
    total_qty: float | None = None
    total_value: float | None = None
    entries: list[SourceDataEntry]
    error: str | None = None
```

### 2.3 Anotar endpoints

En `server.py`, añadir `response_model=` a cada ruta y sustituir el parseo manual `await request.json()` de los POST por los modelos `*Create` (validación equivalente a la actual: fecha parseable, Quantity≠0 / >0, etc. — conservar los mensajes de error en español). Tabla de contrato:

| Ruta | Método | Request | Response model |
|---|---|---|---|
| `/api/health` | GET | — | `OkResponse` |
| `/api/dashboard?refresh=bool` | GET | — | `DashboardResponse` |
| `/api/operations` | GET | — | `list[Operation]` |
| `/api/operations` | POST | `OperationCreate` | `dict {ok, row}` |
| `/api/crypto` | GET | — | `list[CryptoOperation]` |
| `/api/crypto` | POST | `CryptoOperationCreate` | `dict {ok, row}` |
| `/api/tax` | GET | — | `TaxResponse` |
| `/api/sources` | GET | — | `dict` (JSON raw de sources.json) |
| `/api/sources` | POST | `dict` | `OkResponse` |
| `/api/upload` | POST | multipart files | `UploadResponse` |
| `/api/source-data` | GET | — | `list[SourceData]` |
| `/api/pending-files` | GET | — | `list[str]` |
| `/api/source-files` | GET | — | `list[SourceFileInfo]` |
| `/api/pending-files/{filename}` | DELETE | — | `OkResponse` |
| `/api/invalidate` | GET | — | `OkResponse` |
| `/api/report/pdf` | GET | — | FileResponse (PDF) |
| `/api/report/generate` | POST | — | `dict {ok, file}` |

**Importante:** los nombres de campo con mayúscula (`Date`, `Product`…) son los del CSV canónico — NO renombrar a snake_case, la web vieja y los CSVs dependen de ellos.

### 2.4 Tests de contrato

Crear `backend/tests/test_api.py` con `fastapi.testclient.TestClient`:
- `GET /api/health` → 200 `{"ok": true}`.
- `GET /api/operations` → 200, lista, primer elemento valida contra `Operation`.
- `POST /api/operations` con body inválido (Quantity=0) → 4xx.
- `GET /api/sources` → 200 dict con clave `stock_sources`.
- `GET /api/pending-files` → 200 lista.
- NO testear `/api/dashboard` ni `/api/tax` sin mock (red). Si es fácil reutilizar los mocks de `test_integration.py`, añadir un test de `/api/dashboard` mockeado; si no, omitir.

2.5. Verificar manualmente: `python backend\server.py`, abrir `http://localhost:8000/api/docs` — 17 rutas visibles con schemas. Abrir `http://localhost:8000` — web vieja sigue funcionando (dashboard carga, operaciones lista).

2.6. Commit: `feat(api): modelos Pydantic, OpenAPI, CORS dev, health y endpoints de informe`

### Verificación
- [ ] pytest verde (51 + nuevos)
- [ ] `/api/openapi.json` descargable y contiene `DashboardResponse`
- [ ] Web vieja 100% funcional contra la API anotada

---

## ETAPA 3 — Scaffold del frontend

**Objetivo:** proyecto Vite + React + TS + Tailwind + shadcn/ui con layout, tema y navegación.

### Pasos

3.1. Prerequisitos (verificar, instalar si falta):
```powershell
node --version    # ≥ 20; si falta: winget install OpenJS.NodeJS.LTS
corepack enable; pnpm --version   # habilita pnpm
```

3.2. Crear proyecto (desde la raíz del repo):
```powershell
pnpm create vite frontend --template react-ts
cd frontend
pnpm install
pnpm add @tanstack/react-query react-router-dom
pnpm add -D tailwindcss @tailwindcss/vite openapi-typescript prettier eslint-config-prettier
pnpm add recharts date-fns lucide-react
pnpm dlx shadcn@latest init   # estilo: default; base color: slate; CSS variables: yes
```
Componentes shadcn que se usarán (añadir ahora): `pnpm dlx shadcn@latest add button card table tabs dialog input label select badge sonner skeleton dropdown-menu`

3.3. `frontend/vite.config.ts`:
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
```

3.4. Tema: portar las variables CSS de `web/index.html` (líneas ~14-40: `--bg:#060a12`, `--card:#0d1828`, `--accent:#6366f1`, `--green:#10b981`, `--red`, `--txt:#e2e8f0`, `--txt2:#7d8fa8`, etc.) al CSS global de Tailwind como tokens del tema dark. La app es dark-only (como la actual). Fuente Inter: instalar `@fontsource-variable/inter` (autohospedada, sin CDN).

3.5. Estructura:
```
frontend/src/
├── api/
│   ├── schema.d.ts      # GENERADO — no editar a mano
│   ├── client.ts        # fetch wrapper tipado
│   └── queries.ts       # hooks TanStack Query por endpoint
├── components/
│   ├── ui/              # shadcn (generado)
│   ├── layout/AppShell.tsx      # sidebar + <Outlet/>
│   └── charts/          # se rellena en etapas 5-8
├── lib/format.ts        # fmtEur, fmtPct, fmtDate, fmtNum (locale es-ES)
├── pages/               # Dashboard.tsx, Operations.tsx, Crypto.tsx, Tax.tsx, Import.tsx, Settings.tsx
├── App.tsx              # Router + QueryClientProvider
└── main.tsx
```

3.6. Generación de tipos — script en `frontend/package.json`:
```json
"scripts": { "gen:api": "openapi-typescript http://localhost:8000/api/openapi.json -o src/api/schema.d.ts" }
```
Ejecutar con el backend levantado. `client.ts`: wrapper mínimo `apiGet<T>(path)`, `apiPost<T>(path, body)`, `apiDelete(path)`, `apiUpload(path, files)` que lanza `Error` con el `detail` de FastAPI en no-2xx.

3.7. `queries.ts` — un hook por endpoint: `useDashboard(refresh?)`, `useOperations()`, `useCrypto()`, `useTax()`, `useSources()`, `usePendingFiles()`, `useSourceFiles()`, `useSourceData()` + mutations `useAddOperation()`, `useAddCrypto()`, `useSaveSources()`, `useUpload()`, `useDeletePending()`, `useInvalidate()`. Cada mutation invalida las queries afectadas (p.ej. añadir operación → invalida `operations` y `dashboard`).

3.8. `AppShell.tsx`: sidebar fija con 6 entradas (iconos lucide-react): Dashboard `/`, Operaciones `/operaciones`, Crypto `/crypto`, Fiscalidad `/fiscalidad`, Importar `/importar`, Ajustes `/ajustes`. Replicar estética de la sidebar actual (fondo `--bg2`, item activo con acento). Rutas en `App.tsx` con `createBrowserRouter`; páginas placeholder que muestran el nombre.

3.9. `lib/format.ts`:
```ts
export const fmtEur = (v: number | null | undefined) =>
  v == null ? '—' : v.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })
export const fmtPct = (v: number | null | undefined, dec = 2) =>
  v == null ? '—' : `${v.toLocaleString('es-ES', { maximumFractionDigits: dec, minimumFractionDigits: dec })} %`
export const fmtDate = (iso: string) => /* 'dd/MM/yyyy' con date-fns */
```

3.10. Verificar: backend en `:8000`, `pnpm dev` en `:5173` → shell con navegación funciona; página de prueba muestra `useDashboard()` crudo en `<pre>` (borrarla después).

3.11. Commit: `feat(frontend): scaffold Vite+React+TS+Tailwind+shadcn con layout, tema y cliente API tipado`

### Verificación
- [ ] `pnpm build` sin errores TS
- [ ] `pnpm gen:api` regenera schema sin diff inesperado
- [ ] Navegación entre 6 rutas, tema dark idéntico en espíritu a la web vieja

---

## ETAPA 4 — Página Dashboard

**La página más compleja. Fuente de verdad: sección Dashboard de `web/index.html`.**

### Componentes (en `components/charts/` y `pages/Dashboard.tsx`)

4.1. **KpiGrid** — tarjetas desde `metrics`:
- Fila principal: Valor total (`valor_total`), Capital aportado (`capital_total`), Plusvalía (`plusvalia_total`, verde/rojo según signo), Rentabilidad (`rentabilidad_total`), CAGR (`cagr_total`), TWR anual (`twr_total_anual`).
- Si `benchmark_ticker` presente: tarjeta benchmark con `benchmark_name`, `benchmark_annual` y **alfa** = `twr_total_anual − benchmark_annual`.
- Sub-bloques Acciones y Crypto (colapsables o tabs): capital/valor/plusvalía/CAGR/TWR/peso de cada sleeve (claves `*_acciones`, `*_crypto`/`twr_cripto_*` — ojo: las claves crypto de TWR usan "cripto").

4.2. **PortfolioChart** (Recharts `ComposedChart`): series `portfolio_chart.value` (línea, `--accent`), `portfolio_chart.invested` (línea discontinua, `--txt2`), `portfolio_chart.benchmark` si no-null (línea, color distinto). Área entre value e invested cuando value ≥ invested (verde translúcido). Eje X temporal (los datos vienen como `{x:'YYYY-MM-DD', y}`), tooltip con `fmtEur`. Selector de rango: 1A / 3A / 5A / Todo (filtrado client-side).

4.3. **CompositionDonut** (Recharts `PieChart`): datos de `composition` (ya trae "Otros" agrupado <2%). Tooltip: nombre, valor €, % sobre `portfolio_total_value`. Leyenda lateral con `top_assets` (top 10 con valor y peso).

4.4. **CryptoSection** — solo si `has_crypto`: gráfico línea `crypto_chart.value` vs `crypto_chart.invested` + chips de `crypto_breakdown` (símbolo, valor €, pct).

4.5. **CorrelationCard** — desde `correlation`:
- Si `note` no vacío y matriz vacía: mostrar nota.
- Heatmap de `matrix.values` con `matrix.labels` (grid CSS con celdas coloreadas rojo→verde según valor −1..1, valor numérico dentro; no hace falta librería).
- Listas `top_positive` / `top_negative` (5 pares c/u).

4.6. **Toolbar**: botón "Actualizar precios" → `GET /api/dashboard?refresh=true` (mutation + spinner + toast), botón "Generar PDF" → `POST /api/report/generate` seguido de descarga de `GET /api/report/pdf`. Aviso si `failed_tickers` no vacío (toast/banner con la lista).

4.7. Estados: skeletons durante carga (el dashboard tarda si el caché de precios está frío); si la respuesta trae `error`, pantalla vacía con mensaje y CTA a Importar.

4.8. Verificar contra la web vieja lado a lado (misma cifra en cada KPI, mismas curvas). Commit: `feat(frontend): página Dashboard con paridad funcional`

---

## ETAPA 5 — Páginas Operaciones y Crypto

5.1. **Operations.tsx** — `useOperations()`:
- DataTable (shadcn table + estado propio; ~110 filas, sin virtualización):
  columnas Date, Product, ticker, ISIN, Quantity, Price, Coin, Value. Sort por cualquier columna (default Date desc). Filtros: select ticker, select Coin, rango de fechas (2 inputs date), búsqueda libre (matchea Product/ISIN/ticker). Footer con nº de filas visibles y suma de Value filtrado.
- Dialog "Añadir operación" → form validado (zod opcional o validación manual) → `useAddOperation()`. Campos y reglas = `OperationCreate` (Value opcional con hint "se calcula como ±Cantidad×Precio"). Toast éxito/error.

5.2. **Crypto.tsx** — `useCrypto()`:
- Tabla: Date (con hora), Coin, Quantity, Product, ticker. Filtro por Coin.
- Tarjetas de balance por moneda: suma de Quantity por Coin (client-side) + si dashboard cargado, valor EUR de `crypto_breakdown`.
- Dialog "Añadir movimiento" → `useAddCrypto()` (Quantity > 0, Coin obligatorio).

5.3. Verificar vs web vieja (mismos totales, mismos filtros). Commit: `feat(frontend): páginas Operaciones y Crypto`

---

## ETAPA 6 — Página Fiscalidad

6.1. **Tax.tsx** — `useTax()` (query con `staleTime` alto; tarda por FX):
- Tabs: "Por año" (`annual`), "Por ticker" (`by_ticker`), "Detalle ventas" (`gains`).
- `gains`: tabla con fecha_venta, ticker, cantidad, importes EUR y plusvalía (verde/rojo). Las claves exactas de columnas: inspeccionar la respuesta real de `/api/tax` (vienen de `tax.calculate_fifo_gains`) y tipar un interface local si `schema.d.ts` los deja como `dict`.
- Filtro por año fiscal en el detalle.
- Botón "Exportar CSV": generar client-side desde `gains` (Blob + download) — la web vieja descarga `output/plusvalias_fifo.csv`; replicar el que exista, comprobar en `web/index.html` cómo lo hace y hacer lo mismo.

6.2. Commit: `feat(frontend): página Fiscalidad FIFO`

---

## ETAPA 7 — Página Importar

7.1. **Import.tsx**:
- Dropzone (drag&drop + click): acepta `.csv` múltiples → `useUpload()` → refetch `pending-files`.
- Lista "Archivos pendientes" (`usePendingFiles()`): nombre + botón eliminar (`useDeletePending`, con confirm dialog).
- Lista "Archivos fuente" (`useSourceFiles()`): nombre, fuente asociada, badge enabled.
- Panel "Datos de fuentes" (`useSourceData()`): por cada fuente, tabla de entries (date, quantity, price, value) con totales.
- **Procesamiento:** revisar en `web/index.html` qué endpoint dispara el procesado de pendientes (ingesta a operaciones.csv). Si la web vieja lo hace vía algún endpoint existente, replicar. Si NO existe endpoint (el procesado solo está en CLI opción 2/3), añadir en backend `POST /api/process` que llame a las mismas funciones de `loaders` que usa el CLI y devuelva `{added, duplicates, files}` — y botón "Procesar pendientes" en esta página. Documentar en el commit cuál fue el caso.

7.2. Commit: `feat(frontend): página Importar con upload y gestión de pendientes`

---

## ETAPA 8 — Página Ajustes

8.1. **Settings.tsx** — `useSources()` / `useSaveSources()`:
- Tab "Fuentes": cards por cada `stock_sources[]` y `crypto_sources[]` con switch enabled, campos name/file_pattern y column_map + defaults en tabla clave-valor editable.
- Tab "Benchmark": ticker + name.
- Tab "Ajustes precio/FX": tablas editables de `price_adjustments` y `fx_adjustments` (ignorar/preservar claves `_comment`).
- Tab "JSON": editor `<textarea>` monoespaciado con el JSON completo, validación `JSON.parse` antes de guardar.
- Guardar: envía el objeto COMPLETO a `POST /api/sources` (el backend sobreescribe el archivo entero — no perder claves desconocidas como `zero_value_flow_from_est_eur_tickers` o `_instructions`: partir siempre del objeto recibido y mutar solo lo editado).
- Tras guardar: toast + aviso "los cambios aplican al recalcular el dashboard".

8.2. Commit: `feat(frontend): página Ajustes con editor de sources.json`

---

## ETAPA 9 — Integración de build y single-command

9.1. `pnpm build` → verifica `frontend/dist/` generado.

9.2. `backend/server.py`: `WEB_DIR = os.path.join(config.BASE_DIR, "frontend", "dist")`. El catch-all SPA existente (`/{path:path}` → index.html) ya sirve para React Router. Arrancar `python backend\server.py` y probar las 6 rutas en `:8000` **con refresh del navegador en cada ruta** (verifica el fallback SPA).

9.3. Scripts raíz — crear `run.ps1`:
```powershell
param([ValidateSet('dev','build','serve','test')] [string]$cmd = 'serve')
switch ($cmd) {
  'dev'   { Start-Process powershell -ArgumentList '-NoExit','-Command','python backend\server.py'
            Set-Location frontend; pnpm dev }
  'build' { Set-Location frontend; pnpm build }
  'serve' { python backend\server.py }
  'test'  { Set-Location backend; python -m pytest tests/ -v; Set-Location ..\frontend; pnpm test run }
}
```

9.4. `.gitignore`: añadir `frontend/node_modules/`, `frontend/dist/`, `backend/__pycache__/` (revisar el existente).

9.5. Commit: `feat: build de frontend servido por FastAPI, scripts run.ps1`

### Verificación
- [ ] Con Vite APAGADO: `python backend\server.py` sirve app completa en `:8000`
- [ ] Refresh en `/fiscalidad` no da 404
- [ ] Upload de CSV funciona en producción (multipart contra mismo origen)

---

## ETAPA 10 — Calidad y cutover

10.1. Tests frontend (Vitest + Testing Library):
- `lib/format.test.ts`: fmtEur/fmtPct/fmtDate con casos borde (null, 0, negativos).
- `KpiGrid.test.tsx`: render con metrics mock, plusvalía negativa en rojo.
- `Operations.test.tsx`: filtrado por ticker y búsqueda libre con datos mock (mockear `queries.ts`).
- Script `"test": "vitest"` en package.json.

10.2. Lint: `pnpm add -D eslint prettier` ya configurado por Vite; `pnpm lint` sin errores. Backend: `pip install ruff`; `ruff check backend/` — corregir solo problemas triviales (imports sin uso), no refactorizar.

10.3. **Comparación final de paridad:** abrir web nueva y ejecutar `python backend\main.py` opción 1; anotar en `docs/paridad.md` una tercera columna "post-migración" con las métricas del dashboard. Deben coincidir con la columna de Etapa 0 (mismo día de precios ≈ idénticas).

10.4. Retirar web vieja:
```powershell
git rm -r web
```

10.5. Actualizar `README.md`: nueva estructura de carpetas, sección instalación (`pip install -r backend/requirements.txt`, `pnpm install` en frontend), comandos `run.ps1`, flujo de uso diario, sección desarrollo (dev con proxy, `pnpm gen:api` tras cambiar la API).

10.6. Archivar el notebook:
```powershell
New-Item -ItemType Directory -Force docs\archive
Compress-Archive -Path "C:\Proyectos\FIN\GlobalPositionPersonal\*" -DestinationPath "docs\archive\GlobalPositionPersonal_notebook_2026-07.zip"
```
**NO borrar `GlobalPositionPersonal/`** — dejar nota al usuario para que lo borre él cuando lleve unas semanas usando la app nueva.

10.7. Commit: `chore: retira web legacy, README v2, archivo del notebook` + tag:
```powershell
git tag -a v2.0.0 -m "Frontend React + retirada del notebook"
```

---

## Checklist de aceptación global

- [ ] `docs/paridad.md` con 3 columnas coincidentes (notebook / pre / post)
- [ ] `cd backend; python -m pytest tests/ -v` → verde (51 originales + contrato API)
- [ ] `cd frontend; pnpm test run` → verde; `pnpm build` sin warnings TS
- [ ] `python backend\server.py` sirve app completa sin Node en runtime
- [ ] 6 páginas con paridad funcional (verificadas lado a lado antes de borrar `web/`)
- [ ] `pnpm gen:api` no produce diff (tipos sincronizados con OpenAPI)
- [ ] CLI `python backend\main.py` intacta (las 5 opciones funcionan)
- [ ] PDF descargable desde la web; informes en `output/`
- [ ] README actualizado; notebook zip en `docs/archive/`; tag `v2.0.0`

## Fuera de alcance (NO implementar)

Rebalanceo, dividendos, alertas, PWA/móvil, multi-benchmark, snapshots programados, reemplazo del PDF matplotlib. Ver backlog en [PLAN.md](PLAN.md) §7.
