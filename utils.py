"""
utils.py
───────────────────────────────────────────────────────────────────────────
Enterprise Data Engine & Multi-Client Synchronization Utilities.
- Auto-locates powebijson.json across all project paths.
- Step-by-step verified BigQuery loader without background thread context loss.
- Non-blocking SQL Server queries with 8s connection timeout.
- Fully unified helper functions for all child pages.
- Session-cached Promotional Analysis (PA) data support.
"""

from __future__ import annotations

import datetime as dt
import html as _html_lib
import itertools
import json
import os
import re
import sys
import time
import urllib.parse
from typing import Any, Callable

from dotenv import load_dotenv
import numpy as np
import pandas as pd
import sqlalchemy as sa
import streamlit as st

load_dotenv()

_SS_BQ_SCOPE = "_bq_master_scope"
_SS_BQ_AUDIT = "_bq_deliverable_audit"
_SS_EMAIL_RECON = "_bq_email_reconciliation"
_SS_PA_DATA = "_bq_pa_data"  # 👈 Dedicated session cache for Promotional Analysis (PA) data
_SS_CLIENT_DATA = "_session_client_data"
_PRIMARY_TEXT_CACHE: dict[str, str] = {}


def clean_id(v: Any) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "000000"
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return "000000"
    try:
        if s.endswith(".0"):
            s = s[:-2]
        fl = float(s)
        res = str(int(fl)) if fl == int(fl) else s
        return res.zfill(6)
    except Exception:
        return s.zfill(6)


def extract_primary_text(val: Any) -> str:
    if val is None or pd.isna(val):
        return ""

    if isinstance(val, (list, tuple)):
        return extract_primary_text(val[0]) if len(val) > 0 else ""

    if isinstance(val, dict):
        for key in ["name", "Name", "brand_name", "BrandName", "product_name", "ProductName", "id", "Id", "ID", "value"]:
            if key in val and val[key]:
                return str(val[key]).strip()
        for v in val.values():
            if v:
                return str(v).strip()
        return ""

    s_val = str(val).strip()
    if not s_val or s_val.lower() in ["nan", "none", "null", "[]", "{}"]:
        return ""

    if s_val in _PRIMARY_TEXT_CACHE:
        return _PRIMARY_TEXT_CACHE[s_val]

    result = s_val
    if (s_val.startswith("{") and s_val.endswith("}")) or (s_val.startswith("[") and s_val.endswith("]")):
        try:
            parsed = json.loads(s_val)
            result = extract_primary_text(parsed)
            _PRIMARY_TEXT_CACHE[s_val] = result
            return result
        except Exception:
            pass

    match = re.search(r'["\'](?:name|brand_name|BrandName|product_name|ProductName|id|Id)["\']\s*:\s*["\']?([^"\'},\]]+)', s_val)
    if match:
        result = match.group(1).strip()
        _PRIMARY_TEXT_CACHE[s_val] = result
        return result

    if "," in s_val:
        result = s_val.split(",")[0].strip()

    _PRIMARY_TEXT_CACHE[s_val] = result
    return result


def find_service_account_path() -> str | None:
    """Finds powebijson.json across all common relative paths."""
    candidates = [
        "powebijson.json",
        os.path.join(os.getcwd(), "powebijson.json"),
        os.path.join(os.path.dirname(__file__), "powebijson.json"),
        os.path.join(os.path.dirname(__file__), "..", "powebijson.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "powebijson.json"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def require_credentials() -> None:
    if not st.session_state.get("credentials_set", False):
        if not st.session_state.get("project_id"):
            st.session_state["project_id"] = "clicflyer-c7f5e"
        st.session_state["credentials_set"] = True


def log_telemetry_event(source_type: str, task_name: str, latency: float, row_count: int, status: str = "Success") -> None:
    log_store = st.session_state.setdefault("telemetry_logs", [])
    log_store.append({
        "Timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Engine": source_type,
        "Query / Task": task_name,
        "Rows Fetched": f"{row_count:,}",
        "Latency": f"{latency:.2f}s",
        "RawSeconds": latency,
        "Status": "✅ " + status if status == "Success" else "⚠️ " + status,
    })


def get_cache_stats() -> dict[str, Any]:
    total_bytes = 0
    cached_tables: list[dict[str, Any]] = []

    store = st.session_state.get(_SS_CLIENT_DATA, {}).get("client_data", {})
    if isinstance(store, dict):
        for name, df in store.items():
            if isinstance(df, pd.DataFrame):
                mem = int(df.memory_usage(deep=True).sum())
                total_bytes += mem
                cached_tables.append({"source": f"Client: {name}", "rows": len(df), "bytes": mem})

    master_keys = [
        _SS_BQ_SCOPE, _SS_BQ_AUDIT, _SS_EMAIL_RECON, _SS_PA_DATA,
        "master_sql_df", "master_scope_df", "master_gsheet_df",
        "_sku_active_df", "app_data_cache"
    ]
    for key in master_keys:
        val = st.session_state.get(key)
        if isinstance(val, pd.DataFrame) and not val.empty:
            mem = int(val.memory_usage(deep=True).sum())
            total_bytes += mem
            cached_tables.append({"source": f"Master: {key}", "rows": len(val), "bytes": mem})

    total_bytes += sys.getsizeof(_PRIMARY_TEXT_CACHE)

    return {
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "total_bytes": total_bytes,
        "table_count": len(cached_tables),
        "breakdown": cached_tables,
    }


def clear_all_caches() -> None:
    try:
        st.cache_data.clear()
        st.cache_resource.clear()
    except Exception:
        pass

    _PRIMARY_TEXT_CACHE.clear()

    flush_keys = [
        _SS_CLIENT_DATA, _SS_BQ_SCOPE, _SS_BQ_AUDIT, _SS_EMAIL_RECON, _SS_PA_DATA,
        "app_data_cache", "master_sql_df", "master_scope_df", "master_gsheet_df",
        "_sku_active_df", "cached_gsheet_df", "uploaded_custom_df", "_data_cache",
        "telemetry_logs", "last_fetch_duration"
    ]
    for k in flush_keys:
        st.session_state.pop(k, None)


# ══════════════════════════════════════════════════════════════════════════════
# BIGQUERY CLIENT
# ══════════════════════════════════════════════════════════════════════════════

def get_bq_client():
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        sa_json = st.session_state.get("service_account_json")
        if sa_json:
            info = json.loads(sa_json) if isinstance(sa_json, str) else sa_json
            creds = service_account.Credentials.from_service_account_info(info)
            project = st.session_state.get("project_id", info.get("project_id", "clicflyer-c7f5e"))
            return bigquery.Client(credentials=creds, project=project)

        key_path = find_service_account_path()
        if key_path:
            creds = service_account.Credentials.from_service_account_file(key_path)
            with open(key_path, "r") as f:
                data = json.load(f)
            proj = data.get("project_id", "clicflyer-c7f5e")
            return bigquery.Client(credentials=creds, project=proj)

        return bigquery.Client(project=st.session_state.get("project_id", "clicflyer-c7f5e"))
    except Exception as e:
        st.error(f"BigQuery Connection Error: {e}")
        return None


def run_query_cached(sql: str) -> pd.DataFrame:
    client = get_bq_client()
    if client is None:
        return pd.DataFrame()
    try:
        return client.query(sql).to_dataframe()
    except Exception as e:
        st.error(f"BigQuery Execution Error: {e}")
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# SQL QUERIES DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

Daily_Deliverables = """
SELECT DISTINCT
    id, CountryName, Ecom_Source,
    SAFE_CAST(Data_ExtractionDate AS DATE) AS Data_ExtractionDate,
    Ecom_Desc_Name, PromoMechanicGroup,
    COALESCE(promoprice_calculated, 0) AS Ecom_PromoPrice,
    Ecom_RegularPrice, Ecom_Discount_Desc, Ecom_ImageUrl, Ecom_WebUrl,
    COALESCE(discount_calculated, 0) AS Ecom_Discount,
    ProductName, BrandName, PackSize,
    CONCAT(COALESCE(BrandName,''), '|', COALESCE(ProductName,''), '|', COALESCE(PackSize,'')) AS Ecom_SKU,
    weekvar AS weeknum, BrandFlag, 'Abbott' AS Client
FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Abbott`
"""

Weekly_Deliverables = """SELECT DISTINCT
    id, CountryName, Ecom_Source, Ecom_Desc_Name,
    SAFE_CAST(Data_ExtractionDate AS DATE) AS Data_ExtractionDate,
    PromoMechanicGroup, Ecom_PromoPrice, Ecom_RegularPrice,
    Ecom_Discount, Ecom_Discount_Desc, Ecom_WebUrl,
    CAST(Ecom_ImageUrl AS STRING) AS Ecom_ImageUrl,
    Brandid, BrandName, ProductId, ProductName, PacksizeId, PackSize,
    CONCAT(COALESCE(BrandName,''), '|', COALESCE(ProductName,''), '|', COALESCE(PackSize,'')) AS Ecom_SKU,
    weeknum, BrandFlag, 'Henkel' AS Client
FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Henkel`
UNION ALL
SELECT DISTINCT
    id, CountryName, Ecom_Source, Ecom_Desc_Name,
    SAFE_CAST(Data_ExtractionDate AS DATE) AS Data_ExtractionDate,
    PromoMechanicGroup, Ecom_PromoPrice, Ecom_RegularPrice,
    Ecom_Discount, Ecom_Discount_Desc, Ecom_WebUrl,
    CAST(Ecom_ImageUrl AS STRING) AS Ecom_ImageUrl,
    Brandid, BrandName, ProductId, ProductName, PacksizeId, PackSize,
    CONCAT(COALESCE(BrandName,''), '|', COALESCE(ProductName,''), '|', COALESCE(PackSize,'')) AS Ecom_SKU,
    weeknum, BrandFlag, 'Kenvue' AS Client
FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Kenvue`
UNION ALL
SELECT DISTINCT
    id, CountryName, Ecom_Source, Ecom_Desc_Name,
    SAFE_CAST(Data_ExtractionDate AS DATE) AS Data_ExtractionDate,
    PromoMechanicGroup, Ecom_PromoPrice, Ecom_RegularPrice,
    Ecom_Discount, Ecom_Discount_Desc, Ecom_WebUrl,
    CAST(Ecom_ImageUrl AS STRING) AS Ecom_ImageUrl,
    Brandid, BrandName, ProductId, Product AS ProductName, PacksizeId, PackSize,
    CONCAT(COALESCE(BrandName,''), '|', COALESCE(Product,''), '|', COALESCE(PackSize,'')) AS Ecom_SKU,
    weeknum, BrandFlag, 'Stada' AS Client
FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Stada`
UNION ALL
SELECT DISTINCT
    id, CountryName, Ecom_Source, Ecom_Desc_Name,
    SAFE_CAST(Data_ExtractionDate AS DATE) AS Data_ExtractionDate,
    PromoMechanicGroup, Ecom_PromoPrice, Ecom_RegularPrice,
    Ecom_Discount, Ecom_Discount_Desc, Ecom_WebUrl,
    CAST(Ecom_ImageUrl AS STRING) AS Ecom_ImageUrl,
    Brandid, BrandName, ProductId, ProductName AS ProductName, PacksizeId, PackSize,
    CONCAT(COALESCE(BrandName,''), '|', COALESCE(ProductName,''), '|', COALESCE(PackSize,'')) AS Ecom_SKU,
    weeknum, BrandFlag, 'Bayara' AS Client
FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Bayara`;
"""

BQ_MASTER_SCOPE_QUERY = """
WITH
-- 1. KENVUE SCOPE
Kenvue_Scope AS (
  SELECT DISTINCT CountryName, CAST(BrandId AS STRING) AS BrandId, BrandName,
                  CAST(ProductId AS STRING) AS ProductId, ProductName,
                  COALESCE(BrandFlag, 'Competition') AS BrandFlag
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.Ecom_Deliverable_Scope_Kenvue`
),
Kenvue_CountrySource AS (
  SELECT DISTINCT CountryName, Ecom_Source 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Kenvue`
),
Kenvue_FinalScope AS (
  SELECT 'Kenvue' AS Client, s.CountryName, cs.Ecom_Source, s.BrandId, s.BrandName, s.ProductId, s.ProductName, s.BrandFlag
  FROM Kenvue_Scope s INNER JOIN Kenvue_CountrySource cs ON s.CountryName = cs.CountryName
),

-- 2. STADA SCOPE
Stada_BrandFlag_Mapping AS (
  SELECT DISTINCT CAST(BrandId AS STRING) AS BrandId, BrandFlag
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Stada` WHERE BrandFlag IS NOT NULL
),
Stada_Scope AS (
  SELECT DISTINCT s.CountryName, CAST(s.BrandId AS STRING) AS BrandId, s.BrandName,
                  CAST(s.ProductId AS STRING) AS ProductId, s.ProductName,
                  COALESCE(bf.BrandFlag, 'Competition') AS BrandFlag
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.Ecom_Deliverable_Scope_Stada` s
  LEFT JOIN Stada_BrandFlag_Mapping bf ON CAST(s.BrandId AS STRING) = bf.BrandId
),
Stada_CountrySource AS (
  SELECT DISTINCT CountryName, Ecom_Source FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Stada`
),
Stada_FinalScope AS (
  SELECT 'Stada' AS Client, s.CountryName, cs.Ecom_Source, s.BrandId, s.BrandName, s.ProductId, s.ProductName, s.BrandFlag
  FROM Stada_Scope s INNER JOIN Stada_CountrySource cs ON s.CountryName = cs.CountryName
),

-- 3. HENKEL SCOPE
Henkel_ExpectedBrands AS (
  SELECT DISTINCT CAST(BrandID AS STRING) AS BrandId, BrandName, CAST(ProductID AS STRING) AS ProductId, ProductName, 'My Brand' AS BrandFlag
  FROM `clicflyer-c7f5e.AnalyticSolutions.PromoAnalysis_tbl_Henkel` WHERE Brands_for_monthly_File = 'Yes'
),
Henkel_ExpectedCountrySource AS (
  SELECT DISTINCT CountryName, Ecom_Source FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Henkel`
),
Henkel_FinalScope AS (
  SELECT 'Henkel' AS Client, cs.CountryName, cs.Ecom_Source, b.BrandId, b.BrandName, b.ProductId, b.ProductName, b.BrandFlag
  FROM Henkel_ExpectedBrands b CROSS JOIN Henkel_ExpectedCountrySource cs
),

-- 4. BAYARA SCOPE (NEW WITH FIXED COLUMNS)
Bayara_Scope AS (
  SELECT DISTINCT CountryName, 
                  CAST(Brand_Id AS STRING) AS BrandId, BrandName,
                  CAST(Product_Id AS STRING) AS ProductId, Product_Name AS ProductName,
                  COALESCE(BrandFlag, 'Competition') AS BrandFlag
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.Ecom_Deliverable_Scope_Bayara`
),
Bayara_CountrySource AS (
  SELECT DISTINCT CountryName, Ecom_Source 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Bayara`
),
Bayara_FinalScope AS (
  SELECT 'Bayara' AS Client, s.CountryName, cs.Ecom_Source, s.BrandId, s.BrandName, s.ProductId, s.ProductName, s.BrandFlag
  FROM Bayara_Scope s INNER JOIN Bayara_CountrySource cs ON s.CountryName = cs.CountryName
)

-- FINAL UNION
SELECT Client, CountryName, Ecom_Source, BrandId, BrandName, ProductId, ProductName, BrandFlag,
       CASE WHEN BrandFlag = 'My Brand' THEN CONCAT(Client, ' My Brand') ELSE BrandFlag END AS BrandFlag_New
FROM Kenvue_FinalScope

UNION ALL
SELECT Client, CountryName, Ecom_Source, BrandId, BrandName, ProductId, ProductName, BrandFlag,
       CASE WHEN BrandFlag = 'My Brand' THEN CONCAT(Client, ' My Brand') ELSE BrandFlag END AS BrandFlag_New
FROM Stada_FinalScope

UNION ALL
SELECT Client, CountryName, Ecom_Source, BrandId, BrandName, ProductId, ProductName, BrandFlag,
       CASE WHEN BrandFlag = 'My Brand' THEN CONCAT(Client, ' My Brand') ELSE BrandFlag END AS BrandFlag_New
FROM Henkel_FinalScope

UNION ALL
SELECT Client, CountryName, Ecom_Source, BrandId, BrandName, ProductId, ProductName, BrandFlag,
       CASE WHEN BrandFlag = 'My Brand' THEN CONCAT(Client, ' My Brand') ELSE BrandFlag END AS BrandFlag_New
FROM Bayara_FinalScope;
"""

Email_Reconciliation_Query = """
WITH
Kenvue_Scope AS (
  SELECT DISTINCT CountryName, CAST(BrandId AS STRING) AS BrandId, BrandName, CAST(ProductId AS STRING) AS ProductId, ProductName 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.Ecom_Deliverable_Scope_Kenvue`
),
Kenvue_CountrySource AS (
  SELECT DISTINCT CountryName, Ecom_Source 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Kenvue`
),
Kenvue_Available AS (
  SELECT CountryName, Ecom_Source, CAST(BrandId AS STRING) AS BrandId, CAST(ProductId AS STRING) AS ProductId, COUNT(1) AS RecordCount 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Kenvue` 
  GROUP BY CountryName, Ecom_Source, BrandId, ProductId
),
Kenvue_Final AS (
  SELECT 'Kenvue' AS Client, s.CountryName, cs.Ecom_Source, s.BrandId, s.BrandName, s.ProductId, s.ProductName, COALESCE(a.RecordCount, 0) AS RecordCount
  FROM Kenvue_Scope s 
  INNER JOIN Kenvue_CountrySource cs ON s.CountryName = cs.CountryName
  LEFT JOIN Kenvue_Available a ON a.CountryName = s.CountryName AND a.Ecom_Source = cs.Ecom_Source AND a.BrandId = s.BrandId AND a.ProductId = s.ProductId
),

Stada_Scope AS (
  SELECT DISTINCT s.CountryName, CAST(s.BrandId AS STRING) AS BrandId, s.BrandName, CAST(s.ProductId AS STRING) AS ProductId, s.ProductName 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.Ecom_Deliverable_Scope_Stada` s
),
Stada_CountrySource AS (
  SELECT DISTINCT CountryName, Ecom_Source 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Stada`
),
Stada_Available AS (
  SELECT CountryName, Ecom_Source, CAST(BrandId AS STRING) AS BrandId, CAST(ProductId AS STRING) AS ProductId, COUNT(1) AS RecordCount 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Stada` 
  GROUP BY CountryName, Ecom_Source, BrandId, ProductId
),
Stada_Final AS (
  SELECT 'Stada' AS Client, s.CountryName, cs.Ecom_Source, s.BrandId, s.BrandName, s.ProductId, s.ProductName, COALESCE(a.RecordCount, 0) AS RecordCount
  FROM Stada_Scope s 
  INNER JOIN Stada_CountrySource cs ON s.CountryName = cs.CountryName
  LEFT JOIN Stada_Available a ON a.CountryName = s.CountryName AND a.Ecom_Source = cs.Ecom_Source AND a.BrandId = s.BrandId AND a.ProductId = s.ProductId
),

Bayara_Scope AS (
  SELECT DISTINCT s.CountryName, CAST(s.Brand_Id AS STRING) AS BrandId, s.BrandName, CAST(s.Product_Id AS STRING) AS ProductId, s.Product_Name as ProductName
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.Ecom_Deliverable_Scope_Bayara` s
),
Bayara_CountrySource AS (
  SELECT DISTINCT CountryName, Ecom_Source 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Bayara`
),
Bayara_Available AS (
  SELECT CountryName, Ecom_Source, CAST(BrandId AS STRING) AS BrandId, CAST(ProductId AS STRING) AS ProductId, COUNT(1) AS RecordCount 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Bayara` 
  GROUP BY CountryName, Ecom_Source, BrandId, ProductId
),
Bayara_Final AS (
  SELECT 'Bayara' AS Client, s.CountryName, cs.Ecom_Source, s.BrandId, s.BrandName, s.ProductId, s.ProductName, COALESCE(a.RecordCount, 0) AS RecordCount
  FROM Bayara_Scope s 
  INNER JOIN Bayara_CountrySource cs ON s.CountryName = cs.CountryName
  LEFT JOIN Bayara_Available a ON a.CountryName = s.CountryName AND a.Ecom_Source = cs.Ecom_Source AND a.BrandId = s.BrandId AND a.ProductId = s.ProductId
),

Henkel_ExpectedBrands AS (
  SELECT DISTINCT CAST(BrandID AS STRING) AS BrandID, BrandName, CAST(ProductID AS STRING) AS ProductID, ProductName 
  FROM `clicflyer-c7f5e.AnalyticSolutions.PromoAnalysis_tbl_Henkel` 
  WHERE Brands_for_monthly_File = 'Yes'
),
Henkel_ExpectedCountrySource AS (
  SELECT DISTINCT CountryName, Ecom_Source 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Henkel`
),
Henkel_ExpectedCombination AS (
  SELECT b.BrandID, b.BrandName, b.ProductID, b.ProductName, cs.CountryName, cs.Ecom_Source 
  FROM Henkel_ExpectedBrands b 
  CROSS JOIN Henkel_ExpectedCountrySource cs
),
Henkel_Available AS (
  SELECT CountryName, Ecom_Source, CAST(BrandID AS STRING) AS BrandID, CAST(ProductID AS STRING) AS ProductID, COUNT(1) AS RecordCount 
  FROM `clicflyer-c7f5e.Ecomm_AnalyticSolutions.EcomAnalysis_tbl_Henkel` 
  GROUP BY CountryName, Ecom_Source, BrandID, ProductID
),
Henkel_Final AS (
  SELECT 'Henkel' AS Client, e.CountryName, e.Ecom_Source, e.BrandID AS BrandId, e.BrandName, e.ProductID AS ProductId, e.ProductName, COALESCE(a.RecordCount, 0) AS RecordCount
  FROM Henkel_ExpectedCombination e 
  LEFT JOIN Henkel_Available a ON e.CountryName = a.CountryName AND e.Ecom_Source = a.Ecom_Source AND e.BrandID = a.BrandID AND e.ProductID = a.ProductID
)

SELECT Client, CountryName, Ecom_Source, BrandId, BrandName, ProductId, ProductName, RecordCount FROM Kenvue_Final
UNION ALL 
SELECT Client, CountryName, Ecom_Source, BrandId, BrandName, ProductId, ProductName, RecordCount FROM Stada_Final
UNION ALL 
SELECT Client, CountryName, Ecom_Source, BrandId, BrandName, ProductId, ProductName, RecordCount FROM Bayara_Final
UNION ALL 
SELECT Client, CountryName, Ecom_Source, BrandId, BrandName, ProductId, ProductName, RecordCount FROM Henkel_Final;
"""

PA_Data = """
SELECT DISTINCT
    Offerid , CountryName, RetailerName, OfferName ,
    SAFE_CAST(OfferStartDate AS DATE) AS OfferStartDate,SAFE_CAST(OfferendDate AS DATE) AS OfferendDate,
    PromoMechanicGroup, PromoPrice, RegularPrice,
    Discount,
    CAST(OfferImageURL AS STRING) AS OfferImageURL,
    Brandid, BrandName, ProductId, ProductName, PacksizeId, PackSize,
    CONCAT(COALESCE(BrandName,''), '|', COALESCE(ProductName,''), '|', COALESCE(PackSize,'')) AS Ecom_SKU,
    weeknum, BrandFlag, 'Henkel' AS Client
FROM `clicflyer-c7f5e.AnalyticSolutions.PromoAnalysis_tbl_Henkel` WHERE DATE(OfferStartDate) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH)
UNION ALL
SELECT DISTINCT
     Offerid , CountryName, RetailerName, OfferName ,
    SAFE_CAST(OfferStartDate AS DATE) AS OfferStartDate,SAFE_CAST(OfferendDate AS DATE) AS OfferendDate,
    PromoMechanicGroup, PromoPrice, RegularPrice,
    Discount,
    CAST(OfferImageURL AS STRING) AS OfferImageURL,
    Brandid, BrandName, ProductId, ProductName, PacksizeId, PackSize,
    CONCAT(COALESCE(BrandName,''), '|', COALESCE(ProductName,''), '|', COALESCE(PackSize,'')) AS Ecom_SKU,
    weeknum, BrandFlag, 'Kenvue' AS Client
FROM `clicflyer-c7f5e.AnalyticSolutions.PromoAnalysis_tbl_Kenvue` WHERE DATE(OfferStartDate) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH)
UNION ALL
SELECT DISTINCT
     Offerid , CountryName, RetailerName, OfferName ,
    SAFE_CAST(OfferStartDate AS DATE) AS OfferStartDate,SAFE_CAST(OfferendDate AS DATE) AS OfferendDate,
    PromoMechanicGroup, PromoPrice, RegularPrice,
    Discount,
    CAST(OfferImageURL AS STRING) AS OfferImageURL,
    Brandid, CF_BrandName as BrandName, ProductId, Product AS ProductName, PacksizeId, PackSize,
    CONCAT(COALESCE(CF_BrandName,''), '|', COALESCE(Product,''), '|', COALESCE(PackSize,'')) AS Ecom_SKU,
    weeknum, BrandFlag, 'Stada' AS Client
FROM `clicflyer-c7f5e.AnalyticSolutions.PromoAnalysis_tbl_Stada` WHERE DATE(OfferStartDate) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH)
UNION ALL
SELECT DISTINCT
     Offerid , CountryName, RetailerName, OfferName ,
    SAFE_CAST(OfferStartDate AS DATE) AS OfferStartDate,SAFE_CAST(OfferendDate AS DATE) AS OfferendDate,
    PromoMechanicGroup, PromoPrice, RegularPrice,
    Discount,
    CAST(OfferImageURL AS STRING) AS OfferImageURL,
    Brandid, BrandName, ProductId, ProductName AS ProductName, PacksizeId, PackSize,
    CONCAT(COALESCE(BrandName,''), '|', COALESCE(ProductName,''), '|', COALESCE(PackSize,'')) AS Ecom_SKU,
    weeknum, BrandFlag, 'Bayara' AS Client
FROM `clicflyer-c7f5e.AnalyticSolutions.PromoAnalysis_tbl_Bayara` WHERE DATE(OfferStartDate) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH);
"""


# ══════════════════════════════════════════════════════════════════════════════
# SQL SERVER ENGINE (WITH STRICT TIMEOUT)
# ══════════════════════════════════════════════════════════════════════════════

def _get_sql_engine():
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_DATABASE")
    username = os.getenv("DB_USERNAME")
    password = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", "1433")

    if not server or not database or not username:
        return None

    conn_str = (
        f"mssql+pyodbc://{username}:{password}@{server}:{port}/{database}"
        f"?driver=ODBC+Driver+17+for+SQL+Server&login_timeout=8&timeout=25"
    )
    return sa.create_engine(conn_str, pool_pre_ping=True, pool_size=3, max_overflow=5)


def _extract_scope_signature(scope_df: pd.DataFrame | None) -> tuple[tuple[str, str], ...]:
    if scope_df is None or scope_df.empty or not {"CountryName", "Ecom_Source"}.issubset(scope_df.columns):
        return ()
    pairs = (
        scope_df[["CountryName", "Ecom_Source"]]
        .dropna()
        .drop_duplicates()
        .sort_values(by=["CountryName", "Ecom_Source"])
    )
    return tuple((str(r["CountryName"]).strip(), str(r["Ecom_Source"]).strip()) for _, r in pairs.iterrows())


def _build_query_from_pairs(pairs: tuple[tuple[str, str], ...], review_filter: str = "All") -> str:
    filter_clause = ""
    if pairs:
        conditions = []
        for c, s in pairs:
            c_clean = c.replace("'", "''")
            s_clean = s.replace("'", "''")
            conditions.append(f"(EcommerceCountry = '{c_clean}' AND Source = '{s_clean}')")
        filter_clause = "AND (\n        " + " OR\n        ".join(conditions) + "\n    )"

    if not filter_clause:
        filter_clause = """
        AND Source IN (
            'Amazon','Ninja','Talabat','ElGrocer','Tawseel','HungerStation',
            'Snoonu','Drops','Jemia','Noon Minutes','Careem','Nana',
            'Nahdi_promotions','UnitedPharmacy_promotions','Aldawaa_promotions',
            'Lulu','Al Meera','Carrefour'
        )
        """

    review_clause = ""
    if review_filter == "Reviewed Only (Finalreview = 1)":
        review_clause = "AND ISNULL(Finalreview, 0) = 1"
    elif review_filter == "Unreviewed Only (Finalreview = 0)":
        review_clause = "AND ISNULL(Finalreview, 0) = 0"

    return f"""
    SELECT
        id, EcommerceCountry, Source, ISNULL(Finalreview, 0) AS Finalreview,
        MappingStatus, Matched, ecommerceName, EcommercePackSize,
        MatchedBrandid AS Brandid, MatchedProductid AS Productid,
        EcommCategory, EcommSubCategory, Brand as BrandName, Product as ProductName,
        ImageUrl, ReviewStatus, Deliverables, MatchedProducts, MatchedBrands, MatchedPackSizes
    FROM SKU_Master_Partitioned (NOLOCK)
    WHERE ISNULL(isDeleted, 0) = 0
        {review_clause}
        {filter_clause}
    """


def load_sql_sku_master_partition(scope_df: pd.DataFrame | None = None) -> pd.DataFrame:
    t0 = time.perf_counter()
    pairs_sig = _extract_scope_signature(scope_df)
    try:
        engine = _get_sql_engine()
        if engine is None:
            return pd.DataFrame()
        query = _build_query_from_pairs(pairs_sig, review_filter="All")
        df = pd.read_sql(query, con=engine)
        dur = time.perf_counter() - t0
        log_telemetry_event("SQL Server", "SKU_Master_Partitioned Query", dur, len(df), "Success")
        if not df.empty:
            st.session_state["master_sql_df"] = df
        return df
    except Exception as e:
        dur = time.perf_counter() - t0
        log_telemetry_event("SQL Server", "SKU_Master_Partitioned Query", dur, 0, f"Error: {e}")
        return pd.DataFrame()


def get_global_master_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if "master_scope_df" not in st.session_state or st.session_state["master_scope_df"].empty:
        st.session_state["master_scope_df"] = load_client_deliverable_scope()

    if "master_gsheet_df" not in st.session_state or st.session_state["master_gsheet_df"].empty:
        st.session_state["master_gsheet_df"] = load_google_sheet_data()

    sql_df = st.session_state.get("master_sql_df", pd.DataFrame())
    if sql_df.empty:
        scope_ref = st.session_state.get("master_scope_df", pd.DataFrame())
        sql_df = load_sql_sku_master_partition(scope_ref)

    return (
        st.session_state.get("master_scope_df", pd.DataFrame()),
        sql_df,
        st.session_state.get("master_gsheet_df", pd.DataFrame()),
    )


# ══════════════════════════════════════════════════════════════════════════════
# LOADERS & INGESTION CONTRACTS
# ══════════════════════════════════════════════════════════════════════════════

def load_client_deliverable_scope() -> pd.DataFrame:
    t0 = time.perf_counter()
    df_scope = run_query_cached(BQ_MASTER_SCOPE_QUERY)
    dur = time.perf_counter() - t0
    rc = len(df_scope) if isinstance(df_scope, pd.DataFrame) else 0
    log_telemetry_event("BigQuery", "Deliverable Scope Query", dur, rc, "Success" if rc > 0 else "0 Rows")
    st.session_state[_SS_BQ_SCOPE] = df_scope
    return df_scope


def load_google_sheet_data(force_refresh: bool = False) -> pd.DataFrame:
    sheet_id = st.session_state.get("sheet_id", "  ")
    sheet_name = st.session_state.get("sheet_name", "Missing_SKU")
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv;rowLimit:100000&sheet={sheet_name}"
    t0 = time.perf_counter()
    try:
        df = pd.read_csv(csv_url)
        df.columns = [c.strip() for c in df.columns]
        dur = time.perf_counter() - t0
        log_telemetry_event("Google Sheet", f"Sheet Sync: '{sheet_name}'", dur, len(df), "Success")
        st.session_state["cached_gsheet_df"] = df
        return df
    except Exception as e:
        dur = time.perf_counter() - t0
        log_telemetry_event("Google Sheet", f"Sheet Sync: '{sheet_name}'", dur, 0, f"Error: {e}")
        return pd.DataFrame()


def load_email_reconciliation_data(force_refresh: bool = False) -> pd.DataFrame:
    if not force_refresh and _SS_EMAIL_RECON in st.session_state:
        cached_df = st.session_state[_SS_EMAIL_RECON]
        if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
            return cached_df

    t0 = time.perf_counter()
    df = run_query_cached(Email_Reconciliation_Query)
    dur = time.perf_counter() - t0
    rc = len(df) if isinstance(df, pd.DataFrame) else 0
    log_telemetry_event("BigQuery", "Email Reconciliation Query", dur, rc, "Success" if rc > 0 else "0 Rows")
    st.session_state[_SS_EMAIL_RECON] = df
    return df


def load_pa_data(force_refresh: bool = False) -> pd.DataFrame:
    """Loads and session-caches the Promotional Analysis (PA) dataset."""
    if not force_refresh and _SS_PA_DATA in st.session_state:
        cached_df = st.session_state[_SS_PA_DATA]
        if isinstance(cached_df, pd.DataFrame) and not cached_df.empty:
            return cached_df

    t0 = time.perf_counter()
    df = run_query_cached(PA_Data)
    dur = time.perf_counter() - t0
    rc = len(df) if isinstance(df, pd.DataFrame) else 0
    log_telemetry_event("BigQuery", "Promotional Analysis (PA_Data) Query", dur, rc, "Success" if rc > 0 else "0 Rows")
    st.session_state[_SS_PA_DATA] = df
    return df


def load_abbott() -> pd.DataFrame:
    df = run_query_cached(Daily_Deliverables)
    if isinstance(df, pd.DataFrame) and not df.empty:
        df["Client"] = "Abbott"
    return df


def load_henkel_kenvue() -> pd.DataFrame:
    return run_query_cached(Weekly_Deliverables)


def load_all_profiled(status_placeholder: Any = None) -> dict[str, pd.DataFrame]:
    """Reliable step-by-step query execution with live status and timing display."""
    uploaded_df = st.session_state.get("uploaded_custom_df")
    if uploaded_df is not None and not uploaded_df.empty:
        log_telemetry_event("Local CSV", "Custom Dataset Upload", 0.05, len(uploaded_df), "Success")
        return {"custom_upload": uploaded_df}

    result: dict[str, pd.DataFrame] = {}

    # ── Step 1: Weekly Deliverables (Henkel, Kenvue, Stada) ─────────────────
    if status_placeholder:
        status_placeholder.info("⏳ **Step 1/2**: Executing BigQuery Weekly Deliverables Query (Henkel, Kenvue, Stada)...")
    
    t0 = time.perf_counter()
    hk = run_query_cached(Weekly_Deliverables)
    t_hk = time.perf_counter() - t0
    hk_rows = len(hk) if isinstance(hk, pd.DataFrame) else 0

    log_telemetry_event("BigQuery", "Henkel, Kenvue & Stada Query", t_hk, hk_rows, "Success" if hk_rows > 0 else "0 Rows")

    if isinstance(hk, pd.DataFrame) and not hk.empty and "Client" in hk.columns:
        for client_name in sorted(hk["Client"].dropna().unique()):
            key = str(client_name).strip().lower().replace(" ", "_")
            result[key] = hk[hk["Client"] == client_name].copy()
    else:
        for k in ("henkel", "kenvue", "stada"):
            result.setdefault(k, pd.DataFrame())

    # ── Step 2: Abbott Daily Deliverables ───────────────────────────────────
    if status_placeholder:
        status_placeholder.info(f"✅ **Step 1 Finished** in {t_hk:.1f}s ({hk_rows:,} rows)\n\n⏳ **Step 2/2**: Executing Abbott Daily Query...")

    t1 = time.perf_counter()
    abbott_df = run_query_cached(Daily_Deliverables)
    t_ab = time.perf_counter() - t1
    ab_rows = len(abbott_df) if isinstance(abbott_df, pd.DataFrame) else 0

    log_telemetry_event("BigQuery", "Abbott Isolated Query", t_ab, ab_rows, "Success" if ab_rows > 0 else "0 Rows")

    if isinstance(abbott_df, pd.DataFrame) and not abbott_df.empty:
        abbott_df["Client"] = "Abbott"
        result["abbott"] = abbott_df
    else:
        result["abbott"] = pd.DataFrame()

    if status_placeholder:
        status_placeholder.empty()

    return result


def load_all() -> dict[str, pd.DataFrame]:
    return load_all_profiled()


def load_all_cached() -> dict[str, pd.DataFrame]:
    return load_all()


def get_cached_client_data(force_refresh: bool = False, status_placeholder: Any = None) -> dict[str, pd.DataFrame]:
    store = st.session_state.setdefault(_SS_CLIENT_DATA, {})

    if not force_refresh and "client_data" in store:
        existing = store["client_data"]
        total_cached_rows = sum(len(df) for df in existing.values() if isinstance(df, pd.DataFrame))
        if total_cached_rows > 0:
            return {k: v.copy() if isinstance(v, pd.DataFrame) else pd.DataFrame() for k, v in existing.items()}

    data = load_all_profiled(status_placeholder=status_placeholder)
    normalized = {}
    for key, df in data.items():
        normalized[key] = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    store["client_data"] = normalized
    st.session_state["app_data_cache"] = normalized
    return normalized


def get_combined_df(force_refresh: bool = False) -> pd.DataFrame:
    data = get_cached_client_data(force_refresh=force_refresh)
    frames = [d for d in data.values() if d is not None and not d.empty]
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def get_session_cached_value(namespace: str, key: tuple | str, compute_fn: Callable[[], Any], force_refresh: bool = False) -> Any:
    cache = st.session_state.setdefault("_data_cache", {})
    cache_key = ("session_cached_value", namespace, key)
    if not force_refresh and cache_key in cache:
        return cache[cache_key].copy() if isinstance(cache[cache_key], pd.DataFrame) else cache[cache_key]
    val = compute_fn()
    cache[cache_key] = val
    return val.copy() if isinstance(val, pd.DataFrame) else val


def get_frame_fingerprint(df: pd.DataFrame | None) -> tuple:
    if df is None:
        return ("none",)
    return (df.shape, tuple(df.columns))


def display_table(
    frame: pd.DataFrame, 
    default_cols: list | None = None, 
    key: str | None = None, 
    height: int | None = None, 
    styler: Any | None = None
) -> None:
    if frame is None or frame.empty:
        st.dataframe(frame, use_container_width=True, height=height)
        return
    cols = list(frame.columns)
    default_cols = default_cols if default_cols is not None else cols
    sel_key = f"_colsel_{key or 'anon'}"
    selected = st.multiselect("Columns", options=cols, default=[c for c in default_cols if c in cols], key=sel_key)
    if not selected:
        selected = cols
    st.dataframe(frame[selected].reset_index(drop=True), use_container_width=True, height=height)


def build_rowwise_heatmap(df: pd.DataFrame) -> Any:
    return df.style