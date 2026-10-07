# Enterprise Multi-Client E-commerce Deliverables & Validation Suite

A high-performance, fully optimized multi-page Streamlit application built for tracking e-commerce deliverables, promotions, pricing, data health, and reconciliation across multiple clients (Abbott, Henkel, Kenvue, Stada, and dynamic additions).

## Project Structure
- `app.py`: Main router and configuration hub (includes Google Sheet sync & settings).
- `utils.py`: Centralized BigQuery data loaders, caching utilities, URL generators, and reconciliation logic.
- `loading_ui.py`: Enterprise loading UI with step checklists, live record counts, and memory usage.
- `pages/Home_Dashboard.py`: Cross-client overview, validation summary, pivots, and top 10 lists.
- `pages/Weekly_Deliverables.py`: Weekly SKU movement, pricing, outliers, trends, data health, and CSV/Excel/PDF exports.
- `pages/Daily_Deliverables.py`: Daily Day-over-Day analysis, DoD comparison, calendar heatmap, and custom chart builder.

## Quick Start
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application:
   ```bash
   streamlit run app.py
   ```
