from __future__ import annotations

import io
import os
import re
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import streamlit as st
import requests

# ==========================================
# STEP 1: MODULE IMPORT & ENVIRONMENT SETUP
# ==========================================
try:
    from azure.storage.blob import BlobServiceClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

from utils import get_combined_df, require_credentials, display_table

st.set_page_config(
    page_title="Azure vs BQ Global Summary & Analysis",
    page_icon="🔄",
    layout="wide"
)

require_credentials()

# Inject Custom CSS for UI styling (Cards, Metrics, Breadcrumbs, Headers)
st.markdown("""
<style>
.card{background:#111c35;border:1px solid #1e3a5f;border-radius:9px;padding:1.2rem;margin-bottom:.9rem;}
.metric-box{background:#0d1829;border:1px solid #1e3a5f;border-radius:7px;padding:.9rem;text-align:center; height: 100%;}
.metric-val{font-family:monospace;font-size:1.85rem;font-weight:700;color:#60a5fa}
.metric-lbl{font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-top:4px}
.breadcrumb{background:#0f1a30;border:1px solid #1e3a5f;border-radius:5px;padding:8px 12px;font-family:monospace;font-size:.85rem;color:#e2e8f0;margin-bottom:.8rem;display:flex;align-items:center;justify-content:space-between;}
.section-header {background: linear-gradient(90deg, #1e3a5f 0%, rgba(30,58,95,0) 100%); padding: 8px 15px; border-left: 4px solid #60a5fa; margin: 1.5rem 0 1rem 0; font-weight: 600;}
</style>
""", unsafe_allow_html=True)

st.markdown("# 🔄 Azure vs BigQuery Deliverables Match & Global Summary")
st.markdown("Compare BigQuery deliverables against live Azure Blob Storage vendor files with bulk folder crawling, website/app filters, automated diagnostics, and email reporting.")

# ==========================================
# MASTER URL & PLATFORM DEFINITIONS
# ==========================================
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

master_df = pd.DataFrame(URL_MASTER_DATA, columns=["Country", "Source", "PlatformType", "BaseURL"])

# ==========================================
# STEP 2: FAST TEXT CLEANING ENGINE
# ==========================================
def extract_clean_name_fast(val: Any) -> str:
    if pd.isna(val) or val is None: return ""
    if isinstance(val, (list, tuple)): return extract_clean_name_fast(val[0]) if val else ""
    if isinstance(val, dict):
        for k in ["name", "Name", "brand_name", "BrandName", "product_name", "ProductName", "value"]:
            if k in val and val[k]: return str(val[k]).strip().lower()
        for v in val.values():
            if v: return str(v).strip().lower()
        return ""
    if isinstance(val, str):
        v = val.strip()
        if not v or v.lower() in ("nan", "none", "null", "[]", "{}"): return ""
        import json
        if (v.startswith("{") or v.startswith("[")):
            try:
                parsed = json.loads(v)
                if str(parsed) != v: return extract_clean_name_fast(parsed)
            except: pass
        m = re.search(r'["\'](?:name|brand_name|BrandName|product_name|ProductName)["\']\s*:\s*["\']?([^"\'},\]]+)', v, re.IGNORECASE)
        if m: return m.group(1).strip().lower()
        if "#" in v: v = v.split("#", 1)[-1] 
        if "," in v: v = v.split(",")[0]
        return " ".join(v.split()).lower()
    return str(val).strip().lower()

def safe_clean(df: pd.DataFrame, col_name: str) -> pd.Series:
    if col_name not in df.columns: return pd.Series("", index=df.index)
    series = df[col_name]
    unique_vals = series.dropna().unique()
    clean_map = {val: extract_clean_name_fast(val) for val in unique_vals}
    return series.map(clean_map).fillna("")

# ==========================================
# STEP 3: AZURE BULK STORAGE MANAGER
# ==========================================
class AzureBulkManager:
    def __init__(self, conn_str: str):
        self.conn_str = conn_str.strip() if conn_str else ""
        self._client = None

    @property
    def client(self):
        if self._client is None and AZURE_AVAILABLE and self.conn_str:
            try:
                self._client = BlobServiceClient.from_connection_string(self.conn_str)
            except Exception as e:
                st.error(f"Azure connection failed: {e}")
        return self._client

    def list_containers(self) -> List[str]:
        if not self.client: return ["offline-sample-container"]
        try: return [c.name for c in self.client.list_containers()]
        except Exception: return []

    def get_all_blobs_at_prefix(self, container: str, prefix: str) -> List[Dict[str, Any]]:
        DATA_EXTS = ('.csv', '.xlsx', '.xls', '.json')
        if not self.client:
            return [{'name': f'{prefix}mock_vendor_data.csv', 'size': 1024}]
        
        files = []
        try:
            cc = self.client.get_container_client(container)
            for blob in cc.list_blobs(name_starts_with=prefix):
                if blob.name.lower().endswith(DATA_EXTS):
                    files.append({'name': blob.name, 'size': getattr(blob, 'size', 0)})
        except Exception as e:
            st.error(f"Error scanning prefix '{prefix}': {e}")
        return files

    def read_blob_optimized(self, container: str, blob_name: str) -> Optional[pd.DataFrame]:
        if not self.client:
            return pd.DataFrame({
                'sku_id': ['SKU-001', 'SKU-002', 'SKU-003'],
                'product_name': ['Sample A', 'Sample B', 'Sample C'],
                'OfferUrl': ['https://www.amazon.ae/sample1', 'https://www.amazon.ae/sample2', 'https://www.amazon.ae/sample3']
            })
        try:
            blob_client = self.client.get_container_client(container).get_blob_client(blob_name)
            ext = os.path.splitext(blob_name)[1].lower()
            stream = io.BytesIO()
            blob_client.download_blob().readinto(stream)
            stream.seek(0)
            
            if ext == '.csv': df = pd.read_csv(stream, low_memory=False)
            elif ext in ('.xlsx', '.xls'): df = pd.read_excel(stream)
            elif ext == '.json': df = pd.read_json(stream)
            else:
                try: df = pd.read_csv(stream, low_memory=False)
                except Exception: df = pd.read_excel(stream)
            df['_azure_source_file'] = blob_name
            return df
        except Exception as e:
            return None

# ==========================================
# STEP 4: COMPARISON ENGINE
# ==========================================
class ComparisonEngine:
    def run_comparison(self, client_df: pd.DataFrame, vendor_df: pd.DataFrame, client_keys: List[str], vendor_keys: List[str], apply_clean: bool = True) -> Dict[str, Any]:
        c_df, v_df = client_df.copy(), vendor_df.copy()

        if apply_clean:
            c_df['_match_key'] = c_df[client_keys[0]].astype(str)
            v_df['_match_key'] = v_df[vendor_keys[0]].astype(str)
            for col in client_keys[1:]:
                c_df['_match_key'] += "|" + safe_clean(c_df, col)
            for col in vendor_keys[1:]:
                v_df['_match_key'] += "|" + safe_clean(v_df, col)
        else:
            c_df['_match_key'] = c_df[client_keys].astype(str).agg('|'.join, axis=1)
            v_df['_match_key'] = v_df[vendor_keys].astype(str).agg('|'.join, axis=1)

        c_keys = set(c_df['_match_key'].dropna().unique())
        v_keys = set(v_df['_match_key'].dropna().unique())

        common_keys = c_keys.intersection(v_keys)
        missing_in_vendor = c_keys.difference(v_keys)
        missing_in_client = v_keys.difference(c_keys)

        c_df_unique = c_df.drop_duplicates(subset=['_match_key'], keep='first').copy()
        v_df_unique = v_df.drop_duplicates(subset=['_match_key'], keep='first').copy()

        c_df_unique['Match_Status'] = np.where(c_df_unique['_match_key'].isin(common_keys), 'Matched in Azure', 'Missing in Azure')
        v_df_unique['Match_Status'] = np.where(v_df_unique['_match_key'].isin(common_keys), 'In BQ Scope', 'Extra in Azure (Vendor)')

        return {
            'summary': {
                'total_bq_expected': len(c_keys),
                'total_azure_provided': len(v_keys),
                'matched_skus': len(common_keys),
                'missing_in_azure': len(missing_in_vendor),
                'extra_in_azure': len(missing_in_client),
                'match_rate': (len(common_keys) / max(len(c_keys), 1)) * 100
            },
            'client_df': c_df_unique,
            'vendor_df': v_df_unique
        }

# ==========================================
# STEP 5: STATE & INITIALIZATION
# ==========================================
if "azure_conn_string" not in st.session_state: 
    st.session_state.azure_conn_string = os.getenv("AZURE_CONNECTION_STRING", "")
if "global_vendor_df" not in st.session_state: 
    st.session_state.global_vendor_df = None
if "global_load_summary" not in st.session_state: 
    st.session_state.global_load_summary = None

azure_mgr = AzureBulkManager(st.session_state.azure_conn_string)

with st.spinner("🔄 Checking Global BigQuery Data..."):
    bq_df = get_combined_df(force_refresh=False)

if bq_df is None or bq_df.empty:
    st.warning("⚠️ No BigQuery Deliverables data loaded. Please load master data first.")
    st.stop()

# ==========================================
# STEP 6: UI - GLOBAL CONNECTION & DATE SETUP
# ==========================================
st.markdown('<div class="section-header">1️⃣ Global Connection & Bulk Ingestion Setup</div>', unsafe_allow_html=True)
conn_str = st.text_input("Azure Connection String", value=st.session_state.azure_conn_string, type="password", placeholder="DefaultEndpointProtocol=https;AccountName=...")
if conn_str != st.session_state.azure_conn_string:
    st.session_state.azure_conn_string = conn_str
    st.rerun()

containers = azure_mgr.list_containers()
default_c_idx = containers.index('clicflyer') if 'clicflyer' in containers else 0

c_col1, c_col2 = st.columns(2)
with c_col1:
    sel_container = st.selectbox("Select Azure Container", containers, index=default_c_idx)
with c_col2:
    default_date = datetime.now().date() - timedelta(days=1)
    sel_date = st.date_input("Target Deliverable Date (Folder Path)", value=default_date)

date_str = sel_date.strftime("%d-%m-%Y")
target_prefix = f"processed/Deliverable/{date_str}/"

st.markdown(f'<div class="breadcrumb">📂 Bulk Ingestion Root Path: <b>/{target_prefix}</b></div>', unsafe_allow_html=True)

col_run1, col_run2 = st.columns([3, 1])
with col_run1:
    st.caption("Automatically scans all subfolders and files for the selected date, streaming and merging all vendor payloads into session memory.")
with col_run2:
    run_bulk_load = st.button("🚀 Run Bulk Ingestion", type="primary", use_container_width=True)

if run_bulk_load or st.session_state.global_vendor_df is not None:
    files_to_load = azure_mgr.get_all_blobs_at_prefix(sel_container, target_prefix)
    
    if run_bulk_load:
        if not files_to_load:
            st.error(f"❌ No files found under Azure path: `{target_prefix}`.")
        else:
            merged_list = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_files = len(files_to_load)
            success_hits, failed_hits = 0, 0
            
            for idx, file_meta in enumerate(files_to_load):
                f_name = file_meta['name']
                short_name = f_name.split('/')[-1]
                status_text.markdown(f"🔄 **Processing [{idx+1}/{total_files}]**: `{short_name}`")
                
                df_chunk = azure_mgr.read_blob_optimized(sel_container, f_name)
                if df_chunk is not None and not df_chunk.empty:
                    merged_list.append(df_chunk)
                    success_hits += 1
                else:
                    failed_hits += 1
                progress_bar.progress((idx + 1) / total_files)
                
            status_text.empty()
            progress_bar.empty()
            
            if merged_list:
                st.session_state.global_vendor_df = pd.concat(merged_list, ignore_index=True)
                st.session_state.global_load_summary = {
                    "total_found": total_files,
                    "success": success_hits,
                    "failed": failed_hits,
                    "total_rows": len(st.session_state.global_vendor_df)
                }
                st.success(f"✅ Successfully ingested {success_hits} files ({len(st.session_state.global_vendor_df):,} total rows).")

# ==========================================
# STEP 7: SIDE-BY-SIDE SPLIT VIEW (BQ LEFT, AZURE RIGHT)
# ==========================================
st.markdown('<div class="section-header">2️⃣ Select & Filter Datasets (Side-by-Side View)</div>', unsafe_allow_html=True)
col_bq, col_az = st.columns(2, gap="large")

with col_bq:
    st.markdown("#### 🏢 BigQuery Deliverables (Client Data)")
    st.caption("Filtered master data from your BigQuery session.")
    
    f1, f2 = st.columns(2)
    clients = ["All"] + list(bq_df['Client'].dropna().unique()) if 'Client' in bq_df.columns else ["All"]
    sel_client = f1.selectbox("Filter Client", clients, key="az_client_split")
    
    filtered_bq = bq_df.copy()
    if sel_client != "All": filtered_bq = filtered_bq[filtered_bq['Client'] == sel_client]
    
    countries = ["All"] + list(filtered_bq['CountryName'].dropna().unique()) if 'CountryName' in filtered_bq.columns else ["All"]
    sel_country = f2.selectbox("Filter Country", countries, key="az_country_split")
    
    if sel_country != "All": filtered_bq = filtered_bq[filtered_bq['CountryName'] == sel_country]
    
    # Default Source Type filter to Website based on master definitions
    source_types = ["Website", "App", "All"]
    sel_source_type = st.selectbox("Filter Source Type", source_types, index=0, key="az_sourcetype_split")
    
    if sel_source_type != "All":
        allowed_sources = master_df[master_df['PlatformType'] == sel_source_type]['Source'].unique()
        if 'Ecom_Source' in filtered_bq.columns:
            filtered_bq = filtered_bq[filtered_bq['Ecom_Source'].isin(allowed_sources)]

    sources = ["All"] + list(filtered_bq['Ecom_Source'].dropna().unique()) if 'Ecom_Source' in filtered_bq.columns else ["All"]
    sel_source = st.selectbox("Filter Source", sources, key="az_source_split")
    
    if sel_source != "All": filtered_bq = filtered_bq[filtered_bq['Ecom_Source'] == sel_source]
    
    id_col_bq = 'id' if 'id' in filtered_bq.columns else 'Ecom_SKU' if 'Ecom_SKU' in filtered_bq.columns else filtered_bq.columns[0]
    unique_bq_ids = filtered_bq[id_col_bq].nunique()
    
    st.markdown("##### 📌 Selected Scope Summary")
    s1, s2, s3, s4 = st.columns(4)
    s1.markdown(f'<div class="metric-box" style="padding:0.5rem;"><div class="metric-val" style="font-size:1.0rem;">{sel_client}</div><div class="metric-lbl">Client</div></div>', unsafe_allow_html=True)
    s2.markdown(f'<div class="metric-box" style="padding:0.5rem;"><div class="metric-val" style="font-size:1.0rem;">{sel_country}</div><div class="metric-lbl">Country</div></div>', unsafe_allow_html=True)
    s3.markdown(f'<div class="metric-box" style="padding:0.5rem;"><div class="metric-val" style="font-size:1.0rem;">{sel_source_type}</div><div class="metric-lbl">Type</div></div>', unsafe_allow_html=True)
    s4.markdown(f'<div class="metric-box" style="padding:0.5rem; border-color:#4ade80;"><div class="metric-val" style="font-size:1.1rem; color:#4ade80;">{unique_bq_ids:,}</div><div class="metric-lbl">Unique IDs</div></div>', unsafe_allow_html=True)
    
    st.success(f"✅ **{unique_bq_ids:,}** Unique SKUs/IDs prepared for mapping.")
    
    with st.expander("👀 View BigQuery Data Preview (Top 100)", expanded=False):
        display_table(filtered_bq.head(100), key="bq_preview_split", height=250)

with col_az:
    st.markdown("#### ☁️ Azure Storage (Vendor Data)")
    st.caption("Bulk ingested vendor data from Azure.")
    
    if st.session_state.global_vendor_df is not None:
        v_df_all = st.session_state.global_vendor_df
        summary_meta = st.session_state.get("global_load_summary", {"total_found": len(v_df_all), "success": len(v_df_all), "failed": 0, "total_rows": len(v_df_all)})
        
        st.info(f"📦 Total Loaded Rows in Memory: **{len(v_df_all):,}** across **{summary_meta.get('success', 0)}** files.")
        
        if st.button("🗑️ Clear Merged Azure Data", use_container_width=True):
            st.session_state.global_vendor_df = None
            st.session_state.global_load_summary = None
            if "az_match_results" in st.session_state: del st.session_state["az_match_results"]
            st.rerun()
            
        with st.expander(f"👀 View Merged Azure Data Preview (Total: {len(v_df_all):,} rows)", expanded=False):
            display_table(v_df_all.head(100), key="az_preview_split", height=250)
    else:
        st.warning("⚠️ No Azure data loaded yet. Click **'Run Bulk Ingestion'** above.")

# ==========================================
# STEP 8: MAPPING & EXECUTION
# ==========================================
st.markdown('<div class="section-header">3️⃣ Define Mapping Keys & Execute Reconciliation</div>', unsafe_allow_html=True)

if st.session_state.global_vendor_df is not None:
    v_df = st.session_state.global_vendor_df
    
    m1, m2 = st.columns(2)
    with m1:
        c_cols = list(filtered_bq.columns)
        default_c = ['Ecom_WebUrl'] if 'Ecom_WebUrl' in c_cols else ['id']
        sel_c_keys = st.multiselect("Client Key Sequence (BigQuery)", c_cols, default=default_c)
    with m2:
        v_cols = list(v_df.columns)
        default_v = ['OfferUrl'] if 'OfferUrl' in v_cols else ['sku_id']
        sel_v_keys = st.multiselect("Vendor Key Sequence (Azure)", v_cols, default=default_v)

    clean_keys = st.checkbox("🪄 Auto-Clean Keys (Recommended for JSON strings & ID#Name combos)", value=True)

    if st.button("🚀 Process & Run Global Data Match", type="primary", use_container_width=True):
        if not sel_c_keys or not sel_v_keys:
            st.error("Please select at least one key for both datasets.")
        else:
            with st.spinner("Executing High-Speed Matching Engine..."):
                engine = ComparisonEngine()
                st.session_state.az_match_results = engine.run_comparison(filtered_bq, v_df, sel_c_keys, sel_v_keys, clean_keys)
                st.session_state.used_c_keys = sel_c_keys
                st.session_state.used_v_keys = sel_v_keys
                st.success("Matching Complete!")

# ==========================================
# STEP 9: KPI DASHBOARD & TABBED RESULTS
# ==========================================
if "az_match_results" in st.session_state:
    st.markdown('<div class="section-header">4️⃣ Match Analytics & Executive Summary Dashboard</div>', unsafe_allow_html=True)
    
    res = st.session_state.az_match_results
    summ = res['summary']
    c_res = res['client_df']
    v_res = res['vendor_df']
    total_clients = c_res['Client'].nunique() if 'Client' in c_res.columns else 1
    
    # Complete KPI Cards with hover descriptions
    k0, k1, k2, k3, k4, k5 = st.columns(6)
    k0.markdown(f'<div class="metric-box" title="Unique clients active in this filtered match"><div class="metric-val">{total_clients}</div><div class="metric-lbl">Active Clients</div></div>', unsafe_allow_html=True)
    k1.markdown(f'<div class="metric-box" title="Distinct count of unique keys expected based on BigQuery filter"><div class="metric-val">{summ["total_bq_expected"]:,}</div><div class="metric-lbl">BQ Expected (Total URLs)</div></div>', unsafe_allow_html=True)
    k2.markdown(f'<div class="metric-box" title="Distinct count of keys successfully found in both datasets"><div class="metric-val" style="color:#4ade80;">{summ["matched_skus"]:,}</div><div class="metric-lbl">Available in Azure</div></div>', unsafe_allow_html=True)
    k3.markdown(f'<div class="metric-box" title="Distinct count of keys expected in BQ but NOT found in Azure"><div class="metric-val" style="color:#f87171;">{summ["missing_in_azure"]:,}</div><div class="metric-lbl">Missing in Azure</div></div>', unsafe_allow_html=True)
    k4.markdown(f'<div class="metric-box" title="Distinct count of keys found in Azure but NOT expected in BQ scope"><div class="metric-val" style="color:#a78bfa;">{summ["extra_in_azure"]:,}</div><div class="metric-lbl">Extra in Azure</div></div>', unsafe_allow_html=True)
    k5.markdown(f'<div class="metric-box" title="Percentage of BQ expected keys that were successfully matched"><div class="metric-val" style="color:#fbbf24;">{summ["match_rate"]:.1f}%</div><div class="metric-lbl">Overall Match Rate</div></div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Client-wise summary table
    if 'Client' in c_res.columns:
        st.markdown("##### 🏢 Client-Wise Summary Breakdown")
        client_stats = []
        for client_name, group in c_res.groupby('Client', observed=True):
            expected = group['_match_key'].nunique()
            matched = group[group['Match_Status'] == 'Matched in Azure']['_match_key'].nunique()
            missing = group[group['Match_Status'] == 'Missing in Azure']['_match_key'].nunique()
            match_rate = (matched / expected * 100) if expected > 0 else 0.0
            
            client_stats.append({
                "Client Name": client_name,
                "Total Expected URLs": expected,
                "Azure Available URLs": matched,
                "Missing URLs": missing,
                "Match Rate": f"{match_rate:.1f}%"
            })
        client_summary_df = pd.DataFrame(client_stats)
        st.dataframe(client_summary_df, use_container_width=True, hide_index=True)
        st.markdown("<br>", unsafe_allow_html=True)
    
    # Tabs with clickable Web URLs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["❌ Missing in Azure", "✅ Matched in Both", "➕ Extra in Azure", "🔍 Missing URL Diagnostic", "📥 Full Data Extract Downloads"])
    
    with tab1:
        st.markdown("### Missing SKUs / URLs in Azure (Action Required)")
        st.caption("Click any Web URL cell to open the link directly in a new tab.")
        missing_client = c_res[c_res['Match_Status'] == 'Missing in Azure'].drop(columns=['_match_key'])
        if not missing_client.empty:
            url_col = 'Ecom_WebUrl' if 'Ecom_WebUrl' in missing_client.columns else None
            if url_col:
                st.dataframe(missing_client, use_container_width=True, column_config={url_col: st.column_config.LinkColumn("Web URL")}, height=400)
            else:
                st.dataframe(missing_client, use_container_width=True, height=400)
        else:
            st.success("🎉 All expected BigQuery SKUs were successfully found in Azure!")

    with tab2:
        st.markdown("### Matched SKUs / URLs in Both")
        st.caption("Successfully matched across BigQuery and Azure vendor files.")
        matched_client = c_res[c_res['Match_Status'] == 'Matched in Azure'].drop(columns=['_match_key'])
        if not matched_client.empty:
            url_col = 'Ecom_WebUrl' if 'Ecom_WebUrl' in matched_client.columns else None
            if url_col:
                st.dataframe(matched_client, use_container_width=True, column_config={url_col: st.column_config.LinkColumn("Web URL")}, height=400)
            else:
                st.dataframe(matched_client, use_container_width=True, height=400)
        else:
            st.warning("No records matched.")
            
    with tab3:
        st.markdown("### Extra SKUs in Azure (Vendor)")
        st.caption("Provided by Vendor in Azure, but not expected based on current BQ filters.")
        extra_vendor = v_res[v_res['Match_Status'] == 'Extra in Azure (Vendor)'].drop(columns=['_match_key'])
        if not extra_vendor.empty:
            display_table(extra_vendor, key="extra_az_tbl", height=400)
        else:
            st.info("No extra SKUs crawled outside the expected scope.")
            
    with tab4:
        st.markdown("### 🔍 Missing URL Live Status Checker & Diagnostics")
        st.caption("Select a sample of missing BigQuery URLs to verify their live HTTP status (detecting if they are working, redirecting to home page, or returning errors).")
        
        missing_df_subset = c_res[c_res['Match_Status'] == 'Missing in Azure'].copy()
        url_col_chk = 'Ecom_WebUrl' if 'Ecom_WebUrl' in missing_df_subset.columns else None
        
        if url_col_chk and not missing_df_subset.empty:
            sample_size = st.slider("Select Sample Size to Check", min_value=1, max_value=min(50, len(missing_df_subset)), value=min(10, len(missing_df_subset)))
            
            if st.button("🧪 Run Live URL Status Diagnostics", type="primary"):
                with st.spinner(f"Checking {sample_size} URLs live..."):
                    diagnostic_results = []
                    sample_urls = missing_df_subset[url_col_chk].dropna().head(sample_size).tolist()
                    
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                    for u in sample_urls:
                        status_label = "Unknown"
                        http_code = 0
                        try:
                            resp = requests.get(u, headers=headers, timeout=5)
                            http_code = resp.status_code
                            if resp.status_code == 200:
                                status_label = "Active / Working"
                                if len(resp.text) < 1500:
                                    status_label = "Possible Home Page / Empty Redirect"
                            elif resp.status_code in (404, 410):
                                status_label = "Broken / Not Found (404)"
                            else:
                                status_label = f"HTTP Error ({resp.status_code})"
                        except Exception as e:
                            status_label = f"Connection Failed ({type(e).__name__})"
                            
                        diagnostic_results.append({
                            "Web URL": u,
                            "HTTP Status": http_code,
                            "Diagnostic Reason": status_label
                        })
                        
                    diag_df = pd.DataFrame(diagnostic_results)
                    st.dataframe(diag_df, use_container_width=True, column_config={"Web URL": st.column_config.LinkColumn("Web URL")})
        else:
            st.info("No missing URLs available for diagnostics.")

    with tab5:
        st.markdown("### 📥 Download Complete Merged Reports")
        st.caption("Exports all datasets including exact Azure source file paths (`_azure_source_file`).")
        
        d1, d2 = st.columns(2)
        c_export = c_res.drop(columns=['_match_key']) if not c_res.empty else pd.DataFrame(columns=['No Data'])
        v_export = v_res.drop(columns=['_match_key']) if not v_res.empty else pd.DataFrame(columns=['No Data'])
        
        csv_data = c_export.to_csv(index=False).encode('utf-8')
        d1.download_button("⬇️ Download BQ Client Match Results (CSV)", data=csv_data, file_name="bq_client_match_results_with_path.csv", mime="text/csv", use_container_width=True)

        if OPENPYXL_AVAILABLE:
            out = io.BytesIO()
            try:
                with pd.ExcelWriter(out, engine='openpyxl') as writer:
                    c_export.to_excel(writer, sheet_name='BQ Scope Output', index=False)
                    v_export.to_excel(writer, sheet_name='Azure Vendor Output', index=False)
                out.seek(0)
                d2.download_button("⬇️ Download Complete Multi-Sheet Report (Excel)", data=out.getvalue(), file_name="azure_bq_complete_report_with_path.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            except Exception as e:
                d2.error(f"Excel generation failed: {e}")

    # ==========================================
    # STEP 10: TRIGGER SUMMARY VIA EMAIL SECTION
    # ==========================================
    st.markdown('<div class="section-header">📧 Trigger Summary via Email</div>', unsafe_allow_html=True)
    st.caption("Configure recipients, customize message body, and automatically dispatch the executive summary report along with multi-sheet attachments using `.env` SMTP credentials.")

    with st.expander("✉️ Email Dispatch Configuration & Preview", expanded=True):
        e_col1, e_col2 = st.columns(2)
        with e_col1:
            # Default recipient list management (Add/Remove directly from UI)
            if "email_recipients_to" not in st.session_state:
                st.session_state.email_recipients_to = ["pankaj.budhlakoti@clicflyer.com"]
            
            st.markdown("**TO Recipients**")
            new_to = st.text_input("Add TO Email", placeholder="name@company.com", key="add_to_input")
            if st.button("Add Recipient", key="btn_add_to"):
                if new_to and new_to not in st.session_state.email_recipients_to:
                    st.session_state.email_recipients_to.append(new_to)
                    st.rerun()
            
            to_to_remove = st.selectbox("Remove Recipient", ["Select to remove"] + st.session_state.email_recipients_to, key="rem_to_select")
            if to_to_remove != "Select to remove" and st.button("Remove Selected", key="btn_rem_to"):
                st.session_state.email_recipients_to.remove(to_to_remove)
                st.rerun()
                
            st.info(f"Current TO: {', '.join(st.session_state.email_recipients_to)}")

        with e_col2:
            if "email_recipients_cc" not in st.session_state:
                st.session_state.email_recipients_cc = ["Nilesh.singh@clicflyer.com"]
                
            st.markdown("**CC Recipients**")
            new_cc = st.text_input("Add CC Email", placeholder="cc@company.com", key="add_cc_input")
            if st.button("Add CC Recipient", key="btn_add_cc"):
                if new_cc and new_cc not in st.session_state.email_recipients_cc:
                    st.session_state.email_recipients_cc.append(new_cc)
                    st.rerun()
                    
            cc_to_remove = st.selectbox("Remove CC", ["Select to remove"] + st.session_state.email_recipients_cc, key="rem_cc_select")
            if cc_to_remove != "Select to remove" and st.button("Remove Selected CC", key="btn_rem_cc"):
                st.session_state.email_recipients_cc.remove(cc_to_remove)
                st.rerun()
                
            st.info(f"Current CC: {', '.join(st.session_state.email_recipients_cc)}")

        default_subject = f"Azure vs BigQuery Executive Summary Report - Date: {date_str}"
        email_subject = st.text_input("Email Subject", value=default_subject)

        default_body = f"""Hi Team,

Please find attached the Azure vs BigQuery Deliverables reconciliation report for date: {date_str}.

--- Executive Summary ---
• Total BQ Expected (URLs): {summ['total_bq_expected']:,}
• Successfully Available in Azure: {summ['matched_skus']:,}
• Missing in Azure: {summ['missing_in_azure']:,}
• Extra in Azure: {summ['extra_in_azure']:,}
• Overall Match Rate: {summ['match_rate']:.1f}%

Regards,
Pankaj Budhlakoti"""

        email_body = st.text_area("Email Body (Fully Editable)", value=default_body, height=200)

        if st.button("📤 Send Summary Report via Email", type="primary", use_container_width=True):
            smtp_server = os.getenv("smtp_server")
            smtp_port = int(os.getenv("smtp_port", "587"))
            sender_email = os.getenv("smtp_user", "")
            sender_password = os.getenv("smtp_password", "")

            if not sender_email or not sender_password:
                st.error("🚨 SMTP Credentials (`SENDER_EMAIL` & `SENDER_PASSWORD`) are missing from your `.env` file.")
            elif not st.session_state.email_recipients_to:
                st.error("🚨 Please specify at least one TO recipient.")
            else:
                with st.spinner("Preparing and sending email..."):
                    try:
                        msg = EmailMessage()
                        msg['Subject'] = email_subject
                        msg['From'] = sender_email
                        msg['To'] = ", ".join(st.session_state.email_recipients_to)
                        if st.session_state.email_recipients_cc:
                            msg['Cc'] = ", ".join(st.session_state.email_recipients_cc)
                        
                        msg.set_content(email_body)

                        # Attach generated multi-sheet Excel report
                        if OPENPYXL_AVAILABLE:
                            att_io = io.BytesIO()
                            with pd.ExcelWriter(att_io, engine='openpyxl') as writer:
                                c_export.to_excel(writer, sheet_name='BQ Scope Output', index=False)
                                v_export.to_excel(writer, sheet_name='Azure Vendor Output', index=False)
                            att_io.seek(0)
                            
                            msg.add_attachment(
                                att_io.getvalue(),
                                maintype='application',
                                subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                filename=f"azure_bq_complete_report_{date_str}.xlsx"
                            )

                        # Send via SMTP
                        all_recipients = st.session_state.email_recipients_to + st.session_state.email_recipients_cc
                        with smtplib.SMTP(smtp_server, smtp_port) as server:
                            server.starttls()
                            server.login(sender_email, sender_password)
                            server.send_message(msg, from_addr=sender_email, to_addrs=all_recipients)

                        st.success(f"✅ Email successfully dispatched to {len(all_recipients)} recipient(s) with report attached!")
                    except Exception as e:
                        st.error(f"❌ Failed to send email: {e}")

else:
    st.info("👆 Please ingest Azure data above and run the matching engine to unlock the full executive dashboard and email reporting tools.")