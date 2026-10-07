from __future__ import annotations

import random
import time
from contextlib import contextmanager
from typing import Optional
import streamlit as st

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

TIPS = [
    "Promo Price should never exceed Regular Price.",
    "A duplicate SKU across sources usually means a mapping issue, not bad data.",
    "NULL Ecommerce Names are the #1 cause of broken product cards.",
    "Country + Source is the safest key for coverage checks.",
]

FUN_FACTS = [
    "Still faster than opening a 2 GB Excel file.",
    "BigQuery is doing heavy lifting so your browser stays fast.",
    "No Excel files were harmed in the making of this dashboard.",
]

def _inject_css_once() -> None:
    if st.session_state.get("_loading_ui_css_injected"):
        return
    st.session_state["_loading_ui_css_injected"] = True
    st.markdown('''
        <style>
        .ld-wrap{
            font-family:'Space Grotesk',sans-serif;
            background:linear-gradient(135deg,#111c35,#0d1829);
            border:1px solid #1e3a5f; border-radius:16px;
            padding:1.4rem 1.6rem; margin:.6rem 0 1.2rem;
            color: #e2e8f0;
        }
        .ld-title{font-size:1.05rem;font-weight:700;color:#e2e8f0;margin-bottom:14px;display:flex;align-items:center;gap:8px;}
        .ld-bar-track{width:100%;height:10px;border-radius:6px;background:rgba(255,255,255,.06);overflow:hidden;}
        .ld-bar-fill{height:100%;border-radius:6px;background:linear-gradient(90deg,#60a5fa,#4ade80);transition:width .35s ease;}
        .ld-pct{font-family:'Space Mono',monospace;font-size:.72rem;color:#94a3b8;margin:6px 0 12px;text-align:right;}
        .ld-current{font-size:.85rem;color:#e2e8f0;margin-bottom:10px;display:flex;align-items:center;gap:8px;}
        .ld-steps{display:flex;flex-direction:column;gap:5px;margin-bottom:12px;}
        .ld-step{font-size:.78rem;display:flex;align-items:center;gap:8px;color:#64748b;}
        .ld-step.ld-done{color:#4ade80;}
        .ld-step.ld-active{color:#e2e8f0;font-weight:600;}
        .ld-card{background:#0d1829;border:1px solid #16294a;border-radius:10px;padding:.7rem .9rem;margin-bottom:12px;}
        .ld-card-title{font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px;}
        .ld-rec-row{display:flex;justify-content:space-between;font-size:.78rem;color:#94a3b8;padding:2px 0;}
        .ld-rec-val{color:#e2e8f0;font-weight:600;}
        .ld-meta{display:flex;gap:16px;flex-wrap:wrap;font-size:.72rem;color:#64748b;margin-bottom:10px;font-family:'Space Mono',monospace;}
        </style>
    ''', unsafe_allow_html=True)

class LoadingUI:
    def __init__(self, title: str = "🚀 Loading Dashboard", steps: Optional[list[str]] = None, show_memory: bool = False) -> None:
        _inject_css_once()
        self.title = title
        self.steps = steps or []
        self.show_memory = show_memory and _HAS_PSUTIL
        self.start_time = time.time()
        self.records: dict[str, object] = {}
        self.current_index = -1
        self.container = st.empty()
        self._last_percent = 0
        self._last_text = "Starting..."
        self._render(0, "Starting...")

    def update(self, percent: int, text: str, records: Optional[dict] = None) -> None:
        if records:
            self.records.update(records)
        self._render(percent, text)

    def step(self, index: int, text: str, percent: Optional[int] = None, records: Optional[dict] = None) -> None:
        self.current_index = index
        if records:
            self.records.update(records)
        if percent is None:
            total = max(len(self.steps), 1)
            percent = int(((index + 1) / total) * 100)
        self._render(percent, text)

    def set_records(self, records: dict) -> None:
        self.records.update(records)
        self._render(self._last_percent, self._last_text)

    @contextmanager
    def timed_step(self, index: int, text: str, percent: Optional[int] = None):
        self.step(index, text, percent=percent)
        t0 = time.time()
        try:
            yield self
        finally:
            pass

    def success(self, message: str = "Dashboard Ready", clear: bool = True, linger: float = 0.5) -> None:
        self.current_index = len(self.steps)
        self._render(100, message, done=True)
        if clear:
            time.sleep(linger)
            self.container.empty()

    def _render(self, percent: int, current_text: str, done: bool = False) -> None:
        percent = max(0, min(100, int(percent)))
        self._last_percent, self._last_text = percent, current_text
        elapsed = time.time() - self.start_time
        
        step_html = ""
        if self.steps:
            parts = []
            for i, s in enumerate(self.steps):
                if done or i < self.current_index:
                    icon, cls = "✅", "ld-done"
                elif i == self.current_index:
                    icon, cls = "⏳", "ld-active"
                else:
                    icon, cls = "⬜", ""
                parts.append(f'<div class="ld-step {cls}">{icon} {s}</div>')
            step_html = f'<div class="ld-steps">{"".join(parts)}</div>'

        rec_html = ""
        if self.records:
            rows = []
            for k, v in self.records.items():
                v_disp = f"{v:,}" if isinstance(v, (int, float)) else str(v)
                rows.append(f'<div class="ld-rec-row"><span>{k}</span><span class="ld-rec-val">{v_disp}</span></div>')
            rec_html = f'<div class="ld-card"><div class="ld-card-title">Records Loaded</div>{"".join(rows)}</div>'

        html = f'''
        <div class="ld-wrap">
          <div class="ld-title">{self.title}</div>
          <div class="ld-bar-track"><div class="ld-bar-fill" style="width:{percent}%"></div></div>
          <div class="ld-pct">{percent}%</div>
          <div class="ld-current">{"✅" if done else "⏳"} {current_text}</div>
          {step_html}
          {rec_html}
          <div class="ld-meta"><span>⏱ Elapsed: {elapsed:.1f}s</span></div>
        </div>
        '''
        self.container.markdown(html, unsafe_allow_html=True)

def load_clients_with_ui(title: str = "🚀 Loading Dashboard", show_memory: bool = False) -> dict:
    from utils_old import get_cached_client_data
    loader = LoadingUI(title=title, steps=["Connecting to BigQuery", "Loading client datasets", "Finalizing dashboard"], show_memory=show_memory)
    loader.step(0, "Connecting to BigQuery...")
    with loader.timed_step(1, "Loading client datasets..."):
        data = get_cached_client_data()
    records = {str(k).capitalize(): len(v) for k, v in data.items() if hasattr(v, "__len__")}
    loader.set_records(records)
    loader.step(2, "Finalizing dashboard...")
    loader.success()
    return data
