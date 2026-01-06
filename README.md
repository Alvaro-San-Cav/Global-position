# Global Position Manager

> [!WARNING]
> **⚠️ WORK IN PROGRESS** - Este proyecto está todavía en desarrollo activo y **no es todavía mínimamente funcional**. Utilízalo bajo tu propio riesgo.

Herramienta para gestionar y analizar tu cartera de inversiones.

## 🚀 Instalación

1.  **Instalar dependencias**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Estructura de directorios**:
    ```
    Global-Position/
    ├── input/           # Coloca aquí los CSV de transacciones (se eliminan tras procesarse)
    ├── processing/      # Base de datos de operaciones (operaciones.csv)
    ├── output/          # Informes PDF generados
    └── src/             # Código fuente
    ```

## 🖥️ Uso

Ejecuta el dashboard principal:
```bash
python main.py
```

### Opciones del menú:

#### 1. 📊 Run Analysis & Generate Report
- Carga las operaciones desde `processing/operaciones.csv`.
- Descarga precios de mercado y tipos de cambio.
- Detecta y aplica splits automáticamente.
- Calcula el valor de la cartera y genera un informe PDF en `output/`.

#### 2. 📥 Process New Transactions
- Escanea `input/` buscando archivos `.csv` (incluyendo `Transactions.csv`).
- Parsea las transacciones y busca los tickers correspondientes (usando yfinance y Selenium).
- Añade las nuevas transacciones a `processing/operaciones.csv`.
- **Elimina los archivos CSV procesados** de `input/`.
- Detecta duplicados: las entradas que ya existen en `operaciones.csv` no se añaden de nuevo.

#### 3. 🚪 Exit
Cierra la aplicación.

## 📁 Formato de entrada

El archivo `Transactions.csv` debe tener el formato de exportación de Degiro o similar, con columnas como:
- `Date`, `Product`, `ISIN`, `Quantity`, `Price`, `Value EUR`, etc.

El sistema detecta automáticamente la estructura y mapea las columnas necesarias.

## 📊 Formato de salida

El archivo `processing/operaciones.csv` tiene el esquema:
```
Date,Product,ISIN,Quantity,Price,Coin,Value,eur,ticker
```

## 🔧 Dependencias principales

- `pandas` - Manipulación de datos
- `yfinance` - Datos de mercado
- `selenium` - Búsqueda de tickers
- `reportlab` - Generación de PDFs
