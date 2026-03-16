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

from src import config, loaders, market_data, core, reporter


# ─────────────────────────────────────────────────────────────────────────
#  1. Run full analysis
# ─────────────────────────────────────────────────────────────────────────

def run_analysis():
    print("\n🚀 Starting Global Position Analysis...\n")

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

    # ── Consolidated metrics (notebook step 9) ───────────────────────
    metrics = _compute_metrics(
        valor_total_cartera, aporte_diario,
        valor_total_crypto if has_crypto else None,
        aporte_crypto if has_crypto else None,
        valor_crypto_eur if has_crypto else None,
    )

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
#  Metrics computation  (mirrors notebook step 9)
# ─────────────────────────────────────────────────────────────────────────

def _compute_metrics(valor_total_cartera, aporte_diario,
                     valor_total_crypto, aporte_crypto,
                     valor_crypto_eur) -> dict:
    m: dict = {}
    has_crypto = (valor_total_crypto is not None and not valor_total_crypto.empty)

    # ── Acciones ─────────────────────────────────────────────────────
    cap_acc = aporte_diario.iloc[-1]
    val_acc = valor_total_cartera.iloc[-1]
    pv_acc  = val_acc - cap_acc
    rent_acc = (pv_acc / cap_acc * 100) if cap_acc > 0 else 0

    dias_acc  = (valor_total_cartera.index[-1] - valor_total_cartera.index[0]).days
    anhos_acc = dias_acc / 365.25
    cagr_acc  = ((val_acc / cap_acc) ** (1 / anhos_acc) - 1) * 100 \
                if anhos_acc > 0 and cap_acc > 0 else 0

    twr_acc_t, twr_acc_a = core.compute_twr(valor_total_cartera, aporte_diario)
    m.update(
        capital_aportado_acciones=cap_acc,
        valor_actual_acciones=val_acc,
        plusvalia_acciones=pv_acc,
        rentabilidad_acciones=rent_acc,
        cagr_acciones=cagr_acc,
        twr_acciones_total=twr_acc_t * 100,
        twr_acciones_anual=twr_acc_a * 100,
    )

    # ── Crypto ───────────────────────────────────────────────────────
    cap_cry = val_cry = pv_cry = rent_cry = cagr_cry = 0.0
    twr_cry_t = twr_cry_a = 0.0
    dias_cry = anhos_cry = 0

    if has_crypto and aporte_crypto is not None:
        cap_cry = aporte_crypto.iloc[-1]
        val_cry = valor_total_crypto.iloc[-1]
        pv_cry  = val_cry - cap_cry
        rent_cry = (pv_cry / cap_cry * 100) if cap_cry > 0 else 0

        dias_cry  = (valor_total_crypto.index[-1] - valor_total_crypto.index[0]).days
        anhos_cry = dias_cry / 365.25
        cagr_cry  = ((val_cry / cap_cry) ** (1 / anhos_cry) - 1) * 100 \
                    if anhos_cry > 0 and cap_cry > 0 else 0

        twr_cry_t, twr_cry_a = core.compute_twr(valor_total_crypto, aporte_crypto)
        twr_cry_t *= 100; twr_cry_a *= 100

    m.update(
        capital_aportado_crypto=cap_cry,
        valor_actual_crypto=val_cry,
        plusvalia_crypto=pv_cry,
        rentabilidad_crypto=rent_cry,
        cagr_crypto=cagr_cry,
        twr_cripto_total=twr_cry_t,
        twr_cripto_anual=twr_cry_a,
    )

    # ── Totales combinados ───────────────────────────────────────────
    cap_tot = cap_acc + cap_cry
    val_tot = val_acc + val_cry
    pv_tot  = val_tot - cap_tot
    rent_tot = (pv_tot / cap_tot * 100) if cap_tot > 0 else 0

    dias_tot  = max(dias_acc, dias_cry) if has_crypto else dias_acc
    anhos_tot = dias_tot / 365.25
    cagr_tot  = ((val_tot / cap_tot) ** (1 / anhos_tot) - 1) * 100 \
                if anhos_tot > 0 and cap_tot > 0 else 0

    # TWR combinado
    if has_crypto:
        common_idx = valor_total_cartera.index.union(valor_total_crypto.index).sort_values()
        vc  = valor_total_cartera.reindex(common_idx).ffill().fillna(0)
        vcy = valor_total_crypto.reindex(common_idx).ffill().fillna(0)
        v_comb = vc + vcy
        a_acc  = aporte_diario.reindex(common_idx).ffill().fillna(0)
        a_cry  = aporte_crypto.reindex(common_idx).ffill().fillna(0)
        a_comb = a_acc + a_cry
        twr_tot_t, twr_tot_a = core.compute_twr(v_comb, a_comb)
    else:
        twr_tot_t, twr_tot_a = twr_acc_t, twr_acc_a

    peso_acc = (val_acc / val_tot * 100) if val_tot > 0 else 100
    peso_cry = (val_cry / val_tot * 100) if val_tot > 0 else 0

    m.update(
        capital_total=cap_tot,
        valor_total=val_tot,
        plusvalia_total=pv_tot,
        rentabilidad_total=rent_tot,
        cagr_total=cagr_tot,
        twr_total_total=twr_tot_t * 100,
        twr_total_anual=twr_tot_a * 100,
        peso_acciones=peso_acc,
        peso_crypto=peso_cry,
        dias_totales=dias_tot,
        anhos_totales=anhos_tot,
        fecha_actual=valor_total_cartera.index[-1].strftime('%Y-%m-%d'),
    )
    return m


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
        print("4. 🚪 Exit")

        choice = input("Select an option: ").strip()

        if choice == "1":
            run_analysis()
        elif choice == "2":
            process_transactions()
        elif choice == "3":
            process_crypto()
        elif choice == "4":
            print("Bye!")
            sys.exit()
        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()
