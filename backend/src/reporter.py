"""
reporter.py – PDF report generation.

Produces a single-page PDF that mirrors the notebook output:
  • Stock evolution chart            (top-left)
  • Portfolio composition pie chart  (top-right)
  • Crypto evolution chart           (middle, if data available)
  • Consolidated summary text        (bottom: two columns)
"""

import glob
import os
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt                        # noqa: E402
import matplotlib.dates as mdates                      # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages   # noqa: E402
from matplotlib.lines import Line2D                    # noqa: E402
import pandas as pd                                    # noqa: E402

from . import config


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────

def generate_full_report(
    *,
    valor_total_cartera: pd.Series,
    aporte_diario: pd.Series,
    valor_cartera: pd.DataFrame,
    # Crypto (all optional)
    valor_total_crypto: pd.Series | None = None,
    aporte_crypto_eur_acumulado: pd.Series | None = None,
    valor_crypto_eur: pd.DataFrame | None = None,
    # Metrics (pre-calculated)
    metrics: dict | None = None,
    # Failed / Missing Data (optional)
    failed_assets_summary: pd.DataFrame | None = None,
    # Benchmark (optional, normalised series starting at 100)
    benchmark_series: pd.Series | None = None,
) -> str:
    """
    Generate the PDF and return the file path.

    ``metrics`` dict is expected to have keys like::

        capital_aportado_acciones, valor_actual_acciones, plusvalia_acciones,
        rentabilidad_acciones, cagr_acciones,
        twr_acciones_total, twr_acciones_anual,
        capital_aportado_crypto, valor_actual_crypto, plusvalia_crypto,
        rentabilidad_crypto, cagr_crypto,
        twr_cripto_total, twr_cripto_anual,
        capital_total, valor_total, plusvalia_total,
        rentabilidad_total, cagr_total,
        twr_total_total, twr_total_anual,
        peso_acciones, peso_crypto,
        dias_totales, anhos_totales,
        fecha_actual, …
    """
    if metrics is None:
        metrics = {}

    has_crypto = (valor_total_crypto is not None and not valor_total_crypto.empty)

    # Ensure output dirs
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs(config.HIST_DIR, exist_ok=True)

    # Move old PDFs to hist-inf
    old = glob.glob(os.path.join(config.OUTPUT_DIR, "resumen_cartera_*.pdf"))
    for p in old:
        shutil.move(p, os.path.join(config.HIST_DIR, os.path.basename(p)))

    fecha_actual = metrics.get('fecha_actual', valor_total_cartera.index[-1].strftime('%Y-%m-%d'))
    nombre_pdf = os.path.join(config.OUTPUT_DIR, f"resumen_cartera_{fecha_actual}.pdf")

    with PdfPages(nombre_pdf) as pdf:
        fig = plt.figure(figsize=(11, 14), facecolor='#d9d9d9')

        # ── Decorative lines ─────────────────────────────────────────
        fig.add_artist(Line2D([0, 1], [1, 1], transform=fig.transFigure,
                              color='#003366', linewidth=25))
        fig.add_artist(Line2D([0, 1], [0, 0], transform=fig.transFigure,
                              color='#003366', linewidth=25))

        # ══════════════════════════════════════════════════════════════
        #  CHART 1 – Stock evolution   (top-left)
        # ══════════════════════════════════════════════════════════════
        ax1 = fig.add_axes([0.07, 0.7, 0.42, 0.25])
        # Left limit = first data point (no hardcoded year, B8).
        _starts = [x.dropna().index.min() for x in (valor_total_cartera, aporte_diario)
                   if x is not None and not x.dropna().empty]
        fecha_inicio = min(_starts) if _starts else None
        ax1.plot(valor_total_cartera, label='Valor de la cartera',
                 color='#2E86AB', linewidth=2)
        ax1.plot(aporte_diario, label='Capital aportado neto',
                 linestyle='--', color='#A23B72', linewidth=1.5)

        # Benchmark overlay: scale normalised series to capital units
        has_benchmark = benchmark_series is not None and not benchmark_series.empty
        if has_benchmark:
            bm_name = metrics.get('benchmark_name', metrics.get('benchmark_ticker', 'Benchmark'))
            cap0 = aporte_diario.dropna().iloc[0] if not aporte_diario.dropna().empty else 1.0
            bm_scaled = benchmark_series / 100.0 * cap0
            bm_scaled = bm_scaled.reindex(valor_total_cartera.index).ffill()
            ax1.plot(bm_scaled, label=f'Benchmark ({bm_name})',
                     linestyle=':', color='#F4A261', linewidth=1.5)

        ax1.set_title('Evolución cartera acciones', fontsize=12,
                       fontweight='bold', fontfamily='sans-serif')
        ax1.set_xlabel('Fecha', fontsize=9)
        ax1.set_ylabel('€', fontsize=9)
        ax1.legend(fontsize=7, loc='upper left')
        ax1.grid(True, alpha=0.3)
        if fecha_inicio is not None:
            ax1.set_xlim(left=fecha_inicio)
        ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        for lab in ax1.get_xticklabels():
            lab.set_rotation(45); lab.set_fontsize(7)

        # ══════════════════════════════════════════════════════════════
        #  CHART 2 – Composition pie   (top-right)
        # ══════════════════════════════════════════════════════════════
        ax2 = fig.add_axes([0.50, 0.62, 0.49, 0.32])
        ax2.set_facecolor('#d9d9d9')
        ultima_fecha = valor_cartera.index[-1]
        valor_por_activo = valor_cartera.loc[ultima_fecha].copy()

        # Add crypto coins if available
        if has_crypto and valor_crypto_eur is not None and not valor_crypto_eur.empty:
            for coin in valor_crypto_eur.columns:
                if ultima_fecha in valor_crypto_eur.index:
                    valor_por_activo[coin] = valor_crypto_eur.loc[ultima_fecha, coin]

        valor_por_activo = valor_por_activo[valor_por_activo > 0]
        if valor_por_activo.empty or valor_por_activo.sum() <= 0:
            ax2.text(0.5, 0.5, 'Sin posiciones valoradas', ha='center',
                     va='center', fontsize=11, color='grey')
            ax2.axis('off')
        else:
            total = valor_por_activo.sum()
            pcts = valor_por_activo / total * 100

            grandes = valor_por_activo[pcts >= 2]
            pequenos = valor_por_activo[pcts < 2]
            if not pequenos.empty:
                grandes['Otros'] = pequenos.sum()
            grandes = grandes.sort_values(ascending=False)

            def _autopct(pct):
                return f'{pct:.1f}%' if pct >= 1 else ''

            pie_colors = [
                '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
                '#aec7e8', '#ffbb78', '#98df8a', '#ff9896',
            ]

            wedges, texts, autotexts = ax2.pie(
                grandes, labels=grandes.index, autopct=_autopct,
                startangle=140,
                colors=pie_colors[:len(grandes)],
                textprops={'fontsize': 7},
                wedgeprops={'linewidth': 1.0, 'edgecolor': '#d9d9d9'},
            )
            for at in autotexts:
                at.set_fontweight('bold'); at.set_fontsize(7)
            ax2.set_title(f'Composición total cartera\n({ultima_fecha.date()})',
                           fontsize=12, fontweight='bold', fontfamily='sans-serif')

        # ══════════════════════════════════════════════════════════════
        #  CHART 3 – Crypto evolution  (middle)
        # ══════════════════════════════════════════════════════════════
        ax3 = fig.add_axes([0.07, 0.38, 0.9, 0.20])
        if has_crypto:
            ax3.plot(valor_total_crypto, label='Valor cartera cripto (EUR)',
                     color='#F7931A', linewidth=2)
            if aporte_crypto_eur_acumulado is not None and not aporte_crypto_eur_acumulado.empty:
                ax3.plot(aporte_crypto_eur_acumulado,
                         label='Capital aportado cripto (EUR)',
                         linestyle='--', color='#627EEA', linewidth=1.5)
            ax3.set_title('Evolución cartera cripto', fontsize=12,
                           fontweight='bold', fontfamily='sans-serif')
            ax3.set_xlabel('Fecha', fontsize=9)
            ax3.set_ylabel('€', fontsize=9)
            ax3.legend(fontsize=7, loc='upper left')
            ax3.grid(True, alpha=0.3)
            ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            for lab in ax3.get_xticklabels():
                lab.set_rotation(45); lab.set_fontsize(7)
        else:
            ax3.text(0.5, 0.5, 'Sin datos de cripto', ha='center',
                     va='center', fontsize=11, color='grey')
            ax3.axis('off')

        # ══════════════════════════════════════════════════════════════
        #  TEXT – Left column (totals)
        # ══════════════════════════════════════════════════════════════
        m = metrics
        ax4 = fig.add_axes([0.05, 0.01, 0.42, 0.3])
        ax4.axis('off')

        bm_block = ""
        if m.get('benchmark_ticker'):
            bm_block = (
                f"Benchmark ({m.get('benchmark_name', m['benchmark_ticker'])})\n"
                f"  Total:     {m.get('benchmark_total', 0):.2f}%\n"
                f"  Anual:     {m.get('benchmark_annual', 0):.2f}%\n"
                f"  Alfa TWR:  {m.get('twr_total_anual', 0) - m.get('benchmark_annual', 0):.2f}%\n"
                "──────────────────────────────────────────────────────────\n"
            )

        resumen_izq = (
            "\n"
            "──────────────────────────────────────────────────────────\n"
            "\n"
            "\n"
            "TOTAL CARTERA\n"
            "\n"
            f"Capital aportado total:     €{m.get('capital_total', 0):,.2f}\n"
            f"Valor actual total:         €{m.get('valor_total', 0):,.2f}\n"
            f"Plusvalía total:            €{m.get('plusvalia_total', 0):,.2f}\n"
            f"Rentabilidad total:           {m.get('rentabilidad_total', 0):.2f}%\n"
            f"CAGR (anualizado):            {m.get('cagr_total', 0):.2f}%\n"
            f"TWR Total:                    {m.get('twr_total_total', 0):.2f}%\n"
            f"TWR Anualizado:               {m.get('twr_total_anual', 0):.2f}%\n"
            "\n"
            "──────────────────────────────────────────────────────────\n"
            + bm_block +
            "\n"
            f"Fecha de evaluación: {m.get('fecha_actual', '')}\n"
            f"Período: {m.get('anhos_totales', 0):.2f} años\n"
        )
        ax4.text(0, 1, resumen_izq, fontsize=8.5, fontfamily='monospace',
                 va='top', wrap=True, multialignment='left')

        # ══════════════════════════════════════════════════════════════
        #  TEXT – Right column (breakdown)
        # ══════════════════════════════════════════════════════════════
        ax5 = fig.add_axes([0.53, 0.01, 0.42, 0.3])
        ax5.axis('off')

        resumen_der = (
            "\n"
            "─────────────────────────────────────────\n"
            "\n"
            "ACCIONES\n"
            "\n"
            f"• Capital aportado:   €{m.get('capital_aportado_acciones', 0):,.2f}\n"
            f"• Valor actual:       €{m.get('valor_actual_acciones', 0):,.2f}\n"
            f"• Plusvalía:          €{m.get('plusvalia_acciones', 0):,.2f}\n"
            f"• Rentabilidad:        {m.get('rentabilidad_acciones', 0):.2f}%\n"
            f"• CAGR:                {m.get('cagr_acciones', 0):.2f}%\n"
            f"• TWR Total:           {m.get('twr_acciones_total', 0):.2f}%\n"
            f"• TWR Anualizado:      {m.get('twr_acciones_anual', 0):.2f}%\n"
            f"• Peso en cartera:     {m.get('peso_acciones', 100):.2f}%\n"
        )

        if has_crypto:
            resumen_der += (
                "\n"
                "─────────────────────────────────────────\n"
                "\n"
                "CRIPTOMONEDAS\n"
                "\n"
                f"• Capital aportado:   €{m.get('capital_aportado_crypto', 0):,.2f}\n"
                f"• Valor actual:       €{m.get('valor_actual_crypto', 0):,.2f}\n"
                f"• Plusvalía:          €{m.get('plusvalia_crypto', 0):,.2f}\n"
                f"• Rentabilidad:        {m.get('rentabilidad_crypto', 0):.2f}%\n"
                f"• CAGR:                {m.get('cagr_crypto', 0):.2f}%\n"
                f"• TWR Total:           {m.get('twr_cripto_total', 0):.2f}%\n"
                f"• TWR Anualizado:      {m.get('twr_cripto_anual', 0):.2f}%\n"
                f"• Peso en cartera:     {m.get('peso_crypto', 0):.2f}%\n"
            )

        ax5.text(0, 1, resumen_der, fontsize=8.5, fontfamily='monospace',
                 va='top', wrap=True, multialignment='left')

        # Save page
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

        # ══════════════════════════════════════════════════════════════
        #  PAGE 2 – Failed Assets (if any)
        # ══════════════════════════════════════════════════════════════
        if failed_assets_summary is not None and not failed_assets_summary.empty:
            fig2 = plt.figure(figsize=(11, 14))
            ax_fa = fig2.add_axes([0.1, 0.1, 0.8, 0.8])
            ax_fa.axis('off')
            
            title_text = "⚠️ ACTIVOS EXCLUIDOS DE LOS CÁLCULOS ⚠️\n(Sin datos recientes de precio o deslistados)\n\n"
            
            header = f"{'Activo':<15} | {'Tipo':<10} | {'Cantidad':>15} | {'Capital Aportado (€)':>22}\n"
            sep = "-" * 68 + "\n"
            
            rows_str = ""
            for idx, row in failed_assets_summary.iterrows():
                asset = str(row['Asset'])[:14]
                typ = str(row.get('Type', 'Stock'))[:9]
                qty_val = float(row.get('Quantity', 0.0))
                qty = f"{qty_val:.6g}"
                inv_val = float(row.get('Invested Capital (EUR)', 0.0))
                inv = f"{inv_val:,.2f}"
                rows_str += f"{asset:<15} | {typ:<10} | {qty:>15} | {inv:>22}\n"
                
            footer = "\n\n\n(Estos activos mantienen su histórico de operaciones pero no afectan\n a los totales, gráficas ni porcentajes de la página anterior)"
            
            full_text = title_text + header + sep + rows_str + footer
            
            ax_fa.text(0.5, 0.8, full_text, fontsize=11, fontfamily='monospace',
                     va='top', ha='center', wrap=True)
                     
            pdf.savefig(fig2, dpi=150)
            plt.close(fig2)

    print(f"\n📄 PDF generado: {nombre_pdf}")
    return nombre_pdf
