# Global Position Manager

Herramienta de análisis de cartera de inversión personal implementada en Python. Agrega transacciones de múltiples fuentes (broker, RSUs, exchanges de crypto, etc.), descarga precios de mercado, detecta splits automáticamente y genera un informe PDF con la evolución y métricas de la cartera.

## Instalación

```bash
pip install -r requirements.txt
```

Dependencias: `pandas`, `numpy`, `yfinance`, `matplotlib`, `seaborn`.

## Estructura del proyecto

```
Global-Position/
├── main.py              # Punto de entrada CLI
├── sources.json         # Configuración de fuentes de datos externas
├── requirements.txt
├── input/               # Coloca aquí los CSV nuevos de transacciones
├── processing/
│   ├── operaciones.csv  # Base de datos consolidada de operaciones (stocks)
│   └── crypto.csv       # Base de datos de operaciones crypto
├── output/              # Informes PDF generados
│   └── hist/            # Histórico de informes
└── src/
    ├── config.py        # Rutas, constantes, carga de sources.json
    ├── loaders.py       # Carga genérica de datos (stocks + crypto)
    ├── market_data.py   # Resolución de tickers, precios, tipos de cambio
    ├── core.py          # Splits, valoración de cartera, TWR
    └── reporter.py      # Generación de informe PDF (matplotlib)
```

## Uso

```bash
python main.py
```

### Opciones del menú

| Opción | Descripción |
|--------|-------------|
| **1. Run Analysis** | Carga operaciones, descarga precios/FX, detecta splits, calcula cartera, genera PDF |
| **2. Process Transactions** | Escanea `input/` buscando CSVs nuevos, los parsea y añade a `processing/operaciones.csv` |
| **3. Process Crypto** | Procesa transacciones crypto desde `processing/crypto.csv` según `sources.json` |
| **4. Exit** | Cierra la aplicación |

## Fuentes de datos

### Operaciones de broker (Degiro)

El archivo principal es `processing/operaciones.csv` con el esquema:

```
Date,Product,ISIN,Quantity,Price,Coin,Value,eur,ticker
```

Para añadir nuevas transacciones, coloca el CSV de exportación de Degiro en `input/` y usa la opción 2 del menú. El sistema:
- Detecta y mapea columnas automáticamente
- Resuelve tickers vía ISIN usando yfinance Search
- Elimina duplicados
- Borra los CSV procesados de `input/`

### Fuentes externas configurables (`sources.json`)

El sistema es **genérico y extensible**. Puedes añadir cualquier fuente de datos adicional (RSUs, vests, exchanges de crypto, etc.) editando `sources.json`:

```json
{
    "stock_sources": [
        {
            "name": "Mi fuente de acciones",
            "enabled": true,
            "file_pattern": "mi_fuente_*.csv",
            "column_map": {
                "Date": "fecha_columna",
                "Quantity": "cantidad_columna",
                "Price": "precio_columna"
            },
            "defaults": {
                "Product": "Nombre del producto",
                "ISIN": "XX0000000000",
                "Coin": "EUR",
                "ticker": "TICK"
            }
        }
    ],
    "crypto_sources": [
        {
            "name": "Mi exchange",
            "enabled": true,
            "file_pattern": "exchange*.csv",
            "column_map": {
                "Date": "fecha_col",
                "Coin": "moneda_col",
                "Quantity": "cantidad_col",
                "Operation": "tipo_col"
            },
            "coins": ["BTC", "ETH"],
            "buy_operations": ["Buy", "Deposit"]
        }
    ]
}
```

**stock_sources**: Cada entrada define un CSV externo con operaciones de acciones. `column_map` traduce las columnas del CSV al esquema interno. `defaults` rellena valores fijos por fila.

**crypto_sources**: Cada entrada define un exchange de crypto. `coins` filtra las monedas a rastrear. `buy_operations` define qué tipos de operación se consideran compras.

Coloca los CSV correspondientes en `input/` (para stock sources) o `processing/` (para crypto) y pon `"enabled": true`.

## Cálculos

- **Splits**: Detección automática desde operaciones (pares valor-neutral) + verificación con yfinance. Ajusta cantidades y precios históricos.
- **Valoración**: `cantidad_acumulada × precio_EUR` por ticker por día, sumado para toda la cartera.
- **CAGR**: Tasa de crecimiento anual compuesta sobre el valor total vs. capital invertido.
- **TWR**: Time-Weighted Return calculado con chain-linking diario, con guardas para denominadores pequeños.
- **Cripto**: Valoración independiente con balances acumulados y coste medio en EUR.

## Informe PDF

El informe generado en `output/` incluye:
- Evolución temporal de la cartera de acciones
- Composición por ticker (gráfico de tarta)
- Evolución de crypto (si hay datos)
- Resumen con métricas: valor total, CAGR, TWR, desglose por ticker y por crypto
