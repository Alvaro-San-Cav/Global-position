# Global Position Manager

Herramienta de análisis de cartera de inversión personal. Agrega transacciones
de múltiples fuentes (broker, RSUs, exchanges de crypto), descarga precios de
mercado y tipos de cambio, detecta splits automáticamente, compara el
rendimiento con un benchmark de referencia, calcula plusvalías fiscales (FIFO)
y muestra todo en un **dashboard web moderno** (React) además de un informe PDF.

> **v2.0** — El frontend es ahora una SPA React + Vite + TypeScript (sustituye a
> la web vanilla y al notebook original). El backend Python (FastAPI + pandas)
> se conserva íntegro. Ver [PLAN.md](PLAN.md) e
> [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) para el detalle de la migración.

---

## Estructura del proyecto

```
Global-Position/
├── backend/                 # Todo el código Python
│   ├── main.py              # CLI (5 opciones)
│   ├── server.py            # FastAPI: API /api/* + sirve frontend/dist
│   ├── sources.json         # Configuración de fuentes, benchmark, ajustes
│   ├── requirements.txt
│   ├── src/
│   │   ├── config.py        # Rutas, constantes, logger, validate_sources()
│   │   ├── api_models.py    # Contratos Pydantic de request/response
│   │   ├── schemas.py       # Contrato canónico de operaciones
│   │   ├── loaders.py       # Carga y normalización (stocks + crypto)
│   │   ├── market_data.py   # Tickers, precios con caché, tipos de cambio
│   │   ├── core.py          # Splits, valoración, TWR, benchmark, métricas
│   │   ├── tax.py           # Plusvalías fiscales FIFO
│   │   └── reporter.py      # Informe PDF (matplotlib)
│   └── tests/               # 61 tests (lógica, loaders, integración, API)
│
├── frontend/                # SPA React + Vite + TypeScript + Tailwind v4
│   ├── src/
│   │   ├── api/             # client.ts, queries.ts, types.ts, schema.d.ts
│   │   ├── components/      # ui/ (shadcn), charts/, dashboard/, layout/…
│   │   ├── pages/           # Dashboard, Operations, Crypto, Tax, Import, Settings
│   │   └── lib/             # format.ts (es-ES), utils.ts
│   └── dist/                # Build de producción (generado, gitignored)
│
├── input/                   # CSVs nuevos a importar
├── processing/              # operaciones.csv, crypto.csv, cache/, backup/
├── output/                  # PDFs e histórico (hist-inf/)
├── run.ps1                  # Lanzador (dev / build / serve / test)
└── docs/paridad.md          # Verificación de paridad con el notebook original
```

---

## Instalación

Requisitos: **Python 3.12+**, **Node 20+**, **pnpm** (`corepack enable` o `npm i -g pnpm`).

```powershell
# Backend
pip install -r backend/requirements.txt

# Frontend
cd frontend; pnpm install; cd ..
```

---

## Uso diario (producción)

```powershell
# 1. Construir el frontend una vez (o tras cambios de UI)
.\run.ps1 build

# 2. Arrancar el servidor: sirve API + web en http://localhost:8000
.\run.ps1 serve
```

Abre `http://localhost:8000`. Flujo típico:

```
Descargar CSV de Degiro/Binance → arrastrar a "Importar" en la web
→ "Procesar pendientes" → el Dashboard se actualiza (caché incremental de precios)
→ PDF / fiscalidad bajo demanda
```

### Páginas

| Página | Contenido |
|--------|-----------|
| **Dashboard** | KPIs (valor, capital, plusvalía, CAGR, TWR, alfa vs benchmark), evolución del portfolio, composición, correlaciones, sección crypto; botones «Actualizar precios» y «Generar PDF» |
| **Operaciones** | Tabla con orden y filtros (ticker, moneda, fechas, búsqueda); alta manual |
| **Crypto** | Movimientos, balance por moneda con valor EUR |
| **Fiscalidad** | Resumen FIFO por año fiscal y ticker, detalle de ventas, export CSV |
| **Importar** | Upload drag & drop, archivos pendientes/fuente, procesar |
| **Ajustes** | Editor de `sources.json` (fuentes, benchmark, ajustes precio/FX, JSON raw) |

### CLI (equivalente, sin navegador)

```powershell
$env:PYTHONIOENCODING='utf-8'; python backend/main.py
```

| Opción | Acción |
|--------|--------|
| 1 | Run Analysis → pipeline completo + PDF |
| 2 | Procesar transacciones de acciones de `input/` |
| 3 | Procesar exportaciones de crypto de `input/` |
| 4 | Tax Report – Plusvalías FIFO |
| 5 | Salir |

---

## Desarrollo

```powershell
.\run.ps1 dev
```

Levanta el backend (uvicorn con reload en `:8000`) y el frontend (Vite en
`:5173`, con proxy `/api → :8000`). Edita en `frontend/src` con hot-reload.

Tras cambiar la API (endpoints o modelos Pydantic), regenera los tipos TS:

```powershell
cd frontend; pnpm gen:api    # requiere el backend levantado
```

### Tests

```powershell
.\run.ps1 test          # pytest backend + vitest frontend
```

- Backend: 61 tests (lógica financiera, loaders/dedup, integración con mocks de
  yfinance, contratos de API). No requieren red.
- Frontend: formateadores, KpiGrid, DataTable.

---

## Configuración de fuentes (`backend/sources.json`)

Toda la configuración de fuentes, benchmark y ajustes vive en
`backend/sources.json`, editable también desde la página **Ajustes**.

### Fuentes de acciones personalizadas (ej. RSUs/vests SAP)

```json
"stock_sources": [{
  "name": "SAP Vests",
  "enabled": true,
  "file_pattern": "sap*.csv",
  "column_map": { "Date": "date", "Quantity": "available", "Price": "strike_price" },
  "defaults": { "Product": "SAP SE", "ISIN": "DE0007164600", "Coin": "USD", "Value": 0.0, "ticker": "SAP.DE" }
}]
```

### Fuentes crypto (ej. Binance)

```json
"crypto_sources": [{
  "name": "Binance",
  "enabled": true,
  "file_pattern": "binance*.csv",
  "column_map": { "Date": "UTC_Time", "Coin": "Coin", "Quantity": "Change", "Operation": "Operation" },
  "coins": ["BTC", "ETH"],
  "buy_operations": ["Transaction Buy", "Binance Convert", "Crypto Box"]
}]
```

### Benchmark y ajustes

```json
"benchmark": { "ticker": "IWDA.AS", "name": "MSCI World (IWDA)" },
"price_adjustments": { "NEPTF": 1000, "PSH.L": 100 },
"fx_adjustments":    { "GBX": 100 }
```

`price_adjustments`/`fx_adjustments` dividen el precio/FX descargado (útil para
valores en milésimas o peniques). Deja `benchmark.ticker` vacío para deshabilitarlo.

---

## Cálculos financieros

| Métrica | Descripción |
|---------|-------------|
| **Rentabilidad** | `(valor − capital) / capital` |
| **CAGR** | `(valor / capital)^(1/años) − 1` |
| **TWR** | Chain-linking diario eliminando el efecto de las aportaciones; anualizado |
| **Alfa** | `TWR_anual_cartera − rendimiento_anual_benchmark` |
| **Plusvalías** | FIFO por lotes (criterio AEAT), resumen por año fiscal y ticker |

Los splits se detectan por dos vías (pares compra+venta de valor neto cero, y el
historial de yfinance) y se aplican retroactivamente a las cantidades.

### Trazabilidad

- **Backup automático** de `operaciones.csv`/`crypto.csv` en `processing/backup/`
  antes de cada escritura (retención 30 días).
- **Log de auditoría** en `processing/ingesta.log`.
- **Caché incremental** de precios/FX en `processing/cache/` (solo descarga los
  días que faltan).

---

## Nota de paridad

`docs/paridad.md` documenta la equivalencia con el notebook original y una
**discrepancia pre-existente** entre el valor de acciones del CLI y el del
dashboard web (distinta resolución de tickers en cada ruta). No fue introducida
por la migración de frontend; se recomienda unificar ambas rutas como tarea
aparte.
