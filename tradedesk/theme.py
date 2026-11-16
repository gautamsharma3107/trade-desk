"""Apple-style look: system font, soft rounded cards, quiet colours, light and dark appearance.

Colours follow Apple's system palette. Custom HTML uses translucent fills so the
same CSS reads well on both the light and dark Streamlit themes set in
.streamlit/config.toml.
"""
from __future__ import annotations

import re

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Apple system colours (mid tones that read on light and dark backgrounds).
BLUE = "#0A84FF"
GREEN = "#30B158"
RED = "#FF3B30"
ORANGE = "#FF9500"
PURPLE = "#AF52DE"
TEAL = "#30B0C7"
MUTED = "#8E8E93"
ACCENT = BLUE
# Older names, kept so every page keeps working.
AMBER = ORANGE
GRID = "rgba(142,142,147,0.22)"
FILL = "rgba(120,120,128,0.10)"
HIGHLIGHT = "rgba(10,132,255,0.12)"  # row highlight for "your stock" in tables

FONT = ('-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Inter", "Segoe UI", Roboto, '
        '"Helvetica Neue", Arial, sans-serif')

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, [data-testid="stMetricValue"], [data-testid="stSidebar"] {{
  font-family: {FONT} !important; -webkit-font-smoothing: antialiased; }}
.stApp {{ font-variant-numeric: tabular-nums; }}
.block-container {{ padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1240px; }}

/* Headings: sentence case, tight tracking, clear hierarchy */
.stApp h1 {{ font-size: 2rem !important; font-weight: 700 !important; letter-spacing: -0.025em; }}
.stApp h2 {{ font-size: 1.45rem !important; font-weight: 700 !important; letter-spacing: -0.02em;
  padding-top: 1.2rem !important; }}
.stApp h3 {{ font-size: 1.15rem !important; font-weight: 600 !important; letter-spacing: -0.01em;
  padding-top: 1rem !important; }}
.stApp h4 {{ font-size: 1rem !important; font-weight: 600 !important; padding: .6rem 0 .2rem 0 !important; }}

/* Metric tiles */
[data-testid="stMetric"] {{ background: {FILL}; border-radius: 18px; padding: 14px 18px; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED} !important; font-size: .82rem !important; font-weight: 500; }}
[data-testid="stMetricValue"] {{ font-size: 1.6rem !important; font-weight: 600; letter-spacing: -0.02em; }}

/* Cards (bordered containers), expanders, tables */
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{ border-radius: 18px; }}
[data-testid="stExpander"] details {{ border-radius: 14px; }}
[data-testid="stDataFrame"], [data-testid="stTable"] {{ border-radius: 14px; overflow: hidden; }}
[data-testid="stAlert"] > div {{ border-radius: 14px; }}
.stButton button, .stDownloadButton button, .stLinkButton a, [data-testid="stFormSubmitButton"] button {{
  border-radius: 980px !important; font-weight: 500; padding-left: 1.1rem; padding-right: 1.1rem; }}

/* Tabs inside a page: segmented control look */
.stTabs [role="tablist"] {{ gap: 2px; background: {FILL}; padding: 3px; border-radius: 12px;
  width: fit-content; max-width: 100%; overflow-x: auto; border-bottom: none !important; box-shadow: none; }}
.stTabs [role="tab"] {{ height: auto; padding: 6px 14px; border-radius: 9px; background: transparent; }}
.stTabs [role="tab"] p {{ font-size: .88rem; font-weight: 500; }}
.stTabs [role="tab"][aria-selected="true"] {{ background: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,.12); }}
.stTabs [role="tab"][aria-selected="true"] p {{ color: #1d1d1f !important; font-weight: 600; }}
.stTabs .react-aria-SelectionIndicator, .stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {{ display: none !important; }}

/* Top bar: time, market status and indices as soft pills */
.td-bar {{ display: flex; flex-wrap: wrap; gap: 8px; margin: .2rem 0 1rem 0; }}
.td-bar .cell {{ background: {FILL}; border-radius: 12px; padding: 7px 12px; min-width: 84px; line-height: 1.25; }}
.td-bar .lbl {{ display: block; color: {MUTED}; font-size: .72rem; font-weight: 500; }}
.td-bar .val {{ display: block; font-size: .95rem; font-weight: 600; white-space: nowrap; }}
.td-bar .up {{ color: {GREEN}; }} .td-bar .dn {{ color: {RED}; }} .td-bar .amb {{ color: inherit; }}

/* Portfolio summary card */
.td-hero {{ background: {FILL}; border-radius: 22px; padding: 22px 24px; margin: .2rem 0 1rem 0; }}
.td-hero .lbl {{ color: {MUTED}; font-size: .9rem; font-weight: 500; }}
.td-hero .big {{ font-size: 2.6rem; font-weight: 700; letter-spacing: -0.03em; line-height: 1.15; margin: 2px 0 6px 0; }}
.td-hero .row {{ display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 1rem; font-weight: 500; }}
.td-hero .row span.k {{ color: {MUTED}; font-weight: 400; margin-left: 4px; }}
.up {{ color: {GREEN}; }} .dn {{ color: {RED}; }}
.td-stats {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: .6rem; }}
.td-stats > div {{ background: {FILL}; border-radius: 16px; padding: 12px 16px; }}
.td-stats .lbl {{ color: {MUTED}; font-size: .8rem; font-weight: 500; }}
.td-stats .val {{ font-size: 1.3rem; font-weight: 600; letter-spacing: -0.01em; white-space: nowrap; }}
.td-card-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }}
.td-card-head .t {{ font-size: 1.15rem; font-weight: 600; }}
.td-card-head .r {{ text-align: right; white-space: nowrap; }}
.td-phone-only {{ display: none; }}

.td-pill {{ display: inline-block; padding: 2px 10px; border-radius: 980px; font-size: .78rem; font-weight: 600;
  background: {FILL}; margin-left: 6px; vertical-align: middle; }}
.td-pill.sell {{ background: rgba(255,59,48,.14); color: {RED}; }}
.td-pill.review {{ background: rgba(255,149,0,.16); color: #C76E00; }}
.td-pill.hold {{ background: rgba(48,177,88,.14); color: {GREEN}; }}

.td-panel {{ background: {FILL}; border-radius: 14px; padding: 12px 16px; margin-bottom: 10px; font-size: .95rem;
  line-height: 1.5; }}
.td-panel .k {{ color: {MUTED}; font-size: .78rem; font-weight: 600; }}
.td-mini {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
.td-mini td {{ padding: 6px 6px; border-bottom: 1px solid {GRID}; }}
.td-mini td.r {{ text-align: right; }}
.td-src {{ color: {MUTED}; font-size: .78rem; margin-top: .4rem; }}

[data-testid="stSidebar"] h1 {{ font-size: 1.4rem !important; }}
@media (max-width: 640px) {{
  .block-container {{ padding-left: 1rem; padding-right: 1rem; padding-top: 3.5rem; }}
  .td-bar .cell {{ min-width: 0; padding: 6px 10px; }}
  .td-hero .big {{ font-size: 2.1rem; }}
  .td-hero {{ padding: 18px 18px; }}
  .td-stats {{ gap: 8px; }} .td-stats > div {{ padding: 10px 12px; }}
  .td-stats .val {{ font-size: 1rem; }} .td-stats .lbl {{ font-size: .72rem; }}
  .td-phone-only {{ display: block; color: {MUTED}; font-size: .8rem; margin: -.4rem 0 .6rem 0; }}
  [data-testid="stMetricValue"] {{ font-size: 1.35rem !important; }}
}}
</style>
"""

_KEEP = {"FII", "DII", "PCR", "NSE", "BSE", "IST", "P&L", "OI", "MTF", "LTP", "STCG", "LTCG", "F&O", "GST", "STT"}
_SWAP = {"CHG": "Change", "52W": "52-week", "VOL": "Volume"}


def _label(text: str) -> str:
    """'NEAR 52W HIGH (<3%)' -> 'Near 52-week high (<3%)', keeping acronyms like FII."""
    if text != text.upper():
        return text
    words = [w if w in _KEEP else _SWAP.get(w, w.lower()) for w in text.split(" ")]
    out = " ".join(words)
    return re.sub(r"^[a-z]", lambda m: m.group(0).upper(), out)


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        dark = st.context.theme.type == "dark"
    except Exception:  # older Streamlit
        dark = False
    if dark:
        st.markdown("<style>.stTabs [role='tab'][aria-selected='true'] { background: #636366 !important; }"
                    ".stTabs [role='tab'][aria-selected='true'] p { color: #fff !important; }"
                    ".td-pill.review { color: #FF9F0A; }</style>", unsafe_allow_html=True)
    tmpl = go.layout.Template()
    tmpl.layout.update(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                       font=dict(family=FONT, size=12),
                       colorway=[BLUE, ORANGE, GREEN, PURPLE, TEAL, RED, "#FFCC00", MUTED],
                       xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, showline=False),
                       yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, showline=False),
                       legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                       hoverlabel=dict(font_family=FONT),
                       margin=dict(l=10, r=10, t=30, b=10))
    pio.templates["apple"] = tmpl
    pio.templates.default = "apple"


def color(v: float | None) -> str:
    if v is None or v != v:
        return ""
    return f"color: {GREEN}" if v > 0 else f"color: {RED}" if v < 0 else ""


def bar(cells: list[tuple[str, str, str]]) -> None:
    """A row of small (label, value, css class) tiles."""
    html = "".join(f'<span class="cell"><span class="lbl">{_label(lbl)}</span><span class="val {cls}">{val}</span></span>'
                   for lbl, val, cls in cells)
    st.markdown(f'<div class="td-bar">{html}</div>', unsafe_allow_html=True)


def updown(v: float | None) -> str:
    if v is None or v != v:
        return ""
    return "up" if v > 0 else "dn" if v < 0 else ""
