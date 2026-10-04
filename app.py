"""
app.py - Smart Money Terminal
Delivery-based accumulation + re-entry tracking + bulk/block deals + sector rotation.
Run: streamlit run app.py
"""
import hashlib

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import engine as E
import alt_data as A

st.set_page_config(page_title="Smart Money Terminal", page_icon="📈", layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1rem;max-width:1500px}
.topbar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;
 padding:12px 18px;border-radius:12px;background:linear-gradient(90deg,#0f172a,#1e293b);
 border:1px solid #334155;margin-bottom:14px}
.brand{font-size:1.35rem;font-weight:800;color:#f8fafc;letter-spacing:.5px}
.brand span{color:#22c55e}
.meta{color:#94a3b8;font-size:.82rem}
.kpi{background:#0f172a;border:1px solid #334155;border-radius:12px;padding:12px 16px;height:100%}
.kpi .l{color:#94a3b8;font-size:.72rem;text-transform:uppercase;letter-spacing:.8px}
.kpi .v{color:#f8fafc;font-size:1.2rem;font-weight:700}
.kpi .d{font-size:.8rem;font-weight:600;color:#94a3b8}
.g{color:#22c55e!important}.r{color:#ef4444!important}.y{color:#f59e0b!important}
.why{background:#0f172a;border-left:3px solid #22c55e;padding:8px 14px;margin:5px 0;
 border-radius:6px;color:#e2e8f0;font-size:.9rem}
.st-key-kpis button{width:100%;height:92px;border-radius:12px;border:1px solid #334155;
 background:#0f172a;white-space:pre-line;line-height:1.35}
.st-key-kpis button p{font-size:.95rem;font-weight:600}
.st-key-kpis button:hover{border-color:#22c55e}
</style>
""", unsafe_allow_html=True)


def kpi(col, label, value, sub="", cls=""):
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="v {cls}">{value}</div>'
                 f'<div class="d">{sub}</div></div>', unsafe_allow_html=True)


@st.cache_data(ttl=1800, show_spinner="Downloading NSE delivery + deals data (first load ~60 sec)...")
def load():
    hist, info = E.fetch_history(80)
    scr = E.compute_screener(hist, (), 0.0, E.fetch_sector_map()) if not hist.empty else pd.DataFrame()
    deals = pd.DataFrame()
    if not scr.empty:
        try:
            deals = A.fetch_bulk_block_deals()
        except Exception:
            deals = pd.DataFrame()
        try:
            scr = A.enrich_screener(scr, hist, deals)
        except Exception:
            pass
    return hist, scr, info, E.now_ist(), deals


hist, scr, info, fetched, deals = load()
if hist.empty or scr.empty:
    st.error("NSE data could not be loaded. NSE may be blocking this server or files are not yet "
             f"published (network errors: {info['errors']}). Click Refresh after a few minutes.")
    st.stop()
if "Ret_3M" not in scr.columns:
    st.cache_data.clear()
    st.error("engine.py purana version hai. GitHub pe engine.py aur app.py dono naye upload karo, "
             "phir app reboot karo.")
    st.stop()

asof = hist.Date.max()

# ---- Re-entry tracking (auto) ----
try:
    E.update_sl_hits(hist)
    scr = E.reentry_stats(scr, asof.date())
    E.log_screener_run(scr, asof.date())
except Exception:
    scr["Reentry"] = "🆕 First time"
    scr["Appearances_120D"] = 1
    scr["Days_Since_First"] = 0

ALL_SYMS = sorted(scr.Symbol.tolist())
if "Is_New_Listing" in scr.columns:
    NEW_LISTINGS = sorted(scr[scr.Is_New_Listing].Symbol.tolist())
else:
    NEW_LISTINGS = []

STAGES = ["Base (not moved)", "Early move", "Rally on", "Extended (already ran)"]
SETUPS = ["In range (base)", "Breakout", "Trending / wide", "Breakdown"]
BUYS = ["Continuing", "Just started", "Fading", "Not buying"]
SIGNALS = ["Strong Accumulation", "Accumulation", "Neutral", "Distribution", "Low volume (ignore)"]
FRESH = list(E.FRESH_SET)
FRESH_SEL = ["All fresh"] + FRESH
REENTRY_OPTS = ["🆕 First time", "🔁 Second chance", "🔁 Repeat", "🔁 SL hit earlier"]
ESTAT = {"In zone": "🟢 In zone", "Above zone (wait)": "🟡 Above zone", "Below zone": "🔴 Below zone"}
FICON = {"Spike today": "🔥 Spike today", "Spike (last 3D)": "⚡ Spike (last 3D)",
         "Building (5D)": "🔵 Building (5D)", "None": "-"}
BICON = {"Continuing": "🟢 Continuing", "Just started": "🔵 Just started", "Fading": "🟡 Fading",
         "Not buying": "⚪ Not buying"}
QICON = {"Leading": "🟢 Leading", "Improving": "🔵 Improving", "Weakening": "🟡 Weakening", "Lagging": "🔴 Lagging"}
QCOL = {"Leading": "#22c55e", "Improving": "#3b82f6", "Weakening": "#f59e0b", "Lagging": "#ef4444"}

# ------------------------------ sidebar ----------------------------------- #
with st.sidebar:
    st.markdown("### ⚙️ Controls")
    if st.button("🔄 Refresh data now"):
        st.cache_data.clear()
        st.rerun()
    universe = st.radio(
        "Universe", ["My watchlist", "All liquid NSE stocks"], index=1,
        help="My watchlist = sirf wo stocks jo engine.py ki SECTOR_OF me hain + jo tum neeche add karo.\n\n"
             "All liquid NSE = NSE ke saare EQ stocks jinka avg daily turnover niche slider se zyada hai.")
    min_turn = st.slider("Min avg turnover (₹ Cr/day)", 0, 100, 5,
                         help="Sirf 'All liquid NSE' pe lagta hai. 5–10 Cr swing trading ke liye theek hai.")
    extras = st.multiselect("Add stocks to My watchlist", ALL_SYMS, placeholder="Type symbol...")
    st.caption("Source: NSE bhavcopy + bulk/block deals (end-of-day), ~6-7 PM IST ke baad. "
               "Re-entry tracker auto-save karta hai signals_log.db me. "
               "Analysis tool only, not investment advice.")

st.markdown(f"""
<div class="topbar">
 <div class="brand">SMART<span>MONEY</span> TERMINAL</div>
 <div class="meta">Data as of <b>{asof:%d %b %Y}</b> (EOD) &nbsp;|&nbsp;
 Fetched <b>{fetched:%d %b %Y, %I:%M %p} IST</b> &nbsp;|&nbsp; Sessions loaded: <b>{info['days']}</b>
 &nbsp;|&nbsp; Window: <b>1M vs previous 2M</b></div>
</div>""", unsafe_allow_html=True)
if info["errors"]:
    st.warning(f"{info['errors']} din ka NSE data download nahi ho paya - Refresh karke dekho.")

# ---- Data sanity checks ----
_warn = []
if info.get("days", 0) < 40:
    _warn.append(f"Sirf {info['days']} sessions mile — 3M comparison weak ho sakta hai.")
try:
    if scr.Deliv_Per_1M.gt(100).any():
        _warn.append(f"{int(scr.Deliv_Per_1M.gt(100).sum())} stocks me delivery % > 100 — NSE source data suspicious.")
    if (scr.Price <= 0).any():
        _warn.append("Kuch stocks ka price 0 hai — bhavcopy row corrupt.")
    if scr.Deliv_Qty_X.gt(20).any():
        _warn.append(f"{int(scr.Deliv_Qty_X.gt(20).sum())} stocks me Deliv qty 1M÷3M > 20x — split/bonus adjust issue ho sakta hai.")
    if "Has_Split_Adjust" in scr.columns and scr.Has_Split_Adjust.any():
        _warn.append(f"{int(scr.Has_Split_Adjust.sum())} stocks me recent split/bonus detect hua — "
                     f"unka Score/ratios **verify** karo (split flag screener table me 'Split?' column me hai).")
except Exception:
    pass
if _warn:
    st.warning("**Data warnings:**\n- " + "\n- ".join(_warn))

watch_all = set(E.SECTOR_OF) | set(extras)
if universe == "My watchlist":
    pool = scr[scr.Symbol.isin(watch_all)]
else:
    pool = scr[(scr.Avg_Turnover_Cr >= min_turn) | scr.Symbol.isin(extras)]


# --------------------------- shared pieces -------------------------------- #
def render_detail(sym: str, k: str):
    r = scr[scr.Symbol == sym].iloc[0]
    g = E.symbol_view(hist, sym).tail(80)
    st.markdown(f"### {sym}  <span style='color:#94a3b8;font-size:.9rem'>{r.Sector}</span>", unsafe_allow_html=True)
    if r.get("Is_New_Listing", False):
        st.warning(
            f"🆕 **Recently listed stock** — sirf {len(g)} sessions ka data hai. "
            "1M vs 3M comparison weak hai (3M avg me ~kam sessions aaye hain). "
            "**Delivery %, bulk/block deals, aur price action pe focus karo.** "
            "Ye stock 20+ sessions ke baad full metrics ke saath screener me aayega."
        )
    if r.get("Has_Split_Adjust", False):
        st.warning(
            "⚠️ **Is stock me split/bonus detect hua hai last 3 mahine me.** "
            "Delivered qty ratios (1M÷3M) aur Score **unreliable** ho sakte hain kyunki adjustment "
            "perfect nahi hoti. **Delivery %, price action, aur bulk deals pe zyada bharosa karo.**"
        )

    sc = "g" if r.Score >= 55 else "y" if r.Score >= 35 else "r"
    bc = {"Continuing": "g", "Just started": "g", "Fading": "y", "Not buying": "r"}[r.Buying_Status]
    c = st.columns(6)
    kpi(c[0], "Last price", f"₹{r.Price:,.2f}", f"{r.Chg_Pct:+.2f}% today", "g" if r.Chg_Pct >= 0 else "r")
    kpi(c[1], "Accumulation score", f"{r.Score}/100", r.Signal, sc)
    kpi(c[2], "Buying status", r.Buying_Status, f"{r.Buy_Weeks}/4 weeks net buying", bc)
    kpi(c[3], "Delivered qty 1M÷3M", f"{r.Deliv_Qty_X:.2f}x", f"{r.Deliv_Qty_1M:,} vs {r.Deliv_Qty_3M:,}")
    kpi(c[4], "Delivery % 1M vs prev 2M", f"{r.Deliv_Per_1M:.1f}%", f"was {r.Deliv_Per_3M:.1f}% ({r.Deliv_Per_Chg:+.1f}pp)")
    kpi(c[5], "Net buy flow 1M", f"{r.Net_Flow_1M:+.0f}%", f"prev 2M {r.Net_Flow_3M:+.0f}%",
        "g" if r.Net_Flow_1M > 0 else "r")

    c2 = st.columns(4)
    rs = r.get("RS_1M", np.nan)
    rs_cls = "g" if pd.notna(rs) and rs > 0 else "r"
    kpi(c2[0], "Rel. strength 1M vs Nifty", f"{rs:+.1f}%" if pd.notna(rs) else "-",
        "Outperforming" if pd.notna(rs) and rs > 0 else "Underperforming", rs_cls)
    kpi(c2[1], "Deliv value 1M", f"₹{r.get('Deliv_Val_1M_Cr', 0):,.1f} Cr",
        f"prev 2M ₹{r.get('Deliv_Val_3M_Cr', 0):,.1f} Cr")
    bk = r.get("Bulk_Flag", "-")
    kpi(c2[2], "Bulk/Block today", bk,
        f"Net ₹{r.get('Bulk_Net_Cr', 0):+,.2f} Cr ({int(r.get('Deals_Today', 0))} deals)",
        "g" if "Buy" in str(bk) else "r" if "Sell" in str(bk) else "")
    rflag = r.get("Reentry", "-")
    kpi(c2[3], "Re-entry status", rflag,
        f"Appeared {int(r.get('Appearances_120D', 1))}x in last 120D",
        "y" if "SL" in str(rflag) else "")

    st.markdown("#### Trade plan (range based)")
    c = st.columns(5)
    kpi(c[0], "Price vs Entry zone", f"₹{r.Price:,.2f}  |  ₹{r.Entry_Low:,.2f}–{r.Entry_High:,.2f}",
        f"{ESTAT[r.Entry_Status]} ({r.Entry_Gap:+.1f}% vs entry)")
    kpi(c[1], "Stop loss", f"₹{r.SL:,.2f}", f"-{r.Risk_Pct:.1f}% from entry", "r")
    for i, tk in enumerate(["T1", "T2", "T3"]):
        kpi(c[2 + i], f"Target {i + 1}", f"₹{r[tk]:,.2f}", f"+{(r[tk] / r.Entry - 1) * 100:.1f}% from entry", "g")

    why = [f"Setup: <b>{r.Setup}</b> - 30D range ₹{r.Range_Lo:,.2f} to ₹{r.Range_Hi:,.2f} ({r.Range_Pct}%). {r.Plan_Status}."]
    if r.Stage.startswith("Extended"):
        why.append("Stock pehle hi kaafi chal chuka hai - pullback/retest pe hi socho, chase mat karo.")
    elif r.Stage.startswith("Base"):
        why.append("Price abhi 20D low ke paas hai - move shuru hona baki ho sakta hai.")
    why.append(f"1 mahine me delivered qty pichle 2 mahine ke avg se {r.Deliv_Qty_X:.2f}x; "
               f"delivery % {r.Deliv_Per_Chg:+.1f}pp.")
    why.append(f"Net buy flow {r.Net_Flow_1M:+.0f}% (pichle 2M: {r.Net_Flow_3M:+.0f}%); "
               f"{r.Acc_Days} accumulation din vs {r.Dist_Days} distribution din (last 21).")
    why.append(f"Fresh activity: <b>{FICON[r.Fresh]}</b> | last 5 days: {r.Last5} | "
               f"aaj ki delivered qty 3M avg ka {r.Today_X:.2f}x.")
    if pd.notna(rs):
        why.append(f"Relative strength 1M vs Nifty: <b>{rs:+.1f}%</b> "
                   f"({'outperforming' if rs > 0 else 'underperforming'}).")
    bk_net = r.get("Bulk_Net_Cr", 0)
    if abs(bk_net) > 0.01:
        why.append(f"<b>Bulk/Block today: ₹{bk_net:+,.2f} Cr net</b> "
                   f"({int(r.get('Deals_Today',0))} deals) — big player footprint.")
    if str(rflag).startswith("🔁"):
        why.append(f"<b>Re-entry:</b> {rflag} — pehle bhi screener me aaya tha. "
                   f"History neeche dekho, purane entry/SL check karo.")
    why.append("SL range ke lowest low ke neeche (ya breakout level ke neeche). Targets = range top aur "
               "range height ka projection. News/resistance khud check karo.")
    for w in why:
        st.markdown(f'<div class="why">{w}</div>', unsafe_allow_html=True)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.55, 0.22, 0.23],
                        vertical_spacing=0.03, subplot_titles=("Price with plan", "Delivery %", "Delivered quantity"))
    fig.add_trace(go.Candlestick(x=g.Date, open=g.OPEN_PRICE, high=g.HIGH_PRICE, low=g.LOW_PRICE,
                                 close=g.CLOSE_PRICE, name=sym), row=1, col=1)
    fig.add_trace(go.Scatter(x=g.Date, y=g.CLOSE_PRICE.rolling(20).mean(), name="20 DMA",
                             line=dict(color="#f59e0b", width=1.3)), row=1, col=1)
    fig.add_hrect(y0=r.Range_Lo, y1=r.Range_Hi, fillcolor="#38bdf8", opacity=0.07, line_width=0, row=1, col=1)
    for lvl, col, name in [(r.Entry, "#38bdf8", "Entry"), (r.SL, "#ef4444", "SL"), (r.T1, "#22c55e", "T1"),
                           (r.T2, "#22c55e", "T2"), (r.T3, "#22c55e", "T3")]:
        fig.add_hline(y=lvl, line_dash="dot", line_color=col, annotation_text=f"{name} {lvl:,.1f}",
                      annotation_position="right", row=1, col=1)
    colors = np.where((g.CLOSE_PRICE >= g.PREV_CLOSE).values, "#22c55e", "#ef4444")
    fig.add_trace(go.Bar(x=g.Date, y=g.DELIV_PER, marker_color=colors), row=2, col=1)
    fig.add_hline(y=r.Deliv_Per_1M, line_dash="dash", line_color="#38bdf8", row=2, col=1)
    fig.add_hline(y=r.Deliv_Per_3M, line_dash="dash", line_color="#94a3b8", row=2, col=1)
    fig.add_trace(go.Bar(x=g.Date, y=g.DELIV_QTY, marker_color=colors), row=3, col=1)
    fig.add_hline(y=r.Deliv_Qty_3M, line_dash="dash", line_color="#94a3b8", row=3, col=1)
    fig.update_layout(height=760, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=70, t=30, b=10))
    st.plotly_chart(fig, width="stretch", key=f"{k}_price")
    st.caption("Bar: green = close up, red = down. Blue dashed = last 1M avg, grey dashed = previous 2M avg. "
               "Shaded band = 30D range.")

    wf = E.weekly_flows(g, 12)
    fig2 = go.Figure(go.Bar(x=[d.strftime("%d %b") for d, _ in wf], y=[f for _, f in wf],
                            marker_color=["#22c55e" if f > 0 else "#ef4444" for _, f in wf]))
    fig2.update_layout(height=280, template="plotly_dark", margin=dict(l=10, r=10, t=40, b=10),
                       title="Weekly net delivery buying - last 12 weeks (up-day − down-day delivery, shares)")
    st.plotly_chart(fig2, width="stretch", key=f"{k}_wk")

    # Re-entry history
    rh = E.reentry_history(sym, limit=30)
    if not rh.empty:
        st.markdown("#### 🔁 Re-entry history (last 30 appearances)")
        st.dataframe(rh, hide_index=True, width="stretch",
                     column_config={
                         "Price": st.column_config.NumberColumn("Price", format="₹%.2f"),
                         "Entry": st.column_config.NumberColumn("Entry", format="₹%.2f"),
                         "SL": st.column_config.NumberColumn("SL", format="₹%.2f"),
                         "SL_Hit": st.column_config.CheckboxColumn("SL hit?"),
                     })

    # Bulk/block history for this stock
    if deals is not None and not deals.empty:
        dsub = deals[deals.Symbol == sym]
        if not dsub.empty:
            st.markdown("#### 📜 Bulk / Block deals (today)")
            st.dataframe(
                A.deals_table(dsub, limit=50), hide_index=True, width="stretch",
                column_config={
                    "Value_Cr": st.column_config.NumberColumn("Value", format="₹%.2f Cr"),
                    "Qty":      st.column_config.NumberColumn("Qty", format="%d"),
                    "Price":    st.column_config.NumberColumn("Price", format="₹%.2f"),
                })


@st.dialog("Stock detail", width="large")
def detail_dialog(sym: str):
    render_detail(sym, "dlg")


TABLE_COLS = ["Symbol", "Reentry", "Is_New_Listing", "Has_Split_Adjust",
              "Price", "Entry_Zone", "Entry_Status", "SL", "T1", "T2", "T3",
              "Score", "Signal", "Fresh", "Last5", "Buying_Status", "Buy_Weeks", "Setup", "Stage",
              "Deliv_Qty_X", "Today_X", "Deliv_Per_Chg", "Net_Flow_1M", "Deliv_Per_1M", "Deliv_Per_3M",
              "Acc_Days", "Range_Pct", "Chg_Pct", "RS_1M", "Deliv_Val_1M_Cr", "Deliv_Val_3M_Cr",
              "Bulk_Flag", "Bulk_Net_Cr", "Deals_Today", "Appearances_120D", "Days_Since_First", "Sector"]

TABLE_CFG = {
    "Symbol": st.column_config.TextColumn("Symbol", pinned=True),
    "Reentry": st.column_config.TextColumn(
        "Re-entry",
        help="Past 120 days ke screener history se."),
    "Is_New_Listing": st.column_config.CheckboxColumn(
        "🆕 New",
        help="Recently listed — 20 sessions se kam data. 1M vs 3M comparison weak hai."),
    "Has_Split_Adjust": st.column_config.CheckboxColumn(
        "Split?",
        help="Last 3 mahine me split/bonus detect hua. Score/ratios verify karo."),
    "Price": st.column_config.NumberColumn("Price", format="₹%.2f"),
    "Entry_Zone": st.column_config.TextColumn("Entry zone (₹)"),
    "Entry_Status": st.column_config.TextColumn("Price vs zone"),
    "SL": st.column_config.NumberColumn("SL", format="₹%.2f"),
    "T1": st.column_config.NumberColumn("T1", format="₹%.2f"),
    "T2": st.column_config.NumberColumn("T2", format="₹%.2f"),
    "T3": st.column_config.NumberColumn("T3", format="₹%.2f"),
    "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
    "Fresh": st.column_config.TextColumn("Fresh activity"),
    "Last5": st.column_config.TextColumn(
        "Last 5 days",
        help="Purana → aaj. 🟢 strong delivery + price up, 🔴 strong delivery + price down, ⚪ normal"),
    "Buy_Weeks": st.column_config.NumberColumn("Buy weeks /4", format="%d"),
    "Deliv_Qty_X": st.column_config.NumberColumn("Deliv qty 1M÷3M", format="%.2fx"),
    "Today_X": st.column_config.NumberColumn("Today deliv ÷ 3M avg", format="%.2fx"),
    "Deliv_Per_Chg": st.column_config.NumberColumn("Deliv % Δ 1M−3M", format="%+.1f pp"),
    "Net_Flow_1M": st.column_config.NumberColumn("Net buy flow 1M", format="%+.0f%%"),
    "Deliv_Per_1M": st.column_config.NumberColumn("Deliv % 1M", format="%.1f%%"),
    "Deliv_Per_3M": st.column_config.NumberColumn("Deliv % prev 2M", format="%.1f%%"),
    "Acc_Days": st.column_config.NumberColumn("Acc days /21", format="%d"),
    "Range_Pct": st.column_config.NumberColumn("30D range", format="%.1f%%"),
    "Chg_Pct": st.column_config.NumberColumn("Chg %", format="%.2f%%"),
    "RS_1M": st.column_config.NumberColumn("RS vs Nifty 1M", format="%+.1f%%"),
    "Deliv_Val_1M_Cr": st.column_config.NumberColumn("Deliv val 1M", format="₹%.1f Cr"),
    "Deliv_Val_3M_Cr": st.column_config.NumberColumn("Deliv val prev 2M", format="₹%.1f Cr"),
    "Bulk_Flag": st.column_config.TextColumn("Bulk/Block today"),
    "Bulk_Net_Cr": st.column_config.NumberColumn("Bulk net", format="₹%+.2f Cr"),
    "Deals_Today": st.column_config.NumberColumn("Deals today", format="%d"),
    "Appearances_120D": st.column_config.NumberColumn("Appears /120D", format="%d"),
    "Days_Since_First": st.column_config.NumberColumn("Days since 1st", format="%d"),
}


def stock_table(d: pd.DataFrame, name: str, height: int = 560):
    view = d.copy()
    view["Entry_Status"] = view.Entry_Status.map(ESTAT)
    view["Buying_Status"] = view.Buying_Status.map(BICON)
    view["Fresh"] = view.Fresh.map(FICON)
    cols = [c for c in TABLE_COLS if c in view.columns]
    sig = hashlib.md5(",".join(view.Symbol).encode()).hexdigest()[:10]
    ev = st.dataframe(view[cols], hide_index=True, width="stretch", height=height,
                      column_config=TABLE_CFG, on_select="rerun", selection_mode="single-row",
                      key=f"tbl_{name}_{sig}")
    rows = ev.selection.rows
    last_key = f"last_{name}"
    if not rows:
        st.session_state[last_key] = None
        return None
    sym = view.iloc[rows[0]].Symbol
    if sym != st.session_state.get(last_key):
        st.session_state[last_key] = sym
        return sym
    return None


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔎 Accumulation Screener", "🔄 Sector Rotation", "🎯 Stock Plan",
    "⚖️ Compare", "📜 Bulk / Block Deals",
])
open_sym = None

# ---------------------------- Screener ------------------------------------ #
with tab1:
    QUICK = {
        "strong": ("Strong accumulation", pool[pool.Signal == "Strong Accumulation"]),
        "acc":    ("Accumulation", pool[pool.Signal == "Accumulation"]),
        "cont":   ("Buying continuing", pool[pool.Buying_Status == "Continuing"]),
        "fresh":  ("Fresh activity", pool[pool.Fresh.isin(FRESH)].sort_values("Last5_X", ascending=False)),
        "reentry":("🔁 Re-entry stocks", pool[pool.Reentry.astype(str).str.startswith("🔁", na=False)]),
        "dist":   ("Distribution", pool[pool.Signal == "Distribution"]),
    }
    if "quick" not in st.session_state:
        st.session_state.quick = None

    def set_quick(k):
        st.session_state.quick = None if (k is None or st.session_state.quick == k) else k

    with st.container(key="kpis"):
        kc = st.columns(7)
        kc[0].button(f"Stocks scanned\n{len(pool)}", key="q_all", on_click=set_quick, args=(None,),
                     type="primary" if st.session_state.quick is None else "secondary")
        labels = {"strong": "🟢 Strong acc.", "acc": "🟢 Accumulation", "cont": "🟢 Buying cont.",
                  "fresh": "⚡ Fresh activity", "reentry": "🔁 Re-entry", "dist": "🔴 Distribution"}
        for i, k in enumerate(QUICK, start=1):
            extra = f"  (today {int((pool.Fresh == 'Spike today').sum())})" if k == "fresh" else ""
            kc[i].button(f"{labels[k]}\n{len(QUICK[k][1])}{extra}", key=f"q_{k}", on_click=set_quick, args=(k,),
                         type="primary" if st.session_state.quick == k else "secondary")
    st.caption("👆 Card pe click karo - wahi stocks table me aa jayenge. Dobara click = filters pe wapas.")

    q = st.multiselect("🔍 Search stock", ALL_SYMS, placeholder="e.g. BAJAJHFL")

    PRESETS = {"Balanced (recommended)": (1.2, 3), "Strict (few, best)": (1.5, 6),
               "Loose (more ideas)": (1.0, 0), "Custom": None}
    p1, p2 = st.columns([1, 2])
    preset = p1.selectbox("Scan preset", list(PRESETS))
    if PRESETS[preset] is None:
        s1, s2 = p2.columns(2)
        min_x = s1.slider("Min delivery qty × (1M ÷ 3M)", 0.5, 4.0, 1.2, 0.1)
        min_pp = s2.slider("Min delivery % rise (pp)", -10, 30, 3)
    else:
        min_x, min_pp = PRESETS[preset]
        p2.info(f"1M delivered qty ≥ **{min_x}x** pichle 2M avg  |  1M delivery % ≥ **+{min_pp}pp**")

    h1, h2, h3 = st.columns(3)
    only_acc  = h1.checkbox("Sirf Accumulation / Strong Accumulation dikhao", value=True)
    hide_ext  = h2.checkbox("Extended (already ran) chhupao", value=True)
    only_bulk = h3.checkbox("Sirf jinke aaj Bulk/Block BUY hue", value=False)

    f = st.columns(4)
    sig = f[0].multiselect("Signal", SIGNALS, placeholder="All")
    stg = f[1].multiselect("Stage", STAGES, placeholder="All")
    setup_sel = f[2].multiselect("Setup", SETUPS, placeholder="All")
    buy_sel = f[3].multiselect("Buying status", BUYS, placeholder="All")

    g2 = st.columns(4)
    sec_sel = g2[0].multiselect("Sector / Industry", sorted(pool.Sector.unique()), placeholder="All")
    min_wk = g2[1].slider("Min buying weeks (last 4 me se)", 0, 4, 0)
    fresh_sel = g2[2].multiselect("Fresh activity", FRESH_SEL, placeholder="All",
        help="'All fresh' = teeno types ek saath.")
    reentry_sel = g2[3].multiselect("Re-entry filter", REENTRY_OPTS, placeholder="All",
        help="🆕 First time = pehli baar screener me. 🔁 Second chance = pehle bhi aaya. "
             "🔁 Repeat = 3+ baar. 🔁 SL hit earlier = pehle SL laga tha.")

    fresh_picks = []
    if fresh_sel:
        fresh_picks = FRESH if "All fresh" in fresh_sel else [x for x in fresh_sel if x in FRESH]
    has_fresh = bool(fresh_picks)

    funnel = [("Universe", len(pool))]
    quick = st.session_state.quick
    if q:
        d = scr[scr.Symbol.isin(q)]
        funnel = [("Search", len(d))]
    elif quick:
        d = QUICK[quick][1]
        st.success(f"Showing: **{QUICK[quick][0]}** - {len(d)} stocks (baaki filters ignore).")
        funnel = []
    else:
        d = pool
        if only_bulk and "Bulk_Flag" in d.columns:
            d = d[d.Bulk_Flag.astype(str).str.contains("Buy", na=False)]
            funnel.append(("Bulk buy only", len(d)))
        if reentry_sel:
            d = d[d.Reentry.isin(reentry_sel)]
            funnel.append(("Re-entry", len(d)))
        if has_fresh:
            d = d[d.Fresh.isin(fresh_picks)]
            funnel.append(("Fresh activity", len(d)))
        elif sig:
            d = d[d.Signal.isin(sig)]
            funnel.append(("Signal", len(d)))
        elif only_acc:
            d = d[d.Signal.isin(["Strong Accumulation", "Accumulation"])]
            funnel.append(("Accumulation signal", len(d)))
        if stg:
            d = d[d.Stage.isin(stg)]
            funnel.append(("Stage", len(d)))
        elif hide_ext:
            d = d[d.Stage != STAGES[3]]
            funnel.append(("Extended hidden", len(d)))
        if not has_fresh:
            d = d[(d.Deliv_Qty_X >= min_x) & (d.Deliv_Per_Chg >= min_pp)]
            funnel.append(("Scan preset", len(d)))
        if setup_sel: d = d[d.Setup.isin(setup_sel)]
        if buy_sel:   d = d[d.Buying_Status.isin(buy_sel)]
        if sec_sel:   d = d[d.Sector.isin(sec_sel)]
        d = d[d.Buy_Weeks >= min_wk]
        funnel.append(("Setup/Buying/Sector/Weeks", len(d)))
        if has_fresh:
            d = d.sort_values("Last5_X", ascending=False)
    st.caption(f"{len(d)} stocks | prices as of {asof:%d %b %Y}  |  👆 Row pe click karo → detail khulega")
    if funnel:
        st.caption("🔻 Filter funnel:  " + "  →  ".join(f"{n}: **{c}**" for n, c in funnel))

    open_sym = stock_table(d, "scr") or open_sym
    st.download_button("⬇️ Download CSV", d.to_csv(index=False).encode(),
                       f"accumulation_{asof:%Y%m%d}.csv", "text/csv")
    with st.expander("Score kaise banta hai? + Re-entry tracker info"):
        st.markdown("""
**Score (1M vs previous 2M):**
- **Delivered qty 1M ÷ pichle 2M avg**: ≥1.5x → 20, ≥1.2x → 14, ≥1.05x → 7
- **Delivery % (1M − pichle 2M)**: ≥8pp → 15, ≥4pp → 10, >0 → 4
- **Net buy flow 1M**: ≥30% → 20, ≥15% → 14, >0 → 7
- **Buying weeks** (last 4 calendar weeks): 4 → 15, 3 → 11, 2 → 6
- **Setup** In range / Breakout → 10
- **Range hold** → 10
- **Aaj ki delivered qty ≥ 3M avg** → 10

**Re-entry tracker (auto):**
Har roz ka screener output `signals_log.db` me save hota hai. Jab bhi koi stock dubara aata hai:
- **🆕 First time** = pehli baar screener me
- **🔁 Second chance** = pehle bhi aaya tha (SL nahi laga)
- **🔁 Repeat** = 3+ baar aaya hai
- **🔁 SL hit earlier** = pehle aaya tha aur tab SL laga tha

**Split/Bonus flag:**
Agar stock me last 3 mahine me split/bonus hua hai, to "Split?" column ✅ hoga aur stock detail me warning aayegi.
Un stocks me Deliv_Qty_X aur Score unreliable ho sakte hain — delivery %, price, bulk deals pe bharosa karo.
        """)

# ------------------------- Sector rotation -------------------------------- #
with tab2:
    try:
        sec = E.sector_rotation(pool)
    except Exception as ex:
        sec = pd.DataFrame()
        st.error(f"sector_rotation error: {ex}")
    if sec is None or sec.empty:
        st.warning("Sector data nahi mila.")
    else:
        q_counts = sec.groupby("Quadrant").size().to_dict() if "Quadrant" in sec.columns else {}
        q_flow = sec.groupby("Quadrant").Flow_1M.mean().to_dict() if "Quadrant" in sec.columns else {}
        kc = st.columns(4)
        for i, q in enumerate(["Leading", "Improving", "Weakening", "Lagging"]):
            n = int(q_counts.get(q, 0)); fval = q_flow.get(q, 0.0)
            cls = {"Leading": "g", "Improving": "g", "Weakening": "y", "Lagging": "r"}[q]
            kpi(kc[i], f"{QICON[q]}", f"{n} sectors",
                f"Avg flow {fval:+.1f}%" if n else "No sector", cls)

        st.markdown("##### 🧭 Rotation map — Flow 1M (X) vs Flow change vs prev 2M (Y)")
        st.caption("Top-right (Leading) = already strong. Top-left (Improving) = early entry zone.")

        try:
            xs = sec.Flow_1M.replace([np.inf, -np.inf], np.nan).dropna()
            ys = sec.Flow_Chg.replace([np.inf, -np.inf], np.nan).dropna()
            if xs.empty or ys.empty:
                st.info("Sector flow data insufficient.")
            else:
                pad_x = max(abs(xs.min()), abs(xs.max())) * 1.15 + 5
                pad_y = max(abs(ys.min()), abs(ys.max())) * 1.15 + 3
                x0, x1 = -pad_x, pad_x; y0, y1 = -pad_y, pad_y
                fig = go.Figure()
                for xA, xB, yA, yB, col, label in [
                    (0, x1, 0, y1, "#22c55e", "LEADING"),
                    (x0, 0, 0, y1, "#3b82f6", "IMPROVING"),
                    (0, x1, y0, 0, "#f59e0b", "WEAKENING"),
                    (x0, 0, y0, 0, "#ef4444", "LAGGING"),
                ]:
                    fig.add_shape(type="rect", x0=xA, x1=xB, y0=yA, y1=yB,
                                  fillcolor=col, opacity=0.055, line_width=0, layer="below")
                    fig.add_annotation(x=(xA+xB)/2, y=yB*0.92, text=label, showarrow=False,
                                       font=dict(size=11, color=col), opacity=0.6)
                for qn, col in QCOL.items():
                    s = sec[sec.Quadrant == qn]
                    if s.empty: continue
                    custom_cols = []
                    for cn in ["Acc_Pct", "Stocks", "Fresh", "Deliv_Qty_X", "Ret_1M"]:
                        custom_cols.append(s[cn].values if cn in s.columns else np.zeros(len(s)))
                    fig.add_trace(go.Scatter(
                        x=s.Flow_1M, y=s.Flow_Chg, mode="markers+text",
                        text=s.Sector, textposition="top center", textfont=dict(size=10),
                        name=QICON[qn],
                        marker=dict(size=np.clip(s.Stocks * 1.2 + 12, 14, 44) if "Stocks" in s.columns else 20,
                                    color=col, opacity=0.85, line=dict(color="#0f172a", width=1.5)),
                        customdata=np.stack(custom_cols, axis=1),
                        hovertemplate=("<b>%{text}</b><br>Flow 1M: %{x:+.1f}%<br>"
                                       "Change vs prev 2M: %{y:+.1f} pp<br>"
                                       "Accumulating: %{customdata[0]}%% of %{customdata[1]}<br>"
                                       "Fresh: %{customdata[2]}<extra></extra>")))
                fig.add_vline(x=0, line_color="#475569", line_width=1)
                fig.add_hline(y=0, line_color="#475569", line_width=1)
                fig.update_layout(height=560, template="plotly_dark",
                                  margin=dict(l=10, r=10, t=10, b=10),
                                  xaxis=dict(title="Net buy flow 1M (%)", range=[x0, x1], zeroline=False),
                                  yaxis=dict(title="Change vs prev 2M (pp)", range=[y0, y1], zeroline=False),
                                  legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"))
                st.plotly_chart(fig, width="stretch", key="sec_chart")
        except Exception as ex:
            st.warning(f"Chart render issue: {ex}")

        c1, c2 = st.columns(2)
        show_cols = [c for c in ["Sector", "Quadrant", "Flow_1M", "Flow_Chg", "Acc_Pct", "Stocks"] if c in sec.columns]
        try:
            top = sec.sort_values("Flow_Chg", ascending=False).head(5)[show_cols]
            bot = sec.sort_values("Flow_Chg").head(5)[show_cols]
        except Exception:
            top = bot = pd.DataFrame()
        with c1:
            st.markdown("###### 🚀 Fastest-improving")
            if not top.empty:
                st.dataframe(top, hide_index=True, width="stretch",
                             column_config={
                                 "Flow_1M": st.column_config.NumberColumn(format="%+.1f%%"),
                                 "Flow_Chg": st.column_config.NumberColumn(format="%+.1f pp"),
                                 "Acc_Pct": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%")})
        with c2:
            st.markdown("###### 🧊 Fastest-weakening")
            if not bot.empty:
                st.dataframe(bot, hide_index=True, width="stretch",
                             column_config={
                                 "Flow_1M": st.column_config.NumberColumn(format="%+.1f%%"),
                                 "Flow_Chg": st.column_config.NumberColumn(format="%+.1f pp"),
                                 "Acc_Pct": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%")})

        st.markdown("###### 📋 All sectors — click row")
        sv = sec.copy()
        if "Quadrant" in sv.columns:
            sv["Quadrant"] = sv.Quadrant.map(QICON)
        if "Flow_Chg" in sv.columns:
            sv = sv.sort_values("Flow_Chg", ascending=False)
        sec_cfg = {
            "Sector": st.column_config.TextColumn("Sector", pinned=True, width="medium"),
            "Quadrant": st.column_config.TextColumn("State", width="small"),
            "Acc_Pct": st.column_config.ProgressColumn("Acc %", min_value=0, max_value=100, format="%d%%"),
            "Stocks": st.column_config.NumberColumn("Stocks", format="%d"),
            "Flow_1M": st.column_config.NumberColumn("Flow 1M", format="%+.1f%%"),
            "Flow_Prev": st.column_config.NumberColumn("Flow prev 2M", format="%+.1f%%"),
            "Flow_Chg": st.column_config.NumberColumn("Flow Δ", format="%+.1f pp"),
            "Ret_1W": st.column_config.NumberColumn("Ret 1W", format="%+.1f%%"),
            "Ret_1M": st.column_config.NumberColumn("Ret 1M", format="%+.1f%%"),
            "Ret_3M": st.column_config.NumberColumn("Ret 3M", format="%+.1f%%"),
        }
        ev = st.dataframe(sv, hide_index=True, width="stretch",
                          height=min(560, 40 + 35 * len(sv)),
                          on_select="rerun", selection_mode="single-row", key="sec_tbl",
                          column_config=sec_cfg)
        if ev.selection.rows:
            chosen = sv.iloc[ev.selection.rows[0]].Sector
            sd = pool[pool.Sector == chosen].sort_values(["Score", "Deliv_Qty_X"], ascending=False)
            st.markdown(f"#### {chosen} — {len(sd)} stocks")
            open_sym = stock_table(sd, "sec", height=420) or open_sym

        with st.expander("🔍 Verify sector data"):
            sm = E.fetch_sector_map()
            st.write(f"**Sector map entries:** {len(sm)}")
            if len(sm) > 0 and isinstance(sm, dict):
                sm_df = pd.DataFrame(list(sm.items())[:20], columns=["Symbol", "Industry"])
                st.dataframe(sm_df, hide_index=True, use_container_width=True)
            unknown = pool[pool.Sector.isin(["Unknown", "unknown", "", "nan", "NaN"])]
            if not unknown.empty:
                st.warning(f"⚠️ {len(unknown)} stocks ka sector 'Unknown' hai")
            else:
                st.success("✅ Saare stocks ka sector mapped hai.")

# ---------------------------- Stock plan ---------------------------------- #
with tab3:
    if NEW_LISTINGS:
        with st.expander(f"🆕 Recently listed stocks ({len(NEW_LISTINGS)}) — 20 sessions se kam data", expanded=False):
            st.caption("In stocks pe 1M vs 3M comparison meaningful nahi hai (bahut kam data). "
                       "Fir bhi daily delivery %, net flow, bulk deals dekh sakte ho. "
                       "Search box me type karke inko bhi select kar sakte ho.")
            st.markdown(", ".join([f"`{s}`" for s in NEW_LISTINGS]))
    idx = ALL_SYMS.index("BAJAJHFL") if "BAJAJHFL" in ALL_SYMS else 0
    sym = st.selectbox("Stock (type karke search)", ALL_SYMS, index=idx)
    render_detail(sym, "tab")

# ----------------------------- Compare ------------------------------------ #
with tab4:
    pick = st.multiselect("Select up to 4 stocks", ALL_SYMS,
                          default=[s for s in ["BAJAJHFL", "BAJFINANCE"] if s in ALL_SYMS], max_selections=4)
    if pick:
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                            subplot_titles=("Delivery % (5-day smoothed)", "Cumulative net delivery flow",
                                            "Price rebased to 100"))
        for s in pick:
            gs = E.symbol_view(hist, s).tail(80)
            up, dn = gs.CLOSE_PRICE > gs.PREV_CLOSE, gs.CLOSE_PRICE < gs.PREV_CLOSE
            net = (gs.DELIV_QTY.where(up, 0) - gs.DELIV_QTY.where(dn, 0)).cumsum()
            fig.add_trace(go.Scatter(x=gs.Date, y=gs.DELIV_PER.rolling(5).mean(), name=s), row=1, col=1)
            fig.add_trace(go.Scatter(x=gs.Date, y=net, name=s, showlegend=False), row=2, col=1)
            fig.add_trace(go.Scatter(x=gs.Date, y=gs.CLOSE_PRICE / gs.CLOSE_PRICE.iloc[0] * 100,
                                     name=s, showlegend=False), row=3, col=1)
        fig.update_layout(height=820, template="plotly_dark", hovermode="x unified",
                          margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width="stretch", key="cmp_chart")
        cmp_cols = [c for c in ["Symbol", "Reentry", "Price", "Entry_Zone", "SL", "T1", "T2", "T3",
                                "Score", "Signal", "Buying_Status", "Buy_Weeks", "Setup", "Stage",
                                "Deliv_Qty_X", "Deliv_Per_Chg", "Net_Flow_1M", "Net_Flow_3M", "RS_1M",
                                "Deliv_Val_1M_Cr", "Bulk_Flag", "Bulk_Net_Cr"] if c in scr.columns]
        st.dataframe(scr[scr.Symbol.isin(pick)][cmp_cols], hide_index=True, width="stretch")

# ---------------------------- Bulk/Block Deals ---------------------------- #
with tab5:
    if deals is None or deals.empty:
        st.info("Aaj ke bulk/block deals NSE se load nahi ho paye. ~6-7 PM IST ke baad try karo.")
    else:
        st.markdown("### 📜 Aaj ke Bulk & Block Deals (NSE)")
        c1, c2, c3, c4 = st.columns(4)
        nb = int((deals.Deal_Type == "Bulk").sum()); nk = int((deals.Deal_Type == "Block").sum())
        buy_cr = float(deals[deals.Buy_Sell.str.startswith("B")].Value_Cr.sum())
        sell_cr = float(deals[~deals.Buy_Sell.str.startswith("B")].Value_Cr.sum())
        kpi(c1, "Bulk deals", f"{nb}", "Total entries")
        kpi(c2, "Block deals", f"{nk}", "Total entries")
        kpi(c3, "Total Buy",  f"₹{buy_cr:,.1f} Cr", "", "g")
        kpi(c4, "Total Sell", f"₹{sell_cr:,.1f} Cr", "", "r")
        st.markdown("---")
        f1, f2, f3 = st.columns(3)
        typ_f = f1.multiselect("Type", ["Bulk", "Block"], default=["Bulk", "Block"])
        side_f = f2.multiselect("Side", ["BUY", "SELL"], default=["BUY", "SELL"])
        min_cr = f3.slider("Min deal size (₹ Cr)", 0.0, 100.0, 0.0, 0.5)
        dv = deals[deals.Deal_Type.isin(typ_f) & deals.Buy_Sell.isin(side_f) & (deals.Value_Cr >= min_cr)]
        st.caption(f"{len(dv)} deals match filters")
        st.dataframe(A.deals_table(dv, limit=500), hide_index=True, width="stretch", height=600,
                     column_config={
                         "Value_Cr": st.column_config.NumberColumn("Value", format="₹%.2f Cr"),
                         "Qty":      st.column_config.NumberColumn("Qty", format="%d"),
                         "Price":    st.column_config.NumberColumn("Price", format="₹%.2f"),
                     })
        st.caption("Source: NSE bulk.csv + block.csv. Bulk = 0.5%+ volume ek client ne. "
                   "Block = 5 lakh+ shares ya ₹5 Cr+ single trade.")

if open_sym:
    detail_dialog(open_sym)
