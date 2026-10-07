from __future__ import annotations

import os
import sys
import warnings
import time
import urllib.parse
from pathlib import Path

# Path resolution for project imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import streamlit as st

from utils import (
    display_table,
    get_global_master_data,
    require_credentials,
)

warnings.filterwarnings("ignore")

# ── 1. PAGE CONFIG & STYLES ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Client Completeness & Priority Matrix",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_credentials()

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: #0d1117; color: #e6edf3; }

/* KPI Grids */
.kpi-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; margin-bottom:20px; }
.kpi-card { background:#161b22; border:1px solid #30363d; border-radius:10px; padding:16px 18px; text-align:center; transition: transform 0.2s; }
.kpi-card:hover { transform: translateY(-2px); border-color: #58a6ff; }
.kpi-card .kpi-label { font-size:11px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:#8b949e; margin-bottom:6px; }
.kpi-card .kpi-value { font-family:'Space Mono',monospace; font-size:24px; font-weight:700; color:#e6edf3; line-height:1; }
.kpi-card .kpi-sub { font-size:11px; margin-top:5px; color:#58a6ff; }

/* Table Centering */
[data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th, 
[data-testid="stTable"] td, [data-testid="stTable"] th, 
table td, table th {
    text-align: center !important;
    vertical-align: middle !important;
}

.section-header { font-family:'Space Mono',monospace; font-size:14px; font-weight:700; letter-spacing:.08em;
                  text-transform:uppercase; color:#58a6ff; border-bottom:1px solid #21262d;
                  padding-bottom:8px; margin:24px 0 16px; }

/* Tooltip & Split KPI Cards (Compact UI) */
.split-container { display: flex; gap: 20px; margin-bottom: 20px; }
.split-column { flex: 1; background: #11161d; border: 1px solid #30363d; border-radius: 8px; padding: 12px; }
.split-header { font-size: 13px; font-weight: 700; text-transform: uppercase; margin-bottom: 12px; text-align: center; color: #e6edf3; border-bottom: 2px solid #30363d; padding-bottom: 8px; }

.hover-card {
    background: #161b22; border: 1px solid #30363d; border-radius: 4px; padding: 8px 12px;
    margin-bottom: 6px; position: relative; cursor: default;
    display: flex; justify-content: space-between; align-items: center;
}
.hover-card:hover { border-color: #58a6ff; }
.hover-title { font-weight: 700; font-size: 12px; color: #58a6ff; text-transform: uppercase; margin: 0; }
.hover-metric { font-family: 'Space Mono', monospace; font-size: 14px; color: #e6edf3; font-weight: bold; margin: 0; }

/* Tooltip text */
.hover-card .tooltiptext {
    visibility: hidden; width: 260px; background-color: #21262d; color: #e6edf3;
    text-align: left; border-radius: 6px; padding: 12px; position: absolute;
    z-index: 100; bottom: 105%; left: 50%; margin-left: -130px;
    opacity: 0; transition: opacity 0.2s; border: 1px solid #58a6ff; font-size: 11px;
    box-shadow: 0px 4px 10px rgba(0,0,0,0.5);
}
.hover-card:hover .tooltiptext { visibility: visible; opacity: 1; }
.tooltip-row { display: flex; justify-content: space-between; margin-bottom: 6px; }
.tooltip-val { font-weight: bold; font-family: 'Space Mono', monospace; font-size: 12px; }
</style>
""",
    unsafe_allow_html=True,
)

col_title, col_sync = st.columns([4, 1])
with col_title:
    st.markdown("# 📈 Client-Wise Completeness & Priority Matrix")
    st.markdown("Analyze expected SKUs against Live Client Deliverables, Master Records, and Sheet exclusions.")
with col_sync:
    st.write("") # Spacing
    if st.button("🔄 Sync & Refresh Data", use_container_width=True, help="Clear cache and fetch latest BQ and Sheet data"):
        st.cache_data.clear()
        for key in ["scope_data", "master_sql_df", "gsheet_data", "url_master_df"]:
            st.session_state.pop(key, None)
        st.rerun()

# ── 2. EDITABLE MASTER URL CONFIGURATION ──────────────────────────────────────
DEFAULT_URL_MASTER_DATA = [
    ["Bahrain", "Ninja", "Website", "https://ananinja.com/bh/en/product"],
    ["Kuwait", "Jemia", "Website", "https://www.jm3eia.com"],
    ["Kuwait", "Tawseel", "Website", "https://www.taw9eel.com/en/"],
    ["Kuwait", "Lulu", "Website", "https://gcc.luluhypermarket.com/en-kw"],
    ["Oman", "Lulu", "Website", "https://gcc.luluhypermarket.com/en-om/"],
    ["Qatar", "Snoonu", "Website", "https://snoonu.com/"],
    ["Qatar", "Al Meera", "Website", "https://www.almeera.com.qa/search-product"],
    ["Qatar", "Lulu", "Website", "https://gcc.luluhypermarket.com/en-qa/"],
    ["Saudi Arabia", "Aldawaa_promotions", "Website", "https://www.al-dawaa.com/en/"],
    ["Saudi Arabia", "Nahdi_promotions", "Website", "https://www.nahdionline.com/en-sa"],
    ["Saudi Arabia", "UnitedPharmacy_promotions", "Website", "https://unitedpharmacy.sa/en/"],
    ["Saudi Arabia", "Amazon", "Website", "https://www.amazon.sa/"],
    ["Saudi Arabia", "Ninja", "Website", "https://ananinja.com/sa/en/product"],
    ["Saudi Arabia", "Noon Minutes", "Website", "https://minutes.noon.com/saudi-en/"],
    ["United Arab Emirates", "Amazon", "Website", "https://www.amazon.ae/"],
    ["United Arab Emirates", "Noon Minutes", "Website", "https://minutes.noon.com/uae-en/"],
    ["United Arab Emirates", "Carrefour", "Website", "https://www.carrefouruae.com/mafuae/en"],
    ["United Arab Emirates", "Lulu", "Website", "https://gcc.luluhypermarket.com/en-ae/"],
    ["Bahrain", "Talabat", "App", ""],
    ["Kuwait", "Drops", "App", ""],
    ["Kuwait", "Talabat", "App", ""],
    ["Oman", "Talabat", "App", ""],
    ["Qatar", "Talabat", "App", ""],
    ["Saudi Arabia", "HungerStation", "Website", "https://hungerstation.com/sa-en/hmarket/regions/riyadh/al-rawdah/branch/hmarket-56617"],
    ["Saudi Arabia", "Nana", "App", ""],
    ["United Arab Emirates", "Careem", "App", ""],
    ["United Arab Emirates", "ElGrocer", "App", ""],
    ["United Arab Emirates", "Talabat", "App", ""]
]

if "url_master_df" not in st.session_state:
    st.session_state["url_master_df"] = pd.DataFrame(DEFAULT_URL_MASTER_DATA, columns=["CountryName", "Ecom_Source", "PlatformType", "BaseURL"])

with st.expander("🔗 Manage Website URLs & Master Mapping (Add/Update)", expanded=False):
    st.write("Edit existing URLs or add new sources. Changes apply instantly to the generated Search URLs below.")
    edited_urls = st.data_editor(
        st.session_state["url_master_df"],
        num_rows="dynamic",
        use_container_width=True,
        key="url_editor_table"
    )
    st.session_state["url_master_df"] = edited_urls
    master_url_df = edited_urls

def create_search_url(row, brand_col, product_col, mapping_df):
    country = str(row.get('CountryName', '')).strip()
    source = str(row.get('Ecom_Source', '')).strip()
    brand = str(row.get(brand_col, '')) if pd.notnull(row.get(brand_col)) else ''
    product = str(row.get(product_col, '')) if pd.notnull(row.get(product_col)) else ''
    
    query = f"{brand} {product}".strip()
    if not query:
        return ""
    
    encoded_query = urllib.parse.quote_plus(query)
    match = mapping_df[(mapping_df['CountryName'] == country) & (mapping_df['Ecom_Source'] == source)]
    
    if match.empty:
        return ""
        
    cap_source = match.iloc[0]['PlatformType']
    base_link = match.iloc[0]['BaseURL']
    
    if cap_source == 'App' or pd.isna(base_link) or str(base_link).strip() == "":
        return ""
        
    base_link = str(base_link).strip().rstrip('/')
    if not base_link.startswith('http'):
        base_link = 'https://' + base_link
        
    source_lower = source.lower()
    
    if 'amazon' in source_lower: return f"{base_link}/s?k={encoded_query}&rh=p_6%3AAmazon"
    elif 'lulu' in source_lower: return f"{base_link}/list/?search_text={encoded_query}"
    elif 'al meera' in source_lower: return f"{base_link}?s={encoded_query}"
    elif 'taw9eel' in source_lower or 'unitedpharmacy' in source_lower: return f"{base_link}/catalogsearch/result/?q={encoded_query}"
    elif 'aldawaa' in source_lower: return f"{base_link}/search/{encoded_query}" 
    elif 'aldawaa_promotions' in source_lower or 'nahdi' in source_lower or 'hungerstation' in source_lower: 
        return f"{base_link}?query={encoded_query}"
    else: return f"{base_link}/search?q={encoded_query}"

# ── 3. SMART TIMED LOADING (Client + Master Isolation) ─────────────────────────

@st.cache_data(show_spinner=False, ttl=1800)
def get_optimized_matrix_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # 1. BQ Expected Scope
    scope = st.session_state.get("scope_data", pd.DataFrame())
    
    # 2. Final Client Deliverable Data (Available)
    client = pd.DataFrame()
    raw_dict = st.session_state.get("_session_client_data", {}).get("client_data", {})
    frames = [df for k, df in raw_dict.items() if k in ["henkel", "kenvue", "stada", "bayara", "abbott"] and isinstance(df, pd.DataFrame) and not df.empty]
    if frames:
        client = pd.concat(frames, ignore_index=True, sort=False)
        
    # 3. Master SQL Records (Not yet in Client)
    master = st.session_state.get("master_sql_df", st.session_state.get("_sku_active_df", pd.DataFrame()))
        
    # 4. Excluded GSheet Data
    gsheet = st.session_state.get("gsheet_data", pd.DataFrame())
    
    # Fallback Data Pull if essential data is missing
    if scope.empty or master.empty:
        fetched_scope, fetched_sql, fetched_gsheet = get_global_master_data()
        scope = fetched_scope if fetched_scope is not None and not fetched_scope.empty else scope
        master = fetched_sql if fetched_sql is not None and not fetched_sql.empty else master
        gsheet = fetched_gsheet if fetched_gsheet is not None and not fetched_gsheet.empty else gsheet
        
    return scope, client, master, gsheet

# Pre-initialize globals to prevent NameError
scope_df, client_df, master_df, gsheet_df = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
total_start_time = time.time()

with st.status("🚀 Initializing Pipeline (Scope ➔ Master ➔ Client)...", expanded=False) as status:
    st.write("📥 Fetching Data Layers...")
    
    try:
        scope_df, client_df, master_df, gsheet_df = get_optimized_matrix_data()
        
        # Add Platform Type to Scope if available
        if not scope_df.empty and 'PlatformType' not in scope_df.columns:
            scope_df = scope_df.merge(master_url_df[['CountryName', 'Ecom_Source', 'PlatformType']], on=['CountryName', 'Ecom_Source'], how='left')
            scope_df['PlatformType'] = scope_df['PlatformType'].fillna("Unknown")
        
        with st.expander("📊 Data Pipeline Status", expanded=True):
            if not scope_df.empty: st.success(f"✅ **BQ Expected Scope:** Loaded ({len(scope_df):,} records)")
            else: st.warning("⚠️ **BQ Expected Scope:** Skipped")

            if not client_df.empty: st.success(f"✅ **Client Table (Available):** Loaded ({len(client_df):,} records)")
            else: st.warning("⚠️ **Client Table:** Missing (Ensure Weekly Deliverables page is loaded)")

            if not master_df.empty: st.success(f"✅ **SQL Master Records:** Loaded ({len(master_df):,} records)")
            else: st.warning("⚠️ **SQL Master Records:** Missing (Ensure Home Dashboard is loaded)")

            if not gsheet_df.empty: st.success(f"✅ **GSheet Exclusions:** Loaded ({len(gsheet_df):,} records)")
            else: st.warning("⚠️ **GSheet Exclusions:** Skipped")

    except Exception as e:
        st.write(f"⚠️ Pipeline error: {e}")

    if scope_df.empty:
        status.update(label="⚠️ Pipeline Paused: Missing Expected Scope Data", state="error", expanded=True)
        st.stop()
    else:
        status.update(label=f"🎉 Pipeline Ready! (Loaded in {time.time() - total_start_time:.2f}s)", state="complete", expanded=False)

# ── 4. DYNAMIC MATCH KEY CONFIGURATION (WITH PREVIEW & AUTO-NAMES) ─────────────
st.markdown('<div class="section-header">🔑 Dynamic Match Key Configuration</div>', unsafe_allow_html=True)

with st.expander("⚙️ Open Key Configurator, Mapping & Preview", expanded=True):
    st.write("Select exact columns from your datasets to build a unified key. Options dynamically load from your actual data.")
    
    def guess_columns(df, pref_lists):
        if df is None or df.empty: return []
        cols = []
        df_cols = df.columns.tolist()
        for prefs in pref_lists:
            found = next((c for c in prefs if c in df_cols), None)
            if found: cols.append(found)
        return cols

    # Prioritize NAMES over IDs to match your manual mapping
    col_preferences = [
        ['CountryName', 'EcommerceCountry', 'Country', 'Country Name', 'country'],
        ['Ecom_Source', 'Source', 'Ecom Source', 'source'],
        ['BrandName', 'Brand', 'brand_name'],
        ['ProductName', 'Product', 'product_name'],
    ]

    with st.form("key_mapping_form"):
        c1, c2, c3, c4 = st.columns(4)
        
        # Pull actual columns
        scope_cols = scope_df.columns.tolist() if not scope_df.empty else []
        client_cols = client_df.columns.tolist() if not client_df.empty else []
        master_cols = master_df.columns.tolist() if not master_df.empty else []
        gs_cols = gsheet_df.columns.tolist() if not gsheet_df.empty else []

        # Smart defaults
        scope_defs = guess_columns(scope_df, col_preferences)
        client_defs = guess_columns(client_df, col_preferences)
        master_defs = guess_columns(master_df, col_preferences)
        gs_defs = guess_columns(gsheet_df, col_preferences)
        
        scope_sel = c1.multiselect("Scope (Expected)", options=scope_cols, default=scope_defs)
        client_sel = c2.multiselect("Client Table", options=client_cols, default=client_defs)
        master_sel = c3.multiselect("Master SQL", options=master_cols, default=master_defs)
        gs_sel = c4.multiselect("GSheet Exclusions", options=gs_cols, default=gs_defs)
        
        st.caption("⚠️ Ensure you select the exact same *number* of columns in the *same order*.")
        apply_btn = st.form_submit_button("💾 Save Keys & Generate Preview")

    if apply_btn:
        st.session_state["scope_keys"] = scope_sel
        st.session_state["client_keys"] = client_sel
        st.session_state["master_keys"] = master_sel
        st.session_state["gs_keys"] = gs_sel
        st.success("Keys updated successfully! Check previews below.")

    if "scope_keys" not in st.session_state:
        st.session_state["scope_keys"] = scope_sel
        st.session_state["client_keys"] = client_sel
        st.session_state["master_keys"] = master_sel
        st.session_state["gs_keys"] = gs_sel

def create_eval_key(df: pd.DataFrame, cols: list) -> pd.Series:
    """Robust string conversion that drops trailing `.0` from ID floats before matching."""
    if df.empty or not cols: return pd.Series("", index=df.index)
    key_series = pd.Series("", index=df.index)
    for col in cols:
        if col in df.columns:
            s = df[col].astype(str)
            s = s.str.replace(r'\.0$', '', regex=True) # Fix pandas float bug
            val = s.str.lower().str.replace(r'[\s\W_]+', '', regex=True)
            val = np.where(df[col].isna(), "missing", val)
            val = np.where(val == "nan", "missing", val)
            val = np.where(val == "none", "missing", val)
        else:
            val = pd.Series("missing", index=df.index)
        key_series = key_series + "|" + val
    return key_series.str.strip("|")

scope_df['eval_key'] = create_eval_key(scope_df, st.session_state["scope_keys"])
if not client_df.empty: client_df['eval_key'] = create_eval_key(client_df, st.session_state["client_keys"])
if not master_df.empty: master_df['eval_key'] = create_eval_key(master_df, st.session_state["master_keys"])
if not gsheet_df.empty: gsheet_df['eval_key'] = create_eval_key(gsheet_df, st.session_state["gs_keys"])

client_active_keys = set(client_df['eval_key'].dropna().unique()) if not client_df.empty else set()
master_active_keys = set(master_df['eval_key'].dropna().unique()) if not master_df.empty else set()
gsheet_excluded_keys = set(gsheet_df['eval_key'].dropna().unique()) if not gsheet_df.empty else set()

# ── KEY PREVIEW UI ──
with st.expander("👀 View Generated Key Previews", expanded=False):
    st.write("Review a sample of how the keys are constructed.")
    p_c1, p_c2 = st.columns(2)
    
    with p_c1:
        st.markdown("**Expected Scope Preview**")
        if not scope_df.empty and st.session_state["scope_keys"]:
            valid_scope_cols = [c for c in st.session_state["scope_keys"] if c in scope_df.columns]
            st.dataframe(scope_df[valid_scope_cols + ['eval_key']].head(3), use_container_width=True)
            
    with p_c2:
        st.markdown("**Master SQL Preview**")
        if not master_df.empty and st.session_state["master_keys"]:
            valid_master_cols = [c for c in st.session_state["master_keys"] if c in master_df.columns]
            st.dataframe(master_df[valid_master_cols + ['eval_key']].head(3), use_container_width=True)

st.write("---")
c_1, c_2, c_3 = st.columns(3)
c_1.metric("Scope Keys Mapped", f"{len(scope_df['eval_key'].unique()):,}")
c_2.metric("Master SQL Keys Mapped", f"{len(master_active_keys):,}")
c_3.metric("GSheet Exclusions Mapped", f"{len(gsheet_excluded_keys):,}")

# ── 5. PRIORITY FILTERS ───────────────────────────────────────────────────────
st.markdown('<div class="section-header">🔽 Priority Filters</div>', unsafe_allow_html=True)
f_col1, f_col2, f_col3, f_col4 = st.columns(4)

with f_col1:
    clients = sorted([c for c in scope_df['Client'].dropna().unique().tolist() if str(c).strip() != ""])
    selected_client = st.selectbox("1. Client", ["All"] + clients)

with f_col2:
    countries = sorted([c for c in scope_df['CountryName'].dropna().unique().tolist() if str(c).strip() != ""])
    selected_country = st.selectbox("2. Country", ["All"] + countries)

with f_col3:
    sources = sorted([s for s in scope_df['Ecom_Source'].dropna().unique().tolist() if str(s).strip() != ""])
    selected_source = st.selectbox("3. Ecom Source", ["All"] + sources)

with f_col4:
    platforms = sorted([p for p in scope_df['PlatformType'].dropna().unique().tolist() if str(p).strip() != ""])
    selected_platform = st.selectbox("4. Platform Type", ["All"] + platforms)

filtered_scope = scope_df.copy()
if selected_client != "All": filtered_scope = filtered_scope[filtered_scope['Client'] == selected_client]
if selected_country != "All": filtered_scope = filtered_scope[filtered_scope['CountryName'] == selected_country]
if selected_source != "All": filtered_scope = filtered_scope[filtered_scope['Ecom_Source'] == selected_source]
if selected_platform != "All": filtered_scope = filtered_scope[filtered_scope['PlatformType'] == selected_platform]

# ── 6. TRUE STATUS ASSIGNMENT ─────────────────────────────────────────────────
is_client = filtered_scope['eval_key'].isin(client_active_keys)
is_master = filtered_scope['eval_key'].isin(master_active_keys)
is_excluded = filtered_scope['eval_key'].isin(gsheet_excluded_keys)

conditions = [
    is_client,
    (~is_client) & is_master,
    (~is_client) & (~is_master) & is_excluded,
]
choices = [
    'Available (Client Table)',
    'Master Records (Not in Client)',
    'Excluded (Google Sheet)',
]
filtered_scope['Completeness_Status'] = np.select(conditions, choices, default='True Missing (Action Required)')

# ── 7. EXECUTIVE METRICS STRIP ────────────────────────────────────────────────
total_scope = len(filtered_scope)
av_count = int(is_client.sum())
master_only_count = int((~is_client & is_master).sum())
excl_count = int((is_excluded & ~is_client & ~is_master).sum())
miss_count = int(total_scope - (av_count + master_only_count + excl_count))
delivery_rate = (av_count / total_scope * 100) if total_scope else 0.0

st.markdown(f"""
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="kpi-label">Total Expected Scope</div>
        <div class="kpi-value">{total_scope:,}</div>
        <div class="kpi-sub">Contractual Master Base</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Available (Current)</div>
        <div class="kpi-value" style="color:#3fb950;">{av_count:,}</div>
        <div class="kpi-sub">In Client Table: {delivery_rate:.1f}%</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Master Records</div>
        <div class="kpi-value" style="color:#d29922;">{master_only_count:,}</div>
        <div class="kpi-sub">In SQL but missing from Client</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Excluded (Sheet)</div>
        <div class="kpi-value" style="color:#8b949e;">{excl_count:,}</div>
        <div class="kpi-sub">Verified Out-of-Scope</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">True Missing</div>
        <div class="kpi-value" style="color:#f85149;">{miss_count:,}</div>
        <div class="kpi-sub">Total Extraction Failures</div>
    </div>
</div>
""", unsafe_allow_html=True)




# ── 9. CLIENT-WISE COMPREHENSIVE RECONCILIATION PIVOT ─────────────────────────
st.markdown('<div class="section-header">📋 Client-Wise Master Reconciliation Pivot</div>', unsafe_allow_html=True)
st.caption("ℹ️ Comprehensive breakdown showing total scope, live client deliveries, SQL master records, Google Sheet exclusions, and action required gaps.")

# Aggregate summary pivot
summary_pivot = filtered_scope.groupby(['Client', 'PlatformType'], observed=True).agg(
    Total_In_Scope=('eval_key', 'count'),
    Available_Client_Table=('Completeness_Status', lambda x: (x == 'Available (Client Table)').sum()),
    Master_SQL_Records=('Completeness_Status', lambda x: (x == 'Master Records (Not in Client)').sum()),
    Google_Sheet_Excluded=('Completeness_Status', lambda x: (x == 'Excluded (Google Sheet)').sum()),
    Action_Required_Missing=('Completeness_Status', lambda x: (x == 'True Missing (Action Required)').sum())
).reset_index()

summary_pivot['Delivery Rate %'] = (summary_pivot['Available_Client_Table'] / summary_pivot['Total_In_Scope'] * 100).round(1)
summary_pivot = summary_pivot.sort_values(by=['Client', 'Total_In_Scope'], ascending=[True, False]).reset_index(drop=True)

st.dataframe(summary_pivot, use_container_width=True, height=400)    

# ── 8. HOVER KPI CARDS ────────────────────────────────────────────────────────
st.markdown('<div class="section-header">📱 Platform Distribution (Hover for details)</div>', unsafe_allow_html=True)

web_df = filtered_scope[filtered_scope['PlatformType'] == 'Website']
app_df = filtered_scope[filtered_scope['PlatformType'] == 'App']

def render_hover_cards(df, title):
    html = f'<div class="split-column"><div class="split-header">{title}</div>\n'
    if df.empty:
        html += "<div style='text-align:center; color:#8b949e; margin-top:10px; font-size: 12px;'>No data available</div>\n"
    else:
        grouped = df.groupby('Client').agg(
            Total=('eval_key', 'count'),
            Current=('Completeness_Status', lambda x: (x == 'Available (Client Table)').sum()),
            MasterOnly=('Completeness_Status', lambda x: (x == 'Master Records (Not in Client)').sum()),
            Missing=('Completeness_Status', lambda x: (x == 'True Missing (Action Required)').sum())
        ).reset_index()
        
        for _, row in grouped.iterrows():
            card_html = f"""<div class="hover-card">
<span class="hover-title">{row['Client']}</span>
<span class="hover-metric">{row['Total']:,}</span>
<div class="tooltiptext">
<div class="tooltip-row"><span>Available (Client Table):</span> <span class="tooltip-val" style="color:#3fb950;">{row['Current']:,}</span></div>
<div class="tooltip-row"><span>Master Records Only:</span> <span class="tooltip-val" style="color:#d29922;">{row['MasterOnly']:,}</span></div>
<div class="tooltip-row"><span>True Missing:</span> <span class="tooltip-val" style="color:#f85149;">{row['Missing']:,}</span></div>
</div>
</div>
"""
            html += card_html
    html += '</div>'
    return html

st.markdown(f"""<div class="split-container">
{render_hover_cards(web_df, "🌐 Website Platforms")}
{render_hover_cards(app_df, "📱 App Platforms")}
</div>""", unsafe_allow_html=True)


# ── 9. CLIENT & COUNTRY-WISE PIVOT SUMMARY ───────────────────────────────────
st.markdown('<div class="section-header">📋 Detailed Breakdown Summary</div>', unsafe_allow_html=True)

grp_cols = ['Client', 'CountryName', 'PlatformType', 'Ecom_Source']
summary_pivot = filtered_scope.groupby(grp_cols, observed=True).agg(
    Total_SKUs=('eval_key', 'count'),
    Client_Available=('Completeness_Status', lambda x: (x == 'Available (Client Table)').sum()),
    Master_Only=('Completeness_Status', lambda x: (x == 'Master Records (Not in Client)').sum()),
    GSheet_Excluded=('Completeness_Status', lambda x: (x == 'Excluded (Google Sheet)').sum()),
    True_Missing=('Completeness_Status', lambda x: (x == 'True Missing (Action Required)').sum())
).reset_index()

summary_pivot['Client Delivery %'] = (summary_pivot['Client_Available'] / summary_pivot['Total_SKUs'] * 100).round(1)
summary_pivot = summary_pivot.sort_values(by=['Client', 'Total_SKUs'], ascending=[True, False]).reset_index(drop=True)

st.dataframe(summary_pivot, use_container_width=True, height=400)


# ── 10. ACTION REQUIRED & MASTER REVIEW LIST ──────────────────────────────────
st.markdown('<div class="section-header">🔍 Deep Dive & Missing Actions</div>', unsafe_allow_html=True)

status_filter = st.multiselect(
    "Filter by Status (Select records to view in table below):",
    options=['True Missing (Action Required)', 'Master Records (Not in Client)', 'Excluded (Google Sheet)', 'Available (Client Table)'],
    default=['True Missing (Action Required)', 'Master Records (Not in Client)']
)

missing_df = filtered_scope[filtered_scope['Completeness_Status'].isin(status_filter)].copy()

if not missing_df.empty:
    b_col = 'BrandName' if 'BrandName' in missing_df.columns else (st.session_state["scope_keys"][2] if len(st.session_state["scope_keys"]) > 2 else '')
    p_col = 'ProductName' if 'ProductName' in missing_df.columns else (st.session_state["scope_keys"][3] if len(st.session_state["scope_keys"]) > 3 else '')
    
    missing_df['Search_URL'] = missing_df.apply(lambda row: create_search_url(row, b_col, p_col, master_url_df), axis=1)

    raw_disp = ['Client', 'CountryName', 'PlatformType', 'Ecom_Source'] + st.session_state["scope_keys"] + ['Completeness_Status', 'Search_URL']
    valid_disp_cols = []
    for c in raw_disp:
        if c in missing_df.columns and c not in valid_disp_cols:
            valid_disp_cols.append(c)
    
    display_df = missing_df[valid_disp_cols].sort_values(by=['Client', 'Completeness_Status']).reset_index(drop=True)

    search_query = st.text_input("🔍 Quick Search (Brand, Product, Source, etc.)", "")
    if search_query:
        mask = display_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False, na=False)).any(axis=1)
        display_df = display_df[mask]

    st.dataframe(
        display_df, 
        use_container_width=True, 
        height=450,
        column_config={
            "Search_URL": st.column_config.LinkColumn("Verify URL", help="Click to search this product on the retailer website")
        }
    )
    
    st.download_button(
        label=f"📥 Download {len(display_df):,} Filtered Items as CSV",
        data=display_df.to_csv(index=False).encode('utf-8'),
        file_name=f"matrix_deep_dive_report.csv",
        mime="text/csv",
        use_container_width=True
    )
else:
    st.success("🎉 No records found for the selected statuses!")
