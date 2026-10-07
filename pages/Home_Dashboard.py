from __future__ import annotations

import datetime as dt
import html as _html_lib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to Python module search path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import streamlit as st

from utils import (
    clean_id,
    display_table,
    get_cached_client_data,
    get_global_master_data,
    load_email_reconciliation_data,
    load_google_sheet_data,
    require_credentials,
)

st.set_page_config(page_title="Home Dashboard", page_icon="🏠", layout="wide")
require_credentials()

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap');
html,body,[class*="css"]{font-family:'Space Grotesk',sans-serif;}
.stApp{background:linear-gradient(135deg,#0a0e1a 0%,#0d1526 100%);color:#e2e8f0;}

/* KPI Card Styles */
.kpi-card{background:linear-gradient(135deg,#111c35,#0d1829);border:1px solid #1e3a5f;border-radius:14px;padding:1.2rem 1.5rem;text-align:center; position: relative; cursor: help;}
.kpi-val{font-size:1.8rem;font-weight:700;color:#60a5fa;line-height:1.1;}
.kpi-lbl{font-size:0.75rem;color:#94a3b8;margin-top:6px;text-transform:uppercase;letter-spacing:.05em;}
.daily-card{background:linear-gradient(135deg,#0f243a,#0c192e);border:1px solid #0284c7;border-radius:14px;padding:1.1rem 1.3rem; position: relative; cursor: help;}

/* Custom Tooltip on Hover */
.kpi-card:hover::after, .daily-card:hover::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: 105%; left: 50%; transform: translateX(-50%);
    background: #1e293b; color: #f8fafc; padding: 10px 14px;
    border-radius: 8px; font-size: 0.8rem; font-family: 'Space Mono', monospace;
    white-space: pre-wrap; z-index: 100; text-align: left;
    box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5);
    border: 1px solid #334155; width: max-content; min-width: 150px;
    pointer-events: none;
}

/* Header Badges */
.hd-section-header{
    position:sticky; top:0; z-index:15;
    display:flex; align-items:center; gap:10px; flex-wrap:wrap;
    background:linear-gradient(90deg,#0d1526 0%,#0d1526 85%,rgba(13,21,38,0));
    padding:10px 2px 10px; margin:1.5rem 0 .8rem;
    border-bottom:1px solid #16294a;
}
.hd-section-header .hd-num{font-size:.7rem;color:#38bdf8;border:1px solid #0284c7;border-radius:6px;padding:2px 8px;font-weight:700;}
.hd-section-header .hd-title{font-size:1.05rem;font-weight:600;margin:0;color:#f8fafc;}
.hd-section-header .hd-desc{font-size:.78rem;color:#64748b;margin-left:auto;}

/* Pivots & Custom Tables */
.hd-pivot-card{background:#0d1829;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;}
.hd-pivot-scroll{max-height:340px;overflow:auto;}
table.hd-pivot{width:100%;border-collapse:collapse;font-size:.78rem;}
table.hd-pivot thead th{
    position:sticky; top:0; z-index:2; background:#0f1a30; color:#94a3b8;
    font-weight:600; text-transform:uppercase; letter-spacing:.04em; font-size:.65rem;
    padding:9px 12px; text-align:center; border-bottom:1px solid #1e3a5f; white-space:nowrap;
}
table.hd-pivot tbody td{padding:8px 12px;text-align:center;color:#cbd5e1;border-bottom:1px solid rgba(30,58,95,.35);font-family:'Space Mono',monospace;}
table.hd-pivot tbody td:first-child{text-align:left;color:#e2e8f0;font-family:'Space Grotesk',sans-serif;font-weight:500;}
table.hd-pivot tbody tr:hover td{background:rgba(96,165,250,.07);}
table.hd-pivot tfoot td{padding:9px 12px;font-weight:700;color:#e2e8f0;border-top:1px solid #1e3a5f;background:rgba(96,165,250,.1);font-family:'Space Mono',monospace;text-align:center;}
table.hd-pivot tfoot td:first-child{font-family:'Space Grotesk',sans-serif;text-align:left;}

/* Top 10 Ranking Rows */
.top10-card{background:#0d1829;border:1px solid #1e3a5f;border-radius:12px;padding:14px 16px;}
.rank-row{display:flex;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.04);}
.rank-row .rnk{font-size:.7rem;color:#64748b;width:22px;flex:0 0 auto;font-family:'Space Mono',monospace;}
.rank-row .name{font-size:.78rem;color:#f8fafc;flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding-right:8px;}
.rank-row .bar-track{flex:0 0 35%;height:6px;background:rgba(255,255,255,.08);border-radius:3px;overflow:hidden;}
.rank-row .bar-fill{height:100%;border-radius:3px;display:block;}
.rank-row .val{font-size:.75rem;color:#60a5fa;width:65px;text-align:right;flex:0 0 auto;font-family:'Space Mono',monospace;font-weight:600;}

/* Quick Widgets */
.quick-card{background:linear-gradient(135deg,#111c35,#0d1829);border:1px solid #1e3a5f;border-radius:12px;padding:14px 16px;}
.qhead{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;}
.qhead .qtitle{font-size:.8rem;font-weight:600;color:#f8fafc;}
.qhead .qtotal{font-family:'Space Mono',monospace;font-size:.72rem;color:#94a3b8;}
.qrow{display:flex;align-items:center;gap:10px;padding:4px 0;}
.qrow .qname{font-size:.76rem;color:#f8fafc;width:105px;flex:0 0 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.qrow .qbar-track{flex:1 1 auto;height:6px;background:rgba(255,255,255,.08);border-radius:3px;overflow:hidden;}
.qrow .qbar-fill{height:100%;border-radius:3px;display:block;}
.qrow .qval{font-size:.72rem;color:#60a5fa;width:55px;text-align:right;flex:0 0 auto;font-family:'Space Mono',monospace;font-weight:600;}

[data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th {
    text-align: center !important;
    vertical-align: middle !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown("# 🏠 Home Dashboard & Multi-Client Overview")
st.markdown("Real-time cross-client deliverable monitoring, Daily (T-1) run tracker, reconciliation pivots, and data coverage health.")

# ── Pre-compile Regex for massive speed boost on 1.3M+ rows ───────────
_CLEAN_NAME_REGEX = re.compile(r'["\'](?:name|brand_name|BrandName|product_name|ProductName)["\']\s*:\s*["\']?([^"\'},\]]+)', re.IGNORECASE)

# ── Step-by-Step Timed Loading Monitor ──────────────────────────────
total_start_time = time.time()
combined = pd.DataFrame()
client_frames = {}
scope_df, sql_df, gsheet_df = None, None, None
email_bq_df = pd.DataFrame()

with st.status("🚀 Initializing Dashboard Data Pipeline...", expanded=True) as status:
    # 1. Client Data
    st.write("📥 Fetching cached client data...")
    t0 = time.time()
    data = get_cached_client_data(force_refresh=False)
    client_frames = {k: v for k, v in data.items() if isinstance(v, pd.DataFrame) and not v.empty}
    t1 = time.time()
    st.write(f"✅ Client data fetched in {t1 - t0:.2f} seconds")

    # 2. Optimization & Concat
    if client_frames:
        st.write("⚙️ Optimizing and merging datasets...")
        processed_frames = []
        
        for name, df in client_frames.items():
            temp_df = df.copy()
            if "Client" not in temp_df.columns:
                temp_df["Client"] = name.capitalize()
            processed_frames.append(temp_df)

        combined = pd.concat(processed_frames, ignore_index=True, sort=False)
        
        cat_cols = ["CountryName", "Ecom_Source", "BrandName", "ProductName", "Client"]
        for col in cat_cols:
            if col in combined.columns:
                combined[col] = combined[col].astype("category")
                
        t2 = time.time()
        st.write(f"✅ Datasets merged ({len(combined):,} rows) in {t2 - t1:.2f} seconds")
    else:
        st.write("⚠️ No client data available to merge.")
        t2 = time.time()

    # 3. Master Data (SQL/Sheets) - SAFE LOAD (NO HANGING)
    st.write("📥 Checking Session for Global Master Data (SQL & GSheets)...")
    
    # Strictly rely on session state to avoid hanging database connections
    sql_df = st.session_state.get("master_sql_df", st.session_state.get("_sku_active_df", pd.DataFrame()))
    gsheet_df = st.session_state.get("gsheet_data", pd.DataFrame())

    if sql_df.empty:
        st.write("⚠️ SQL data not loaded in session. Skipping SQL analysis to prevent freezing.")
    else:
        st.write(f"✅ SQL data found ({len(sql_df):,} rows).")

    if gsheet_df.empty:
        st.write("⚠️ Google Sheet data not loaded in session. Skipping GSheet analysis.")
    else:
        st.write(f"✅ Google Sheet data found ({len(gsheet_df):,} rows).")

    t3 = time.time()
    st.write(f"✅ Master data check completed in {t3 - t2:.2f} seconds")

    # 4. Email Recon Data - SAFE LOAD
    st.write("📥 Checking Email Reconciliation Data...")
    try:
        # Check session first, if not try quick load
        if "email_bq_df" in st.session_state:
            email_bq_df = st.session_state["email_bq_df"]
            st.write("✅ Recon data loaded from session.")
        else:
            email_bq_df = load_email_reconciliation_data()
            if email_bq_df is None:
                email_bq_df = pd.DataFrame()
            else:
                st.session_state["email_bq_df"] = email_bq_df
    except Exception as e:
        st.write("⚠️ Reconciliation data skipped (Database disconnected).")
        email_bq_df = pd.DataFrame()
        
    t4 = time.time()
    st.write(f"✅ Recon data step completed in {t4 - t3:.2f} seconds")
    
    total_time = t4 - total_start_time
    status.update(label=f"🎉 Dashboard Ready! (Total load time: {total_time:.2f}s)", state="complete", expanded=False)

# ── Post-Load Processing ──────────────────────────────────────────────────────

def _find_id_col(df: pd.DataFrame) -> str | None:
    for col in ["Id", "ID", "id", "Ecom_SKU", "SKU"]:
        if col in df.columns:
            return col
    return None

# ── 1. Dataset Overview (Unique IDs + SKUs) ───────────────────────────────────
st.markdown('<div class="hd-section-header"><span class="hd-num mono">01</span><span class="hd-title">Dataset Overview (Records, Unique IDs, SKUs, Brands, Products)</span><span class="hd-desc">All Active Client Partitions</span></div>', unsafe_allow_html=True)
if not client_frames:
    st.info("No client data loaded yet. Please ensure data is loaded from the main App page.")
else:
    cols = st.columns(min(len(client_frames) + 1, 5))
    comb_id_col = _find_id_col(combined)
    total_unique_ids = combined[comb_id_col].nunique() if comb_id_col else len(combined)
    total_skus = combined["Ecom_SKU"].nunique() if "Ecom_SKU" in combined.columns else 0
    total_brands = combined["BrandName"].nunique() if "BrandName" in combined.columns else 0

    with cols[0]:
        hover_total = f"Global Dataset Details\n----------------------\nTotal Records: {len(combined):,}\nUnique IDs: {total_unique_ids:,}\nUnique SKUs: {total_skus:,}\nUnique Brands: {total_brands:,}"
        st.markdown(
            f'<div class="kpi-card" data-tooltip="{hover_total}"><div class="kpi-val">{len(combined):,}</div>'
            f'<div class="kpi-lbl">Total Records</div>'
            f'<div style="font-size:.72rem;color:#94a3b8;margin-top:4px">IDs: <b style="color:#38bdf8;">{total_unique_ids:,}</b> | SKUs: {total_skus:,} | Brands: {total_brands:,}</div></div>',
            unsafe_allow_html=True,
        )
    for i, (name, df) in enumerate(client_frames.items()):
        col = cols[(i + 1) % len(cols)]
        id_col = _find_id_col(df)
        ids_n = df[id_col].nunique() if id_col else len(df)
        skus_n = df["Ecom_SKU"].nunique() if "Ecom_SKU" in df.columns else 0
        brands_n = df["BrandName"].nunique() if "BrandName" in df.columns else 0
        prods_n = df["ProductName"].nunique() if "ProductName" in df.columns else 0
        
        hover_client = f"{name.capitalize()} Details\n----------------------\nTotal Records: {len(df):,}\nUnique IDs: {ids_n:,}\nUnique SKUs: {skus_n:,}\nUnique Brands: {brands_n:,}\nUnique Products: {prods_n:,}"
        
        with col:
            st.markdown(
                f'<div class="kpi-card" data-tooltip="{hover_client}"><div class="kpi-val">{len(df):,}</div>'
                f'<div class="kpi-lbl">{name.capitalize()} Records</div>'
                f'<div style="font-size:.72rem;color:#94a3b8;margin-top:4px">IDs: <b style="color:#38bdf8;">{ids_n:,}</b> | SKUs: {skus_n:,} | Brands: {brands_n:,} | Prods: {prods_n:,}</div></div>',
                unsafe_allow_html=True,
            )

# ── 2. DAILY DELIVERABLES SUMMARY (T-1 / PREVIOUS DAY) ────────────────────────
st.markdown('<div class="hd-section-header"><span class="hd-num mono">02</span><span class="hd-title">Daily Deliverables Monitor (Yesterday / T-1 Extraction Health)</span><span class="hd-desc">Tracks Daily Crawl & Ingestion Status</span></div>', unsafe_allow_html=True)
st.caption("ℹ️ Analyzes the latest daily crawl run (Current Date - 1 day) against Day-over-Day movements.")

date_col = next((c for c in ["Data_ExtractionDate", "ExtractionDate", "extraction_date", "CreatedOn"] if c in combined.columns), None)

if date_col is not None and not combined.empty:
    combined["_temp_date"] = pd.to_datetime(combined[date_col], errors="coerce").dt.normalize()
    valid_dates = combined["_temp_date"].dropna()

    if not valid_dates.empty:
        max_date = valid_dates.max()
        target_yesterday = max_date
        day_before = target_yesterday - dt.timedelta(days=1)

        t1_df = combined[combined["_temp_date"] == target_yesterday]
        t2_df = combined[combined["_temp_date"] == day_before]

        t1_total = len(t1_df)
        t1_skus = t1_df["Ecom_SKU"].nunique() if "Ecom_SKU" in t1_df.columns else 0
        t1_clients = t1_df["Client"].nunique() if "Client" in t1_df.columns else 0
        t1_sources = t1_df["Ecom_Source"].nunique() if "Ecom_Source" in t1_df.columns else 0

        dod_delta = t1_total - len(t2_df)
        dod_pct = (dod_delta / len(t2_df) * 100) if len(t2_df) > 0 else 0.0

        d1, d2, d3, d4 = st.columns(4)
        
        hover_t1 = f"T-1 Run ({target_yesterday.strftime('%d %b %Y')})\n----------------------\nTotal Records: {t1_total:,}\nPrevious Day (T-2): {len(t2_df):,}\nVariance: {dod_delta:+,} ({dod_pct:+.1f}%)"
        with d1:
            st.markdown(
                f'<div class="daily-card" data-tooltip="{hover_t1}"><div class="kpi-val" style="color:#38bdf8;">{t1_total:,}</div>'
                f'<div class="kpi-lbl">T-1 Scraped Records ({target_yesterday.strftime("%d %b %Y")})</div>'
                f'<div style="font-size:.74rem;color:{"#4ade80" if dod_delta >= 0 else "#f87171"};margin-top:4px;">DoD: {dod_delta:+,} ({dod_pct:+.1f}%)</div></div>',
                unsafe_allow_html=True,
            )
            
        hover_skus = f"SKUs Active Today\n----------------------\nDelivered SKUs: {t1_skus:,}\nSpanning Across: {t1_sources} E-com platforms"
        with d2:
            st.markdown(
                f'<div class="daily-card" data-tooltip="{hover_skus}"><div class="kpi-val" style="color:#a78bfa;">{t1_skus:,}</div>'
                f'<div class="kpi-lbl">Active SKUs Delivered (T-1)</div>'
                f'<div style="font-size:.74rem;color:#94a3b8;margin-top:4px;">Across {t1_sources} E-com Platforms</div></div>',
                unsafe_allow_html=True,
            )
            
        hover_clients = f"Client Batches\n----------------------\nBatches Ready: {t1_clients}\nTotal Expected: {len(client_frames)}"
        with d3:
            st.markdown(
                f'<div class="daily-card" data-tooltip="{hover_clients}"><div class="kpi-val" style="color:#4ade80;">{t1_clients} / {len(client_frames)}</div>'
                f'<div class="kpi-lbl">Client Batches Ready</div>'
                f'<div style="font-size:.74rem;color:#94a3b8;margin-top:4px;">Delivery Completeness</div></div>',
                unsafe_allow_html=True,
            )
            
        hover_sources = f"Platform Reach\n----------------------\nTotal Crawled Sources: {t1_sources}\nStatus: Active Extraction"
        with d4:
            st.markdown(
                f'<div class="daily-card" data-tooltip="{hover_sources}"><div class="kpi-val" style="color:#f59e0b;">{t1_sources}</div>'
                f'<div class="kpi-lbl">Total Crawled Sources</div>'
                f'<div style="font-size:.74rem;color:#94a3b8;margin-top:4px;">Web & App Channels</div></div>',
                unsafe_allow_html=True,
            )

        daily_client_summary = t1_df.groupby("Client", as_index=False, observed=True).agg(
            Yesterday_Records=("Client", "count"),
            Unique_SKUs=("Ecom_SKU", "nunique") if "Ecom_SKU" in t1_df.columns else ("Client", "count"),
            Unique_Brands=("BrandName", "nunique") if "BrandName" in t1_df.columns else ("Client", "count"),
            Active_Sources=("Ecom_Source", "nunique") if "Ecom_Source" in t1_df.columns else ("Client", "count"),
            Countries=("CountryName", "nunique") if "CountryName" in t1_df.columns else ("Client", "count"),
        )
        st.dataframe(daily_client_summary, use_container_width=True, hide_index=True)
    else:
        st.info("No valid extraction dates found in active client datasets.")
else:
    st.info("Data ExtractionDate missing or datasets not loaded.")


# ── 3. EMAIL-STYLE RECONCILIATION PIVOT (FAST MATCHING) ────────────────
st.markdown('<div class="hd-section-header"><span class="hd-num mono">03</span><span class="hd-title">Email Reconciliation Pivot (Expected Scope vs BQ Available vs SQL Available vs Google Sheet)</span><span class="hd-desc">Multi-Client Cross Deliverables Audit</span></div>', unsafe_allow_html=True)
st.caption("ℹ️ Cross-matches BigQuery, SQL Partition Data, and Google Sheets on Country + Brand + Product matching keys.")

def extract_clean_name_fast(val: Any) -> str:
    if pd.isna(val) or val is None:
        return ""
    if isinstance(val, str):
        v = val.strip()
        if not v or v.lower() in ("nan", "none", "null", "[]", "{}"): return ""
        if (v.startswith("{") or v.startswith("[")) and "name" in v.lower():
            try:
                parsed = json.loads(v)
                return extract_clean_name_fast(parsed)
            except:
                pass
        m = _CLEAN_NAME_REGEX.search(v)
        if m: return m.group(1).strip().lower()
        if "," in v: v = v.split(",")[0]
        return " ".join(v.split()).lower()
    
    if isinstance(val, (list, tuple)): return extract_clean_name_fast(val[0]) if val else ""
    if isinstance(val, dict):
        for k in ["name", "Name", "brand_name", "BrandName", "product_name", "ProductName", "value"]:
            if k in val and val[k]: return str(val[k]).strip().lower()
        for v in val.values():
            if v: return str(v).strip().lower()
        return ""
    return str(val).strip().lower()

if not email_bq_df.empty:
    def create_name_match_key(df_source: pd.DataFrame, country_col: str, brand_col: str, prod_col: str) -> pd.Series:
        c = df_source[country_col].fillna("").astype(str).str.strip().str.upper() if country_col in df_source.columns else pd.Series("", index=df_source.index)
        b = df_source[brand_col].map(extract_clean_name_fast) if brand_col in df_source.columns else pd.Series("", index=df_source.index)
        p = df_source[prod_col].map(extract_clean_name_fast) if prod_col in df_source.columns else pd.Series("", index=df_source.index)
        return c + "|" + b + "|" + p

    email_bq_df["Match_Key"] = create_name_match_key(
        email_bq_df,
        country_col="CountryName",
        brand_col="BrandName",
        prod_col="ProductName",
    )

    gsheet_keys = set()
    if gsheet_df is not None and not gsheet_df.empty:
        gs_cols = {c.lower().replace(" ", "").replace("_", ""): c for c in gsheet_df.columns}
        g_country = gs_cols.get("countryname", gs_cols.get("country", ""))
        g_brand = gs_cols.get("brandname", gs_cols.get("brand", ""))
        g_prod = gs_cols.get("productname", gs_cols.get("product", ""))

        if g_country and g_brand:
            gs_temp = gsheet_df.rename(columns={
                g_country: "CountryName",
                g_brand: "BrandName",
                g_prod: "ProductName" if g_prod else "BrandName",
            })
            gsheet_keys = set(create_name_match_key(
                gs_temp,
                country_col="CountryName",
                brand_col="BrandName",
                prod_col="ProductName",
            ).dropna().unique())

    email_bq_df["In_Google_Sheet"] = email_bq_df["Match_Key"].isin(gsheet_keys)
    email_bq_df["Is_Available_BQ"] = email_bq_df["RecordCount"] > 0

    sql_matched_dict = {}
    sql_total_dict = {}

    if sql_df is not None and not sql_df.empty:
        sql_lookup = sql_df.copy()
        sql_col_map = {c.lower().replace(" ", "").replace("_", ""): c for c in sql_lookup.columns}

        c_col = sql_col_map.get("ecommercecountry", sql_col_map.get("country", "EcommerceCountry"))
        b_col = sql_col_map.get("matchedbrands", sql_col_map.get("brand", sql_col_map.get("brandname", "MatchedBrands")))
        p_col = sql_col_map.get("matchedproducts", sql_col_map.get("product", sql_col_map.get("ecommercedescname", "MatchedProducts")))
        matched_flag_col = sql_col_map.get("matched", "Matched")

        sql_lookup["Match_Key"] = create_name_match_key(
            sql_lookup,
            country_col=c_col,
            brand_col=b_col,
            prod_col=p_col,
        )

        if matched_flag_col in sql_lookup.columns:
            sql_lookup["_is_matched"] = sql_lookup[matched_flag_col].isin([1, "1", True, "True", "yes", "Y", "Yes"]).astype(int)
        else:
            sql_lookup["_is_matched"] = 1

        sql_agg = sql_lookup.groupby("Match_Key", as_index=False, observed=True).agg(
            total_records=("Match_Key", "count"),
            matched_records=("_is_matched", "sum"),
        )
        sql_matched_dict = dict(zip(sql_agg["Match_Key"], sql_agg["matched_records"]))
        sql_total_dict = dict(zip(sql_agg["Match_Key"], sql_agg["total_records"]))

    email_bq_df["SQL_Matched_Count"] = email_bq_df["Match_Key"].map(sql_matched_dict).fillna(0).astype(int)
    email_bq_df["SQL_Total_Count"] = email_bq_df["Match_Key"].map(sql_total_dict).fillna(0).astype(int)
    email_bq_df["Is_Available_SQL"] = email_bq_df["SQL_Matched_Count"] > 0

    app_tokens = ("careem", "panda", "hungerstation", "drops", "nana", "talabat", "elgrocer")
    email_bq_df["Source_Type"] = email_bq_df["Ecom_Source"].astype(str).str.lower().apply(
        lambda x: "App Source" if any(t in x for t in app_tokens) else "Website Source"
    )

    recon_rows = []
    for (client_val, country_val, source_val), grp in email_bq_df.groupby(["Client", "CountryName", "Ecom_Source"], observed=True):
        total_scope = len(grp)
        available_sql = int(grp["Is_Available_SQL"].sum())
        
        recon_rows.append({
            "Client": client_val,
            "Country": country_val,
            "Source": source_val,
            "Source Type": grp["Source_Type"].iloc[0],
            "Total Scope": total_scope,
            "Available (BQ)": int(grp["Is_Available_BQ"].sum()),
            "Available in SQL (SKUs)": available_sql,
            "SQL Matched Records": int(grp["SQL_Matched_Count"].sum()),
            "In Google Sheet": int((~grp["Is_Available_BQ"] & grp["In_Google_Sheet"]).sum()),
            "Action Required": int((~grp["Is_Available_BQ"] & ~grp["Is_Available_SQL"] & ~grp["In_Google_Sheet"]).sum()),
            "SQL Delivery Rate %": round((available_sql / total_scope * 100), 1) if total_scope else 0.0,
        })

    recon_df = pd.DataFrame(recon_rows)
    if not recon_df.empty:
        recon_df = recon_df.sort_values(["Client", "Country", "Source"]).reset_index(drop=True)
        
        st.markdown("**📊 Client & Source Type Summary**")
        summary_df = recon_df.groupby(["Client", "Source Type"], as_index=False).agg({
            "Total Scope": "sum",
            "Available (BQ)": "sum",
            "In Google Sheet": "sum",
            "Action Required": "sum"
        }).sort_values(["Client", "Source Type"]).reset_index(drop=True)
        
        display_table(summary_df, default_cols=list(summary_df.columns), key="client_source_type_summary", height=250)
        
        st.markdown("<br>**📋 Detailed Reconciliation**", unsafe_allow_html=True)
        display_table(recon_df, default_cols=list(recon_df.columns), key="email_recon_pivot_main_table", height=420)
    else:
        st.info("No records matched email reconciliation query.")
else:
    st.info("Reconciliation scope data not loaded or empty. Check backend scope tables.")



# ── 4. Google Sheet Live Search ────────────────────────────────────
st.markdown('<div class="hd-section-header"><span class="hd-num mono">04</span><span class="hd-title">Google Sheet Reference Data & Live Search</span><span class="hd-desc">Non-Promoted Exclusions</span></div>', unsafe_allow_html=True)
if gsheet_df is not None and not gsheet_df.empty:
    search_query = st.text_input("🔍 Search Google Sheet Records (Brand, Product, Client, Country...)")
    search_df = gsheet_df
    if search_query:
        mask = pd.Series(False, index=gsheet_df.index)
        for col in gsheet_df.columns:
            mask |= gsheet_df[col].astype(str).str.contains(search_query, case=False, na=False)
        search_df = gsheet_df[mask]
        
    st.caption(f"Showing {len(search_df):,} record(s) from Google Sheet.")
    display_table(search_df, default_cols=list(search_df.columns), key="gsheet_search_tbl", height=320)
else:
    st.info("Google Sheet is empty or not synced. Click 'Sync Google Sheet Now' in the sidebar.")

# ── 5. Overlapping Country + Source ──────────────────────────────
st.markdown('<div class="hd-section-header"><span class="hd-num mono">05</span><span class="hd-title">Overlapping Country + Source Combinations</span><span class="hd-desc">Multi-Client Platform Coverage</span></div>', unsafe_allow_html=True)

if len(client_frames) >= 2:
    combo_to_clients = {}
    for name, df in client_frames.items():
        if "CountryName" in df.columns and "Ecom_Source" in df.columns:
            for cs in set(zip(df["CountryName"].dropna(), df["Ecom_Source"].dropna())):
                combo_to_clients.setdefault(cs, []).append(name.capitalize())

    overlap_rows = [{"Country": c, "Source": s, "Shared Across Clients": ", ".join(sorted(clients)), "Client Count": len(clients)}
                    for (c, s), clients in combo_to_clients.items() if len(clients) > 1]
    
    overlap_df = pd.DataFrame(overlap_rows)
    if not overlap_df.empty:
        overlap_df = overlap_df.sort_values(["Client Count", "Country"], ascending=[False, True]).reset_index(drop=True)
        display_table(overlap_df, default_cols=list(overlap_df.columns), key="overlap_clean_tbl", height=300)
    else:
        st.info("No overlapping Country + Source combinations found.")
else:
    st.info("Need at least 2 clients loaded to compute overlaps.")

# ═══════════════════════════════════════════════════════════════════════════
# COMPREHENSIVE OVERALL SUMMARY, VALIDATION, SUMMARY PIVOTS & TOP 10s
# ═══════════════════════════════════════════════════════════════════════════

def _first_col(frame: pd.DataFrame, candidates: list) -> str | None:
    if frame is None or frame.empty: return None
    lookup = {c.lower(): c for c in frame.columns}
    for cand in candidates:
        if cand.lower() in lookup: return lookup[cand.lower()]
    return None

def _nunique(frame: pd.DataFrame, col: str | None) -> int:
    return int(frame[col].nunique()) if col and col in frame.columns else 0

def _fmt_k(value) -> str:
    if not isinstance(value, (int, float)): return "N/A"
    return f"{value/1000:.1f}k" if value >= 1000 else f"{value:,}"

def _esc(val) -> str: return _html_lib.escape(str(val))

def _hd_pivot_table(df: pd.DataFrame, show_total_row: bool = True) -> str:
    if df is None or df.empty: return '<div class="hd-pivot-card"><div class="hd-empty" style="padding:15px;color:#64748b;">No data available.</div></div>'
    cols = list(df.columns); label_col = cols[0]; value_cols = cols[1:]
    thead = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    body_rows = []
    for _, row in df.iterrows():
        cells = [f"<td>{_esc(row[label_col])}</td>"] + [f"<td>{v:,}</td>" if isinstance(v, (int, float)) and pd.notna(v) else f"<td>{_esc(v)}</td>" for v in row[value_cols]]
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    tfoot = "<tfoot><tr>" + "".join(f"<td>{t}</td>" for t in (["Total"] + [f"{int(df[c].sum()):,}" if pd.api.types.is_numeric_dtype(df[c]) else "—" for c in value_cols])) + "</tr></tfoot>" if show_total_row else ""
    return f'<div class="hd-pivot-card"><div class="hd-pivot-scroll"><table class="hd-pivot"><thead><tr>{thead}</tr></thead><tbody>{"".join(body_rows)}</tbody>{tfoot}</table></div></div>'

def _hd_rank_list(series: pd.Series, color: str) -> str:
    if series is None or series.empty: return '<div class="top10-card"><div class="hd-empty" style="padding:12px;color:#64748b;">Not available.</div></div>'
    max_val = series.max() or 1
    rows = [f'<div class="rank-row"><span class="rnk mono">{i:02d}</span><span class="name">{_esc(name)}</span><span class="bar-track"><span class="bar-fill" style="width:{max(2, int(round((val / max_val) * 100)))}%;background:{color}"></span></span><span class="val mono">{val:,}</span></div>' for i, (name, val) in enumerate(series.items(), 1)]
    return f'<div class="top10-card">{"".join(rows)}</div>'

def _hd_quick_widget(title: str, total_label: str, series: pd.Series, color: str, top_n: int = 3) -> str:
    if series is None or series.empty: body = '<div class="hd-empty" style="padding:10px;color:#64748b;">Not available.</div>'
    else:
        top = series.head(top_n); max_val = top.max() or 1
        body = "".join(f'<div class="qrow"><span class="qname">{_esc(name)}</span><span class="qbar-track"><span class="qbar-fill" style="width:{max(2, int(round((val / max_val) * 100)))}%;background:{color}"></span></span><span class="qval mono">{_fmt_k(val)}</span></div>' for name, val in top.items())
    return f'<div class="quick-card"><div class="qhead"><span class="qtitle">{_esc(title)}</span><span class="qtotal mono">{_esc(total_label)}</span></div>{body}</div>'

if not combined.empty:
    col_sku = _first_col(combined, ["Ecom_SKU", "SKU"])
    col_client = _first_col(combined, ["Client"])
    col_country = _first_col(combined, ["CountryName", "Country"])
    col_source = _first_col(combined, ["Ecom_Source", "Source"])
    col_product = _first_col(combined, ["ProductName", "Product_Name", "Product"])
    col_brand = _first_col(combined, ["BrandName", "Brand_Name", "Brand"])
    col_ecom_nm = _first_col(combined, ["Ecom_Desc_Name", "EcommerceName", "Ecom_Name"])
    
    # ── 6. Data Validation Quality Summary ───────────────────────────────────
    st.markdown('<div class="hd-section-header"><span class="hd-num mono">06</span><span class="hd-title">Data Validation Summary (Quality & Anomaly Checks)</span><span class="hd-desc">Duplicate Keys & NULL Audits</span></div>', unsafe_allow_html=True)
    
    prices = pd.to_numeric(combined["Ecom_PromoPrice"], errors="coerce") if "Ecom_PromoPrice" in combined.columns else pd.Series(np.nan, index=combined.index)

    def _dup_stats_opt(group_cols):
        if not all(c in combined.columns for c in group_cols): return 0, 0, 0.0
        counts = combined.groupby(group_cols, observed=True).size()
        dups = counts[counts > 1]
        total_recs = int(dups.sum())
        return 0, total_recs, 0.0

    ecom_dup_skus, ecom_dup_tot, ecom_dup_price = _dup_stats_opt([col_country, col_source, col_ecom_nm]) if col_country and col_source and col_ecom_nm else (0, 0, 0.0)
    sku_dup_skus, sku_dup_tot, sku_dup_price = _dup_stats_opt([col_country, col_source, col_sku]) if col_country and col_source and col_sku else (0, 0, 0.0)
    
    val_df = pd.DataFrame([
        {"Check Name": "EcommerceName Duplicate Count", "Total Records": ecom_dup_tot, "Status": "Bad" if ecom_dup_tot > 0 else "OK"},
        {"Check Name": "SKU Duplicate Count", "Total Records": sku_dup_tot, "Status": "Bad" if sku_dup_tot > 0 else "OK"},
    ])
    display_table(val_df, default_cols=list(val_df.columns), key="val_summary_tbl", height=150)

    # ── 7. Summary Pivots ────────────────────────────────────────────────────
    st.markdown('<div class="hd-section-header"><span class="hd-num mono">07</span><span class="hd-title">Summary Pivots</span><span class="hd-desc">Client · Country · Source · Product Aggregations</span></div>', unsafe_allow_html=True)

    def _summary_pivot(group_col, extra_nunique_cols, sku_col=col_sku):
        if not group_col: return pd.DataFrame()
        agg_map = {out_name: (src_col, "nunique") for out_name, src_col in extra_nunique_cols if src_col in combined.columns}
        if sku_col: agg_map["Total SKUs"] = (sku_col, "nunique")
        if not agg_map: return pd.DataFrame()
        out = combined.groupby(group_col, observed=True).agg(**agg_map).reset_index()
        return out.sort_values("Total SKUs" if "Total SKUs" in out.columns else out.columns[-1], ascending=False)

    pv1, pv2 = st.columns(2)
    with pv1:
        st.markdown("**Client Summary Pivot**")
        st.markdown(_hd_pivot_table(_summary_pivot(col_client, [("Unique Countries", col_country), ("Unique Sources", col_source)])), unsafe_allow_html=True)
    with pv2:
        st.markdown("**Country Summary Pivot**")
        st.markdown(_hd_pivot_table(_summary_pivot(col_country, [("Clients", col_client), ("Sources", col_source)])), unsafe_allow_html=True)

    pv3, pv4 = st.columns(2)
    with pv3:
        st.markdown("**Source Summary Pivot**")
        st.markdown(_hd_pivot_table(_summary_pivot(col_source, [("Client", col_client), ("Country", col_country)])), unsafe_allow_html=True)
    with pv4:
        st.markdown("**Product Summary Pivot**")
        prod_pivot = _summary_pivot(col_product, [("Client Count", col_client), ("Source Count", col_source)])
        st.markdown(_hd_pivot_table(prod_pivot.head(200) if not prod_pivot.empty else prod_pivot, show_total_row=False), unsafe_allow_html=True)

    # ── 8. Top 10 Ranked Lists ────────────────────────────────────────────────
    st.markdown('<div class="hd-section-header"><span class="hd-num mono">08</span><span class="hd-title">Top 10 Rankings</span><span class="hd-desc">Ranked by Active SKU Count</span></div>', unsafe_allow_html=True)

    def _top10_by_sku(group_col):
        if not group_col or not col_sku or group_col not in combined.columns: return pd.Series(dtype="int64")
        return combined.groupby(group_col, observed=True)[col_sku].nunique().nlargest(10)

    top10_brand = _top10_by_sku(col_brand)
    top10_product = _top10_by_sku(col_product)
    top10_country = _top10_by_sku(col_country)
    top10_source = _top10_by_sku(col_source)
    top10_client = _top10_by_sku(col_client)

    t10_1, t10_2, t10_3 = st.columns(3)
    with t10_1:
        st.markdown("**🏷️ Top 10 Brands**")
        st.markdown(_hd_rank_list(top10_brand, "#60a5fa"), unsafe_allow_html=True)
    with t10_2:
        st.markdown("**📦 Top 10 Products**")
        st.markdown(_hd_rank_list(top10_product, "#a78bfa"), unsafe_allow_html=True)
    with t10_3:
        st.markdown("**🌍 Top 10 Countries**")
        st.markdown(_hd_rank_list(top10_country, "#4ade80"), unsafe_allow_html=True)

    # ── 9. Quick Dimension Widgets ───────────────────────────────────────────
    st.markdown('<div class="hd-section-header"><span class="hd-num mono">09</span><span class="hd-title">Quick Dimension Widgets</span><span class="hd-desc">Top 3 Per Segment</span></div>', unsafe_allow_html=True)
    
    quick_html = ['<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px;">']
    quick_html.append(_hd_quick_widget("Client-wise SKUs", f"{_nunique(combined, col_client)} clients", top10_client, "#60a5fa"))
    quick_html.append(_hd_quick_widget("Country-wise SKUs", f"{_nunique(combined, col_country)} countries", top10_country, "#4ade80"))
    quick_html.append(_hd_quick_widget("Source-wise SKUs", f"{_nunique(combined, col_source)} sources", top10_source, "#f59e0b"))
    quick_html.append(_hd_quick_widget("Brand-wise SKUs", f"{_nunique(combined, col_brand)} brands", top10_brand, "#a78bfa"))
    quick_html.append(_hd_quick_widget("Product-wise SKUs", f"{_nunique(combined, col_product)} products", top10_product, "#14b8a6"))
    quick_html.append("</div>")
    
    st.markdown("".join(quick_html), unsafe_allow_html=True)