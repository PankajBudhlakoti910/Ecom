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
import plotly.express as px

from utils import (
    get_cached_client_data,
    load_pa_data,
    require_credentials,
)

warnings.filterwarnings("ignore")

# ── 1. PAGE CONFIG & STYLES ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Ecom vs Promotional Analysis (PA) Reconciliation",
    page_icon="⚖️",
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
.kpi-card { background:#161b22; border:1px solid #30363d; border-radius:10px; padding:16px 18px; text-align:center; transition: transform 0.2s; position: relative; }
.kpi-card:hover { transform: translateY(-2px); border-color: #58a6ff; }
.kpi-card .kpi-label { font-size:11px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:#8b949e; margin-bottom:6px; }
.kpi-card .kpi-value { font-family:'Space Mono',monospace; font-size:22px; font-weight:700; color:#e6edf3; line-height:1; }
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
</style>
""",
    unsafe_allow_html=True,
)

# Master URL mapping for missing SKUs
URL_MASTER_DATA = [
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
]
master_url_df = pd.DataFrame(URL_MASTER_DATA, columns=["CountryName", "Ecom_Source", "PlatformType", "BaseURL"])

def create_search_url(row, country_col, source_col, brand_col, product_col):
    country = str(row.get(country_col, '')).strip()
    source = str(row.get(source_col, '')).strip()
    brand = str(row.get(brand_col, '')) if pd.notnull(row.get(brand_col)) else ''
    product = str(row.get(product_col, '')) if pd.notnull(row.get(product_col)) else ''
    
    query = f"{brand} {product}".strip()
    if not query: return ""
    
    encoded_query = urllib.parse.quote_plus(query)
    match = master_url_df[(master_url_df['CountryName'] == country) & (master_url_df['Ecom_Source'] == source)]
    if match.empty: return ""
    
    base_link = str(match.iloc[0]['BaseURL']).strip().rstrip('/')
    if not base_link.startswith('http'): base_link = 'https://' + base_link
    
    source_lower = source.lower()
    if 'amazon' in source_lower: return f"{base_link}/s?k={encoded_query}&rh=p_6%3AAmazon"
    elif 'lulu' in source_lower: return f"{base_link}/list/?search_text={encoded_query}"
    elif 'aldawaa' in source_lower: return f"{base_link}/search/{encoded_query}"
    else: return f"{base_link}/search?q={encoded_query}"

# Title & Refresh Bar
col_title, col_sync = st.columns([4, 1])
with col_title:
    st.markdown("# ⚖️ Ecom Deliverables vs Promotional Analysis (PA) Reconciliation")
    st.markdown("Compare E-commerce live tracking against Promotional Analysis datasets, evaluate pricing deltas, and audit SKU coverage.")
with col_sync:
    st.write("")
    if st.button("🔄 Sync & Refresh Datasets", use_container_width=True, help="Reloads both Ecom and PA datasets from BQ cache"):
        st.cache_data.clear()
        for key in ["_session_client_data", "_bq_pa_data"]:
            st.session_state.pop(key, None)
        st.rerun()

# ── 2. DATA LOADING (ECOM + PA) ───────────────────────────────────────────────
with st.status("🚀 Loading Ecom & Promotional Analysis (PA) Datasets...", expanded=True) as status:
    st.write("📥 Fetching Ecom Deliverable Datasets...")
    client_data_dict = get_cached_client_data(force_refresh=False)
    
    ecom_frames = [df for df in client_data_dict.values() if isinstance(df, pd.DataFrame) and not df.empty]
    ecom_df = pd.concat(ecom_frames, ignore_index=True, sort=False) if ecom_frames else pd.DataFrame()
    st.write(f"✅ Ecom Dataset Loaded: **{len(ecom_df):,} rows**")

    st.write("📥 Fetching Session-Cached Promotional Analysis (PA) Data...")
    pa_df = load_pa_data(force_refresh=False)
    st.write(f"✅ PA Dataset Loaded: **{len(pa_df):,} rows**")

    if ecom_df.empty or pa_df.empty:
        status.update(label="⚠️ Warning: One or both datasets are empty.", state="error", expanded=True)
        st.warning("Please verify your BigQuery credentials and ensure source tables contain data.")
    else:
        status.update(label=f"🎉 Data Ready! (Ecom: {len(ecom_df):,} | PA: {len(pa_df):,})", state="complete", expanded=False)

if ecom_df.empty or pa_df.empty:
    st.stop()

# Date range banners
def get_date_range_str(df, date_col):
    if date_col in df.columns:
        valid_dates = pd.to_datetime(df[date_col], errors='coerce').dropna()
        if not valid_dates.empty:
            return f"{valid_dates.min().strftime('%Y-%m-%d')} to {valid_dates.max().strftime('%Y-%m-%d')}"
    return "N/A"

ecom_date_col = next((c for c in ['Data_ExtractionDate', 'offerstartdate', 'OfferStartDate'] if c in ecom_df.columns), None)
pa_date_col = next((c for c in ['OfferStartDate', 'offerstartdate', 'Data_ExtractionDate'] if c in pa_df.columns), None)

st.info(f"📅 **Dataset Timeline Coverage** | 🌐 **Ecom Data Range:** {get_date_range_str(ecom_df, ecom_date_col)} | 📊 **PA Data Range:** {get_date_range_str(pa_df, pa_date_col)}")

# ── 3. DYNAMIC KEY CONFIGURATOR & SEPARATE PREVIEWS ───────────────────────────
st.markdown('<div class="section-header">🔑 Dataset Alignment & Key Configuration</div>', unsafe_allow_html=True)

with st.expander("⚙️ Configure Matching Keys (Auto-Guessed)", expanded=False):
    st.write("Select matching columns for both datasets to align products, brands, and regions.")
    
    def guess_cols(df, options_list):
        return [opt for opt in options_list if opt in df.columns]

    default_key_options = ['CountryName', 'BrandName', 'ProductName', 'PackSize']
    
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        ecom_keys = st.multiselect("Ecom Dataset Key Columns", options=ecom_df.columns.tolist(), default=guess_cols(ecom_df, default_key_options))
    with col_k2:
        pa_keys = st.multiselect("PA Dataset Key Columns", options=pa_df.columns.tolist(), default=guess_cols(pa_df, default_key_options))

def create_eval_key(df: pd.DataFrame, cols: list) -> pd.Series:
    if df.empty or not cols: return pd.Series("", index=df.index)
    key_series = pd.Series("", index=df.index)
    for col in cols:
        if col in df.columns:
            s = df[col].astype(str).str.replace(r'\.0$', '', regex=True)
            val = s.str.lower().str.replace(r'[\s\W_]+', '', regex=True)
            val = np.where(df[col].isna(), "missing", val)
            val = np.where(val == "nan", "missing", val)
            val = np.where(val == "none", "missing", val)
        else:
            val = pd.Series("missing", index=df.index)
        key_series = key_series + "|" + val
    return key_series.str.strip("|")

ecom_df['match_key'] = create_eval_key(ecom_df, ecom_keys)
pa_df['match_key'] = create_eval_key(pa_df, pa_keys)

# Separate Top 50 Previews
col_p1, col_p2 = st.columns(2)
with col_p1:
    if ecom_keys:
        st.markdown("#### 🌐 Ecom Top 50 Rows Preview")
        st.dataframe(ecom_df[ecom_keys].drop_duplicates().head(50), use_container_width=True, height=220)
with col_p2:
    if pa_keys:
        st.markdown("#### 📊 PA Top 50 Rows Preview")
        st.dataframe(pa_df[pa_keys].drop_duplicates().head(50), use_container_width=True, height=220)

# ── 4. PRICING LOGIC EXTRACTION (SELLING PRICE) ───────────────────────────────
ecom_promo_col = next((c for c in ecom_df.columns if 'promoprice' in c.lower()), None)
ecom_reg_col = next((c for c in ecom_df.columns if 'regularprice' in c.lower()), None)

if ecom_promo_col and ecom_reg_col:
    ecom_df['Selling_Price'] = np.where(
        (ecom_df[ecom_promo_col].isna()) | (ecom_df[ecom_promo_col] <= 0),
        pd.to_numeric(ecom_df[ecom_reg_col], errors='coerce'),
        pd.to_numeric(ecom_df[ecom_promo_col], errors='coerce')
    )
else:
    ecom_df['Selling_Price'] = 0.0

pa_promo_col = next((c for c in pa_df.columns if c.lower() in ['promoprice', 'offerprice']), None)
pa_reg_col = next((c for c in pa_df.columns if c.lower() in ['regularprice', 'price']), None)

if pa_promo_col and pa_reg_col:
    pa_df['Selling_Price'] = np.where(
        (pa_df[pa_promo_col].isna()) | (pa_df[pa_promo_col] <= 0),
        pd.to_numeric(pa_df[pa_reg_col], errors='coerce'),
        pd.to_numeric(pa_df[pa_promo_col], errors='coerce')
    )
else:
    pa_df['Selling_Price'] = 0.0

# ── 5. EXPANDABLE FILTERS SECTION (SEPARATE ECOM & PA SLICERS) ────────────────
st.markdown('<div class="section-header">🔍 Advanced Filters & Slicers</div>', unsafe_allow_html=True)

with st.expander("📌 Expand Filters (Client, Country, Source/Retailer, Brand, Product, PackSize)", expanded=False):
    f_tab1, f_tab2 = st.tabs(["🌐 Ecom Filters", "📊 PA (Flyer) Filters"])
    
    with f_tab1:
        e_c1, e_c2, e_c3 = st.columns(3)
        with e_c1:
            e_clients = sorted(ecom_df.get('Client', pd.Series()).dropna().unique().tolist())
            sel_e_clients = st.multiselect("Ecom Client", options=e_clients, default=[], key="sel_e_client")
            e_countries = sorted(ecom_df.get('CountryName', pd.Series()).dropna().unique().tolist())
            sel_e_countries = st.multiselect("Ecom Country", options=e_countries, default=[], key="sel_e_country")
        with e_c2:
            e_sources = sorted(ecom_df.get('Ecom_Source', pd.Series()).dropna().unique().tolist())
            sel_e_sources = st.multiselect("Ecom Source", options=e_sources, default=[], key="sel_e_source")
            e_brands = sorted(ecom_df.get('BrandName', pd.Series()).dropna().unique().tolist())
            sel_e_brands = st.multiselect("Ecom Brand Name", options=e_brands, default=[], key="sel_e_brand")
        with e_c3:
            e_prods = sorted(ecom_df.get('ProductName', pd.Series()).dropna().unique().tolist())
            sel_e_prods = st.multiselect("Ecom Product Name", options=e_prods, default=[], key="sel_e_prod")
            e_packs = sorted(ecom_df.get('PackSize', pd.Series()).dropna().unique().tolist())
            sel_e_packs = st.multiselect("Ecom Pack Size", options=e_packs, default=[], key="sel_e_pack")

    with f_tab2:
            p_c1, p_c2, p_c3 = st.columns(3)
            with p_c1:
                p_clients = sorted(pa_df.get('Client', pd.Series()).dropna().unique().tolist())
                sel_p_clients = st.multiselect("PA Client", options=p_clients, default=[], key="sel_p_client")
                p_countries = sorted(pa_df.get('CountryName', pd.Series()).dropna().unique().tolist())
                sel_p_countries = st.multiselect("PA Country", options=p_countries, default=[], key="sel_p_country")
            with p_c2:
                p_retailers = sorted(pa_df.get('RetailerName', pd.Series()).dropna().unique().tolist())
                sel_p_retailers = st.multiselect("PA Retailer Name", options=p_retailers, default=[], key="sel_p_retailer")
                p_brands = sorted(pa_df.get('BrandName', pd.Series()).dropna().unique().tolist())
                sel_p_brands = st.multiselect("PA Brand Name", options=p_brands, default=[], key="sel_p_brand")
            with p_c3:
                p_prods = sorted(pa_df.get('ProductName', pd.Series()).dropna().unique().tolist())
                sel_p_prods = st.multiselect("PA Product Name", options=p_prods, default=[], key="sel_p_prod")
                p_packs = sorted(pa_df.get('PackSize', pd.Series()).dropna().unique().tolist())
                sel_p_packs = st.multiselect("PA Pack Size", options=p_packs, default=[], key="sel_p_pack")

# Apply filters independently
filtered_ecom = ecom_df.copy()
if sel_e_clients: filtered_ecom = filtered_ecom[filtered_ecom.get('Client', '').isin(sel_e_clients)]
if sel_e_countries: filtered_ecom = filtered_ecom[filtered_ecom.get('CountryName', '').isin(sel_e_countries)]
if sel_e_sources: filtered_ecom = filtered_ecom[filtered_ecom.get('Ecom_Source', '').isin(sel_e_sources)]
if sel_e_brands: filtered_ecom = filtered_ecom[filtered_ecom.get('BrandName', '').isin(sel_e_brands)]
if sel_e_prods: filtered_ecom = filtered_ecom[filtered_ecom.get('ProductName', '').isin(sel_e_prods)]
if sel_e_packs: filtered_ecom = filtered_ecom[filtered_ecom.get('PackSize', '').isin(sel_e_packs)]

filtered_pa = pa_df.copy()
if sel_p_clients: filtered_pa = filtered_pa[filtered_pa.get('Client', '').isin(sel_p_clients)]
if sel_p_countries: filtered_pa = filtered_pa[filtered_pa.get('CountryName', '').isin(sel_p_countries)]
if sel_p_retailers: filtered_pa = filtered_pa[filtered_pa.get('RetailerName', '').isin(sel_p_retailers)]
if sel_p_brands: filtered_pa = filtered_pa[filtered_pa.get('BrandName', '').isin(sel_p_brands)]
if sel_p_prods: filtered_pa = filtered_pa[filtered_pa.get('ProductName', '').isin(sel_p_prods)]
if sel_p_packs: filtered_pa = filtered_pa[filtered_pa.get('PackSize', '').isin(sel_p_packs)]



# ── 6. SKU OVERLAP & KPI SUMMARY WITH CLIENT COUNTS ──────────────────────────
st.markdown('<div class="section-header">📊 SKU Coverage & Overlap Analysis</div>', unsafe_allow_html=True)

ecom_keys_set = set(filtered_ecom['match_key'].dropna().unique())
pa_keys_set = set(filtered_pa['match_key'].dropna().unique())

common_skus = ecom_keys_set.intersection(pa_keys_set)
ecom_only_skus = ecom_keys_set - pa_keys_set
pa_only_skus = pa_keys_set - ecom_keys_set

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Ecom Unique SKUs</div><div class="kpi-value">{len(ecom_keys_set):,}</div><div class="kpi-sub">Filtered Active Base</div></div>', unsafe_allow_html=True)
with m2:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">PA Unique SKUs</div><div class="kpi-value">{len(pa_keys_set):,}</div><div class="kpi-sub">Filtered Promotional Base</div></div>', unsafe_allow_html=True)
with m3:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Common SKUs (Overlap)</div><div class="kpi-value" style="color:#3fb950;">{len(common_skus):,}</div><div class="kpi-sub">Available in Both</div></div>', unsafe_allow_html=True)
with m4:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Exclusive in Ecom</div><div class="kpi-value" style="color:#d29922;">{len(ecom_only_skus):,}</div><div class="kpi-sub">Not Present in PA</div></div>', unsafe_allow_html=True)
with m5:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Exclusive in PA</div><div class="kpi-value" style="color:#f85149;">{len(pa_only_skus):,}</div><div class="kpi-sub">Not Present in Ecom</div></div>', unsafe_allow_html=True)

# ── 7. RESTORED: CLIENT-WISE SKU DISTRIBUTION & OVERLAP ──────────────────────
st.markdown('<div class="section-header">📋 Client-Wise SKU Distribution & Overlap</div>', unsafe_allow_html=True)

if 'Client' in filtered_ecom.columns and 'Client' in filtered_pa.columns:
    clients = sorted(list(set(filtered_ecom['Client'].dropna().unique()).union(set(filtered_pa['Client'].dropna().unique()))))
    client_summary = []
    
    for cl in clients:
        sub_e = filtered_ecom[filtered_ecom['Client'] == cl]
        sub_p = filtered_pa[filtered_pa['Client'] == cl]
        
        e_set = set(sub_e['match_key'].dropna().unique())
        p_set = set(sub_p['match_key'].dropna().unique())
        
        overlap = len(e_set.intersection(p_set))
        e_new = len(e_set - p_set)
        p_new = len(p_set - e_set)
        
        client_summary.append({
            "Client": cl,
            "Ecom SKU Count": len(e_set),
            "PA SKU Count": len(p_set),
            "Common SKUs": overlap,
            "Exclusive in Ecom": e_new,
            "Exclusive in PA (Missing in Ecom)": p_new
        })
    
    df_client_summary = pd.DataFrame(client_summary)
    st.dataframe(df_client_summary, use_container_width=True, height=220)


# ── 8. SOURCE-WISE SKU AVAILABILITY & GAP AUDIT ──────────────────────────────
st.markdown('<div class="section-header">🔍 Source-Wise SKU Availability & Gap Audit</div>', unsafe_allow_html=True)
st.caption("ℹ️ Evaluates how many PA promotional SKUs are present vs missing across individual e-commerce source platforms.")

if 'Ecom_Source' in filtered_ecom.columns:
    sources = sorted(filtered_ecom['Ecom_Source'].dropna().unique())
    source_audit = []
    
    for src in sources:
        sub_src = filtered_ecom[filtered_ecom['Ecom_Source'] == src]
        src_keys = set(sub_src['match_key'].dropna().unique())
        
        present_in_src = len(src_keys.intersection(pa_keys_set))
        missing_in_src = len(pa_keys_set - src_keys)
        
        source_audit.append({
            "Ecom Source": src,
            "Total PA SKUs Target": len(pa_keys_set),
            "Present in Source": present_in_src,
            "Missing in Source": missing_in_src,
            "Source Coverage %": round((present_in_src / len(pa_keys_set) * 100), 1) if len(pa_keys_set) > 0 else 0.0
        })
    
    df_source_audit = pd.DataFrame(source_audit)
    st.dataframe(df_source_audit, use_container_width=True, height=250)


# ── 9. RESTORED: SIDE-BY-SIDE PRICING & VARIANCE ANALYSIS ─────────────────────
st.markdown('<div class="section-header">⚖️ Side-by-Side Pricing & Variance Analysis</div>', unsafe_allow_html=True)
st.caption("ℹ️ Aggregated comparison of pricing between Ecom and Promotional Analysis based on selected key alignment.")

agg_ecom = filtered_ecom.groupby('match_key', observed=True).agg(
    Ecom_Price=('Selling_Price', 'mean'),
    Ecom_Records=('match_key', 'count')
).reset_index()

agg_pa = filtered_pa.groupby('match_key', observed=True).agg(
    PA_Price=('Selling_Price', 'mean'),
    PA_Records=('match_key', 'count')
).reset_index()

merged_recon = pd.merge(agg_ecom, agg_pa, on='match_key', how='inner')
merged_recon['Price_Difference (Ecom - PA)'] = (merged_recon['Ecom_Price'] - merged_recon['PA_Price']).round(2)
merged_recon['Price_Variance_%'] = np.where(
    merged_recon['PA_Price'] > 0,
    ((merged_recon['Ecom_Price'] - merged_recon['PA_Price']) / merged_recon['PA_Price'] * 100).round(2),
    0.0
)

sample_attr = filtered_ecom[ecom_keys + ['match_key']].drop_duplicates(subset=['match_key'])
display_recon = pd.merge(sample_attr, merged_recon, on='match_key', how='inner').drop(columns=['match_key'])

search_q = st.text_input("🔍 Search Reconciled SKUs (Brand, Product, etc.)", "")
if search_q:
    mask = display_recon.astype(str).apply(lambda x: x.str.contains(search_q, case=False, na=False)).any(axis=1)
    display_recon = display_recon[mask]

st.dataframe(display_recon, use_container_width=True, height=350)


# ── 10. SEARCH URL GENERATOR FOR MISSING PA SKUS (FIXED DUPLICATE COLUMNS) ─────
st.markdown('<div class="section-header">🌐 Actionable Search URLs for PA SKUs Missing in Ecom</div>', unsafe_allow_html=True)
st.caption("ℹ️ SKUs present in Promotional Analysis but missing from Ecom are listed below with generated retailer search links (using text/name columns only).")

pa_only_skus = set(filtered_pa['match_key'].dropna().unique()) - set(filtered_ecom['match_key'].dropna().unique())
missing_pa_df = filtered_pa[filtered_pa['match_key'].isin(pa_only_skus)].drop_duplicates(subset=['match_key']).copy()

if not missing_pa_df.empty:
    country_c = next((c for c in missing_pa_df.columns if 'country' in c.lower()), 'CountryName')
    source_c = next((c for c in missing_pa_df.columns if 'retailer' in c.lower() or 'source' in c.lower()), 'RetailerName')
    brand_c = next((c for c in missing_pa_df.columns if c.lower() in ['brandname', 'brand']), 'BrandName')
    prod_c = next((c for c in missing_pa_df.columns if c.lower() in ['productname', 'product', 'offername']), 'ProductName')

    missing_pa_df['Search_URL'] = missing_pa_df.apply(lambda r: create_search_url(r, country_c, source_c, brand_c, prod_c), axis=1)
    
    # Strictly select unique name/text columns to prevent duplicate column errors in Arrow/PyArrow
    desired_cols = [country_c, source_c, brand_c, prod_c, 'Search_URL']
    unique_disp_cols = []
    for c in desired_cols:
        if c in missing_pa_df.columns and c not in unique_disp_cols:
            unique_disp_cols.append(c)

    disp_missing = missing_pa_df[unique_disp_cols].copy()
    st.dataframe(
        disp_missing,
        use_container_width=True,
        height=300,
        column_config={"Search_URL": st.column_config.LinkColumn("Retailer Search Link", help="Click to search product online")}
    )
else:
    st.success("🎉 No missing PA SKUs found! All promotional items are captured in Ecom.")


# ── 11. SIDE-BY-SIDE DATA TABLES & SEPARATE DOWNLOAD OPTIONS ──────────────────
st.markdown('<div class="section-header">📦 Side-by-Side Data Tables & Export Options</div>', unsafe_allow_html=True)

row_limit_opt = st.selectbox("Select Row Limit for Tables:", options=[500, 1000, "All"], index=0)
limit_val = len(filtered_ecom) if row_limit_opt == "All" else int(row_limit_opt)

col_t1, col_t2 = st.columns(2)
with col_t1:
    st.markdown("#### 🌐 Ecom Deliverables Data")
    st.dataframe(filtered_ecom.head(limit_val), use_container_width=True, height=400)
with col_t2:
    st.markdown("#### 📊 Promotional Analysis (PA) Data")
    st.dataframe(filtered_pa.head(limit_val), use_container_width=True, height=400)

# Separate and Consolidated Downloads
st.markdown("### 📥 Export Reports")
dl_c1, dl_c2, dl_c3, dl_c4 = st.columns(4)

with dl_c1:
    st.download_button(
        "📥 Download Available in Both",
        data=filtered_ecom[filtered_ecom['match_key'].isin(common_skus)].to_csv(index=False).encode('utf-8'),
        file_name="available_in_both.csv",
        mime="text/csv",
        use_container_width=True
    )
with dl_c2:
    st.download_button(
        "📥 Download Ecom All",
        data=filtered_ecom.to_csv(index=False).encode('utf-8'),
        file_name="ecom_all.csv",
        mime="text/csv",
        use_container_width=True
    )
with dl_c3:
    st.download_button(
        "📥 Download PA All",
        data=filtered_pa.to_csv(index=False).encode('utf-8'),
        file_name="pa_all.csv",
        mime="text/csv",
        use_container_width=True
    )
with dl_c4:
    # Consolidated Excel Export
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        filtered_ecom[filtered_ecom['match_key'].isin(common_skus)].to_excel(writer, sheet_name='Available in Both', index=False)
        filtered_ecom.to_excel(writer, sheet_name='Ecom All', index=False)
        filtered_pa.to_excel(writer, sheet_name='PA All', index=False)
        display_recon.to_excel(writer, sheet_name='Pricing Variance', index=False)
    processed_data = output.getvalue()
    
    st.download_button(
        "📥 Download Consolidated Excel",
        data=processed_data,
        file_name="ecom_vs_pa_consolidated_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )


# ── 12. SKU-WISE DYNAMIC CHART WITH WEEK SELECTION ───────────────────────────
st.markdown('<div class="section-header">📈 SKU-Wise Dynamic Trendline Chart</div>', unsafe_allow_html=True)

week_col_e = next((c for c in filtered_ecom.columns if 'week' in c.lower()), None)
week_col_p = next((c for c in filtered_pa.columns if 'week' in c.lower()), None)

if week_col_e and week_col_p:
    all_weeks = sorted(list(set(filtered_ecom[week_col_e].dropna().unique()).union(set(filtered_pa[week_col_p].dropna().unique()))))
    
    if all_weeks:
        ch_c1, ch_c2 = st.columns([1, 2])
        with ch_c1:
            selected_week = st.selectbox("Select Week Number:", options=all_weeks, index=len(all_weeks)-1)
            chart_metric = st.selectbox("Select Pricing Metric:", options=['Selling_Price', 'Regular Price', 'Promo Price'], index=0)
            
        wk_ecom = filtered_ecom[filtered_ecom[week_col_e] == selected_week]
        wk_pa = filtered_pa[filtered_pa[week_col_p] == selected_week]
        
        group_key = 'BrandName' if 'BrandName' in wk_ecom.columns else 'match_key'
        
        chart_e = wk_ecom.groupby(group_key, observed=True)['Selling_Price'].mean().reset_index()
        chart_e['Dataset'] = 'Ecom Deliverables'
        
        chart_p = wk_pa.groupby(group_key, observed=True)['Selling_Price'].mean().reset_index()
        chart_p['Dataset'] = 'Promotional Analysis (PA)'
        
        chart_merged = pd.concat([chart_e, chart_p], ignore_index=True)
        
        with ch_c2:
            if not chart_merged.empty:
                fig = px.bar(
                    chart_merged.head(20), 
                    x=group_key, 
                    y='Selling_Price', 
                    color='Dataset',
                    barmode='group',
                    title=f"SKU Pricing Comparison for Week: {selected_week}",
                    template='plotly_dark',
                    labels={'Selling_Price': 'Average Price', group_key: 'SKU / Brand'}
                )
                fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No data available for the selected week.")
    else:
        st.info("No weeks found for chart generation.")
else:
    st.info("Week columns not present for SKU-wise charting.")