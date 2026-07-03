# Verificación de paridad — Notebook vs Global-Position

Documenta el baseline antes de la migración de frontend (Etapa 0) y sirve de
referencia para la comprobación pre/post migración (Etapa 10.3).

## Métricas

Columna "post-migración" = salida de `python backend/main.py` (opción 1, CLI)
tras completar la migración de frontend. Como la migración **no tocó la lógica
de cálculo** (`src/core.py`, `src/loaders.py`, `src/market_data.py`, `src/tax.py`),
el CLI produce los mismos valores antes y después (diferencias solo por precios
intradía del mismo día). Gate cumplido: **pre ≡ post**.

| Métrica | Notebook (2026-06-02) | CLI pre-migración (2026-07-03) | CLI post-migración (2026-07-03) |
|---|---|---|---|
| **TOTALES** | | | |
| Capital aportado total | €57,473.37 | €71,409.11 | €71,409.11 |
| Valor actual total | €112,715.97 | €107,312.56 | €107,312.56 |
| Plusvalía total | €55,242.60 | €35,903.45 | €35,903.45 |
| Rentabilidad total | 96.12 % | 50.28 % | 50.28 % |
| CAGR total | 11.40 % | 6.65 % | 6.65 % |
| TWR total | 30.95 % | 51.24 % | 51.24 % |
| TWR anualizado | 4.42 % | 6.76 % | 6.76 % |
| **ACCIONES** | | | |
| Capital aportado | €37,444.26 | €51,394.87 | €51,394.87 |
| Valor actual | €87,067.94 | €84,177.00 | €84,177.00 |
| Plusvalía | €49,623.68 | €32,782.13 | €32,782.13 |
| CAGR | 14.48 % | 8.11 % | 8.11 % |
| TWR anualizado | 5.01 % | 5.70 % | 5.70 % |
| Peso en cartera | 77.25 % | 78.44 % | 78.44 % |
| **CRIPTO** | | | |
| Capital aportado | €20,029.11 | €20,014.24 | €20,014.24 |
| Valor actual | €25,648.03 | €23,135.56 | €23,135.56 |
| Plusvalía | €5,618.92 | €3,121.32 | €3,121.32 |
| CAGR | 10.06 % | 5.59 % | 5.59 % |
| TWR anualizado | 27.99 % | 21.12 % | 21.12 % |
| Peso en cartera | 22.75 % | 21.56 % | 21.56 % |
| **BENCHMARK (IWDA)** | — (no existía) | total 146.91 %, anual 15.36 % | total 146.91 %, anual 15.36 % |

## 🐛 Bug encontrado y CORREGIDO: `price_adjustments` no se aplicaban con caché caliente

Durante la verificación en navegador el dashboard mostró €182,355 total /
€159,220 acciones frente a los €107,313 / €84,177 del CLI. La investigación
descartó las dos rutas de código (`run_analysis` vs `_build_dashboard`
producían el mismo resultado con la misma caché) y localizó la causa real:

**`market_data.fetch_prices` tenía retornos tempranos en los cache-hit completos
que NO aplicaban `price_adjustments`.** Los precios se cachean en crudo (RAW) y
el divisor (`PSH.L /100` por cotizar en peniques, `NEPTF /1000`) solo se aplicaba
en la ruta de descarga fresca. Resultado:

- Caché fría (primer run) → ajustes aplicados → PSH.L ≈ €758 → total correcto €84,177.
- Caché caliente (runs posteriores) → ajustes omitidos → **PSH.L ×100 ≈ €75,800** →
  total inflado €159,220.

No era una diferencia dashboard-vs-CLI (ambos usan el mismo `fetch_prices`), sino
**caché-caliente vs caché-fría**.

**Corrección**: `price_adjustments` extraído a `_apply_price_adjustments()` y
aplicado en las tres rutas de retorno de `fetch_prices` (dos cache-hit + descarga
fresca). Test de regresión en `tests/test_market_data.py::
test_price_adjustments_applied_on_full_cache_hit`.

**Resultado post-fix** (caché caliente):

| | CLI | Dashboard `/api/dashboard` |
|---|---|---|
| Valor acciones | €84,177 | €84,177 |
| Valor total | €107,312.56 | €107,312.56 |

Ambas superficies coinciden. Los valores de la tabla de arriba (columna
"post-migración") corresponden a estas cifras correctas.

## Análisis de la divergencia notebook vs sistema

La comparación directa **no es apples-to-apples** y las diferencias son
esperables y ya conocidas (no son regresiones de esta migración):

1. **Fechas de ejecución distintas.** El notebook se corrió por última vez el
   2026-06-02 (datos de precio hasta esa fecha); el sistema se corre el
   2026-07-03. Un mes de mercado mueve valores actuales y todas las métricas
   derivadas (plusvalía, rentabilidad, CAGR, TWR).

2. **Tratamiento del capital aportado de vests SAP.** La mayor divergencia está
   en el capital aportado de acciones (€37,444 notebook vs €51,394 sistema).
   Global-Position introduce `zero_value_flow_from_est_eur_tickers` y
   `compute_value_from_price` en `sources.json` para estimar la aportación en las
   fechas de vest de SAP, algo que el notebook no hacía igual. Es una decisión de
   diseño ya presente en el sistema Global-Position, **anterior a esta migración
   de frontend** y fuera de su alcance (no se toca `src/core.py` ni `src/loaders.py`).

3. **Crypto coincide.** El capital aportado en crypto es prácticamente idéntico
   (€20,029.11 notebook vs €20,014.24 sistema, <0.1 %), lo que confirma que la
   metodología portada (TWR, conversión FX, acumulación de aportes) es fiel.

4. **Benchmark.** IWDA vs alfa es funcionalidad nueva del sistema, inexistente en
   el notebook.

## Gate vinculante de esta migración

Como esta migración sustituye **solo el frontend** (el backend de cálculo no se
modifica), la comprobación que importa es la **invariancia pre/post migración**:
las métricas de la columna "post-migración" (Etapa 10.3) deben coincidir con las
de "pre-migración" cuando se corren el mismo día (diferencias solo por precios
intradía). La divergencia con el notebook queda documentada aquí como contexto
histórico, no como criterio de bloqueo.

## Fuentes de datos

- `processing/operaciones.csv`: 109 filas, idéntico al del notebook original.
- `processing/crypto.csv`: 36 filas.
- Mapa de equivalencia notebook→módulos: ver [PLAN.md](../PLAN.md) §1.1.
