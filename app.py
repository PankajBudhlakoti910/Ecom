from __future__ import annotations

import json
import os
import time
from typing import Any

import pandas as pd
import streamlit as st

from utils import (
    clear_all_caches,
    find_service_account_path,
    get_cache_stats,
    get_cached_client_data,
    load_client_deliverable_scope,
    load_google_sheet_data,
    load_sql_sku_master_partition,
    load_pa_data,
    require_credentials,
)

st.set_page_config(
    page_title="Enterprise E-commerce Deliverables Suite",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Space+Mono:wght@400;700&display=swap');
html, body, [class*="css"], .stMarkdown, p, span, label, div, h1, h2, h3 { 
    font-family: 'Space Grotesk', sans-serif; 
}
.stApp { background-color: #0b1329 !important; color: #f8fafc !important; }

section[data-testid="stSidebar"] { 
    background-color: #0f172a !important; 
    border-right: 1px solid #334155; 
}
section[data-testid="stSidebar"] *, 
section[data-testid="stSidebar"] p, 
section[data-testid="stSidebar"] span, 
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stMarkdown { 
    color: #f8fafc !important; 
}

section[data-testid="stSidebar"] input, 
section[data-testid="stSidebar"] textarea, 
section[data-testid="stSidebar"] [data-baseweb="input"] {
    background-color: #1e293b !important;
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}

section[data-testid="stSidebar"] [data-testid="stFileUploader"] {
    background-color: #1e293b !important;
    border: 1px dashed #475569 !important;
    border-radius: 8px;
    padding: 10px;
}
section[data-testid="stSidebar"] [data-testid="stFileUploader"] * {
    color: #f8fafc !important;
}

.main-title { font-size: 2.2rem; font-weight: 700; color: #60a5fa !important; margin-bottom: 0.2rem; }
.sub-title { font-size: 1rem; color: #94a3b8 !important; margin-bottom: 1.5rem; }

.card { 
    background: #1e293b !important; 
    border: 1px solid #334155 !important; 
    border-radius: 12px; 
    padding: 1.25rem 1.5rem; 
    margin-bottom: 1rem; 
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2); 
    color: #f8fafc !important; 
}
.card * { color: #f8fafc !important; }

.telemetry-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.85rem;
    font-family: 'Space Mono', monospace;
    background: #0f172a;
    border: 1px solid #334155;
    color: #38bdf8 !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="main-title">⚡ E-commerce Deliverables & Validation Hub</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Multi-client automated tracking, reconciliation, SQL partitions, and data health suite</div>', unsafe_allow_html=True)

require_credentials()

# ── Sidebar: 1. Google Sheet Sync ────────────────────────────────────────────
st.sidebar.markdown("### ☁️ Google Sheet Sync")
sheet_id = st.sidebar.text_input(
    "Google Sheet ID",
    value=st.session_state.get("sheet_id", " "),
)
sheet_name = st.sidebar.text_input(
    "Sheet Name",
    value=st.session_state.get("sheet_name", "Missing_SKU"),
)
st.session_state["sheet_id"] = sheet_id
st.session_state["sheet_name"] = sheet_name

if st.sidebar.button("🔄 Sync Google Sheet Now", use_container_width=True):
    t0 = time.perf_counter()
    with st.spinner(f"Fetching Google Sheet '{sheet_name}'..."):
        try:
            gsheet_df = load_google_sheet_data(force_refresh=True)
            gsheet_time = time.perf_counter() - t0
            if isinstance(gsheet_df, pd.DataFrame) and not gsheet_df.empty:
                st.session_state["gsheet_data"] = gsheet_df  
                st.sidebar.success(f"✅ Synced {len(gsheet_df):,} rows in {gsheet_time:.2f}s!")
            else:
                st.sidebar.warning("Sheet retrieved empty or connection failed.")
        except Exception as e:
            st.sidebar.error(f"Sheet sync failed: {e}")

st.sidebar.markdown("---")

# ── Sidebar: 2. BigQuery Credentials & Sample Format Export ───────────────────
st.sidebar.markdown("### 🔑 BigQuery Credentials")
uploaded_json = st.sidebar.file_uploader("Upload Service Account JSON", type=["json"], key="bq_sa_upload")
if uploaded_json is not None:
    try:
        sa_info = json.load(uploaded_json)
        st.session_state["service_account_json"] = sa_info
        st.session_state["project_id"] = sa_info.get("project_id", "clicflyer-c7f5e")
        st.session_state["credentials_set"] = True
        clear_all_caches()
        st.sidebar.success("Service account loaded successfully! Caches purged.")
    except Exception as e:
        st.sidebar.error(f"Invalid JSON file: {e}")

# Sample format export for BigQuery JSON
bq_sample_format = {
    "type": "service_account",
    "project_id": "your-gcp-project-id",
    "private_key_id": "abcdef123456...",
    "private_key": "-----BEGIN PRIVATE KEY-----\\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC3...\\n-----END PRIVATE KEY-----\\n",
    "client_email": "service-account@your-project.iam.gserviceaccount.com",
    "client_id": "123456789...",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token"
}
st.sidebar.download_button(
    "📥 Export Sample BQ JSON Format",
    data=json.dumps(bq_sample_format, indent=2),
    file_name="sample_bq_service_account.json",
    mime="application/json",
    use_container_width=True
)

# ── Sidebar: BigQuery Manual Load Button ─────────────────────────────────────
if st.sidebar.button("⚡ Load BigQuery Data Now", use_container_width=True):
    t0 = time.perf_counter()
    with st.spinner("Connecting & executing BigQuery pipelines..."):
        try:
            # Trigger fresh load for client data and PA data
            data_dict = get_cached_client_data(force_refresh=True)
            pa_df = load_pa_data(force_refresh=True)
            bq_time = time.perf_counter() - t0
            
            total_bq_rows = sum(len(df) for df in data_dict.values() if isinstance(df, pd.DataFrame)) + len(pa_df)
            if total_bq_rows > 0:
                st.sidebar.success(f"✅ Loaded {total_bq_rows:,} total rows in {bq_time:.2f}s.")
                st.session_state["app_data_cache"] = data_dict
                st.session_state["last_fetch_duration"] = bq_time
                st.session_state["last_fetch_source"] = "Google BigQuery (Manual Load)"
            else:
                st.sidebar.warning("⚠️ Connected, but returned 0 rows.")
        except Exception as e:
            st.sidebar.error(f"BigQuery load failed: {e}")

st.sidebar.markdown("---")

# ── Sidebar: 3. SQL Server Credentials & Manual Load ─────────────────────────
st.sidebar.markdown("### 🗄️ SQL Partition & Credentials")
uploaded_sql_json = st.sidebar.file_uploader("Upload SQL Config JSON", type=["json"], key="sql_config_upload")
if uploaded_sql_json is not None:
    try:
        sql_info = json.load(uploaded_sql_json)
        os.environ["DB_SERVER"] = sql_info.get("DB_SERVER", "")
        os.environ["DB_DATABASE"] = sql_info.get("DB_DATABASE", "")
        os.environ["DB_USERNAME"] = sql_info.get("DB_USERNAME", "")
        os.environ["DB_PASSWORD"] = sql_info.get("DB_PASSWORD", "")
        os.environ["DB_PORT"] = sql_info.get("DB_PORT", "1433")
        st.sidebar.success("SQL configuration loaded into environment!")
    except Exception as e:
        st.sidebar.error(f"Invalid SQL JSON config: {e}")

# Sample format export for SQL JSON
sql_sample_format = {
    "DB_SERVER": "your-sql-server.database.windows.net",
    "DB_DATABASE": "your_database_name",
    "DB_USERNAME": "your_db_user",
    "DB_PASSWORD": "your_secure_password",
    "DB_PORT": "1433"
}
st.sidebar.download_button(
    "📥 Export Sample SQL JSON Format",
    data=json.dumps(sql_sample_format, indent=2),
    file_name="sample_sql_config.json",
    mime="application/json",
    use_container_width=True
)

# Manual Load Data button for SQL Partition
if st.sidebar.button("🔌 Load SQL Partition Data", use_container_width=True):
    t0 = time.perf_counter()
    with st.spinner("Connecting & executing SKU_Master partition query..."):
        try:
            scope_sample = load_client_deliverable_scope()
            sql_test_df = load_sql_sku_master_partition(scope_sample)
            sql_time = time.perf_counter() - t0
            if isinstance(sql_test_df, pd.DataFrame) and not sql_test_df.empty:
                st.sidebar.success(f"✅ Loaded {len(sql_test_df):,} rows in {sql_time:.2f}s.")
            else:
                st.sidebar.warning("⚠️ Connected, but returned 0 rows or timed out.")
        except Exception as e:
            st.sidebar.error(f"Connection failed: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🧭 Navigation")
st.sidebar.info("Use the multi-page menu to navigate between Home Dashboard, Weekly Deliverables, Daily Deliverables, SKU Master Partition Audit, and Ecom vs PA Reconciliation.")

# ── Overview Card ────────────────────────────────────────────────────────────
st.markdown(
    """
<div class="card">
  <h3>Welcome to the E-commerce Deliverables Portal</h3>
  <p>This suite provides unified tracking across Abbott, Kenvue, Stada, Henkel, and Bayara datasets with real-time Google Sheet synchronization, automated search URL generation, packing-level reconciliation against PA scope tables, dynamic SQL Server partition loading, and high-performance session caching.</p>
</div>
""",
    unsafe_allow_html=True,
)

# ── Cache Management & Live Footprint Console ────────────────────────────────
cache_stats = get_cache_stats()

st.markdown("#### ⚡ Cache Management & Live Footprint")
c_col1, c_col2, c_col3 = st.columns([3, 3, 4])

with c_col1:
    st.metric("Cached Memory Size", f"{cache_stats['total_mb']} MB")
with c_col2:
    st.metric("Cached Tables In-Memory", cache_stats["table_count"])
with c_col3:
    st.write("")
    if st.button("🗑️ Delete All Caches & Force Fresh Reload", use_container_width=True, type="primary"):
        clear_all_caches()
        st.success("All cached tables wiped clean. Pulling fresh dataset...")
        time.sleep(0.5)
        st.rerun()

# ── Data Pipeline Execution Panel ────────────────────────────────────────────
status_placeholder = st.empty()
step_timer_placeholder = st.empty()

has_creds = (
    st.session_state.get("credentials_set", False) 
    or (find_service_account_path() is not None)
)

if not has_creds:
    status_placeholder.warning(
        "⚠️ Status: **Not Initialized** — Please upload BigQuery Service Account JSON or provide 'powebijson.json' to initiate loading."
    )
else:
    data_dict = {}
    fetch_duration = st.session_state.get("last_fetch_duration", 0.0)

    cached_store = st.session_state.get("app_data_cache")
    has_valid_cached_data = (
        isinstance(cached_store, dict) 
        and any(isinstance(df, pd.DataFrame) and not df.empty for df in cached_store.values())
    )

    if has_valid_cached_data:
        data_dict = cached_store
    else:
        try:
            t_start = time.perf_counter()
            data_dict = get_cached_client_data(force_refresh=True, status_placeholder=step_timer_placeholder)
            
            # Load PA Data into session as well
            pa_df = load_pa_data(force_refresh=True)
            
            fetch_duration = time.perf_counter() - t_start
            st.session_state["last_fetch_source"] = "Google BigQuery"

            st.session_state["app_data_cache"] = data_dict
            st.session_state["last_fetch_duration"] = fetch_duration

        except Exception as e:
            step_timer_placeholder.empty()
            status_placeholder.error(f"❌ Data extraction failed: {e}")
            data_dict = {}

    if data_dict:
        total_recs = 0
        total_ram_mb = 0.0
        table_summary = []

        for name, df in data_dict.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                rc = len(df)
                total_recs += rc
                mem = df.memory_usage(deep=True).sum() / (1024 * 1024)
                total_ram_mb += mem
                table_summary.append({
                    "Client / Dataset": str(name),
                    "Status": "✅ Loaded",
                    "Rows Count": f"{rc:,}",
                    "Columns": len(df.columns),
                    "RAM Footprint": f"{mem:.2f} MB",
                })
            else:
                table_summary.append({
                    "Client / Dataset": str(name),
                    "Status": "⚠️ Empty / 0 Rows",
                    "Rows Count": "0",
                    "Columns": 0,
                    "RAM Footprint": "0.00 MB",
                })

        # Append PA Data to table summary for visibility
        pa_cached = st.session_state.get("_bq_pa_data", pd.DataFrame())
        if not pa_cached.empty:
            pa_mem = pa_cached.memory_usage(deep=True).sum() / (1024 * 1024)
            total_ram_mb += pa_mem
            table_summary.append({
                "Client / Dataset": "Promotional Analysis (PA)",
                "Status": "✅ Loaded",
                "Rows Count": f"{len(pa_cached):,}",
                "Columns": len(pa_cached.columns),
                "RAM Footprint": f"{pa_mem:.2f} MB",
            })

        source_info = st.session_state.get("last_fetch_source", "Active Memory")

        status_placeholder.markdown(
            f"""
            <div class="card" style="border-left: 5px solid #10b981 !important;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <span style="font-size: 1.1rem; font-weight: 700; color: #10b981;">✅ Pipeline Status: Ready</span>
                        <div style="font-size: 0.9rem; color: #94a3b8; margin-top: 4px;">
                            Active Source: <b>{source_info}</b>
                        </div>
                    </div>
                    <div>
                        <span class="telemetry-badge">⏱️ Total Pipeline Time: {fetch_duration:.2f}s</span>
                        <span class="telemetry-badge">📦 Datasets: {len(data_dict) + 1}</span>
                        <span class="telemetry-badge">📊 Total Rows: {total_recs + len(pa_cached):,}</span>
                        <span class="telemetry-badge">💾 Memory: ~{total_ram_mb:.1f} MB</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        telemetry_logs = st.session_state.get("telemetry_logs", [])
        if telemetry_logs:
            log_df = pd.DataFrame(telemetry_logs)
            bq_time = log_df[log_df["Engine"] == "BigQuery"]["RawSeconds"].sum()
            sql_time = log_df[log_df["Engine"] == "SQL Server"]["RawSeconds"].sum()
            gsheet_time = log_df[log_df["Engine"] == "Google Sheet"]["RawSeconds"].sum()

            with st.expander("📊 Engine & Query-Wise Performance Telemetry", expanded=True):
                m_col1, m_col2, m_col3 = st.columns(3)
                with m_col1:
                    st.metric("Google BigQuery Total", f"{bq_time:.2f}s", help="Combined latency of Weekly, Daily & PA BigQuery datasets")
                with m_col2:
                    st.metric("SQL Server Total", f"{sql_time:.2f}s" if sql_time > 0 else "0.00s", help="Latency of SKU Partition Queries")
                with m_col3:
                    st.metric("Google Sheet Sync Total", f"{gsheet_time:.2f}s" if gsheet_time > 0 else "0.00s", help="Latency of Google Sheet fetch")

                st.markdown("##### Detailed Query Execution Log")
                display_cols = ["Timestamp", "Engine", "Query / Task", "Rows Fetched", "Latency", "Status"]
                st.dataframe(log_df[display_cols], use_container_width=True, hide_index=True)

        with st.expander("🔍 Inspect Loaded Client Tables, PA & Record Breakdown", expanded=False):
            st.dataframe(pd.DataFrame(table_summary), use_container_width=True, hide_index=True)

            if not pa_cached.empty and 'Client' in pa_cached.columns:
                st.markdown("##### 📊 Client-Wise Promotional Analysis (PA) SKU Count Breakdown")
                pa_client_counts = pa_cached.groupby('Client', observed=True).size().reset_index(name='PA SKU Count')
                st.dataframe(pa_client_counts, use_container_width=True, hide_index=True)