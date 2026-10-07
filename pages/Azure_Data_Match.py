from __future__ import annotations

import io
import os
import re
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import streamlit as st

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

# Import global utilities from your app ecosystem
from utils import get_combined_df, require_credentials, display_table

# Configure Streamlit page layout and metadata
st.set_page_config(
    page_title="Azure vs BQ Data Match",
    page_icon="🔄",
    layout="wide"
)

# Enforce user authentication using custom utility
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

st.markdown("# 🔄 Azure vs BigQuery Deliverables Match")
st.markdown("Compare BigQuery deliverables against live Azure Blob Storage vendor files based on distinct SKUs (ignoring price fluctuations).")

# ==========================================
# STEP 2: FAST TEXT CLEANING ENGINE
# ==========================================
def extract_clean_name_fast(val: Any) -> str:
    """Recursively extracts and standardizes a clean string from various data types."""
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
    """Applies the text cleaning function only to unique values to save processing time."""
    if col_name not in df.columns: return pd.Series("", index=df.index)
    series = df[col_name]
    unique_vals = series.dropna().unique()
    clean_map = {val: extract_clean_name_fast(val) for val in unique_vals}
    return series.map(clean_map).fillna("")

# ==========================================
# STEP 3: AZURE STORAGE MANAGER
# ==========================================
class AzureBlobManager:
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

    def get_items_at_path(self, container: str, path: str) -> Dict[str, List[Any]]:
        DATA_EXTS = ('.csv', '.xlsx', '.xls', '.json')
        if not self.client:
            if path == "": return {'folders': ['Mock_Folder_A'], 'files': []}
            return {'folders': [], 'files': [{'name': f'{path}mock_vendor_data.csv', 'size': 1024}]}

        folders, files = [], []
        try:
            cc = self.client.get_container_client(container)
            for item in cc.walk_blobs(name_starts_with=path, delimiter='/'):
                name = item.name
                if name.endswith('/'):
                    fn = name[len(path):].rstrip('/')
                    if fn and fn != "[..]": folders.append(fn)
                else:
                    if name.lower().endswith(DATA_EXTS):
                        fn = name.split('/')[-1]
                        if fn and fn != "[..]":
                            files.append({'name': name, 'size': getattr(item, 'size', 0)})
        except Exception as e:
            st.error(f"Error listing path '{path}': {e}")
        return {'folders': sorted(folders), 'files': files}

    def read_blob_optimized(self, container: str, blob_name: str) -> Optional[pd.DataFrame]:
        if not self.client:
            return pd.DataFrame({
                'sku_id': ['SKU-001', 'SKU-002', 'SKU-003'],
                'product_name': ['Sample A', 'Sample B', 'Sample C'],
                'source': ['Amazon', 'Carrefour', 'Lulu']
            })
        try:
            blob_client = self.client.get_container_client(container).get_blob_client(blob_name)
            ext = os.path.splitext(blob_name)[1].lower()
            stream = io.BytesIO()
            blob_client.download_blob().readinto(stream)
            stream.seek(0)
            
            if ext == '.csv': return pd.read_csv(stream, low_memory=False)
            elif ext in ('.xlsx', '.xls'): return pd.read_excel(stream)
            elif ext == '.json': return pd.read_json(stream)
            else:
                try: return pd.read_csv(stream, low_memory=False)
                except Exception: return pd.read_excel(stream)
        except Exception as e:
            st.error(f"Error reading {blob_name}: {e}")
            return None

# ==========================================
# STEP 4: COMPARISON ENGINE (De-duplicated)
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
# STEP 5: STATE & DATA INITIALIZATION
# ==========================================
if "azure_conn_string" not in st.session_state: 
    st.session_state.azure_conn_string = os.getenv("AZURE_CONNECTION_STRING", "")
if "azure_path" not in st.session_state: 
    st.session_state.azure_path = "processed/Deliverable/"
if "loaded_azure_files" not in st.session_state: 
    st.session_state.loaded_azure_files = [] 
if "vendor_df" not in st.session_state: 
    st.session_state.vendor_df = None

azure_mgr = AzureBlobManager(st.session_state.azure_conn_string)

with st.spinner("🔄 Checking Global BigQuery Data..."):
    bq_df = get_combined_df(force_refresh=False)

if bq_df is None or bq_df.empty:
    st.warning("⚠️ No BigQuery Deliverables data loaded. Please go to the App/Home page to load your master data first.")
    st.stop()

# ==========================================
# STEP 6: UI - GLOBAL CONNECTION SETUP
# ==========================================
st.markdown('<div class="section-header">1️⃣ Global Connection Setup</div>', unsafe_allow_html=True)
conn_str = st.text_input("Azure Connection String", value=st.session_state.azure_conn_string, type="password", placeholder="DefaultEndpointProtocol=https;AccountName=...")
if conn_str != st.session_state.azure_conn_string:
    st.session_state.azure_conn_string = conn_str
    st.rerun()

if not AZURE_AVAILABLE:
    st.error("🚨 `azure-storage-blob` is not installed. Using offline mock mode.")

# ==========================================
# STEP 7: UI - SIDE-BY-SIDE DATA LOADERS
# ==========================================
st.markdown('<div class="section-header">2️⃣ Select & Filter Datasets</div>', unsafe_allow_html=True)
col_bq, col_az = st.columns(2, gap="large")

with col_bq:
    st.markdown("#### 🏢 BigQuery Deliverables (Client Data)")
    st.caption("Data is instantly pulled from your cached Home page session.")
    
    f1, f2 = st.columns(2)
    clients = ["All"] + list(bq_df['Client'].dropna().unique()) if 'Client' in bq_df.columns else ["All"]
    sel_client = f1.selectbox("Filter Client", clients, key="az_client")
    
    filtered_bq = bq_df.copy()
    if sel_client != "All": filtered_bq = filtered_bq[filtered_bq['Client'] == sel_client]
    
    countries = ["All"] + list(filtered_bq['CountryName'].dropna().unique()) if 'CountryName' in filtered_bq.columns else ["All"]
    sel_country = f2.selectbox("Filter Country", countries, key="az_country")
    
    if sel_country != "All": filtered_bq = filtered_bq[filtered_bq['CountryName'] == sel_country]
    
    sources = ["All"] + list(filtered_bq['Ecom_Source'].dropna().unique()) if 'Ecom_Source' in filtered_bq.columns else ["All"]
    sel_source = st.selectbox("Filter Source", sources, key="az_source")
    
    if sel_source != "All": filtered_bq = filtered_bq[filtered_bq['Ecom_Source'] == sel_source]
    
    id_col_bq = 'id' if 'id' in filtered_bq.columns else 'Ecom_SKU' if 'Ecom_SKU' in filtered_bq.columns else filtered_bq.columns[0]
    unique_bq_ids = filtered_bq[id_col_bq].nunique()
    
    st.markdown("##### 📌 Selected Scope Summary")
    s1, s2, s3, s4 = st.columns(4)
    s1.markdown(f'<div class="metric-box" style="padding:0.5rem;"><div class="metric-val" style="font-size:1.1rem;">{sel_client}</div><div class="metric-lbl">Client</div></div>', unsafe_allow_html=True)
    s2.markdown(f'<div class="metric-box" style="padding:0.5rem;"><div class="metric-val" style="font-size:1.1rem;">{sel_country}</div><div class="metric-lbl">Country</div></div>', unsafe_allow_html=True)
    s3.markdown(f'<div class="metric-box" style="padding:0.5rem;"><div class="metric-val" style="font-size:1.1rem;">{sel_source}</div><div class="metric-lbl">Source</div></div>', unsafe_allow_html=True)
    s4.markdown(f'<div class="metric-box" style="padding:0.5rem; border-color:#4ade80;"><div class="metric-val" style="font-size:1.2rem; color:#4ade80;">{unique_bq_ids:,}</div><div class="metric-lbl">Unique IDs</div></div>', unsafe_allow_html=True)
    
    st.success(f"✅ **{unique_bq_ids:,}** Unique SKUs/IDs prepared for mapping (filtered from {len(filtered_bq):,} raw pricing rows).")
    
    with st.expander("👀 View BigQuery Data Preview (Top 100)", expanded=False):
        display_table(filtered_bq.head(100), key="bq_preview", height=250)

with col_az:
    st.markdown("#### ☁️ Azure Storage (Vendor Data)")
    
    containers = azure_mgr.list_containers()
    default_idx = containers.index('clicflyer') if 'clicflyer' in containers else 0
    sel_container = st.selectbox("Select Azure Container", containers, index=default_idx)

    c_bc1, c_bc2 = st.columns([4, 1])
    with c_bc1:
        st.markdown(f'<div class="breadcrumb">📂 Path: /{st.session_state.azure_path}</div>', unsafe_allow_html=True)
    with c_bc2:
        if st.session_state.azure_path and st.button("⬅️ Back"):
            parts = st.session_state.azure_path.rstrip('/').split('/')
            st.session_state.azure_path = '/'.join(parts[:-1]) + '/' if len(parts) > 1 else ''
            st.rerun()

    items = azure_mgr.get_items_at_path(sel_container, st.session_state.azure_path)
    
    if items['folders']:
        f_cols = st.columns(3)
        for idx, folder in enumerate(items['folders']):
            if f_cols[idx % 3].button(f"📁 {folder}", key=f"fld_{folder}", use_container_width=True):
                st.session_state.azure_path = f"{st.session_state.azure_path}{folder}/"
                st.rerun()
                
    if items['files']:
        file_names = [f['name'] for f in items['files']]
        sel_file = st.selectbox("Select Target File to Add", file_names)
        
        # Display Success Message directly tied to session state before Rerun
        if "az_success_msg" in st.session_state:
            st.success(st.session_state.az_success_msg)
            del st.session_state.az_success_msg
            
        if st.button("📥 Load & Merge Vendor File", type="primary", use_container_width=True):
            with st.spinner("Downloading and merging..."):
                new_v_df = azure_mgr.read_blob_optimized(sel_container, sel_file)
                if new_v_df is not None:
                    if st.session_state.vendor_df is None:
                        st.session_state.vendor_df = new_v_df
                    else:
                        st.session_state.vendor_df = pd.concat([st.session_state.vendor_df, new_v_df], ignore_index=True)
                    
                    st.session_state.loaded_azure_files.append(sel_file)
                    # Use Session State to hold success msg so it survives the explicit rerun
                    st.session_state.az_success_msg = f"✅ Added {len(new_v_df):,} rows! Total merged rows: {len(st.session_state.vendor_df):,}"
                    
                    # FORCE RERUN TO UPDATE FILE SELECTOR AND LIST STATE
                    st.rerun()
    else:
        st.caption("No files in this directory.")
        
    if st.session_state.get("loaded_azure_files"):
        st.markdown("---")
        st.markdown("##### 📦 Currently Merged Files")
        for i, f_path in enumerate(st.session_state.loaded_azure_files, 1):
            st.markdown(f"<div style='background:#1e3a5f; padding:8px; border-radius:5px; margin-bottom:5px; font-size:0.8rem; color:#e2e8f0; word-break: break-all;'><b>{i}.</b> {f_path}</div>", unsafe_allow_html=True)
            
        if st.button("🗑️ Clear All Merged Data", use_container_width=True):
            st.session_state.vendor_df = None
            st.session_state.loaded_azure_files = []
            if "az_match_results" in st.session_state:
                del st.session_state["az_match_results"]
            st.rerun()
            
    if st.session_state.vendor_df is not None:
        with st.expander(f"👀 View Merged Azure Data Preview (Total: {len(st.session_state.vendor_df):,} rows)", expanded=False):
            display_table(st.session_state.vendor_df.head(100), key="az_preview", height=250)

# ==========================================
# STEP 8: UI - KEY CONFIGURATION & EXECUTION
# ==========================================
st.markdown('<div class="section-header">3️⃣ Define Mapping Keys & Execute</div>', unsafe_allow_html=True)

if st.session_state.vendor_df is not None:
    v_df = st.session_state.vendor_df
    
    m1, m2 = st.columns(2)
    with m1:
        c_cols = list(filtered_bq.columns)
        default_c = ['Ecom_WebUrl'] if 'Ecom_WebUrl' in c_cols else ['id']
        sel_c_keys = st.multiselect("Client Key Sequence (BigQuery)", c_cols, default=default_c)
        
    with m2:
        v_cols = list(v_df.columns)
        default_v = ['OfferUrl'] if 'OfferUrl' in v_cols else ['Product_Name']
        sel_v_keys = st.multiselect("Vendor Key Sequence (Azure)", v_cols, default=default_v)

    clean_keys = st.checkbox("🪄 Auto-Clean Keys (Highly Recommended for JSON strings & ID#Name combos)", value=True)

    if st.button("🚀 Process & Run Data Match", type="primary", use_container_width=True):
        if not sel_c_keys or not sel_v_keys:
            st.error("Please select at least one key for both datasets.")
        else:
            with st.spinner("Executing High-Speed Matching Engine (De-duplicating Prices)..."):
                engine = ComparisonEngine()
                st.session_state.az_match_results = engine.run_comparison(filtered_bq, v_df, sel_c_keys, sel_v_keys, clean_keys)
                st.session_state.used_c_keys = sel_c_keys
                st.session_state.used_v_keys = sel_v_keys
                st.success("Matching Complete!")
                
    if "az_match_results" in st.session_state:
        with st.expander("🔍 View Generated Match Keys (Top 50)", expanded=False):
            k_c1, k_c2 = st.columns(2)
            c_preview = st.session_state.az_match_results['client_df']
            v_preview = st.session_state.az_match_results['vendor_df']
            u_c_keys = st.session_state.get("used_c_keys", [])
            u_v_keys = st.session_state.get("used_v_keys", [])
            
            with k_c1:
                st.caption("BigQuery Normalized Keys")
                cols_to_show_c = [c for c in u_c_keys + ['_match_key'] if c in c_preview.columns]
                st.dataframe(c_preview[cols_to_show_c].head(50), use_container_width=True)
            with k_c2:
                st.caption("Azure Normalized Keys")
                cols_to_show_v = [c for c in u_v_keys + ['_match_key'] if c in v_preview.columns]
                st.dataframe(v_preview[cols_to_show_v].head(50), use_container_width=True)

else:
    st.info("👆 Please load a Vendor file from Azure to unlock key configuration.")

# ==========================================
# STEP 9: UI - KPI DASHBOARD & TABBED RESULTS
# ==========================================
if "az_match_results" in st.session_state:
    st.markdown('<div class="section-header">4️⃣ Match Analytics & Results</div>', unsafe_allow_html=True)
    
    res = st.session_state.az_match_results
    summ = res['summary']
    c_res = res['client_df']
    v_res = res['vendor_df']
    total_clients = c_res['Client'].nunique() if 'Client' in c_res.columns else 1
    
    k0, k1, k2, k3, k4, k5 = st.columns(6)
    k0.markdown(f'<div class="metric-box" title="Unique clients active in this filtered match"><div class="metric-val">{total_clients}</div><div class="metric-lbl">Active Clients</div></div>', unsafe_allow_html=True)
    k1.markdown(f'<div class="metric-box" title="Distinct count of unique keys expected based on BQ filter"><div class="metric-val">{summ["total_bq_expected"]:,}</div><div class="metric-lbl">BQ Expected (Unique)</div></div>', unsafe_allow_html=True)
    k2.markdown(f'<div class="metric-box" title="Distinct count of keys successfully found in both datasets"><div class="metric-val" style="color:#4ade80;">{summ["matched_skus"]:,}</div><div class="metric-lbl">Successfully Matched</div></div>', unsafe_allow_html=True)
    k3.markdown(f'<div class="metric-box" title="Distinct count of keys expected in BQ but NOT found in Azure"><div class="metric-val" style="color:#f87171;">{summ["missing_in_azure"]:,}</div><div class="metric-lbl">Missing in Azure</div></div>', unsafe_allow_html=True)
    k4.markdown(f'<div class="metric-box" title="Distinct count of keys found in Azure but NOT expected in BQ scope"><div class="metric-val" style="color:#a78bfa;">{summ["extra_in_azure"]:,}</div><div class="metric-lbl">Extra in Azure</div></div>', unsafe_allow_html=True)
    k5.markdown(f'<div class="metric-box" title="Percentage of BQ expected keys that were matched"><div class="metric-val" style="color:#fbbf24;">{summ["match_rate"]:.1f}%</div><div class="metric-lbl">Overall Match Rate</div></div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    if 'Client' in c_res.columns:
        st.markdown("##### 🏢 Client-Wise Breakdown")
        
        client_stats = []
        for client_name, group in c_res.groupby('Client', observed=True):
            expected = group['_match_key'].nunique()
            matched = group[group['Match_Status'] == 'Matched in Azure']['_match_key'].nunique()
            missing = group[group['Match_Status'] == 'Missing in Azure']['_match_key'].nunique()
            match_rate = (matched / expected * 100) if expected > 0 else 0.0
            
            client_stats.append({
                "Client Name": client_name,
                "Expected (Unique SKUs)": expected,
                "Successfully Matched": matched,
                "Missing in Azure": missing,
                "Match Rate": f"{match_rate:.1f}%"
            })
            
        client_summary_df = pd.DataFrame(client_stats)
        st.dataframe(client_summary_df, use_container_width=True, hide_index=True)
        st.markdown("<br>", unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs(["❌ Missing in Azure", "✅ Matched in Both", "➕ Extra in Azure (Vendor)", "📦 Full Data Extract Downloads"])
    
    with tab1:
        st.markdown("### Missing SKUs (Action Required)")
        st.caption("Expected in BigQuery but absent from the Azure file. Data is de-duplicated by match key.")
        missing_client = c_res[c_res['Match_Status'] == 'Missing in Azure'].drop(columns=['_match_key'])
        if not missing_client.empty:
            with st.expander("👀 View Table (Missing in Azure)", expanded=True):
                display_table(missing_client, key="missing_az_tbl", height=400)
        else:
            st.success("🎉 All expected BigQuery SKUs were successfully found!")

    with tab2:
        st.markdown("### Matched SKUs")
        st.caption("Successfully matched across both BigQuery and Azure.")
        matched_client = c_res[c_res['Match_Status'] == 'Matched in Azure'].drop(columns=['_match_key'])
        if not matched_client.empty:
            with st.expander("👀 View Table (Matched Records)", expanded=False):
                display_table(matched_client, key="matched_az_tbl", height=400)
        else:
            st.warning("No records matched. Check your key mapping.")
            
    with tab3:
        st.markdown("### Extra SKUs")
        st.caption("Provided by Vendor in Azure, but not expected based on current BQ filters. Data is de-duplicated by match key.")
        extra_vendor = v_res[v_res['Match_Status'] == 'Extra in Azure (Vendor)'].drop(columns=['_match_key'])
        if not extra_vendor.empty:
            with st.expander("👀 View Table (Extra in Azure)", expanded=True):
                display_table(extra_vendor, key="extra_az_tbl", height=400)
        else:
            st.info("No extra SKUs crawled outside the expected scope.")
            
    with tab4:
        st.markdown("### 📥 Download Complete Datasets")
        st.caption("Generate full CSV or Excel exports containing all rows and match statuses. De-duplicated keys ensure counts match KPIs.")
        
        d1, d2 = st.columns(2)
        
        c_export = c_res.drop(columns=['_match_key']) if not c_res.empty else pd.DataFrame(columns=['No Data'])
        v_export = v_res.drop(columns=['_match_key']) if not v_res.empty else pd.DataFrame(columns=['No Data'])
        
        csv_data = c_export.to_csv(index=False).encode('utf-8')
        d1.download_button("⬇️ Download BQ Client Match Results (CSV)", data=csv_data, file_name="bq_client_match_results.csv", mime="text/csv", use_container_width=True)

        if OPENPYXL_AVAILABLE:
            out = io.BytesIO()
            try:
                with pd.ExcelWriter(out, engine='openpyxl') as writer:
                    c_export.to_excel(writer, sheet_name='BQ Scope Output', index=False)
                    v_export.to_excel(writer, sheet_name='Azure Vendor Output', index=False)
                out.seek(0)
                d2.download_button("⬇️ Download Complete Multi-Sheet Report (Excel)", data=out.getvalue(), file_name="azure_bq_complete_report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            except Exception as e:
                d2.error(f"Excel generation failed: {e}")