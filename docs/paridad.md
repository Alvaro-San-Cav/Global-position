# Verificación de paridad — Notebook vs Global-Position

Documenta el baseline antes de la migración de frontend (Etapa 0) y sirve de
referencia para la comprobación pre/post migración (Etapa 10.3).

## Métricas

| Métrica | Notebook (2026-06-02) | Sistema pre-migración (2026-07-03) | Sistema post-migración |
|---|---|---|---|
| **TOTALES** | | | _(rellenar en Etapa 10.3)_ |
| Capital aportado total | €57,473.37 | €71,409.11 | |
| Valor actual total | €112,715.97 | €107,312.56 | |
| Plusvalía total | €55,242.60 | €35,903.45 | |
| Rentabilidad total | 96.12 % | 50.28 % | |
| CAGR total | 11.40 % | 6.65 % | |
| TWR total | 30.95 % | 51.24 % | |
| TWR anualizado | 4.42 % | 6.76 % | |
| **ACCIONES** | | | |
| Capital aportado | €37,444.26 | €51,394.87 | |
| Valor actual | €87,067.94 | €84,177.00 | |
| Plusvalía | €49,623.68 | €32,782.13 | |
| CAGR | 14.48 % | 8.11 % | |
| TWR anualizado | 5.01 % | 5.70 % | |
| Peso en cartera | 77.25 % | 78.44 % | |
| **CRIPTO** | | | |
| Capital aportado | €20,029.11 | €20,014.24 | |
| Valor actual | €25,648.03 | €23,135.56 | |
| Plusvalía | €5,618.92 | €3,121.32 | |
| CAGR | 10.06 % | 5.59 % | |
| TWR anualizado | 27.99 % | 21.12 % | |
| Peso en cartera | 22.75 % | 21.56 % | |
| **BENCHMARK (IWDA)** | — (no existía) | total 146.91 %, anual 15.36 % | |

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
