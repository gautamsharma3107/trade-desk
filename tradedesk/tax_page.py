"""Tax tab: this year's capital gains and trading income, estimated tax, and loss-harvesting ideas."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import demo, market, pnl, tax
from .theme import bar, color

INR = "₹{:,.0f}".format


def render(token: str | None, table: pd.DataFrame, demo_mode: bool) -> None:
    from .terminal import load_pnl

    ps = [p for p in pnl.periods() if p.label.startswith(("FY", "Last year"))]
    c = st.columns([3, 2])
    pick = c[0].radio("Year", [p.label for p in ps], horizontal=True, key="tx_year", label_visibility="collapsed")
    period = ps[[p.label for p in ps].index(pick)]
    slab = c[1].select_slider("Your income-tax slab (for intraday and F&O)", tax.SLABS, value=0.30,
                              format_func=lambda v: f"{v * 100:.0f}%", key="tx_slab",
                              help="The marginal rate on your other income. New regime FY 2025-26 onward: 30% "
                                   "above ₹24 lakh, 25% ₹20–24 lakh, 20% ₹16–20 lakh, 15% ₹12–16 lakh.")
    if demo_mode:
        trades, charges, errors = demo.PNL_TRADES, dict(demo.PNL_CHARGES), []
        st.caption("Sample trades. Log in to see your own.")
    else:
        trades, charges, errors = load_pnl(token, tuple(period.chunks()))
    for e in errors:
        if "No data" not in e and "UDAPI100" not in e:
            st.caption(f"Couldn't load {e}")
    df = pnl.in_period(pnl.trades_frame(trades), period)
    fo_charges = sum(v for k, v in charges.items() if k in ("FO", "COM", "CD"))
    h = tax.heads(df, fo_charges)
    taxable, carried, notes = tax.set_off(dict(zip(h["Head"], h["Net"])))
    est = tax.estimate(taxable, slab)

    st.markdown(f"## Tax estimate · {period.label.split('(')[0].strip()}")
    m = st.columns(5)
    m[0].metric("Estimated tax", INR(est["total"]), "incl. 4% cess", delta_color="off")
    m[1].metric("STCG (20%)", INR(taxable["STCG"]))
    m[2].metric("LTCG (12.5%)", INR(taxable["LTCG"]), f"₹{est['ltcg_exempt_left']:,.0f} of ₹1.25L exemption left",
                delta_color="off")
    m[3].metric("Intraday income", INR(taxable["Speculative"]))
    m[4].metric("F&O income", INR(taxable["F&O"]))

    show = h.assign(**{"After set-off": h["Head"].map(taxable), "Carried forward": h["Head"].map(carried).fillna(0),
                       "Rate": h["Head"].map({"STCG": "20%", "LTCG": "12.5% above ₹1.25L",
                                              "Speculative": f"slab {slab * 100:.0f}%",
                                              "F&O": f"slab {slab * 100:.0f}%"}),
                       "Tax": h["Head"].map(est["by_head"])})
    show = show[["Label", "Trades", "Gains", "Losses", "Expenses", "Net", "After set-off", "Carried forward", "Rate",
                 "Tax"]].rename(columns={"Label": "Head", "Expenses": "Charges deducted"})
    money = ["Gains", "Losses", "Charges deducted", "Net", "After set-off", "Carried forward", "Tax"]
    st.dataframe(show.style.format({k: "₹{:,.0f}" for k in money}).map(color, subset=["Net"]),
                 use_container_width=True, hide_index=True)
    bar([("TAX", INR(est["tax"]), "amb"), ("CESS 4%", INR(est["cess"]), ""), ("TOTAL", INR(est["total"]), "amb"),
         ("LOSSES CARRIED FWD", INR(sum(carried.values())), "dn" if carried else "")])
    for n in notes:
        st.markdown(f"- {n}")
    fo = h[h["Head"] == "F&O"].iloc[0]
    if fo["Trades"]:
        st.caption(f"F&O turnover for tax-audit purposes (sum of absolute profit and loss per trade): "
                   f"{INR(fo['Turnover'])}. Above ₹10 crore (with almost no cash transactions) a tax audit is needed; "
                   "below that, an audit can still apply if you report a loss or a low profit, so ask your CA. "
                   "F&O and intraday go in ITR-3.")

    st.markdown("#### Advance tax")
    sched = tax.advance_tax_schedule(est["total"], period.start.year if period.start.month >= 4 else
                                     period.start.year - 1, market.now_ist().date())
    st.dataframe(sched.style.format({"Due by": "{:%d %b %Y}", "Cumulative share": "{:.0f}%",
                                     "Cumulative amount": "₹{:,.0f}"}), use_container_width=True, hide_index=True)
    st.caption("If the year's total tax is ₹10,000 or more, pay it in these instalments to avoid interest under "
               "sections 234B/234C. Capital gains only count from the instalment after they're made. TDS on salary "
               "reduces what's due.")

    st.divider()
    st.markdown("## Tax-loss harvesting")
    losers, winners = tax.harvest(table, taxable, est["ltcg_exempt_left"])
    if losers.empty:
        st.info("None of your holdings is at a loss right now.")
    else:
        saved = losers["Tax saved (approx)"].sum()
        bar([("HOLDINGS AT A LOSS", str(len(losers)), "dn"), ("UNREALISED LOSS", INR(losers["Unrealised loss"].sum()),
                                                               "dn"),
             ("COULD SAVE", INR(saved), "up" if saved else "")])
        st.dataframe(losers.style.format({"Qty": "{:,.0f}", "Avg": "₹{:,.2f}", "LTP": "₹{:,.2f}",
                                          "Unrealised loss": "₹{:,.0f}", "Offsets gains": "₹{:,.0f}",
                                          "Tax saved (approx)": "₹{:,.0f}"}),
                     use_container_width=True, hide_index=True)
        st.caption("Selling a holding at a loss books that loss against this year's capital gains. Saving assumes "
                   "it's used against short-term gains first (20%), then long-term (12.5%). India has no wash-sale "
                   "rule, but buy back on a later day, not the same day (a same-day sell and buy is treated as "
                   "intraday), and a sale made only to save tax could be questioned. Upstox doesn't give buy dates "
                   "for holdings, so check whether each one is short- or long-term in your Upstox holdings report.")
    if not winners.empty and est["ltcg_exempt_left"] > 0:
        st.markdown("#### Use the ₹1.25 lakh long-term exemption")
        st.dataframe(winners.style.format({"Qty": "{:,.0f}", "Unrealised gain": "₹{:,.0f}",
                                           "Tax-free if long-term": "₹{:,.0f}"}),
                     use_container_width=True, hide_index=True)
        st.caption(f"₹{est['ltcg_exempt_left']:,.0f} of this year's long-term exemption is unused. For holdings held "
                   "over 12 months, selling enough to book that much gain and buying back the next day resets your "
                   "cost higher, tax-free. Only shares held over 12 months qualify.")
    with st.expander("Download for your CA"):
        out = df.drop(columns=["booked"]).assign(tax_head=df["bucket"].map(tax.HEADS))
        st.download_button("Closed trades with tax head (CSV)", out.to_csv(index=False).encode(),
                           f"tax_trades_{period.start:%Y}.csv", "text/csv", key="tx_csv")
        st.download_button("Summary (CSV)", show.to_csv(index=False).encode(), f"tax_summary_{period.start:%Y}.csv",
                           "text/csv", key="tx_sum")
    st.markdown("<div class='td-src'>Estimate only, not tax advice. Rates from 23 Jul 2024 (Finance Act 2024): STCG "
                "20%, LTCG 12.5% above ₹1.25 lakh, plus 4% cess; surcharge, the 87A rebate, grandfathering for shares "
                "bought before 1 Feb 2018, and charges on delivery trades (STT isn't deductible) are not applied. "
                "Holding period and P&L come from Upstox's P&L report. Check with a CA before filing.</div>",
                unsafe_allow_html=True)
