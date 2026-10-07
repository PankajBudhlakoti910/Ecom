"""
Weekly Deliverables & SKU Analysis Tracking System
===================================================
High-performance tracking dashboard for client-wise delivery percentages, 
weekly price points, coverage heatmaps, and dead/unpromoted SKU audits.
Optimized for instant filtering and vectorized aggregations.
"""

from __future__ import annotations

import os
import sys
import warnings
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

# ── 1. PAGE CONFIG & STYLES ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Weekly Deliverables Tracking System",
    page_icon="🗓️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: #0d1117; color: #e6edf3; }

.kpi-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:12px; margin-bottom:20px; }
.kpi-card { background:#161b22; border:1px solid #30363d; border-radius:10px; padding:16px 18px;
            position:relative; overflow:hidden; text-align:center; }
.kpi-card .kpi-label { font-size:11.5px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:#8b949e; margin-bottom:6px; }
.kpi-card .kpi-value { font-family:'Space Mono',monospace; font-size:24px; font-weight:700; color:#e6edf3; line-height:1; }
.kpi-card .kpi-sub { font-size:11px; margin-top:5px; color:#58a6ff; }

.client-card { background:#161b22; border:1px solid #30363d; border-top: 3px solid #58a6ff; border-radius:8px; padding:14px; }
.client-card .c-title { font-size:15px; font-weight:700; color:#e6edf3; margin-bottom:12px; text-transform:uppercase; letter-spacing:0.05em; }
.client-card .c-row { display:flex; justify-content:space-between; margin-bottom:6px; align-items:center; }
.client-card .c-lbl { font-size:11.5px; color:#8b949e; }
.client-card .c-val { font-size:13px; font-weight:700; font-family:'Space Mono',monospace; }

[data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th,
[data-testid="stTable"] td, [data-testid="stTable"] th,
table td, table th { text-align:center !important; vertical-align:middle !important; }

.section-header { font-family:'Space Mono',monospace; font-size:14px; font-weight:700; letter-spacing:.08em;
                  text-transform:uppercase; color:#58a6ff; border-bottom:1px solid #21262d;
                  padding-bottom:8px; margin:32px 0 16px; }
</style>
""",
    unsafe_allow_html=True,
)

# ── 2. UTILS IMPORT & PATH RESOLUTION ─────────────────────────────────────────
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from utils import (
        require_credentials,
        get_cached_client_data,
        load_henkel_kenvue,
    )
    _HAS_UTILS = True
except ImportError:
    _HAS_UTILS = False

if _HAS_UTILS:
    require_credentials()

# ── 3. DATA LOADING & IN-MEMORY CACHE PREPARATION ────────────────────────────
@st.cache_data(show_spinner=False, ttl=1800)
def get_clean_weekly_base_df() -> pd.DataFrame:
    """Fetches weekly data and normalizes column types once in memory."""
    # Check if data already exists in global session cache from main page
    raw_dict = st.session_state.get("_session_client_data", {}).get("client_data", {})
    frames = [df for k, df in raw_dict.items() if k in ["henkel", "kenvue", "stada","bayara"] and isinstance(df, pd.DataFrame) and not df.empty]
    
    if frames:
        df = pd.concat(frames, ignore_index=True, sort=False)
    else:
        df = load_henkel_kenvue()

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Standardize columns
    target_cols = ['Client', 'CountryName', 'Ecom_Source', 'BrandFlag', 'weeknum', 'Ecom_SKU', 
                   'Ecom_Desc_Name', 'Ecom_ImageUrl', 'Ecom_WebUrl', 'id', 'BrandName', 'ProductName', 'PackSize']
    for col in target_cols:
        if col not in df.columns:
            df[col] = "Unknown"
        else:
            df[col] = df[col].fillna("Unknown")

    if 'SellingPrice' not in df.columns:
        df['SellingPrice'] = pd.to_numeric(df.get('Ecom_PromoPrice', np.nan), errors='coerce')
    else:
        df['SellingPrice'] = pd.to_numeric(df['SellingPrice'], errors='coerce')

    df['weeknum'] = pd.to_numeric(df['weeknum'], errors='coerce').fillna(0).astype(int)
    return df

with st.spinner("⚡ Fetching weekly dataset..."):
    weekly_df = get_clean_weekly_base_df()

if weekly_df is None or weekly_df.empty:
    st.warning("⚠️ No weekly data available. Please verify BigQuery credentials or load data on Home/App page.")
    st.stop()

# ── 4. INSTANT SIDEBAR FILTERS ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 Tracking Filters")
    
    # Client List
    clients = sorted([c for c in weekly_df['Client'].unique() if c != "Unknown"])
    sel_client = st.multiselect("Client", clients, default=[])
    
    # Country List (Chained)
    df_scope1 = weekly_df[weekly_df['Client'].isin(sel_client)] if sel_client else weekly_df
    countries = sorted([c for c in df_scope1['CountryName'].unique() if c != "Unknown"])
    sel_country = st.multiselect("Country", countries, default=[])
    
    # Source List (Chained)
    df_scope2 = df_scope1[df_scope1['CountryName'].isin(sel_country)] if sel_country else df_scope1
    sources = sorted([s for s in df_scope2['Ecom_Source'].unique() if s != "Unknown"])
    sel_source = st.multiselect("Ecom Source", sources, default=[])

# Apply filters with fast Boolean masking
mask = pd.Series(True, index=weekly_df.index)
if sel_client:
    mask &= weekly_df['Client'].isin(sel_client)
if sel_country:
    mask &= weekly_df['CountryName'].isin(sel_country)
if sel_source:
    mask &= weekly_df['Ecom_Source'].isin(sel_source)

filtered_df = weekly_df[mask]

st.markdown("# 🗓️ Weekly Deliverables Tracking System")
st.markdown("Monitor exact delivery percentages, price point coverage, dead SKUs, and data health across the entire operational pipeline.")

if filtered_df.empty:
    st.info("No records match the current filter selection.")
    st.stop()

# ── 5. EXECUTIVE KPI STRIP ────────────────────────────────────────────────────
weeks_sorted = sorted(filtered_df['weeknum'].unique().tolist(), reverse=True)
latest_week = weeks_sorted[0] if weeks_sorted else 0

latest_df = filtered_df[filtered_df['weeknum'] == latest_week]
idc = "id" if "id" in filtered_df.columns else "Ecom_SKU"

total_distinct_ids = filtered_df[idc].nunique()
total_master_skus = filtered_df['Ecom_SKU'].nunique()
latest_promoted_skus = latest_df['Ecom_SKU'].nunique()
delivery_pct = (latest_promoted_skus / total_master_skus * 100) if total_master_skus > 0 else 0.0
latest_price_points = int(latest_df["SellingPrice"].notna().sum())
total_latest_rows = len(latest_df)

st.markdown(f"""
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="kpi-label">Total Promoted (Distinct IDs)</div>
        <div class="kpi-value">{total_distinct_ids:,}</div>
        <div class="kpi-sub">All-time unique IDs</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Total Unique SKUs (All-Time)</div>
        <div class="kpi-value">{total_master_skus:,}</div>
        <div class="kpi-sub">All-time distinct SKU codes</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Latest Wk Promoted SKUs</div>
        <div class="kpi-value" style="color:#3fb950;">{latest_promoted_skus:,}</div>
        <div class="kpi-sub">Wk {latest_week}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Latest Week Delivery %</div>
        <div class="kpi-value" style="color:{'#3fb950' if delivery_pct >= 50 else '#f85149'};">{delivery_pct:.1f}%</div>
        <div class="kpi-sub">Promoted vs All-Time Base</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Price Points Delivered</div>
        <div class="kpi-value">{latest_price_points:,}</div>
        <div class="kpi-sub">Valid Prices Wk {latest_week}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Latest Wk Records (Rows)</div>
        <div class="kpi-value">{total_latest_rows:,}</div>
        <div class="kpi-sub">Total operational rows</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── CLIENT-WISE BREAKDOWN CARDS ───────────────────────────────────────────────
client_names = sorted([c for c in filtered_df["Client"].unique() if c != "Unknown"])
if client_names:
    st.markdown('<div class="section-header" style="color:#8b949e; margin-top:20px;">🏢 Client-Wise Performance Breakdown</div>', unsafe_allow_html=True)
    num_cols = min(len(client_names), 4)
    cols = st.columns(num_cols)
    
    for i, c_name in enumerate(client_names):
        c_df = filtered_df[filtered_df["Client"] == c_name]
        c_latest_week = int(c_df['weeknum'].max())
        c_latest = c_df[c_df['weeknum'] == c_latest_week]
        
        c_total_ids = c_df[idc].nunique()
        c_unique_skus = c_df["Ecom_SKU"].nunique()
        c_latest_promo_id = c_latest[idc].nunique()
        c_latest_promo_sku = c_latest["Ecom_SKU"].nunique()
        
        card_html = f"""
        <div style="background:#161b22; border:1px solid #30363d; border-top:3px solid #58a6ff; border-radius:8px; padding:16px; margin-bottom:15px;">
            <div style="font-size:15px; font-weight:700; color:#e6edf3; margin-bottom:12px; text-transform:uppercase; letter-spacing:0.05em;">{c_name}</div>
            <div style="display:flex; justify-content:space-between; margin-bottom:6px; align-items:center;">
                <span style="font-size:11px; color:#8b949e;">All-Time (Distinct IDs)</span>
                <span style="font-size:13px; font-weight:700; font-family:'Space Mono',monospace; color:#58a6ff;">{c_total_ids:,}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:6px; align-items:center;">
                <span style="font-size:11px; color:#8b949e;">Master Base (Ecom_SKUs)</span>
                <span style="font-size:13px; font-weight:700; font-family:'Space Mono',monospace; color:#3fb950;">{c_unique_skus:,}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:10px; border-top:1px solid #30363d; padding-top:10px; align-items:center;">
                <span style="font-size:11px; color:#e6edf3;">Latest Wk {c_latest_week} (IDs)</span>
                <span style="font-size:14px; font-weight:700; font-family:'Space Mono',monospace; color:#58a6ff;">{c_latest_promo_id:,}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:6px; align-items:center;">
                <span style="font-size:11px; color:#e6edf3;">Latest Wk {c_latest_week} (Ecom_SKUs)</span>
                <span style="font-size:16px; font-weight:700; font-family:'Space Mono',monospace; color:#d29922;">{c_latest_promo_sku:,}</span>
            </div>
        </div>
        """
        cols[i % num_cols].markdown(card_html, unsafe_allow_html=True)





# ── 6. MASTER SUMMARY: DELIVERY STATUS & WEEKLY TRENDS ────────────────────────
st.markdown('<div class="section-header">📈 Master Delivery Summary & Weekly SKU Trend</div>', unsafe_allow_html=True)
st.caption("ℹ️ A unified view showing Total Master SKUs per Client/Country/Source, their week-over-week promoted volumes, and the final Delivery Percentage with color-coded health indicators.")

# High speed pivot
master_pivot = filtered_df.pivot_table(
    index=['Client', 'CountryName', 'Ecom_Source'],
    columns='weeknum',
    values='Ecom_SKU',
    aggfunc='nunique',
    fill_value=0
)

# Overall distinct SKUs per slice
master_totals = filtered_df.groupby(['Client', 'CountryName', 'Ecom_Source'], observed=True)['Ecom_SKU'].nunique()
master_summary = master_pivot.copy()
master_summary.insert(0, 'Total_Master_SKUs', master_totals)
master_summary = master_summary.reset_index()

w_cols = [c for c in master_summary.columns if isinstance(c, (int, np.integer)) and c > 0]
w_cols_sorted = sorted(w_cols, reverse=True)

if w_cols_sorted:
    latest_c = w_cols_sorted[0]
    master_summary['Latest_Wk_Delivery_%'] = (master_summary[latest_c] / master_summary['Total_Master_SKUs'] * 100).round(1)
else:
    master_summary['Latest_Wk_Delivery_%'] = 0.0

final_cols = ['Client', 'CountryName', 'Ecom_Source', 'Total_Master_SKUs'] + w_cols_sorted + ['Latest_Wk_Delivery_%']
master_summary = master_summary[final_cols].sort_values(by='Total_Master_SKUs', ascending=False)

# ── Conditional Formatting & Styling ──────────────────────────────────────────
def color_delivery_rate(val):
    """Applies conditional coloring based on Delivery Percentage thresholds."""
    if pd.isna(val):
        return ''
    if val >= 75:
        return 'background-color: rgba(46, 160, 67, 0.25); color: #3fb950; font-weight: bold;'  # Green (High)
    elif val >= 40:
        return 'background-color: rgba(210, 153, 34, 0.25); color: #d29922; font-weight: bold;'  # Orange/Yellow (Medium)
    else:
        return 'background-color: rgba(248, 81, 73, 0.25); color: #f85149; font-weight: bold;'   # Red (Low)

try:
    # Apply gradient to weekly columns and threshold coloring to Delivery %
    styled_summary = master_summary.style.background_gradient(subset=w_cols_sorted, cmap="YlGnBu", low=0.1, high=0.1)
    styled_summary = styled_summary.map(color_delivery_rate, subset=['Latest_Wk_Delivery_%'])
    st.dataframe(styled_summary, use_container_width=True, height=400)
except Exception:
    # Fallback if st.dataframe styling throws any version conflict
    st.dataframe(master_summary, use_container_width=True, height=400)

st.download_button("⬇️ Download Master Delivery Summary", master_summary.to_csv(index=False).encode('utf-8'), "master_delivery_summary.csv", "text/csv")







# ── 7. BRAND DISTRIBUTION (MY BRAND VS COMPETITOR) ────────────────────────────
st.markdown('<div class="section-header">🏷️ Brand Distribution & Weekly Trend (My Brand vs Competitor)</div>', unsafe_allow_html=True)
st.caption("ℹ️ Breakdown of Total Master SKUs and Weekly Promoted volumes at the Brand level with performance color gradients.")

brand_pivot = filtered_df.pivot_table(
    index=['Client', 'CountryName', 'Ecom_Source', 'BrandFlag', 'BrandName'],
    columns='weeknum',
    values='Ecom_SKU',
    aggfunc='nunique',
    fill_value=0
)
brand_totals = filtered_df.groupby(['Client', 'CountryName', 'Ecom_Source', 'BrandFlag', 'BrandName'], observed=True)['Ecom_SKU'].nunique()
brand_summary = brand_pivot.copy()
brand_summary.insert(0, 'Total_Master_SKUs', brand_totals)
brand_summary = brand_summary.reset_index()

b_cols = [c for c in brand_summary.columns if isinstance(c, (int, np.integer)) and c > 0]
b_cols_sorted = sorted(b_cols, reverse=True)
brand_final_cols = ['Client', 'CountryName', 'Ecom_Source', 'BrandFlag', 'BrandName', 'Total_Master_SKUs'] + b_cols_sorted
brand_summary = brand_summary[brand_final_cols].sort_values(by=['Client', 'CountryName', 'Ecom_Source', 'Total_Master_SKUs'], ascending=[True, True, True, False])

try:
    # Apply background gradient styling to weekly columns
    styled_brand = brand_summary.style.background_gradient(subset=b_cols_sorted, cmap="YlGnBu", low=0.1, high=0.1)
    st.dataframe(styled_brand, use_container_width=True, height=350)
except Exception:
    st.dataframe(brand_summary, use_container_width=True, height=350)

st.download_button("⬇️ Download Brand Distribution", brand_summary.to_csv(index=False).encode('utf-8'), "brand_distribution_summary.csv", "text/csv")







# ── 8. DEAD / UNPROMOTED SKU AUDIT (Missing Last 5 Weeks) ─────────────────────
st.markdown('<div class="section-header">❌ Dead SKUs Audit (Missing for 5+ Consecutive Weeks)</div>', unsafe_allow_html=True)
st.caption("ℹ️ Identifies SKUs that were active historically but have generated **zero promotions in the last 5 weeks**.")

if len(weeks_sorted) >= 5:
    last_5_weeks = set(weeks_sorted[:5])
    historical_weeks = set(weeks_sorted[5:])

    # Fast set intersections
    recent_skus = set(filtered_df[filtered_df['weeknum'].isin(last_5_weeks)]['Ecom_SKU'])
    historical_skus = set(filtered_df[filtered_df['weeknum'].isin(historical_weeks)]['Ecom_SKU'])
    dead_skus = historical_skus - recent_skus

    if dead_skus:
        dead_df = filtered_df[filtered_df['Ecom_SKU'].isin(dead_skus)]
        last_seen = dead_df.groupby('Ecom_SKU')['weeknum'].max().reset_index(name='Last_Seen_Week')
        
        meta_cols = [c for c in [idc, 'Ecom_SKU', 'Client', 'CountryName', 'Ecom_Source', 'Ecom_Desc_Name', 'Ecom_WebUrl', 'BrandName', 'ProductName', 'PackSize'] if c in dead_df.columns]
        meta_df = dead_df[meta_cols].drop_duplicates(subset=['Ecom_SKU'], keep='last')
        dead_final = meta_df.merge(last_seen, on='Ecom_SKU', how='left')

        st.warning(f"⚠️ Found {len(dead_final):,} SKUs completely missing from delivery for the last 5 weeks.")
        st.dataframe(dead_final, use_container_width=True, height=350)
        st.download_button("⬇️ Download Dead SKUs Audit", dead_final.to_csv(index=False).encode('utf-8'), "dead_skus_5_weeks.csv", "text/csv")
    else:
        st.success("🎉 Excellent! All historically tracked SKUs have appeared at least once in the last 5 weeks.")
else:
    st.info(f"Need at least 5 distinct weeks of data to run this audit. Currently tracking {len(weeks_sorted)} weeks.")

# ── 9. DATA HEALTH & DUPLICATES DRILL-DOWN (VECTORIZED) ────────────────────────
st.markdown('<div class="section-header">🩺 Data Health Issues (Impacted Distinct IDs)</div>', unsafe_allow_html=True)

# 100x faster than .apply(): pure boolean indexing
blank_name_mask = filtered_df['Ecom_Desc_Name'].str.strip().isin(['', 'Unknown'])
blank_img_mask = filtered_df['Ecom_ImageUrl'].str.strip().isin(['', 'Unknown'])

blank_name_ids = filtered_df.loc[blank_name_mask, idc].nunique()
blank_img_ids = filtered_df.loc[blank_img_mask, idc].nunique()

d1, d2, d3 = st.columns(3)
d1.metric("Blank Ecom Names (Impacted IDs)", f"{blank_name_ids:,} / {total_distinct_ids:,}")
d2.metric("Blank Image URLs (Impacted IDs)", f"{blank_img_ids:,} / {total_distinct_ids:,}")
d3.metric("Total Records Checked (Rows)", f"{len(filtered_df):,}")

# Grouped breakdown vectorized
group_cols = ['Client', 'CountryName', 'Ecom_Source']
hb_total = filtered_df.groupby(group_cols, observed=True)[idc].nunique().rename('Total_Distinct_IDs')
hb_names = filtered_df[blank_name_mask].groupby(group_cols, observed=True)[idc].nunique().rename('Blank_Names_IDs')
hb_imgs = filtered_df[blank_img_mask].groupby(group_cols, observed=True)[idc].nunique().rename('Blank_Images_IDs')

health_breakdown = pd.concat([hb_total, hb_names, hb_imgs], axis=1).fillna(0).astype(int).reset_index()
health_breakdown = health_breakdown.sort_values(by='Total_Distinct_IDs', ascending=False)
st.dataframe(health_breakdown, use_container_width=True, height=250)

# ── 10. DETAILED SKU & PRICING RECORDS TABLE ──────────────────────────────────
st.markdown('<div class="section-header">📋 Detailed SKU & Pricing Records</div>', unsafe_allow_html=True)
st.caption("ℹ️ Operational records filtered to your selection, with week numbers as columns showing Selling Price.")

ecom_name_col = 'Ecom_Desc_Name' if 'Ecom_Desc_Name' in filtered_df.columns else 'Ecom_SKU'
index_cols = ['Client', 'CountryName', 'Ecom_Source', idc, ecom_name_col, 'Ecom_SKU']
valid_idx_cols = [c for c in index_cols if c in filtered_df.columns]

# Fast pivot
detail_pivot = filtered_df.pivot_table(
    index=valid_idx_cols,
    columns='weeknum',
    values='SellingPrice',
    aggfunc='last'
).reset_index()

week_cols = [c for c in detail_pivot.columns if isinstance(c, (int, np.integer)) and c > 0]
week_cols_sorted = sorted(week_cols, reverse=True)
final_detail_cols = valid_idx_cols + week_cols_sorted
detail_df = detail_pivot[final_detail_cols].sort_values(by=['Client', 'CountryName', 'Ecom_Source'])

st.dataframe(detail_df, use_container_width=True, height=450)
st.download_button("⬇️ Download Detailed Records", detail_df.to_csv(index=False).encode('utf-8'), "detailed_pricing_records.csv", "text/csv")

# ── 11. 10-WEEK PRICING VARIANCE & PROMOTION AUDIT ────────────────────────────
st.markdown('<div class="section-header">📊 10-Week Pricing Variance & Promotion Audit</div>', unsafe_allow_html=True)
st.caption("ℹ️ Deep dive into SKU performance over the last 10 weeks.")

if len(weeks_sorted) > 0 and valid_idx_cols:
    last_10_weeks = weeks_sorted[:10]
    df_10 = filtered_df[filtered_df['weeknum'].isin(last_10_weeks)]
    
    pivot_10 = df_10.pivot_table(
        index=valid_idx_cols,
        columns='weeknum',
        values='SellingPrice',
        aggfunc='last'
    ).reset_index()

    week_10_cols = sorted([w for w in last_10_weeks if w in pivot_10.columns], reverse=True)
    
    pivot_10['Weeks_Promoted'] = pivot_10[week_10_cols].count(axis=1)
    pivot_10['10_Wk_Avg_Price'] = pivot_10[week_10_cols].mean(axis=1).round(2)
    
    latest_w = week_10_cols[0] if week_10_cols else None
    if latest_w:
        pivot_10['Latest_Wk_Price'] = pivot_10[latest_w]
        pivot_10['Price_Variance_%'] = ((pivot_10['Latest_Wk_Price'] - pivot_10['10_Wk_Avg_Price']) / pivot_10['10_Wk_Avg_Price'] * 100).round(1)
    else:
        pivot_10['Latest_Wk_Price'] = np.nan
        pivot_10['Price_Variance_%'] = np.nan

    final_10_cols = valid_idx_cols + ['Weeks_Promoted', '10_Wk_Avg_Price', 'Latest_Wk_Price', 'Price_Variance_%'] + week_10_cols
    var_df = pivot_10[final_10_cols].sort_values(by=['Client', 'CountryName', 'Ecom_Source'])

    st.dataframe(var_df, use_container_width=True, height=450)
    st.download_button("⬇️ Download 10-Week Variance Audit", var_df.to_csv(index=False).encode('utf-8'), "10_week_variance_audit.csv", "text/csv")