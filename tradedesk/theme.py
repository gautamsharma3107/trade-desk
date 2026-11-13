"""Terminal look: black background, amber accents, monospace numbers, dense tables."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

AMBER = "#ffa028"
GREEN = "#26d07c"
RED = "#ff4d4f"
BLUE = "#4da3ff"
MUTED = "#8a8f98"
BG = "#000000"
PANEL = "#0b0d10"
GRID = "#1c2128"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"], .stApp {{ font-family: 'IBM Plex Sans', sans-serif; }}
.stApp {{ background: {BG}; }}
.block-container {{ padding-top: 2.6rem; padding-bottom: 2rem; max-width: 100%; }}
h1, h2, h3, h4 {{ color: {AMBER} !important; font-family: 'IBM Plex Mono', monospace !important;
  text-transform: uppercase; letter-spacing: .04em; }}
h2 {{ font-size: 1.15rem !important; }} h3 {{ font-size: 1.0rem !important; }}
h4 {{ font-size: .85rem !important; padding: .4rem 0 .2rem 0 !important; }}
[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid {GRID}; border-left: 3px solid {AMBER};
  padding: 6px 10px; border-radius: 2px; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED} !important; font-size: .72rem !important; text-transform: uppercase;
  letter-spacing: .06em; font-family: 'IBM Plex Mono', monospace; }}
[data-testid="stMetricValue"] {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.25rem !important; }}
[data-testid="stMetricDelta"] {{ font-family: 'IBM Plex Mono', monospace; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 0; border-bottom: 1px solid {AMBER}; }}
.stTabs [data-baseweb="tab"] {{ background: {PANEL}; border: 1px solid {GRID}; border-bottom: none; padding: 4px 14px;
  font-family: 'IBM Plex Mono', monospace; text-transform: uppercase; font-size: .8rem; border-radius: 0; }}
.stTabs [aria-selected="true"] {{ background: {AMBER} !important; color: #000 !important; }}
.stTabs [aria-selected="true"] p {{ color: #000 !important; font-weight: 600; }}
[data-testid="stDataFrame"] {{ font-family: 'IBM Plex Mono', monospace; }}
[data-testid="stSidebar"] {{ background: {PANEL}; border-right: 1px solid {GRID}; }}
div[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 2px; }}
.td-bar {{ display: flex; flex-wrap: wrap; gap: 0; border: 1px solid {GRID}; background: {PANEL};
  font-family: 'IBM Plex Mono', monospace; font-size: .78rem; margin-bottom: .6rem; }}
.td-bar .cell {{ padding: 4px 12px; border-right: 1px solid {GRID}; white-space: nowrap; }}
.td-bar .lbl {{ color: {MUTED}; margin-right: 6px; }}
.td-bar .up {{ color: {GREEN}; }} .td-bar .dn {{ color: {RED}; }} .td-bar .amb {{ color: {AMBER}; font-weight: 600; }}
.td-panel {{ border: 1px solid {GRID}; background: {PANEL}; padding: 8px 12px; margin-bottom: 8px;
  font-size: .9rem; line-height: 1.45; }}
.td-panel .k {{ color: {AMBER}; font-family: 'IBM Plex Mono', monospace; font-size: .75rem; text-transform: uppercase; }}
.td-mini {{ width: 100%; border-collapse: collapse; font-family: 'IBM Plex Mono', monospace; font-size: .8rem; }}
.td-mini td {{ padding: 3px 6px; border-bottom: 1px solid {GRID}; }}
.td-mini td.r {{ text-align: right; }}
.td-src {{ color: {MUTED}; font-size: .72rem; font-family: 'IBM Plex Mono', monospace; }}
@media (max-width: 640px) {{ .td-bar .cell {{ padding: 3px 8px; }} }}
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    tmpl = go.layout.Template(pio.templates["plotly_dark"])
    tmpl.layout.update(paper_bgcolor=BG, plot_bgcolor=BG, font=dict(family="IBM Plex Mono, monospace", size=11),
                       colorway=[AMBER, BLUE, "#c792ea", "#7fdbca", "#f78c6c", "#ffd866", "#ff79c6", MUTED],
                       xaxis=dict(gridcolor=GRID, zerolinecolor=GRID), yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
                       margin=dict(l=10, r=10, t=30, b=10))
    pio.templates["terminal"] = tmpl
    pio.templates.default = "terminal"


def color(v: float | None) -> str:
    if v is None or v != v:
        return ""
    return f"color: {GREEN}" if v > 0 else f"color: {RED}" if v < 0 else ""


def bar(cells: list[tuple[str, str, str]]) -> None:
    """A one-line strip of (label, value, css class) cells."""
    html = "".join(f'<span class="cell"><span class="lbl">{lbl}</span><span class="{cls}">{val}</span></span>'
                   for lbl, val, cls in cells)
    st.markdown(f'<div class="td-bar">{html}</div>', unsafe_allow_html=True)


def updown(v: float | None) -> str:
    if v is None or v != v:
        return ""
    return "up" if v > 0 else "dn" if v < 0 else ""
