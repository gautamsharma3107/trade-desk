"""Official exchange data from NSE (and links to BSE/SEBI), plus filing-based research.

NSE's website APIs need the browser-like cookies the site sets on its pages,
so the client first opens a page, then calls the JSON API with those cookies.
Endpoints used (all public, no login):

- corporate-share-holdings-master: quarterly shareholding filings (promoter vs
  public %, with a link to the full XBRL filing)
- results-comparision: last ~5 quarters' reported P&L (₹ lakh)
- annual-reports: annual report PDFs by year
- corporate-bussiness-sustainabilitiy: BRSR filings (spelling is NSE's)

NSE sometimes blocks cloud servers. Every call is wrapped; the page falls back
to Screener.in when NSE says no.

`research_value_chain` asks Claude (Anthropic API, needs ANTHROPIC_API_KEY)
to read a company's filings (annual report, BRSR, investor presentations,
credit-rating rationales) and return what it sells and to whom, and what it
buys and from whom, with sources.
"""
from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
import requests

NSE = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": f"{NSE}/get-quotes/equity?symbol=RELIANCE",
}
TIMEOUT = 20


class FilingError(RuntimeError):
    pass


class NSEClient:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(NSE_HEADERS)
        self._warm = False

    def _warmup(self) -> None:
        if not self._warm:
            try:
                self.s.get(f"{NSE}/companies-listing/corporate-filings-shareholding-pattern", timeout=TIMEOUT)
            except requests.RequestException as e:
                raise FilingError(f"NSE unreachable: {e}") from e
            self._warm = True

    def get(self, path: str, **params) -> Any:
        self._warmup()
        for attempt in range(2):
            try:
                r = self.s.get(f"{NSE}/api/{path}", params=params, timeout=TIMEOUT)
            except requests.RequestException as e:
                raise FilingError(f"NSE: {e}") from e
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    pass
            if attempt == 0:  # cookies expired or blocked; refresh once
                self._warm = False
                self._warmup()
        raise FilingError(f"NSE {path}: HTTP {r.status_code}")

    def shareholding(self, symbol: str) -> list[dict]:
        return self.get("corporate-share-holdings-master", index="equities", symbol=symbol) or []

    def results(self, symbol: str) -> dict:
        return self.get("results-comparision", symbol=symbol) or {}

    def annual_reports(self, symbol: str) -> list[dict]:
        return (self.get("annual-reports", index="equities", symbol=symbol) or {}).get("data") or []

    def brsr(self, symbol: str) -> list[dict]:
        d = self.get("corporate-bussiness-sustainabilitiy", index="equities", symbol=symbol)
        return d.get("data", []) if isinstance(d, dict) else (d or [])


# ---------------------------------------------------------------- parsers
def _f(v) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def shareholding_frame(rows: list[dict]) -> pd.DataFrame:
    """NSE shareholding filings -> one row per quarter (oldest first)."""
    out = []
    for r in rows or []:
        out.append({"Quarter": r.get("date"), "Promoters %": _f(r.get("pr_and_prgrp")),
                    "Public %": _f(r.get("public_val")), "Employee trusts %": _f(r.get("employeeTrusts")),
                    "Filed": r.get("submissionDate") or r.get("broadcastDate"), "XBRL": r.get("xbrl")})
    df = pd.DataFrame(out, columns=["Quarter", "Promoters %", "Public %", "Employee trusts %", "Filed", "XBRL"])
    if df.empty:
        return df
    df["_d"] = pd.to_datetime(df["Quarter"], format="%d-%b-%Y", errors="coerce")
    return df.sort_values("_d").drop(columns="_d").drop_duplicates("Quarter", keep="last").reset_index(drop=True)


def results_frame(data: dict) -> pd.DataFrame:
    """NSE results comparison -> quarters as rows, ₹ crore (NSE reports ₹ lakh)."""
    rows = []
    for r in (data or {}).get("resCmpData") or []:
        lakh = lambda k: (_f(r.get(k)) / 100) if _f(r.get(k)) is not None else None  # noqa: E731
        revenue = lakh("re_net_sale")
        profit = lakh("re_net_profit") if r.get("re_net_profit") is not None else lakh("re_con_pro_loss")
        rows.append({
            "Quarter ending": r.get("re_to_dt"),
            "Revenue (₹ cr)": revenue,
            "Total income (₹ cr)": lakh("re_total_inc"),
            "Expenses (₹ cr)": lakh("re_oth_tot_exp"),
            "Profit before tax (₹ cr)": lakh("re_pro_loss_bef_tax"),
            "Net profit (₹ cr)": profit,
            "EPS (₹)": _f(r.get("re_basic_eps_for_cont_dic_opr") or r.get("re_basic_eps")),
            "Net margin %": (profit / revenue * 100) if revenue and profit is not None else None,
            "Audited": {"A": "Yes", "U": "No"}.get(r.get("re_res_type"), r.get("re_res_type")),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["_d"] = pd.to_datetime(df["Quarter ending"], format="%d-%b-%Y", errors="coerce")
    return df.sort_values("_d").drop(columns="_d").reset_index(drop=True)


def annual_report_links(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows or []:
        if r.get("fileName"):
            out.append({"Year": f"FY {r.get('fromYr', '?')}-{str(r.get('toYr', '?'))[-2:]}",
                        "Filed": (r.get("broadcast_dttm") or "")[:11], "Link": r["fileName"]})
    return sorted(out, key=lambda x: x["Year"], reverse=True)


def brsr_links(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows or []:
        link = r.get("attachmentFile") or r.get("fileName") or r.get("xbrlFile") or r.get("xbrl")
        if link:
            out.append({"Year": r.get("fyFrom") and f"FY {r.get('fyFrom')}-{str(r.get('fyTo', ''))[-2:]}" or
                        r.get("financialYear") or r.get("submissionDate") or "?",
                        "Filed": (r.get("submissionDate") or r.get("broadcastDate") or "")[:11], "Link": link})
    return out


def official_links(symbol: str, name: str = "") -> dict[str, str]:
    q = requests.utils.quote(name or symbol)
    return {
        "NSE quote & filings": f"{NSE}/get-quotes/equity?symbol={requests.utils.quote(symbol)}",
        "NSE shareholding filings": f"{NSE}/companies-listing/corporate-filings-shareholding-pattern?symbol="
                                    f"{requests.utils.quote(symbol)}",
        "NSE annual reports": f"{NSE}/companies-listing/corporate-filings-annual-reports?symbol={requests.utils.quote(symbol)}",
        "NSE BRSR filings": f"{NSE}/companies-listing/corporate-filings-bussiness-sustainabilitiy-reports?symbol="
                            f"{requests.utils.quote(symbol)}",
        "BSE company page": f"https://www.bseindia.com/stock-share-price/x/{requests.utils.quote(symbol)}/",
        "SEBI filings (offer documents)": f"https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&search={q}",
    }


# ---------------------------------------------------------------- AI research from filings
VALUE_CHAIN_SCHEMA_HINT = """{
  "summary": "one or two sentences: what the company does",
  "sells": [{"what": "product or segment", "share": "approx % of revenue, or empty", "to": "who buys it (named customers if public, else customer types)"}],
  "customers": "concentration and named key customers if disclosed (e.g. top 10 customers = X% of sales), export share, domestic vs international",
  "buys": [{"what": "key input or raw material", "from": "named suppliers if public, else supplier types/countries"}],
  "suppliers": "purchase concentration if disclosed (e.g. top 10 suppliers / trading houses = X% of purchases), MSME share, imports",
  "related_parties": "major related-party sales or purchases, if any",
  "as_of": "the filing year the facts come from, e.g. FY2025-26",
  "sources": [{"title": "document name", "url": "https://..."}]
}"""

RESEARCH_PROMPT = """You are an equity research assistant for an Indian retail investor.

Company: {name} (NSE: {symbol}).
Known official documents (read these first if they open):
{docs}

Find out, from primary sources, what this company sells and to whom, and what it buys and from whom.
Prefer, in order: the latest annual report and its Business Responsibility and Sustainability Report (BRSR:
Section A "products/services sold", "markets served", "types of customers", and Principle 1 "concentration of
purchases and sales"); the latest investor presentation and earnings-call transcript; credit rating rationales
(CRISIL, ICRA, CARE, India Ratings) which often name key customers and suppliers; SEBI offer documents (DRHP/RHP)
for recently listed companies. Use exchange (nseindia.com, bseindia.com), SEBI, company and rating-agency sites
before news sites.

Rules: only state facts the sources support. Name customers or suppliers only when a source names them; otherwise
describe their type. If something isn't disclosed, say "Not disclosed". Keep each field short.

Reply with only a JSON object in this shape, no other text:
{schema}"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise FilingError("Research reply had no JSON")
    try:
        return json.loads(m.group(0))
    except ValueError as e:
        raise FilingError(f"Research reply wasn't valid JSON: {e}") from e


def research_value_chain(symbol: str, name: str, docs: list[str], api_key: str,
                         model: str = "claude-opus-5-5") -> dict:
    """Ask Claude to read the company's filings on the web and return the value-chain JSON."""
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise FilingError("The anthropic package is not installed") from e

    client = anthropic.Anthropic(api_key=api_key)
    doc_lines = "\n".join(f"- {d}" for d in docs) or "- (none found; search for them)"
    messages: list[dict] = [{"role": "user", "content": RESEARCH_PROMPT.format(
        name=name or symbol, symbol=symbol, docs=doc_lines, schema=VALUE_CHAIN_SCHEMA_HINT)}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8,
              "user_location": {"type": "approximate", "country": "IN"}},
             {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 6, "max_content_tokens": 60000}]
    try:
        for _ in range(6):  # resume server-tool turns that pause
            with client.beta.messages.stream(
                model=model, max_tokens=16000, messages=messages, tools=tools,
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            ) as stream:
                resp = stream.get_final_message()
            if resp.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": resp.content})
                continue
            break
    except anthropic.AuthenticationError as e:
        raise FilingError("The Anthropic API key was rejected") from e
    except anthropic.RateLimitError as e:
        raise FilingError("Anthropic rate limit hit; try again in a minute") from e
    except anthropic.APIStatusError as e:
        raise FilingError(f"Anthropic API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise FilingError("Couldn't reach the Anthropic API") from e

    if resp.stop_reason == "refusal":
        raise FilingError("The research request was declined")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    data = _extract_json(text)
    data.setdefault("sells", [])
    data.setdefault("buys", [])
    data["generated_by"] = "AI research from filings"
    return data
