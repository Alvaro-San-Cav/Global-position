import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
import pandas as pd
import numpy as np
import os
from datetime import datetime

def compute_metrics(current_val, invested_val, start_date, end_date):
    """Calculates P&L, ROI, and CAGR."""
    if invested_val == 0:
        return 0.0, 0.0, 0.0
    
    pnl = current_val - invested_val
    roi = (pnl / invested_val) * 100
    
    days = (end_date - start_date).days
    years = days / 365.25
    
    if years > 0 and current_val > 0 and invested_val > 0:
        cagr = ((current_val / invested_val) ** (1 / years) - 1) * 100
    else:
        cagr = 0.0
        
    return pnl, roi, cagr

def generate_full_report(data, output_dir="output"):
    """
    Generates a high-quality PDF report for Stocks and Crypto.
    data format: {
        'stocks': {'value': Series, 'invested': Series, 'breakdown': DataFrame},
        'crypto': {'value': Series, 'invested': Series, 'breakdown': DataFrame} (optional)
    }
    """
    
    # --- Prepare Data ---
    stocks = data.get('stocks', {})
    crypto = data.get('crypto', {})
    
    val_s = stocks.get('value', pd.Series(dtype=float))
    inv_s = stocks.get('invested', pd.Series(dtype=float))
    breakdown_s = stocks.get('breakdown', pd.DataFrame())
    
    # Crypto data (might be None)
    val_c = crypto.get('value', pd.Series(dtype=float)) if crypto else pd.Series(dtype=float)
    inv_c = crypto.get('invested', pd.Series(dtype=float)) if crypto else pd.Series(dtype=float)
    breakdown_c = crypto.get('breakdown', pd.DataFrame()) if crypto else pd.DataFrame()
    
    # Check if we have crypto data
    has_crypto = (val_c is not None and not val_c.empty)
    
    # Totals
    curr_val_s = val_s.iloc[-1] if not val_s.empty else 0
    inv_curr_s = inv_s.iloc[-1] if not inv_s.empty else 0
    
    curr_val_c = val_c.iloc[-1] if has_crypto else 0
    # Note: crypto invested is currently always 0 (simplified)
    inv_curr_c = 0  # Simplified for now
    
    # Combined totals
    curr_val_total = curr_val_s + curr_val_c
    inv_curr_total = inv_curr_s + inv_curr_c
    
    # Dates
    if not val_s.empty:
        start_date = val_s.index[0]
        end_date = val_s.index[-1]
    else:
        start_date = pd.Timestamp.now()
        end_date = pd.Timestamp.now()
        
    # Metrics for stocks
    pnl_s, roi_s, cagr_s = compute_metrics(curr_val_s, inv_curr_s, start_date, end_date)
    
    # Metrics for crypto (using current value as both invested and current for ROI calculation)
    if has_crypto:
        # Since we don't track cost basis, show value only
        pnl_c = curr_val_c  # Simplified: all value is shown as gain
        roi_c = 0  # Can't calculate without cost basis
        cagr_c = 0
    else:
        pnl_c = roi_c = cagr_c = 0
    
    # Combined metrics
    pnl_total, roi_total, cagr_total = compute_metrics(curr_val_total, inv_curr_total, start_date, end_date)

    # --- PDF Generation ---
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    date_str = end_date.strftime("%Y-%m-%d")
    title_suffix = "Stocks + Crypto" if has_crypto else "Stocks"
    filename = os.path.join(output_dir, f"GlobalPosition_{date_str}.pdf")
    
    with PdfPages(filename) as pdf:
        fig = plt.figure(figsize=(11, 14))
        
        # 1. Header/Footer Lines
        linea_arriba = Line2D([0, 1], [0.98, 0.98], transform=fig.transFigure, color='#003366', linewidth=15)
        fig.add_artist(linea_arriba)
        linea_abajo = Line2D([0, 1], [0.02, 0.02], transform=fig.transFigure, color='#003366', linewidth=15)
        fig.add_artist(linea_abajo)
        
        # Title
        fig.text(0.5, 0.94, f"Global Position Report ({title_suffix}) - {date_str}", 
                ha='center', fontsize=16, fontweight='bold', fontfamily='sans-serif')

        # 2. Graph 1: Stocks Evolution (Top Left)
        ax1 = fig.add_axes([0.07, 0.65, 0.40, 0.25])
        if not val_s.empty:
            ax1.plot(val_s.index, val_s, label='Market Value', color='#1f77b4', linewidth=2)
            ax1.plot(inv_s.index, inv_s, label='Invested', linestyle='--', color='#ff7f0e', linewidth=2)
            ax1.fill_between(val_s.index, val_s, alpha=0.1, color='#1f77b4')
            ax1.legend(loc='upper left', fontsize=8, frameon=True)
            ax1.grid(True, alpha=0.3)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax1.get_xticklabels(), rotation=45, fontsize=7)
        ax1.set_title('Stocks Evolution (EUR)', fontsize=10, fontweight='bold')
        ax1.set_ylabel('Value (€)', fontsize=9)

        # 3. Graph 2: Crypto Evolution (Top Right) - if available
        ax2 = fig.add_axes([0.55, 0.65, 0.40, 0.25])
        if has_crypto:
            ax2.plot(val_c.index, val_c, label='Crypto Value', color='#F7931A', linewidth=2)
            ax2.fill_between(val_c.index, val_c, alpha=0.1, color='#F7931A')
            ax2.legend(loc='upper left', fontsize=8, frameon=True)
            ax2.grid(True, alpha=0.3)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax2.get_xticklabels(), rotation=45, fontsize=7)
            ax2.set_title('Crypto Evolution (EUR)', fontsize=10, fontweight='bold')
            ax2.set_ylabel('Value (€)', fontsize=9)
        else:
            ax2.text(0.5, 0.5, "No Crypto Data", ha='center', va='center', fontsize=10)
            ax2.axis('off')

        # 4. Graph 3: Combined Composition (Bottom Left)
        ax3 = fig.add_axes([0.05, 0.15, 0.40, 0.40])
        
        # Combine stocks and crypto for composition
        comp_data = {}
        if not breakdown_s.empty:
            last_row_s = breakdown_s.iloc[-1]
            for t, v in last_row_s.items():
                if v > 100: comp_data[t] = v
        
        # Add crypto coins if available
        if has_crypto and not breakdown_c.empty:
            last_row_c = breakdown_c.iloc[-1]
            for coin, v in last_row_c.items():
                if v > 100: comp_data[f"🪙{coin}"] = v  # Add emoji to differentiate
        
        if comp_data:
            s_comp = pd.Series(comp_data).sort_values(ascending=False)
            total_comp = s_comp.sum()
            # Filter < 2%
            mask = (s_comp / total_comp) >= 0.02
            main_holdings = s_comp[mask]
            others = s_comp[~mask].sum()
            if others > 0:
                main_holdings['Others'] = others
            
            def autopct_format(pct):
                return f'{pct:.1f}%' if pct > 2 else ''

            ax3.pie(main_holdings, labels=main_holdings.index, autopct=autopct_format, startangle=140, 
                    textprops={'fontsize': 8}, colors=plt.cm.tab20.colors, pctdistance=0.85)
            
            # Donut style
            centre_circle = plt.Circle((0,0),0.70,fc='white')
            ax3.add_artist(centre_circle)
            
            ax3.set_title('Total Portfolio Composition', fontsize=11, fontweight='bold')
        else:
            ax3.text(0.5, 0.5, "No Data", ha='center', va='center')

        # 5. Text Summary (Bottom Right)
        ax4 = fig.add_axes([0.50, 0.15, 0.45, 0.40])
        ax4.axis('off')
        
        if has_crypto:
            summary_text = f"""
PORTFOLIO SUMMARY
══════════════════════════════════════
TOTAL
 Net Invested:       € {inv_curr_total:,.2f}
 Current Value:      € {curr_val_total:,.2f}
 P&L:                € {pnl_total:,.2f}
 ROI:                  {roi_total:+.2f}%
 CAGR:                 {cagr_total:.2f}%

──────────────────────────────────────
STOCKS
 Invested:           € {inv_curr_s:,.2f}
 Value:              € {curr_val_s:,.2f}
 P&L:                € {pnl_s:,.2f}
 ROI:                  {roi_s:+.2f}%
 CAGR:                 {cagr_s:.2f}%

──────────────────────────────────────
CRYPTO
 Value:              € {curr_val_c:,.2f}
 Weight:               {(curr_val_c / curr_val_total * 100) if curr_val_total > 0 else 0:.1f}%

──────────────────────────────────────
Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}
Duration: {(end_date - start_date).days} days
"""
        else:
            summary_text = f"""
PORTFOLIO SUMMARY
══════════════════════════════════════
 Net Invested:       € {inv_curr_s:,.2f}
 Current Value:      € {curr_val_s:,.2f}
 
 P&L:                € {pnl_s:,.2f}
 ROI:                  {roi_s:+.2f}%
 CAGR:                 {cagr_s:.2f}%
 
──────────────────────────────────────
Analysis Period:
 Start: {start_date.strftime('%Y-%m-%d')}
 End:   {end_date.strftime('%Y-%m-%d')}
 Duration:        {(end_date - start_date).days} days
"""
        ax4.text(0, 0.5, summary_text.strip(), fontsize=9, fontfamily='monospace', va='center')

        pdf.savefig(fig)
        plt.close(fig)
    
    print(f"📄 Full Report generated: {filename}")
    return filename
