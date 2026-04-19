# Global Position Manager

Herramienta de análisis de cartera de inversión personal. Agrega transacciones de múltiples fuentes (broker, RSUs, exchanges de crypto), descarga precios de mercado y tipos de cambio, detecta splits automáticamente, compara el rendimiento con un benchmark de referencia, calcula plusvalías fiscales (FIFO) y genera un informe PDF con la evolución y métricas de la cartera.

---

## Instalación

```bash
pip install -r requirements.txt
```

Dependencias: `pandas`, `numpy`, `yfinance`, `matplotlib`, `seaborn`, `fastapi`, `uvicorn`, `python-multipart`.

---

## Estructura del proyecto

```
Global-Position/
├── main.py              # Punto de entrada CLI
├── server.py            # Servidor web FastAPI
├── sources.json         # Configuración de fuentes, benchmark y ajustes de precio/FX
├── requirements.txt
│
├── input/               # Coloca aquí los CSV nuevos de transacciones
│
├── processing/
│   ├── operaciones.csv  # Base de datos consolidada de operaciones (acciones)
│   ├── crypto.csv       # Base de datos de operaciones crypto
│   ├── ingesta.log      # Log de auditoría de cada importación y split detectado
│   ├── backup/          # Copias de seguridad automáticas de operaciones.csv y crypto.csv
│   └── cache/           # Caché incremental de precios y tipos de cambio (prices.csv, fx.csv)
│
├── output/
│   ├── resumen_cartera_YYYY-MM-DD.pdf  # Último informe generado
│   ├── plusvalias_fifo.csv             # Exportación fiscal FIFO
│   └── hist-inf/        # Histórico de informes anteriores
│
├── src/
│   ├── config.py        # Rutas, constantes, logger compartido, validate_sources()
│   ├── schemas.py       # Contrato canónico de operaciones: validate_dataframe(), coerce_types()
│   ├── loaders.py       # Carga y normalización de datos (stocks + crypto)
│   ├── market_data.py   # Resolución de tickers, precios con caché, tipos de cambio
│   ├── core.py          # Splits, valoración de cartera, TWR, benchmark
│   ├── tax.py           # Cálculo de plusvalías fiscales FIFO
│   └── reporter.py      # Generación de informe PDF (matplotlib)
│
└── tests/
    ├── conftest.py      # Configuración pytest (codificación UTF-8 en Windows)
    ├── fixtures/        # CSVs sintéticos de prueba (Degiro, custom, Binance)
    ├── test_logic.py    # Tests unitarios de cálculos financieros (22 tests)
    ├── test_loaders.py  # Tests de carga, deduplicación y validación (20 tests)
    └── test_integration.py  # Tests E2E de pipeline completo con mocks (9 tests)
```

---

## Uso rápido

### CLI

```bash
python main.py
```

| Opción | Acción |
|--------|--------|
| **1. Run Analysis** | Pipeline completo: carga → precios/FX → splits → valoración → PDF |
| **2. Process Transactions** | Importa CSVs de `input/` a `processing/operaciones.csv` |
| **3. Process Crypto** | Importa exportaciones de exchange a `processing/crypto.csv` |
| **4. Tax Report – Plusvalías FIFO** | Calcula ganancias/pérdidas fiscales y exporta a CSV |
| **5. Exit** | Cierra la aplicación |

### Interfaz web

```bash
python server.py
```

Abre `http://localhost:8000` en el navegador. Páginas disponibles:

| Página | Contenido |
|--------|-----------|
| **Dashboard** | KPIs, evolución del portfolio, comparación vs benchmark, gráfico de composición |
| **Operaciones** | Tabla de transacciones con filtros por ticker, moneda, fecha y búsqueda libre |
| **Crypto** | Transacciones y balance por moneda |
| **Fiscalidad** | Resumen FIFO por año fiscal y ticker, descarga de CSV |
| **Importar** | Upload de CSVs con drag & drop directamente desde el navegador |
| **Ajustes** | Configuración de precios, FX, fuentes de datos y JSON raw |

---

## Flujo de datos

```
input/
  ├── Degiro export CSVs
  ├── Custom stock sources (RSU, vests…)
  └── Exchange crypto CSVs (Binance…)
         │
         ▼  [loaders.py]
processing/
  ├── operaciones.csv   ◄── backup automático antes de cada escritura
  ├── crypto.csv        ◄── backup automático antes de cada escritura
  └── ingesta.log       ◄── auditoría de archivos, filas y splits
         │
         ▼  [market_data.py + caché]
processing/cache/
  ├── prices.csv        ◄── precios históricos (actualización incremental)
  └── fx.csv            ◄── tipos de cambio (actualización incremental)
         │
         ▼  [core.py]
  Splits → Valoración → TWR → Benchmark
         │
         ├──► [reporter.py] → output/resumen_cartera_YYYY-MM-DD.pdf
         ├──► [tax.py]      → output/plusvalias_fifo.csv
         └──► [server.py]   → Web Dashboard (http://localhost:8000)
```

---

## Fuentes de datos (`sources.json`)

Toda la configuración de fuentes vive en `sources.json`. El sistema valida automáticamente que cada fuente tenga los campos obligatorios (`name`, `file_pattern`, `column_map`) antes de procesar.

### Operaciones de broker (Degiro)

El sistema detecta y mapea automáticamente el formato de exportación de Degiro (17 columnas posicionales o con cabeceras nombradas). Coloca el CSV en `input/` y ejecuta la opción 2.

El esquema interno es:

```
Date, Product, ISIN, Quantity, Price, Coin, Value, eur, ticker
```

### Fuentes de acciones personalizadas

```json
"stock_sources": [
    {
        "name": "SAP Vests",
        "enabled": true,
        "file_pattern": "sap_*.csv",
        "column_map": {
            "Date":     "date",
            "Quantity": "available",
            "Price":    "strike_price"
        },
        "defaults": {
            "Product": "SAP SE",
            "ISIN":    "DE0007164600",
            "Coin":    "USD",
            "Value":   0.0,
            "ticker":  "SAP"
        }
    }
]
```

- `column_map`: traduce columnas del CSV al esquema interno.
- `defaults`: valores fijos para columnas no presentes en el CSV.
- Coloca los CSV en `input/` con `"enabled": true`.

### Fuentes crypto

```json
"crypto_sources": [
    {
        "name": "Binance",
        "enabled": true,
        "file_pattern": "binance*.csv",
        "column_map": {
            "Date":      "UTC_Time",
            "Coin":      "Coin",
            "Quantity":  "Change",
            "Operation": "Operation"
        },
        "coins": ["BTC", "ETH"],
        "buy_operations": ["Transaction Buy", "Binance Convert", "Deposit"]
    }
]
```

### Benchmark de referencia

```json
"benchmark": {
    "ticker": "IWDA.AS",
    "name":   "MSCI World (IWDA)"
}
```

El ticker de yfinance se descarga y se escala al capital inicial para comparar visualmente en el gráfico. Se calcula el **alfa** (TWR anualizado de la cartera − rendimiento anualizado del benchmark). Alternativas comunes: `SPY`, `QQQ`, `VWCE.DE`. Deja `ticker` vacío para deshabilitar.

### Ajustes de precio y tipo de cambio

```json
"price_adjustments": { "NEPTF": 1000, "PSH.L": 100 },
"fx_adjustments":    { "GBX": 100 }
```

Divide el precio/FX descargado de yfinance por el valor indicado (útil para valores cotizados en milésimas o peniques).

---

## Trazabilidad y seguridad de datos

### Backup automático

Antes de cada escritura en `processing/operaciones.csv` o `processing/crypto.csv`, el sistema guarda una copia en `processing/backup/` con el nombre `{archivo}_{YYYY-MM-DD}.csv`. Los backups de más de 30 días se eliminan automáticamente (configurable en `config.BACKUP_RETENTION_DAYS`).

### Log de auditoría (`processing/ingesta.log`)

Cada operación de importación queda registrada:

```
2025-04-18 10:30:15 | INFO    | process_new_transactions: archivo=Transactions.csv filas_leídas=47 nuevas=12 duplicadas=35
2025-04-18 10:30:16 | INFO    | split detectado (yfinance post-holding): ticker=NVDA fecha=2024-06-10 ratio=10.0000
2025-04-18 10:30:17 | INFO    | save_operations: 210 filas guardadas → processing/operaciones.csv
```

Permite auditar qué archivos se procesaron, cuántas operaciones se añadieron y qué splits se detectaron automáticamente.

### Caché incremental de precios

Los precios y tipos de cambio se almacenan en `processing/cache/`. En ejecuciones posteriores, sólo se descargan los días que faltan desde la última actualización. Si el caché cubre hasta hoy, no se hace ninguna petición a yfinance.

---

## Cálculos financieros

### Splits de acciones

Detección por dos métodos:
1. **Operaciones**: pares de compra+venta el mismo día con valor neto cero (split registrado como transacción por el broker).
2. **yfinance**: consulta el historial de splits post-tenencia.

Las cantidades se ajustan retroactivamente. El mismo día del split se aplica lógica diferenciada según dirección (compra vs. venta).

### Valoración de cartera

```
valor_cartera[ticker][día] = cantidad_acumulada × precio_EUR
valor_total[día]           = Σ valor_cartera[ticker]
capital_aportado[día]      = Σ (compras en EUR) − Σ (ventas en EUR)
```

### Métricas de rendimiento

| Métrica | Descripción |
|---------|-------------|
| **Rentabilidad** | `(valor_actual − capital) / capital × 100%` |
| **CAGR** | `(valor_final / capital)^(1/años) − 1` |
| **TWR** | Chain-linking diario eliminando el efecto de las aportaciones. Anualizado con `(1+TWR)^(365.25/días) − 1` |
| **Alfa** | `TWR_anual_cartera − rendimiento_anual_benchmark` |

### Plusvalías fiscales (FIFO)

El módulo `src/tax.py` implementa el método FIFO (First In, First Out) conforme al criterio AEAT:

- Los lotes de compra se consumen en orden cronológico.
- Cada venta genera una fila con: ticker, fecha, cantidad, precio de venta (EUR), coste base (EUR) y plusvalía/minusvalía.
- Resumen agregado por año fiscal y por ticker.
- Exportación a `output/plusvalias_fifo.csv` y descarga directa desde la interfaz web.

---

## Tests

```bash
pytest tests/ -v
```

| Fichero | Cobertura |
|---------|-----------|
| `test_logic.py` | Detección y aplicación de splits, valoración de stocks y crypto, TWR, métricas |
| `test_loaders.py` | `clean_eu_float`, formatos Degiro (17 col. y cabeceras), deduplicación, `validate_dataframe`, `validate_sources` |
| `test_integration.py` | Pipeline E2E completo con mocks de yfinance: sin splits, con splits, métricas TWR |

Los tests no requieren conexión de red (yfinance está mockeado en los tests de integración) ni acceso a datos reales.

---

## Añadir una nueva fuente de datos

1. Edita `sources.json` y añade una entrada en `stock_sources` o `crypto_sources`.
2. Define `column_map` apuntando a las columnas de tu CSV y `defaults` para los campos que no existan.
3. Pon `"enabled": true`.
4. Coloca el CSV en `input/`.
5. Ejecuta la opción 2 (acciones) o 3 (crypto) desde la CLI, o usa la página **Importar** de la interfaz web.

El sistema validará automáticamente que el CSV produce el esquema requerido (`Date`, `Product`, `ISIN`, `Quantity`, `Price`, `Value`) antes de concatenar.
