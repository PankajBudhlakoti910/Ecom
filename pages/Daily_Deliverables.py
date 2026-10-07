"""
Daily Deliverables & DoD Analysis Tracking System
===================================================
Comprehensive tracking dashboard for Abbott & daily client deliverables:
- Executive DoD KPI Cards & Daily Health
- Master Daily Delivery & Date-wise SKU Trend Pivot
- Brand Distribution & Daily Trends
- Inactive / Missing SKU Audit (Missing for 3+ consecutive days)
- Data Quality & Impacted Distinct IDs
- Daily Selling Price Records & Intra-Day Price Variance Audit
"""

from __future__ import annotations

import datetime as dt
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
    page_title="Daily Deliverables Tracking System",
    page_icon="📅",
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

from utils import (
    require_credentials,
    load_abbott,
    display_table,
)

require_credentials()

# ── 3. DATA LOADING & IN-MEMORY CACHE PREPARATION ────────────────────────────
@st.cache_data(show_spinner=False, ttl=1800)
def get_clean_daily_base_df() -> pd.DataFrame:
    raw_dict = st.session_state.get("_session_client_data", {}).get("client_data", {})
    if "abbott" in raw_dict and isinstance(raw_dict["abbott"], pd.DataFrame) and not raw_dict["abbott"].empty:
        df = raw_dict["abbott"].copy()
    else:
        df = load_abbott()

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Standardize columns
    target_cols = ['Client', 'CountryName', 'Ecom_Source', 'BrandFlag', 'Ecom_SKU', 
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

    # Date normalization
    date_candidates = ["Data_ExtractionDate", "ExtractionDate", "extraction_date", "CreatedOn"]
    matched_date_col = next((c for c in date_candidates if c in df.columns), None)

    if matched_date_col:
        df["_clean_date"] = pd.to_datetime(df[matched_date_col], errors="coerce").dt.date
    else:
        df["_clean_date"] = dt.date.today()

    return df

with st.spinner("⚡ Fetching daily deliverable dataset..."):
    daily_df = get_clean_daily_base_df()

if daily_df is None or daily_df.empty:
    st.warning("⚠️ No daily Abbott data available. Please verify credentials or load data on Home/App page.")
    st.stop()

# ── 4. INSTANT SIDEBAR FILTERS ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 Daily Tracking Filters")
    
    # Country Filter
    countries = sorted([c for c in daily_df['CountryName'].unique() if c != "Unknown"])
    sel_country = st.multiselect("Country", countries, default=[])
    
    # Source Filter (Chained)
    df_scope = daily_df[daily_df['CountryName'].isin(sel_country)] if sel_country else daily_df
    sources = sorted([s for s in df_scope['Ecom_Source'].unique() if s != "Unknown"])
    sel_source = st.multiselect("Ecom Source", sources, default=[])
    
    # Brand Filter (Chained)
    df_scope2 = df_scope[df_scope['Ecom_Source'].isin(sel_source)] if sel_source else df_scope
    brands = sorted([b for b in df_scope2['BrandName'].unique() if b != "Unknown"])
    sel_brand = st.multiselect("Brand Name", brands, default=[])

# Apply filters
mask = pd.Series(True, index=daily_df.index)
if sel_country:
    mask &= daily_df['CountryName'].isin(sel_country)
if sel_source:
    mask &= daily_df['Ecom_Source'].isin(sel_source)
if sel_brand:
    mask &= daily_df['BrandName'].isin(sel_brand)

filtered_df = daily_df[mask]

st.markdown("# 📅 Daily Deliverables & DoD Analysis System")
st.markdown("Comprehensive daily extraction tracking, DoD movements, price variance audits, and inactive SKU diagnostics.")

if filtered_df.empty:
    st.info("No records match the current filter selection.")
    st.stop()

# ── 5. EXECUTIVE KPI STRIP (T-1 / DoD Analytics) ─────────────────────────────
valid_dates = sorted([d for d in filtered_df["_clean_date"].dropna().unique()], reverse=True)
latest_date = valid_dates[0] if valid_dates else dt.date.today()
day_before = valid_dates[1] if len(valid_dates) > 1 else (latest_date - dt.timedelta(days=1))

latest_df = filtered_df[filtered_df["_clean_date"] == latest_date]
previous_df = filtered_df[filtered_df["_clean_date"] == day_before]

idc = "id" if "id" in filtered_df.columns else "Ecom_SKU"

total_distinct_ids = filtered_df[idc].nunique()
total_master_skus = filtered_df['Ecom_SKU'].nunique()
latest_promoted_skus = latest_df['Ecom_SKU'].nunique()
delivery_pct = (latest_promoted_skus / total_master_skus * 100) if total_master_skus > 0 else 0.0

latest_rows = len(latest_df)
previous_rows = len(previous_df)
dod_diff = latest_rows - previous_rows
dod_pct = (dod_diff / previous_rows * 100) if previous_rows > 0 else 0.0
latest_price_points = int(latest_df["SellingPrice"].notna().sum())

st.markdown(f"""
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="kpi-label">Total Promoted (Distinct IDs)</div>
        <div class="kpi-value">{total_distinct_ids:,}</div>
        <div class="kpi-sub">All-time unique IDs</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Total Master SKUs</div>
        <div class="kpi-value">{total_master_skus:,}</div>
        <div class="kpi-sub">All-time distinct SKU codes</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">T-1 Active SKUs</div>
        <div class="kpi-value" style="color:#3fb950;">{latest_promoted_skus:,}</div>
        <div class="kpi-sub">{latest_date.strftime('%d %b %Y')}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">T-1 Delivery Rate %</div>
        <div class="kpi-value" style="color:{'#3fb950' if delivery_pct >= 50 else '#f85149'};">{delivery_pct:.1f}%</div>
        <div class="kpi-sub">Delivered vs Master Base</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">T-1 Scraped Records (Rows)</div>
        <div class="kpi-value">{latest_rows:,}</div>
        <div class="kpi-sub" style="color:{'#3fb950' if dod_diff >= 0 else '#f85149'};">DoD: {dod_diff:+,} ({dod_pct:+.1f}%)</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Price Points Delivered</div>
        <div class="kpi-value">{latest_price_points:,}</div>
        <div class="kpi-sub">Valid Selling Prices</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── 6. MASTER SUMMARY: DAILY DELIVERY STATUS & DATE TRENDS ───────────────────
st.markdown('<div class="section-header">📈 Master Daily Delivery & Date-Wise SKU Trend</div>', unsafe_allow_html=True)
st.caption("ℹ️ Total Master SKUs per Country/Source with day-by-day promoted SKU counts and latest delivery rate.")

daily_pivot = filtered_df.pivot_table(
    index=['CountryName', 'Ecom_Source'],
    columns='_clean_date',
    values='Ecom_SKU',
    aggfunc='nunique',
    fill_value=0
)

daily_totals = filtered_df.groupby(['CountryName', 'Ecom_Source'], observed=True)['Ecom_SKU'].nunique()
daily_summary = daily_pivot.copy()
daily_summary.insert(0, 'Total_Master_SKUs', daily_totals)
daily_summary = daily_summary.reset_index()

date_cols = [c for c in daily_summary.columns if isinstance(c, dt.date)]
date_cols_sorted = sorted(date_cols, reverse=True)
date_str_map = {c: c.strftime('%Y-%m-%d') for c in date_cols_sorted}
daily_summary = daily_summary.rename(columns=date_str_map)
str_date_cols_sorted = [date_str_map[c] for c in date_cols_sorted]

if str_date_cols_sorted:
    latest_d_col = str_date_cols_sorted[0]
    daily_summary['Latest_Day_Delivery_%'] = (daily_summary[latest_d_col] / daily_summary['Total_Master_SKUs'] * 100).round(1)
else:
    daily_summary['Latest_Day_Delivery_%'] = 0.0

final_summary_cols = ['CountryName', 'Ecom_Source', 'Total_Master_SKUs'] + str_date_cols_sorted + ['Latest_Day_Delivery_%']
daily_summary = daily_summary[final_summary_cols].sort_values(by='Total_Master_SKUs', ascending=False)

st.dataframe(daily_summary, use_container_width=True, height=380)
st.download_button("⬇️ Download Master Daily Summary", daily_summary.to_csv(index=False).encode('utf-8'), "master_daily_summary.csv", "text/csv")

# ── 7. BRAND DISTRIBUTION & DAILY TRENDS ─────────────────────────────────────
st.markdown('<div class="section-header">🏷️ Brand Distribution & Daily Trend (My Brand vs Competitor)</div>', unsafe_allow_html=True)
st.caption("ℹ️ Breakdown of active SKUs per Brand across daily batches.")

brand_pivot = filtered_df.pivot_table(
    index=['CountryName', 'Ecom_Source', 'BrandFlag', 'BrandName'],
    columns='_clean_date',
    values='Ecom_SKU',
    aggfunc='nunique',
    fill_value=0
)
brand_totals = filtered_df.groupby(['CountryName', 'Ecom_Source', 'BrandFlag', 'BrandName'], observed=True)['Ecom_SKU'].nunique()
brand_summary = brand_pivot.copy()
brand_summary.insert(0, 'Total_Master_SKUs', brand_totals)
brand_summary = brand_summary.reset_index().rename(columns=date_str_map)

brand_final_cols = ['CountryName', 'Ecom_Source', 'BrandFlag', 'BrandName', 'Total_Master_SKUs'] + str_date_cols_sorted
brand_summary = brand_summary[brand_final_cols].sort_values(by=['CountryName', 'Ecom_Source', 'Total_Master_SKUs'], ascending=[True, True, False])

st.dataframe(brand_summary, use_container_width=True, height=350)
st.download_button("⬇️ Download Brand Daily Summary", brand_summary.to_csv(index=False).encode('utf-8'), "brand_daily_summary.csv", "text/csv")

# ── 8. INACTIVE / MISSING SKU AUDIT (Missing Last 3+ Days) ────────────────────
st.markdown('<div class="section-header">❌ Inactive SKUs Audit (Missing for 3+ Consecutive Days)</div>', unsafe_allow_html=True)
st.caption("ℹ️ Identifies SKUs that appeared historically but have generated **zero crawls in the latest 3 extraction days**.")

if len(valid_dates) >= 3:
    last_3_days = set(valid_dates[:3])
    historical_days = set(valid_dates[3:])

    recent_skus = set(filtered_df[filtered_df['_clean_date'].isin(last_3_days)]['Ecom_SKU'])
    historical_skus = set(filtered_df[filtered_df['_clean_date'].isin(historical_days)]['Ecom_SKU'])
    dead_skus = historical_skus - recent_skus

    if dead_skus:
        dead_df = filtered_df[filtered_df['Ecom_SKU'].isin(dead_skus)]
        last_seen = dead_df.groupby('Ecom_SKU')['_clean_date'].max().reset_index(name='Last_Seen_Date')
        
        meta_cols = [c for c in [idc, 'Ecom_SKU', 'CountryName', 'Ecom_Source', 'Ecom_Desc_Name', 'Ecom_WebUrl', 'BrandName', 'ProductName', 'PackSize'] if c in dead_df.columns]
        meta_df = dead_df[meta_cols].drop_duplicates(subset=['Ecom_SKU'], keep='last')
        dead_final = meta_df.merge(last_seen, on='Ecom_SKU', how='left')

        st.warning(f"⚠️ Action Required: Found {len(dead_final):,} SKUs missing from daily delivery for the last 3+ days.")
        st.dataframe(dead_final, use_container_width=True, height=320)
        st.download_button("⬇️ Download Inactive SKUs Audit", dead_final.to_csv(index=False).encode('utf-8'), "inactive_skus_daily.csv", "text/csv")
    else:
        st.success("🎉 All historically tracked SKUs were captured within the last 3 days.")
else:
    st.info(f"Need at least 3 distinct extraction dates to run this audit. Currently tracking {len(valid_dates)} date(s).")

# ── 9. DATA HEALTH & QUALITY DRILL-DOWN ───────────────────────────────────────
st.markdown('<div class="section-header">🩺 Daily Data Health Issues (Impacted Distinct IDs)</div>', unsafe_allow_html=True)

blank_name_mask = filtered_df['Ecom_Desc_Name'].str.strip().isin(['', 'Unknown'])
blank_img_mask = filtered_df['Ecom_ImageUrl'].str.strip().isin(['', 'Unknown'])

blank_name_ids = filtered_df.loc[blank_name_mask, idc].nunique()
blank_img_ids = filtered_df.loc[blank_img_mask, idc].nunique()

d1, d2, d3 = st.columns(3)
d1.metric("Blank Ecom Names (Impacted IDs)", f"{blank_name_ids:,} / {total_distinct_ids:,}")
d2.metric("Blank Image URLs (Impacted IDs)", f"{blank_img_ids:,} / {total_distinct_ids:,}")
d3.metric("Total Records Checked (Rows)", f"{len(filtered_df):,}")

# Grouped breakdown
group_cols = ['CountryName', 'Ecom_Source']
hb_total = filtered_df.groupby(group_cols, observed=True)[idc].nunique().rename('Total_Distinct_IDs')
hb_names = filtered_df[blank_name_mask].groupby(group_cols, observed=True)[idc].nunique().rename('Blank_Names_IDs')
hb_imgs = filtered_df[blank_img_mask].groupby(group_cols, observed=True)[idc].nunique().rename('Blank_Images_IDs')

health_breakdown = pd.concat([hb_total, hb_names, hb_imgs], axis=1).fillna(0).astype(int).reset_index()
health_breakdown = health_breakdown.sort_values(by='Total_Distinct_IDs', ascending=False)
st.dataframe(health_breakdown, use_container_width=True, height=240)

# ── 10. DETAILED SKU & DAILY PRICING RECORDS TABLE ────────────────────────────
st.markdown('<div class="section-header">📋 Detailed SKU & Daily Pricing Records</div>', unsafe_allow_html=True)
st.caption("ℹ️ Operational records with extraction dates as columns displaying the latest selling price.")

ecom_name_col = 'Ecom_Desc_Name' if 'Ecom_Desc_Name' in filtered_df.columns else 'Ecom_SKU'
index_cols = ['CountryName', 'Ecom_Source', idc, ecom_name_col, 'Ecom_SKU']
valid_idx_cols = [c for c in index_cols if c in filtered_df.columns]

detail_pivot = filtered_df.pivot_table(
    index=valid_idx_cols,
    columns='_clean_date',
    values='SellingPrice',
    aggfunc='last'
).reset_index().rename(columns=date_str_map)

final_detail_cols = valid_idx_cols + str_date_cols_sorted
detail_df = detail_pivot[final_detail_cols].sort_values(by=['CountryName', 'Ecom_Source'])

st.dataframe(detail_df, use_container_width=True, height=450)
st.download_button("⬇️ Download Detailed Daily Records", detail_df.to_csv(index=False).encode('utf-8'), "detailed_daily_pricing_records.csv", "text/csv")

# ── 11. 7-DAY PRICING VARIANCE & MOVEMENT AUDIT ──────────────────────────────
st.markdown('<div class="section-header">📊 7-Day Daily Pricing Variance Audit</div>', unsafe_allow_html=True)
st.caption("ℹ️ Compares the latest extraction day price against the 7-day trailing average price.")

if len(valid_dates) > 0 and valid_idx_cols:
    last_7_days = valid_dates[:7]
    df_7 = filtered_df[filtered_df['_clean_date'].isin(last_7_days)]
    
    pivot_7 = df_7.pivot_table(
        index=valid_idx_cols,
        columns='_clean_date',
        values='SellingPrice',
        aggfunc='last'
    ).reset_index()

    day_7_cols = sorted([d for d in last_7_days if d in pivot_7.columns], reverse=True)
    
    pivot_7['Days_Promoted'] = pivot_7[day_7_cols].count(axis=1)
    pivot_7['7_Day_Avg_Price'] = pivot_7[day_7_cols].mean(axis=1).round(2)
    
    latest_d = day_7_cols[0] if day_7_cols else None
    if latest_d:
        pivot_7['Latest_Day_Price'] = pivot_7[latest_d]
        pivot_7['Price_Variance_%'] = ((pivot_7['Latest_Day_Price'] - pivot_7['7_Day_Avg_Price']) / pivot_7['7_Day_Avg_Price'] * 100).round(1)
    else:
        pivot_7['Latest_Day_Price'] = np.nan
        pivot_7['Price_Variance_%'] = np.nan

    str_7_map = {d: d.strftime('%Y-%m-%d') for d in day_7_cols}
    pivot_7 = pivot_7.rename(columns=str_7_map)
    str_7_cols = [str_7_map[d] for d in day_7_cols]

    final_7_cols = valid_idx_cols + ['Days_Promoted', '7_Day_Avg_Price', 'Latest_Day_Price', 'Price_Variance_%'] + str_7_cols
    var_df = pivot_7[final_7_cols].sort_values(by=['CountryName', 'Ecom_Source'])

    st.dataframe(var_df, use_container_width=True, height=450)
    st.download_button("⬇️ Download 7-Day Variance Audit", var_df.to_csv(index=False).encode('utf-8'), "7_day_price_variance_audit.csv", "text/csv")