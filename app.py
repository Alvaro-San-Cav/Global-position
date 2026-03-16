"""
Global Position – Streamlit Web App

Provides a web interface for:
  • 📊 Dashboard: portfolio overview with metrics and charts
  • 📋 Operations: view/filter stock and crypto operations
  • ⚙️ Settings: configure price/FX adjustments and data sources
"""

import json
import os
import sys

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# ── Ensure project root is in path ─────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import config, loaders, market_data, core
from main import _compute_metrics

# ═══════════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Global Position",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════
#  CUSTOM CSS
# ═══════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Global ──────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 1rem;
}

/* ── Sidebar ─────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
section[data-testid="stSidebar"] .stRadio label {
    padding: 0.5rem 0.75rem;
    border-radius: 8px;
    transition: background 0.2s;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(255,255,255,0.08);
}

/* ── Metric cards ────────────────────────────────────── */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border: 1px solid #bae6fd;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
div[data-testid="stMetric"] label {
    font-weight: 600 !important;
    color: #334155 !important;
    font-size: 0.85rem !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-weight: 700 !important;
    color: #0f172a !important;
}

/* ── Headers ─────────────────────────────────────────── */
h1 { font-weight: 800 !important; letter-spacing: -0.02em; }
h2 { font-weight: 700 !important; color: #1e293b !important; }
h3 { font-weight: 600 !important; color: #334155 !important; }

/* ── Dataframe ───────────────────────────────────────── */
.stDataFrame { border-radius: 12px; overflow: hidden; }

/* ── Divider ─────────────────────────────────────────── */
hr { border-color: #e2e8f0 !important; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
#  SIDEBAR NAVIGATION
# ═══════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 💼 Global Position")
    st.caption("Portfolio Tracker")
    st.markdown("---")

    page = st.radio(
        "Navegación",
        ["📊 Dashboard", "📋 Operaciones", "🪙 Crypto", "⚙️ Ajustes"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption(f"📁 {config.PROCESSING_DIR}")


# ═══════════════════════════════════════════════════════════════════════
#  HELPER: LOAD DATA WITH CACHING
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner="Cargando operaciones…")
def load_operations():
    return loaders.load_operations()


@st.cache_data(ttl=300, show_spinner="Cargando crypto…")
def load_crypto():
    return loaders.load_crypto_operations()


def load_sources_json() -> dict:
    """Load raw sources.json."""
    if os.path.exists(config.SOURCES_FILE):
        with open(config.SOURCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_sources_json(data: dict):
    """Save sources.json."""
    with open(config.SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════
#  PAGE: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

def page_dashboard():
    st.markdown("# 📊 Dashboard")

    df_ops = load_operations()
    if df_ops.empty:
        st.warning("No hay operaciones en `processing/operaciones.csv`.")
        return

    # ── Run analysis (cached) ──────────────────────────────────────
    with st.status("Ejecutando análisis…", expanded=True) as status:
        st.write("📂 Cargando operaciones…")
        df_ops_merged = loaders.merge_custom_stock_sources(df_ops.copy())

        st.write("🔍 Resolviendo tickers…")
        df_ops_merged = _resolve_tickers_silent(df_ops_merged)
        tickers = [t for t in df_ops_merged['ticker'].dropna().unique()
                    if t and str(t).strip()]
        currencies = df_ops_merged['Coin'].dropna().unique().tolist()

        # Crypto
        df_crypto = load_crypto()
        has_crypto = df_crypto is not None and len(df_crypto) > 0
        crypto_coins = []
        if has_crypto:
            crypto_coins = df_crypto['Coin'].dropna().unique().tolist()

        st.write("📥 Descargando precios…")
        start_date = df_ops_merged['Date'].min()
        prices = market_data.fetch_prices(tickers, start_date)
        fx_rates = market_data.fetch_fx_rates(currencies, start_date,
                                                crypto_coins=crypto_coins or None)

        st.write("🔄 Aplicando splits…")
        df_adj = core.SplitManager.apply_splits(df_ops_merged)

        st.write("📈 Calculando portfolio…")
        vtc, ad, vc = core.calculate_stock_portfolio(df_adj, prices, fx_rates)

        vtc_crypto = aporte_crypto = vc_eur = None
        if has_crypto:
            vtc_crypto, aporte_crypto, vc_eur = \
                core.calculate_crypto_portfolio(df_crypto, fx_rates)
            if vtc_crypto is not None and vtc_crypto.empty:
                has_crypto = False

        metrics = _compute_metrics(
            vtc, ad,
            vtc_crypto if has_crypto else None,
            aporte_crypto if has_crypto else None,
            vc_eur if has_crypto else None,
        )
        status.update(label="✅ Análisis completo", state="complete")

    if vtc.empty:
        st.error("El portfolio está vacío. Revisa los datos.")
        return

    # ── KPI Cards ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 💰 Resumen General")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capital Aportado",
              f"€{metrics['capital_total']:,.2f}")
    c2.metric("Valor Actual",
              f"€{metrics['valor_total']:,.2f}")
    pv = metrics['plusvalia_total']
    c3.metric("Plusvalía",
              f"€{pv:,.2f}",
              delta=f"{metrics['rentabilidad_total']:.2f}%")
    c4.metric("CAGR",
              f"{metrics['cagr_total']:.2f}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("TWR Total", f"{metrics['twr_total_total']:.2f}%")
    c6.metric("TWR Anualizado", f"{metrics['twr_total_anual']:.2f}%")
    c7.metric("Período", f"{metrics['anhos_totales']:.1f} años")
    c8.metric("Fecha", metrics['fecha_actual'])

    # ── Stock / Crypto breakdown ──────────────────────────────────
    st.markdown("---")
    col_stocks, col_crypto = st.columns(2)

    with col_stocks:
        st.markdown("### 📈 Acciones")
        s1, s2 = st.columns(2)
        s1.metric("Capital", f"€{metrics['capital_aportado_acciones']:,.2f}")
        s2.metric("Valor", f"€{metrics['valor_actual_acciones']:,.2f}")
        s3, s4 = st.columns(2)
        s3.metric("Plusvalía", f"€{metrics['plusvalia_acciones']:,.2f}",
                  delta=f"{metrics['rentabilidad_acciones']:.2f}%")
        s4.metric("CAGR", f"{metrics['cagr_acciones']:.2f}%")
        s5, s6 = st.columns(2)
        s5.metric("TWR Total", f"{metrics['twr_acciones_total']:.2f}%")
        s6.metric("Peso", f"{metrics['peso_acciones']:.1f}%")

    with col_crypto:
        st.markdown("### 🪙 Criptomonedas")
        if has_crypto:
            cr1, cr2 = st.columns(2)
            cr1.metric("Capital", f"€{metrics['capital_aportado_crypto']:,.2f}")
            cr2.metric("Valor", f"€{metrics['valor_actual_crypto']:,.2f}")
            cr3, cr4 = st.columns(2)
            cr3.metric("Plusvalía", f"€{metrics['plusvalia_crypto']:,.2f}",
                       delta=f"{metrics['rentabilidad_crypto']:.2f}%")
            cr4.metric("CAGR", f"{metrics['cagr_crypto']:.2f}%")
            cr5, cr6 = st.columns(2)
            cr5.metric("TWR Total", f"{metrics['twr_cripto_total']:.2f}%")
            cr6.metric("Peso", f"{metrics['peso_crypto']:.1f}%")
        else:
            st.info("Sin datos de crypto configurados.")

    # ── Charts ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📈 Evolución del Portfolio")

    # Evolution chart
    fig_evo = go.Figure()
    fig_evo.add_trace(go.Scatter(
        x=vtc.index, y=vtc.values,
        name="Valor cartera",
        line=dict(color="#2563eb", width=2.5),
        fill='tonexty' if False else None,
    ))
    fig_evo.add_trace(go.Scatter(
        x=ad.index, y=ad.values,
        name="Capital aportado",
        line=dict(color="#7c3aed", width=2, dash="dash"),
    ))
    # Fill area between
    fig_evo.add_trace(go.Scatter(
        x=vtc.index, y=vtc.values,
        fill='tonexty',
        fillcolor='rgba(37, 99, 235, 0.08)',
        line=dict(width=0),
        showlegend=False,
    ))
    fig_evo.update_layout(
        template="plotly_white",
        height=400,
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", y=1.05),
        xaxis=dict(title=""),
        yaxis=dict(title="€", tickformat=",.0f"),
    )
    st.plotly_chart(fig_evo, use_container_width=True)

    # Composition and crypto side by side
    chart_left, chart_right = st.columns(2)

    with chart_left:
        st.markdown("### 🥧 Composición de la cartera")
        ultima_fecha = vc.index[-1]
        vpa = vc.loc[ultima_fecha].copy()
        if has_crypto and vc_eur is not None and not vc_eur.empty:
            for coin in vc_eur.columns:
                if ultima_fecha in vc_eur.index:
                    vpa[coin] = vc_eur.loc[ultima_fecha, coin]
        vpa = vpa[vpa > 0].sort_values(ascending=False)
        total = vpa.sum()
        pcts = vpa / total * 100

        grandes = vpa[pcts >= 2]
        pequenos = vpa[pcts < 2]
        if not pequenos.empty:
            grandes["Otros"] = pequenos.sum()

        fig_pie = px.pie(
            values=grandes.values,
            names=grandes.index,
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set3,
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label',
                               textfont_size=11)
        fig_pie.update_layout(
            height=400,
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=False,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with chart_right:
        if has_crypto and vtc_crypto is not None:
            st.markdown("### 🪙 Evolución Crypto")
            fig_cry = go.Figure()
            fig_cry.add_trace(go.Scatter(
                x=vtc_crypto.index, y=vtc_crypto.values,
                name="Valor crypto",
                line=dict(color="#f59e0b", width=2.5),
            ))
            if aporte_crypto is not None:
                fig_cry.add_trace(go.Scatter(
                    x=aporte_crypto.index, y=aporte_crypto.values,
                    name="Capital aportado",
                    line=dict(color="#6366f1", width=2, dash="dash"),
                ))
            fig_cry.update_layout(
                template="plotly_white",
                height=400,
                margin=dict(l=20, r=20, t=30, b=20),
                legend=dict(orientation="h", y=1.05),
                yaxis=dict(title="€", tickformat=",.0f"),
            )
            st.plotly_chart(fig_cry, use_container_width=True)
        else:
            st.markdown("### 📊 Top Activos por Valor")
            top = vpa.head(10)
            fig_bar = px.bar(
                x=top.values, y=top.index,
                orientation='h',
                color=top.values,
                color_continuous_scale="Blues",
                labels={"x": "Valor (€)", "y": "Ticker"},
            )
            fig_bar.update_layout(
                height=400,
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=False,
                coloraxis_showscale=False,
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_bar, use_container_width=True)


def _resolve_tickers_silent(df_ops):
    """Resolve tickers without interactive prompts."""
    if 'ticker' not in df_ops.columns:
        df_ops['ticker'] = ''
    df_ops['ticker'] = df_ops['ticker'].fillna('').astype(str).str.strip()

    bad = df_ops['ticker'].isin(['', 'None', 'nan', 'Not found'])
    isin_missing = df_ops.loc[bad, 'ISIN'].dropna().unique().tolist()
    isin_missing = [i for i in isin_missing if i and str(i).strip()]

    if not isin_missing:
        return df_ops

    resolved = market_data.lookup_tickers_batch(isin_missing)
    for isin, ticker in resolved.items():
        df_ops.loc[df_ops['ISIN'] == isin, 'ticker'] = ticker

    return df_ops


# ═══════════════════════════════════════════════════════════════════════
#  PAGE: OPERATIONS
# ═══════════════════════════════════════════════════════════════════════

def page_operations():
    st.markdown("# 📋 Operaciones de Acciones")

    df = load_operations()
    if df.empty:
        st.warning("No hay operaciones cargadas.")
        return

    # ── Filters ───────────────────────────────────────────────────
    st.markdown("### 🔍 Filtros")
    fc1, fc2, fc3 = st.columns(3)

    with fc1:
        tickers = sorted(df['ticker'].dropna().unique().tolist())
        sel_tickers = st.multiselect("Ticker", tickers, default=[])

    with fc2:
        coins = sorted(df['Coin'].dropna().unique().tolist())
        sel_coins = st.multiselect("Moneda", coins, default=[])

    with fc3:
        min_date = df['Date'].min()
        max_date = df['Date'].max()
        if pd.notna(min_date) and pd.notna(max_date):
            date_range = st.date_input(
                "Rango de fechas",
                value=(min_date.date(), max_date.date()),
                min_value=min_date.date(),
                max_value=max_date.date(),
            )
        else:
            date_range = None

    # Apply filters
    filtered = df.copy()
    if sel_tickers:
        filtered = filtered[filtered['ticker'].isin(sel_tickers)]
    if sel_coins:
        filtered = filtered[filtered['Coin'].isin(sel_coins)]
    if date_range and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[
            (filtered['Date'] >= pd.Timestamp(start)) &
            (filtered['Date'] <= pd.Timestamp(end))
        ]

    # ── Stats bar ─────────────────────────────────────────────────
    st.markdown("---")
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Total Operaciones", f"{len(filtered):,}")
    sc2.metric("Tickers Únicos", filtered['ticker'].nunique())
    buys = filtered[filtered['Quantity'] > 0]
    sells = filtered[filtered['Quantity'] < 0]
    sc3.metric("Compras", f"{len(buys):,}")
    sc4.metric("Ventas", f"{len(sells):,}")

    # ── Table ─────────────────────────────────────────────────────
    st.markdown("### 📊 Tabla de Operaciones")

    display_cols = ['Date', 'Product', 'ticker', 'ISIN', 'Quantity', 'Price', 'Coin', 'Value']
    display_df = filtered[[c for c in display_cols if c in filtered.columns]].copy()
    display_df['Date'] = display_df['Date'].dt.strftime('%Y-%m-%d')

    st.dataframe(
        display_df,
        use_container_width=True,
        height=500,
        column_config={
            "Date": st.column_config.TextColumn("Fecha", width="small"),
            "Product": st.column_config.TextColumn("Producto", width="medium"),
            "ticker": st.column_config.TextColumn("Ticker", width="small"),
            "Quantity": st.column_config.NumberColumn("Cantidad", format="%.4f"),
            "Price": st.column_config.NumberColumn("Precio", format="%.4f"),
            "Coin": st.column_config.TextColumn("Moneda", width="small"),
            "Value": st.column_config.NumberColumn("Valor (€)", format="%.2f"),
        },
    )

    # ── Summary by ticker ─────────────────────────────────────────
    st.markdown("### 📊 Resumen por Ticker")
    summary = filtered.groupby('ticker').agg(
        Operaciones=('ticker', 'count'),
        Qty_Total=('Quantity', 'sum'),
        Valor_Total=('Value', 'sum'),
        Primera_Op=('Date', 'min'),
        Última_Op=('Date', 'max'),
    ).sort_values('Valor_Total', ascending=False)

    summary['Primera_Op'] = summary['Primera_Op'].dt.strftime('%Y-%m-%d')
    summary['Última_Op'] = summary['Última_Op'].dt.strftime('%Y-%m-%d')

    st.dataframe(
        summary,
        use_container_width=True,
        column_config={
            "Qty_Total": st.column_config.NumberColumn("Qty Neta", format="%.4f"),
            "Valor_Total": st.column_config.NumberColumn("Valor Total (€)", format="%.2f"),
        },
    )


# ═══════════════════════════════════════════════════════════════════════
#  PAGE: CRYPTO
# ═══════════════════════════════════════════════════════════════════════

def page_crypto():
    st.markdown("# 🪙 Operaciones Crypto")

    df = load_crypto()
    if df is None or df.empty:
        st.warning("No hay operaciones crypto en `processing/crypto.csv`.")
        st.info("Configura una fuente crypto en ⚙️ Ajustes y procesa las transacciones desde la CLI.")
        return

    # ── Filters ───────────────────────────────────────────────────
    fc1, fc2 = st.columns(2)
    with fc1:
        coins = sorted(df['Coin'].dropna().unique().tolist())
        sel_coins = st.multiselect("Moneda", coins, default=coins, key="crypto_coins")
    with fc2:
        if 'Date' in df.columns and pd.api.types.is_datetime64_any_dtype(df['Date']):
            min_d = df['Date'].min()
            max_d = df['Date'].max()
            if pd.notna(min_d) and pd.notna(max_d):
                date_range = st.date_input(
                    "Rango", value=(min_d.date(), max_d.date()),
                    min_value=min_d.date(), max_value=max_d.date(), key="crypto_date"
                )
            else:
                date_range = None
        else:
            date_range = None

    filtered = df.copy()
    if sel_coins:
        filtered = filtered[filtered['Coin'].isin(sel_coins)]
    if date_range and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[
            (filtered['Date'] >= pd.Timestamp(start)) &
            (filtered['Date'] <= pd.Timestamp(end))
        ]

    # ── Stats ─────────────────────────────────────────────────────
    st.markdown("---")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Total Transacciones", f"{len(filtered):,}")
    cc2.metric("Monedas", filtered['Coin'].nunique())
    if 'Quantity' in filtered.columns:
        cc3.metric("Volumen Total", f"{filtered['Quantity'].sum():.6f}")

    # ── Table ─────────────────────────────────────────────────────
    st.markdown("### 📊 Transacciones")
    display = filtered.copy()
    if 'Date' in display.columns:
        display['Date'] = pd.to_datetime(display['Date']).dt.strftime('%Y-%m-%d %H:%M')
    st.dataframe(display, use_container_width=True, height=400)

    # ── Summary per coin ──────────────────────────────────────────
    st.markdown("### 💰 Balance por Moneda")
    if 'Quantity' in filtered.columns:
        balance = filtered.groupby('Coin')['Quantity'].sum().reset_index()
        balance.columns = ['Moneda', 'Balance']
        st.dataframe(balance, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════
#  PAGE: SETTINGS
# ═══════════════════════════════════════════════════════════════════════

def page_settings():
    st.markdown("# ⚙️ Ajustes")

    sources = load_sources_json()

    # ── Tab layout ────────────────────────────────────────────────
    tab_prices, tab_fx, tab_stock_src, tab_crypto_src, tab_raw = st.tabs([
        "📈 Ajustes de Precios",
        "💱 Ajustes de FX",
        "📦 Fuentes de Acciones",
        "🪙 Fuentes Crypto",
        "📝 JSON Raw",
    ])

    # ── Tab 1: Price adjustments ──────────────────────────────────
    with tab_prices:
        st.markdown("### Ajustes de Precios de Tickers")
        st.caption("Divide el precio descargado de yfinance por el divisor indicado.")

        price_adj = sources.get("price_adjustments", {})
        # Filter out _comment
        items = {k: v for k, v in price_adj.items() if k != "_comment"}

        if items:
            edit_df = pd.DataFrame(
                [{"Ticker": k, "Divisor": v} for k, v in items.items()]
            )
            edited = st.data_editor(
                edit_df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Ticker": st.column_config.TextColumn("Ticker", required=True),
                    "Divisor": st.column_config.NumberColumn("Divisor", required=True, min_value=1),
                },
                key="price_adj_editor",
            )
        else:
            edited = st.data_editor(
                pd.DataFrame({"Ticker": [], "Divisor": []}),
                num_rows="dynamic",
                use_container_width=True,
                key="price_adj_editor",
            )

        if st.button("💾 Guardar ajustes de precios", key="save_prices"):
            new_adj = {}
            for _, row in edited.iterrows():
                ticker = str(row.get("Ticker", "")).strip()
                divisor = row.get("Divisor", 1)
                if ticker and divisor:
                    new_adj[ticker] = float(divisor)
            if "_comment" in price_adj:
                new_adj["_comment"] = price_adj["_comment"]
            sources["price_adjustments"] = new_adj
            save_sources_json(sources)
            st.success("✅ Ajustes de precios guardados.")
            st.cache_data.clear()

    # ── Tab 2: FX adjustments ─────────────────────────────────────
    with tab_fx:
        st.markdown("### Ajustes de Tipos de Cambio")
        st.caption("Divide el tipo de cambio descargado por el divisor indicado.")

        fx_adj = sources.get("fx_adjustments", {})
        fx_items = {k: v for k, v in fx_adj.items() if k != "_comment"}

        if fx_items:
            fx_df = pd.DataFrame(
                [{"Moneda": k, "Divisor": v} for k, v in fx_items.items()]
            )
            fx_edited = st.data_editor(
                fx_df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Moneda": st.column_config.TextColumn("Moneda", required=True),
                    "Divisor": st.column_config.NumberColumn("Divisor", required=True, min_value=1),
                },
                key="fx_adj_editor",
            )
        else:
            fx_edited = st.data_editor(
                pd.DataFrame({"Moneda": [], "Divisor": []}),
                num_rows="dynamic",
                use_container_width=True,
                key="fx_adj_editor",
            )

        if st.button("💾 Guardar ajustes de FX", key="save_fx"):
            new_fx = {}
            for _, row in fx_edited.iterrows():
                currency = str(row.get("Moneda", "")).strip()
                divisor = row.get("Divisor", 1)
                if currency and divisor:
                    new_fx[currency] = float(divisor)
            if "_comment" in fx_adj:
                new_fx["_comment"] = fx_adj["_comment"]
            sources["fx_adjustments"] = new_fx
            save_sources_json(sources)
            st.success("✅ Ajustes de FX guardados.")
            st.cache_data.clear()

    # ── Tab 3: Stock sources ──────────────────────────────────────
    with tab_stock_src:
        st.markdown("### Fuentes de Acciones Personalizadas")
        st.caption("Define fuentes CSV adicionales (RSUs, vests, etc.).")

        stock_sources = sources.get("stock_sources", [])
        for i, src in enumerate(stock_sources):
            with st.expander(f"{'🟢' if src.get('enabled') else '🔴'} {src.get('name', f'Source {i}')}", expanded=False):
                src['enabled'] = st.toggle("Habilitada", value=src.get('enabled', False), key=f"ss_en_{i}")
                src['name'] = st.text_input("Nombre", value=src.get('name', ''), key=f"ss_name_{i}")
                src['file_pattern'] = st.text_input("Patrón de archivo", value=src.get('file_pattern', ''), key=f"ss_pat_{i}")
                st.json(src.get('column_map', {}))
                st.json(src.get('defaults', {}))

        if st.button("💾 Guardar fuentes de acciones", key="save_stock_src"):
            sources["stock_sources"] = stock_sources
            save_sources_json(sources)
            st.success("✅ Fuentes de acciones guardadas.")

    # ── Tab 4: Crypto sources ─────────────────────────────────────
    with tab_crypto_src:
        st.markdown("### Fuentes Crypto")
        st.caption("Define exchanges crypto (Binance, etc.).")

        crypto_sources = sources.get("crypto_sources", [])
        for i, src in enumerate(crypto_sources):
            with st.expander(f"{'🟢' if src.get('enabled') else '🔴'} {src.get('name', f'Source {i}')}", expanded=False):
                src['enabled'] = st.toggle("Habilitada", value=src.get('enabled', False), key=f"cs_en_{i}")
                src['name'] = st.text_input("Nombre", value=src.get('name', ''), key=f"cs_name_{i}")
                src['file_pattern'] = st.text_input("Patrón", value=src.get('file_pattern', ''), key=f"cs_pat_{i}")
                coins_str = ", ".join(src.get("coins", []))
                new_coins = st.text_input("Coins (comma-separated)", value=coins_str, key=f"cs_coins_{i}")
                src['coins'] = [c.strip() for c in new_coins.split(",") if c.strip()]
                st.json(src.get('column_map', {}))

        if st.button("💾 Guardar fuentes crypto", key="save_crypto_src"):
            sources["crypto_sources"] = crypto_sources
            save_sources_json(sources)
            st.success("✅ Fuentes crypto guardadas.")

    # ── Tab 5: Raw JSON ───────────────────────────────────────────
    with tab_raw:
        st.markdown("### Editor JSON Directo")
        st.caption("Edita `sources.json` directamente. ⚠️ Ten cuidado con el formato.")

        raw_text = st.text_area(
            "sources.json",
            value=json.dumps(sources, indent=4, ensure_ascii=False),
            height=400,
            key="raw_json",
        )

        if st.button("💾 Guardar JSON", key="save_raw"):
            try:
                parsed = json.loads(raw_text)
                save_sources_json(parsed)
                st.success("✅ JSON guardado correctamente.")
                st.cache_data.clear()
            except json.JSONDecodeError as e:
                st.error(f"❌ JSON inválido: {e}")


# ═══════════════════════════════════════════════════════════════════════
#  ROUTER
# ═══════════════════════════════════════════════════════════════════════

if page == "📊 Dashboard":
    page_dashboard()
elif page == "📋 Operaciones":
    page_operations()
elif page == "🪙 Crypto":
    page_crypto()
elif page == "⚙️ Ajustes":
    page_settings()
