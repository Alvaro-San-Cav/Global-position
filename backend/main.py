"""
Global Position Manager – CLI entry point.

Replicates the full notebook workflow as a consumable script:
  1. Load & update stock operations
  2. Merge custom stock sources (configured in sources.json)
  3. Download prices & FX
  4. Detect & apply splits
  5. Calculate stock portfolio
  6. Load & calculate crypto portfolio (if configured)
  7. Compute consolidated metrics (CAGR, TWR, etc.)
  8. Generate PDF report
"""

import sys
import os

import numpy as np
import pandas as pd

from src import config, loaders, market_data, core, reporter, tax


# ─────────────────────────────────────────────────────────────────────────
#  1. Run full analysis
# ─────────────────────────────────────────────────────────────────────────

def run_analysis():
    print("\n🚀 Starting Global Position Analysis...\n")

    # ── Validate sources.json config ─────────────────────────────────
    try:
        config.validate_sources()
    except ValueError as e:
        print(f"❌ Error en sources.json: {e}")
        return

    # ── Load stock operations ────────────────────────────────────────
    try:
        df_ops = loaders.load_operations()
        print(f"✅ Operations loaded: {len(df_ops)} records.")
    except Exception as e:
        print(f"❌ Error loading operations: {e}")
        return

    if df_ops.empty:
        print("⚠️  No operations found in processing/operaciones.csv")
        return

    # ── Merge custom stock sources (from sources.json) ───────────────
    df_ops = loaders.merge_custom_stock_sources(df_ops)

    # ── Resolve tickers ──────────────────────────────────────────────
    try:
        df_ops = market_data.update_tickers_in_operations(df_ops)
        tickers = [t for t in df_ops['ticker'].dropna().unique()
                   if t and str(t).strip()]
        currencies = df_ops['Coin'].dropna().unique().tolist()
        print(f"ℹ️  Unique tickers: {len(tickers)}")
    except Exception as e:
        print(f"❌ Error resolving tickers: {e}")
        return

    # ── Crypto data ──────────────────────────────────────────────────
    df_crypto = loaders.load_crypto_operations()
    has_crypto = df_crypto is not None and len(df_crypto) > 0
    crypto_coins: list[str] = []
    if has_crypto:
        crypto_coins = df_crypto['Coin'].dropna().unique().tolist()
        print(f"🪙  Crypto coins: {crypto_coins}")

    # ── Market data ──────────────────────────────────────────────────
    try:
        start_date = df_ops['Date'].min()
        print("\n📥 Fetching historical prices...")
        prices = market_data.fetch_prices(tickers, start_date)

        print("📥 Fetching FX rates...")
        fx_rates = market_data.fetch_fx_rates(currencies, start_date,
                                               crypto_coins=crypto_coins or None)
    except Exception as e:
        print(f"❌ Error fetching market data: {e}")
        return

    # ── Identify and Exclude Failed Assets ───────────────────────────
    df_failed_ops = pd.DataFrame()
    df_failed_crypto = pd.DataFrame()
    failed_tickers = []
    failed_cryptos = []

    if not prices.empty:
        downloaded_tickers = set(prices.columns)
        failed_tickers = [t for t in tickers if t not in downloaded_tickers]
    else:
        failed_tickers = tickers

    if failed_tickers:
        df_failed_ops = df_ops[df_ops['ticker'].isin(failed_tickers)].copy()
        df_ops = df_ops[~df_ops['ticker'].isin(failed_tickers)].copy()

    if has_crypto:
        downloaded_fx = set(fx_rates.columns)
        failed_cryptos = [c for c in crypto_coins if c not in downloaded_fx]
        if failed_cryptos:
            df_failed_crypto = df_crypto[df_crypto['Coin'].isin(failed_cryptos)].copy()
            df_crypto = df_crypto[~df_crypto['Coin'].isin(failed_cryptos)].copy()
            if df_crypto.empty:
                has_crypto = False

    failed_assets_summary = core.summarize_failed_assets(
        df_failed_ops if not df_failed_ops.empty else None,
        df_failed_crypto if not df_failed_crypto.empty else None,
        fx_rates
    )

    if not failed_assets_summary.empty:
        print("\n⚠️ The following assets could not be fully downloaded and are excluded from calculations:")
        print(failed_assets_summary.to_string(index=False))

    # ── Splits ───────────────────────────────────────────────────────
    try:
        df_adj = core.SplitManager.apply_splits(df_ops)
    except Exception as e:
        print(f"❌ Error applying splits: {e}")
        return

    # ── Stock portfolio ──────────────────────────────────────────────
    try:
        valor_total_cartera, aporte_diario, valor_cartera = \
            core.calculate_stock_portfolio(df_adj, prices, fx_rates)

        if valor_total_cartera.empty:
            print("⚠️  Portfolio value is empty – check data availability.")
            return
    except Exception as e:
        print(f"❌ Error calculating stock portfolio: {e}")
        import traceback; traceback.print_exc()
        return

    # ── Crypto portfolio ─────────────────────────────────────────────
    valor_total_crypto = aporte_crypto = valor_crypto_eur = None
    if has_crypto:
        try:
            print("\n🪙 Calculating crypto portfolio...")
            valor_total_crypto, aporte_crypto, valor_crypto_eur = \
                core.calculate_crypto_portfolio(df_crypto, fx_rates)
            if valor_total_crypto is not None and not valor_total_crypto.empty:
                print(f"✅ Crypto value: € {valor_total_crypto.iloc[-1]:,.2f}")
            else:
                has_crypto = False
        except Exception as e:
            print(f"⚠️  Crypto calculation failed: {e}")
            has_crypto = False

    # ── Benchmark comparison ─────────────────────────────────────────
    benchmark_series = None
    bm_ticker, bm_name = config.get_benchmark()
    if bm_ticker:
        print(f"\n📊 Descargando benchmark ({bm_name}: {bm_ticker})...")
        benchmark_series, bm_total, bm_annual = core.compute_benchmark_return(
            bm_ticker, start_date=df_ops['Date'].min()
        )
        if not benchmark_series.empty:
            print(f"   Benchmark {bm_name}: total={bm_total*100:.2f}%  anual={bm_annual*100:.2f}%")

    # ── Consolidated metrics (notebook step 9) ───────────────────────
    metrics = core.compute_metrics(
        valor_total_cartera, aporte_diario,
        valor_total_crypto if has_crypto else None,
        aporte_crypto if has_crypto else None,
        valor_crypto_eur if has_crypto else None,
    )
    if benchmark_series is not None and not benchmark_series.empty:
        metrics['benchmark_ticker'] = bm_ticker
        metrics['benchmark_name']   = bm_name
        metrics['benchmark_total']  = bm_total * 100
        metrics['benchmark_annual'] = bm_annual * 100

    # ── Print summary to console ─────────────────────────────────────
    _print_summary(metrics, has_crypto)

    # ── Generate PDF ─────────────────────────────────────────────────
    try:
        reporter.generate_full_report(
            valor_total_cartera=valor_total_cartera,
            aporte_diario=aporte_diario,
            valor_cartera=valor_cartera,
            valor_total_crypto=valor_total_crypto if has_crypto else None,
            aporte_crypto_eur_acumulado=aporte_crypto if has_crypto else None,
            valor_crypto_eur=valor_crypto_eur if has_crypto else None,
            metrics=metrics,
            failed_assets_summary=failed_assets_summary if not failed_assets_summary.empty else None,
            benchmark_series=benchmark_series,
        )
    except Exception as e:
        print(f"❌ Error generating PDF: {e}")
        import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────
#  2. Process new transactions (from input/)
# ─────────────────────────────────────────────────────────────────────────

def process_transactions():
    print("\n🔎 Checking input/ for new transactions...\n")
    try:
        df_ops = loaders.load_operations()
        df_updated = loaders.process_new_transactions(df_ops)

        print("🔍 Resolving tickers...")
        df_updated = market_data.update_tickers_in_operations(df_updated)

        loaders.save_operations(df_updated)
        print("✅ Transaction processing complete.")
    except Exception as e:
        print(f"❌ Error processing transactions: {e}")


# ─────────────────────────────────────────────────────────────────────────
#  3. Process crypto transactions (from input/)
# ─────────────────────────────────────────────────────────────────────────

def process_crypto():
    print("\n🪙 Checking input/ for crypto exports...\n")
    try:
        df = loaders.process_crypto_transactions()
        if df is not None and len(df) > 0:
            print(f"\n📊 Crypto summary:")
            print(f"   Total transactions: {len(df)}")
            for coin in df['Coin'].unique():
                qty = df[df['Coin'] == coin]['Quantity'].sum()
                print(f"   • {coin}: {qty:.8f}")
        print("✅ Crypto processing complete.")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────────────────
#  5. Tax report (FIFO gains/losses)
# ─────────────────────────────────────────────────────────────────────────

def run_tax_report():
    print("\n💶 Calculando plusvalías fiscales (FIFO)...\n")
    try:
        config.validate_sources()
    except ValueError as e:
        print(f"❌ Error en sources.json: {e}")
        return

    df_ops = loaders.load_operations()
    if df_ops.empty:
        print("⚠️  No hay operaciones cargadas.")
        return

    df_ops = loaders.merge_custom_stock_sources(df_ops)
    df_ops = market_data.update_tickers_in_operations(df_ops)

    tickers = [t for t in df_ops['ticker'].dropna().unique() if t and str(t).strip()]
    currencies = df_ops['Coin'].dropna().unique().tolist()
    start_date = df_ops['Date'].min()

    print("📥 Descargando FX para conversión EUR...")
    fx_rates = market_data.fetch_fx_rates(currencies, start_date)

    df_adj = core.SplitManager.apply_splits(df_ops)
    df_gains = tax.calculate_fifo_gains(df_adj, fx_rates)

    if df_gains.empty:
        print("ℹ️  No hay ventas registradas — sin plusvalías que calcular.")
        return

    print("\n📊 PLUSVALÍAS FIFO POR AÑO FISCAL")
    print("=" * 70)
    annual = tax.annual_tax_summary(df_gains)
    for _, row in annual.iterrows():
        sign = "+" if row['plusvalia_total_eur'] >= 0 else ""
        print(f"\n  {int(row['annyo'])}:")
        print(f"    Plusvalía total:   {sign}€{row['plusvalia_total_eur']:,.2f}")
        print(f"    Ganancias:        +€{row['plusvalias_eur']:,.2f}")
        print(f"    Pérdidas:          €{row['minusvalias_eur']:,.2f}")
        print(f"    Nº de ventas:      {int(row['n_ventas'])}")

    print("\n\n📋 DETALLE POR OPERACIÓN DE VENTA:")
    print("=" * 70)
    cols = ['fecha_venta', 'ticker', 'qty_vendida', 'precio_venta_eur', 'coste_base_eur', 'plusvalia_eur']
    print(df_gains[cols].to_string(index=False))

    # Export to CSV
    out_path = os.path.join(config.OUTPUT_DIR, "plusvalias_fifo.csv")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    df_gains.to_csv(out_path, index=False)
    print(f"\n💾 Exportado: {out_path}")


# ─────────────────────────────────────────────────────────────────────────
#  Metrics computation  (mirrors notebook step 9)
# ─────────────────────────────────────────────────────────────────────────
#  Console summary  (mirrors notebook step 9 prints)
# ─────────────────────────────────────────────────────────────────────────

def _print_summary(m: dict, has_crypto: bool):
    arrow = '📈' if m['plusvalia_total'] >= 0 else '📉'

    print("\n" + "=" * 80)
    print("💼 RESUMEN GENERAL DE LA CARTERA COMPLETA".center(80))
    print("=" * 80 + "\n")
    print(f"📅 Fecha de análisis: {m['fecha_actual']}")
    print(f"📆 Período total: {m['dias_totales']} días ({m['anhos_totales']:.2f} años)\n")

    print("=" * 80)
    print("💰 TOTALES CONSOLIDADOS".center(80))
    print("=" * 80)
    print(f"📥 Capital aportado total:       €{m['capital_total']:>18,.2f}")
    print(f"📊 Valor actual total:           €{m['valor_total']:>18,.2f}")
    print(f"{arrow} Plusvalía/Minusvalía total:     €{m['plusvalia_total']:>18,.2f}")
    print("-" * 80)
    print(f"📊 Rentabilidad total:           {m['rentabilidad_total']:>18.2f} %")
    print(f"📈 CAGR (anualizado):            {m['cagr_total']:>18.2f} %")
    print(f"⏱️  TWR Total:                    {m['twr_total_total']:>18.2f} %")
    print(f"⏱️  TWR Anualizado:               {m['twr_total_anual']:>18.2f} %")
    print("=" * 80 + "\n")

    print("=" * 80)
    print("📦 DESGLOSE POR TIPO DE ACTIVO".center(80))
    print("=" * 80)

    a = '📈' if m['plusvalia_acciones'] >= 0 else '📉'
    print("\n📈 ACCIONES:")
    print("-" * 80)
    print(f"   💰 Capital aportado:          €{m['capital_aportado_acciones']:>18,.2f}")
    print(f"   📊 Valor actual:              €{m['valor_actual_acciones']:>18,.2f}")
    print(f"   {a} Plusvalía:                 €{m['plusvalia_acciones']:>18,.2f}")
    print(f"   📊 Rentabilidad total:        {m['rentabilidad_acciones']:>18.2f} %")
    print(f"   📈 CAGR:                      {m['cagr_acciones']:>18.2f} %")
    print(f"   ⏱️  TWR Total:                 {m['twr_acciones_total']:>18.2f} %")
    print(f"   ⏱️  TWR Anualizado:            {m['twr_acciones_anual']:>18.2f} %")
    print(f"   🎯 Peso en cartera:           {m['peso_acciones']:>18.2f} %")

    if has_crypto:
        c = '📈' if m['plusvalia_crypto'] >= 0 else '📉'
        print("\n🪙 CRIPTOMONEDAS:")
        print("-" * 80)
        print(f"   💰 Capital aportado:          €{m['capital_aportado_crypto']:>18,.2f}")
        print(f"   📊 Valor actual:              €{m['valor_actual_crypto']:>18,.2f}")
        print(f"   {c} Plusvalía:                 €{m['plusvalia_crypto']:>18,.2f}")
        print(f"   📊 Rentabilidad total:        {m['rentabilidad_crypto']:>18.2f} %")
        print(f"   📈 CAGR:                      {m['cagr_crypto']:>18.2f} %")
        print(f"   ⏱️  TWR Total:                 {m['twr_cripto_total']:>18.2f} %")
        print(f"   ⏱️  TWR Anualizado:            {m['twr_cripto_anual']:>18.2f} %")
        print(f"   🎯 Peso en cartera:           {m['peso_crypto']:>18.2f} %")

    print("\n" + "=" * 80 + "\n")


# ─────────────────────────────────────────────────────────────────────────
#  CLI menu
# ─────────────────────────────────────────────────────────────────────────

def main():
    while True:
        print("\n=== GLOBAL POSITION MANAGER ===")
        print("1. 📊 Run Analysis & Generate Report")
        print("2. 📥 Process New Stock Transactions (from input/)")
        print("3. 🪙 Process Crypto Transactions (from input/)")
        print("4. 💶 Tax Report – Plusvalías FIFO")
        print("5. 🚪 Exit")

        choice = input("Select an option: ").strip()

        if choice == "1":
            run_analysis()
        elif choice == "2":
            process_transactions()
        elif choice == "3":
            process_crypto()
        elif choice == "4":
            run_tax_report()
        elif choice == "5":
            print("Bye!")
            sys.exit()
        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()
