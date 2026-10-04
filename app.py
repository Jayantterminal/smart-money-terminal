"""
app.py - Smart Money Terminal (v4)
All features: screener, sector rotation, stock plan, compare, bulk/block,
re-entry tracker, market breadth, FII/DII, insider trades, position sizing, Telegram,
last 5 days delivery verification table.
"""
import hashlib
from datetime import datetime

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


@st.cache_data(ttl=1800, show_spinner="Downloading NSE delivery + deals data (first load ~15 sec)...")
def load():
    hist, info = E.fetch_history(65)
    scr = E.compute_screener(hist, (), 0.0, E.fetch_sector_map()) if not hist.empty else pd.DataFrame()
    deals = pd.DataFrame(); insider = pd.DataFrame(); fiidii = None; breadth = {}
    if not scr.empty:
        try: deals = A.fetch_bulk_block_deals()
        except Exception: deals = pd.DataFrame()
        try: scr = A.enrich_screener(scr, hist, deals)
        except Exception: pass
        try: fiidii = A.fetch_fiidii()
        except Exception: fiidii = None
        try: insider = A.fetch_insider_trades(days_back=7)
        except Exception: insider = pd.DataFrame()
        try: breadth = E.market_breadth(hist, scr)
        except Exception: breadth = {}
    return hist, scr, info, E.now_ist(), deals, fiidii, insider, breadth


hist, scr, info, fetched, deals, fiidii, insider, breadth = load()
if hist.empty or scr.empty:
    st.error("NSE data could not be loaded. NSE may be blocking this server. "
             f"Network errors: {info['errors']}. Refresh after a few minutes.")
    st.stop()
if "Ret_3M" not in scr.columns:
    st.cache_data.clear()
    st.error("engine.py purana version hai. Naye files upload karo.")
    st.stop()

asof = hist.Date.max()

try:
    E.update_sl_hits(hist)
    scr = E.reentry_stats(scr, asof.date())
    E.log_screener_run(scr, asof.date())
except Exception:
    scr["Reentry"] = "🆕 First time"
    scr["Appearances_120D"] = 1
    scr["Days_Since_First"] = 0

ALL_SYMS = sorted(scr.Symbol.tolist())
NEW_LISTINGS = sorted(scr[scr.Is_New_Listing].Symbol.tolist()) if "Is_New_Listing" in scr.columns else []

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
BICON = {"Continuing": "🟢 Continuing", "Just started": "🔵 Just started",
         "Fading": "🟡 Fading", "Not buying": "⚪ Not buying"}
QICON = {"Leading": "🟢 Leading", "Improving": "🔵 Improving", "Weakening": "🟡 Weakening", "Lagging": "🔴 Lagging"}
QCOL = {"Leading": "#22c55e", "Improving": "#3b82f6", "Weakening": "#f59e0b", "Lagging": "#ef4444"}

# ------------------------------ sidebar ----------------------------------- #
with st.sidebar:
    st.markdown("### ⚙️ Controls")
    if st.button("🔄 Refresh data now"):
        st.cache_data.clear()
        st.rerun()
    universe = st.radio("Universe", ["My watchlist", "All liquid NSE stocks"], index=1)
    min_turn = st.slider("Min avg turnover (₹ Cr/day)", 0, 100, 5)
    extras = st.multiselect("Add stocks to My watchlist", ALL_SYMS, placeholder="Type symbol...")

    st.markdown("---")
    st.markdown("### 🔔 Telegram Alerts")
    with st.expander("Setup (ek baar karo)", expanded=False):
        st.markdown("""
**1.** Telegram pe **@BotFather** ko message karo → `/newbot` → naam do
**2.** Bot token milega (jaise `1234:ABC...`) → neeche paste karo
**3.** Apne bot ko **@userinfobot** se apna chat_id milega → neeche paste karo
**4.** "Save token" dabao

**Daily 6:30 PM auto-alert ke liye** GitHub Actions setup chahiye (optional). Abhi "Send now" button se manual alert ja sakta hai.
        """)
    tg_token = st.text_input("Bot Token", value=st.session_state.get("tg_token", ""), type="password")
    tg_chat  = st.text_input("Chat ID",   value=st.session_state.get("tg_chat", ""))
    if st.button("💾 Save token"):
        st.session_state["tg_token"] = tg_token
        st.session_state["tg_chat"]  = tg_chat
        st.success("Saved for this session.")
    st.caption("Token sirf is session me yaad rehta hai. Multi-device chahiye to Streamlit Cloud → Secrets me daalo.")

    st.caption("Source: NSE bhavcopy + bulk/block + FII/DII (EOD, ~6-7 PM IST). "
               "Analysis tool only, not investment advice.")

# ---- topbar ---- #
st.markdown(f"""
<div class="topbar">
 <div class="brand">SMART<span>MONEY</span> TERMINAL</div>
 <div class="meta">Data as of <b>{asof:%d %b %Y}</b> (EOD) &nbsp;|&nbsp;
 Fetched <b>{fetched:%d %b %Y, %I:%M %p} IST</b> &nbsp;|&nbsp; Sessions: <b>{info['days']}</b>
 &nbsp;|&nbsp; {breadth.get('nifty_trend','')}</div>
</div>""", unsafe_allow_html=True)
if info["errors"]:
    st.warning(f"{info['errors']} din ka NSE data download nahi ho paya - Refresh karke dekho.")

# ---- FII/DII strip ---- #
if fiidii:
    c1, c2, c3, c4 = st.columns(4)
    fnet = fiidii.get("fii_net", 0); dnet = fiidii.get("dii_net", 0)
    kpi(c1, "FII net (₹ Cr)", f"{fnet:+,.0f}", f"Buy {fiidii.get('fii_buy',0):,.0f} | Sell {fiidii.get('fii_sell',0):,.0f}",
        "g" if fnet > 0 else "r")
    kpi(c2, "DII net (₹ Cr)", f"{dnet:+,.0f}", f"Buy {fiidii.get('dii_buy',0):,.0f} | Sell {fiidii.get('dii_sell',0):,.0f}",
        "g" if dnet > 0 else "r")
    kpi(c3, "Nifty proxy", f"{breadth.get('nifty_price','-')}",
        f"20DMA {breadth.get('nifty_20dma','-')} | 50DMA {breadth.get('nifty_50dma','-')}")
    kpi(c4, "Breadth (% >50DMA)", f"{breadth.get('breadth_pct_50','-')}%",
        f"20DMA: {breadth.get('breadth_pct_20','-')}% | 200DMA: {breadth.get('breadth_pct_200','-')}%")

_warn = []
if info.get("days", 0) < 40:
    _warn.append(f"Sirf {info['days']} sessions mile — 3M comparison weak ho sakta hai.")
try:
    if scr.Deliv_Per_1M.gt(100).any():
        _warn.append(f"{int(scr.Deliv_Per_1M.gt(100).sum())} stocks me delivery % > 100 — NSE source suspicious.")
    if (scr.Price <= 0).any():
        _warn.append("Kuch stocks ka price 0 hai — bhavcopy row corrupt.")
    if "Has_Split_Adjust" in scr.columns and scr.Has_Split_Adjust.any():
        _warn.append(f"{int(scr.Has_Split_Adjust.sum())} stocks me recent split/bonus detect hua — unka Score/ratios unreliable.")
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
def render_detail(sym, k):
    r = scr[scr.Symbol == sym].iloc[0]
    g = E.symbol_view(hist, sym).tail(80)
    st.markdown(f"### {sym}  <span style='color:#94a3b8;font-size:.9rem'>{r.Sector}</span>", unsafe_allow_html=True)
    if r.get("Is_New_Listing", False):
        st.warning(f"🆕 **Recently listed** — sirf {len(g)} sessions. 1M vs 3M comparison weak hai.")
    if r.get("Has_Split_Adjust", False):
        st.warning("⚠️ **Split/bonus detect hua hai.** Delivered qty ratios aur Score unreliable ho sakte hain.")

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

    # Turnover + Trades row
    c3 = st.columns(4)
    to1 = r.get("Turnover_1M_Cr", 0); tox = r.get("Turnover_X", 0)
    tr1 = r.get("Trades_1M_Avg", 0); tpc = r.get("Trades_per_Cr", 0)
    cva = r.get("Close_vs_Avg", 0)
    kpi(c3[0], "Turnover 1M", f"₹{to1:,.1f} Cr",
        f"{tox:.2f}x vs prev 2M" if tox else "-",
        "g" if tox > 1.1 else "r" if tox < 0.9 else "")
    kpi(c3[1], "Trades/day (1M)", f"{int(tr1):,}", "Average daily trades")
    kpi(c3[2], "Trades per ₹ Cr", f"{tpc:.1f}",
        "Kam = institutional" if 0 < tpc < 500 else ("Zyada = retail" if tpc >= 500 else "-"),
        "g" if 0 < tpc < 500 else "y" if tpc < 2000 else "r")
    kpi(c3[3], "Close vs Avg price", f"{cva:+.2f}%",
        "Buyers end me active" if cva > 0 else "Sellers end me active",
        "g" if cva > 0.2 else "r" if cva < -0.2 else "")

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
    if tox:
        why.append(f"Turnover 1M: ₹{to1:,.1f} Cr ({tox:.2f}x vs prev 2M) | "
                   f"Trades/day: {int(tr1):,} | Trades per ₹Cr: {tpc:.1f} "
                   f"({'institutional' if 0 < tpc < 500 else 'retail' if tpc >= 500 else '-'}) | "
                   f"Close vs Avg: {cva:+.2f}%.")
    why.append(f"Fresh activity: <b>{FICON[r.Fresh]}</b> | last 5 days: {r.Last5} | "
               f"aaj ki delivered qty 3M avg ka {r.Today_X:.2f}x.")
    if pd.notna(rs):
        why.append(f"Relative strength 1M vs Nifty: <b>{rs:+.1f}%</b> "
                   f"({'outperforming' if rs > 0 else 'underperforming'}).")
    bk_net = r.get("Bulk_Net_Cr", 0)
    if abs(bk_net) > 0.01:
        why.append(f"<b>Bulk/Block today: ₹{bk_net:+,.2f} Cr net</b> ({int(r.get('Deals_Today',0))} deals).")
    if str(rflag).startswith("🔁"):
        why.append(f"<b>Re-entry:</b> {rflag} — pehle bhi aaya tha, history neeche.")
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

    # -------- Last 5 days delivery data (verify) --------
    try:
        last_n = min(5, len(g))
        tbl = g.tail(last_n).copy()
        tbl = tbl.iloc[::-1].reset_index(drop=True)
        tbl["Date"] = pd.to_datetime(tbl["Date"]).dt.strftime("%a, %d %b %Y")
        tbl["Prev_Close"] = pd.to_numeric(tbl["PREV_CLOSE"], errors="coerce").round(2)
        tbl["Close"] = pd.to_numeric(tbl["CLOSE_PRICE"], errors="coerce").round(2)
        tbl["Chg_%"] = ((tbl["Close"] / tbl["Prev_Close"] - 1) * 100).round(2)
        tbl["Deliv_Qty"] = pd.to_numeric(tbl["DELIV_QTY"], errors="coerce").fillna(0).astype(int)
        tbl["Total_Qty"] = pd.to_numeric(tbl["TTL_TRD_QNTY"], errors="coerce").fillna(0).astype(int)
        tbl["Deliv_%"] = pd.to_numeric(tbl["DELIV_PER"], errors="coerce").round(2)

        try:
            dp_3m = float(pd.to_numeric(g["DELIV_PER"], errors="coerce").tail(63).head(42).mean())
        except Exception:
            dp_3m = 0.0
        try:
            dq_3m = float(pd.to_numeric(g["DELIV_QTY"], errors="coerce").tail(63).head(42).mean())
        except Exception:
            dq_3m = 0.0

        st.markdown("#### 📋 Last 5 days delivery data (verify)")
        show_cols = ["Date", "Prev_Close", "Close", "Chg_%", "Deliv_Qty", "Total_Qty", "Deliv_%"]
        st.dataframe(
            tbl[show_cols], hide_index=True, width="stretch",
            column_config={
                "Prev_Close": st.column_config.NumberColumn("Prev Close", format="₹%.2f"),
                "Close":      st.column_config.NumberColumn("Close", format="₹%.2f"),
                "Chg_%":      st.column_config.NumberColumn("Chg %", format="%+.2f%%"),
                "Deliv_Qty":  st.column_config.NumberColumn("Deliv Qty", format="%d"),
                "Total_Qty":  st.column_config.NumberColumn("Total Qty", format="%d"),
                "Deliv_%":    st.column_config.NumberColumn("Deliv %", format="%.2f%%"),
            })
        st.caption(f"**Reference averages (previous 2M):**  "
                   f"Deliv Qty: **{int(dq_3m):,}**  |  Deliv %: **{dp_3m:.2f}%**  —  "
                   f"ye numbers NSE bhavcopy se direct aate hain, koi calculation nahi.")
    except Exception as ex:
        st.warning(f"Last 5 days table error: {ex}")

    wf = E.weekly_flows(g, 12)
    fig2 = go.Figure(go.Bar(x=[d.strftime("%d %b") for d, _ in wf], y=[f for _, f in wf],
                            marker_color=["#22c55e" if f > 0 else "#ef4444" for _, f in wf]))
    fig2.update_layout(height=280, template="plotly_dark", margin=dict(l=10, r=10, t=40, b=10),
                       title="Weekly net delivery buying - last 12 weeks")
    st.plotly_chart(fig2, width="stretch", key=f"{k}_wk")

    rh = E.reentry_history(sym, limit=30)
    if not rh.empty:
        st.markdown("#### 🔁 Re-entry history")
        st.dataframe(rh, hide_index=True, width="stretch",
                     column_config={"Price": st.column_config.NumberColumn(format="₹%.2f"),
                                    "Entry": st.column_config.NumberColumn(format="₹%.2f"),
                                    "SL": st.column_config.NumberColumn(format="₹%.2f"),
                                    "SL_Hit": st.column_config.CheckboxColumn("SL hit?")})

    dsub = deals[deals.Symbol == sym] if deals is not None and not deals.empty else pd.DataFrame()
    if not dsub.empty:
        st.markdown("#### 📜 Bulk / Block deals (today)")
        st.dataframe(A.deals_table(dsub, limit=50), hide_index=True, width="stretch",
                     column_config={"Value_Cr": st.column_config.NumberColumn("Value", format="₹%.2f Cr"),
                                    "Qty": st.column_config.NumberColumn(format="%d"),
                                    "Price": st.column_config.NumberColumn(format="₹%.2f")})

    isub = insider[insider.Symbol == sym] if insider is not None and not insider.empty else pd.DataFrame()
    if not isub.empty:
        st.markdown("#### 🕵️ Insider / Promoter trades (last 7 days)")
        st.dataframe(isub, hide_index=True, width="stretch",
                     column_config={"Value_Cr": st.column_config.NumberColumn(format="₹%.2f Cr"),
                                    "Qty": st.column_config.NumberColumn(format="%d")})


@st.dialog("Stock detail", width="large")
def detail_dialog(sym):
    render_detail(sym, "dlg")


TABLE_COLS = ["Symbol", "Reentry", "Is_New_Listing", "Price", "Entry_Zone", "Entry_Status", "SL", "T1", "T2", "T3",
              "Score", "Signal", "Fresh", "Last5", "Buying_Status", "Buy_Weeks", "Setup", "Stage",
              "Deliv_Qty_X", "Today_X", "Deliv_Per_Chg", "Net_Flow_1M", "Deliv_Per_1M", "Deliv_Per_3M",
              "Acc_Days", "Range_Pct", "Chg_Pct", "RS_1M", "Deliv_Val_1M_Cr", "Deliv_Val_3M_Cr",
              "Turnover_1M_Cr", "Turnover_X", "Trades_1M_Avg", "Trades_per_Cr", "Close_vs_Avg",
              "Bulk_Flag", "Bulk_Net_Cr", "Deals_Today", "Appearances_120D", "Days_Since_First", "Sector"]
TABLE_CFG = {
    "Symbol": st.column_config.TextColumn("Symbol", pinned=True),
    "Reentry": st.column_config.TextColumn("Re-entry"),
    "Is_New_Listing": st.column_config.CheckboxColumn("🆕 New", help="Recently listed — <20 sessions."),
    "Price": st.column_config.NumberColumn("Price", format="₹%.2f"),
    "Entry_Zone": st.column_config.TextColumn("Entry zone (₹)"),
    "Entry_Status": st.column_config.TextColumn("Price vs zone"),
    "SL": st.column_config.NumberColumn("SL", format="₹%.2f"),
    "T1": st.column_config.NumberColumn("T1", format="₹%.2f"),
    "T2": st.column_config.NumberColumn("T2", format="₹%.2f"),
    "T3": st.column_config.NumberColumn("T3", format="₹%.2f"),
    "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
    "Fresh": st.column_config.TextColumn("Fresh activity"),
    "Last5": st.column_config.TextColumn("Last 5 days"),
    "Buy_Weeks": st.column_config.NumberColumn("Buy weeks /4", format="%d"),
    "Deliv_Qty_X": st.column_config.NumberColumn("Deliv qty 1M÷3M", format="%.2fx"),
    "Today_X": st.column_config.NumberColumn("Today ÷ 3M avg", format="%.2fx"),
    "Deliv_Per_Chg": st.column_config.NumberColumn("Deliv % Δ", format="%+.1f pp"),
    "Net_Flow_1M": st.column_config.NumberColumn("Net flow 1M", format="%+.0f%%"),
    "Deliv_Per_1M": st.column_config.NumberColumn("Deliv % 1M", format="%.1f%%"),
    "Deliv_Per_3M": st.column_config.NumberColumn("Deliv % prev 2M", format="%.1f%%"),
    "Acc_Days": st.column_config.NumberColumn("Acc days /21", format="%d"),
    "Range_Pct": st.column_config.NumberColumn("30D range", format="%.1f%%"),
    "Chg_Pct": st.column_config.NumberColumn("Chg %", format="%.2f%%"),
    "RS_1M": st.column_config.NumberColumn("RS vs Nifty 1M", format="%+.1f%%"),
    "Deliv_Val_1M_Cr": st.column_config.NumberColumn("Deliv val 1M", format="₹%.1f Cr"),
    "Deliv_Val_3M_Cr": st.column_config.NumberColumn("Deliv val prev 2M", format="₹%.1f Cr"),
    "Turnover_1M_Cr": st.column_config.NumberColumn("Turnover 1M", format="₹%.1f Cr",
                                                    help="Last 1 mahine ka total turnover (₹ Cr me). NSE official data."),
    "Turnover_X": st.column_config.NumberColumn("Turnover 1M÷3M", format="%.2fx",
                                                help="1M avg daily turnover ÷ prev 2M avg. Paisa flow badh raha?"),
    "Trades_1M_Avg": st.column_config.NumberColumn("Trades/day (1M)", format="%d",
                                                   help="Roz kitne trades. Bahut zyada = retail frenzy, kam = institutional."),
    "Trades_per_Cr": st.column_config.NumberColumn("Trades/₹Cr", format="%.1f",
                                                   help="Kam value = big players (few trades, high value). "
                                                        "Zyada = retail (many small trades)."),
    "Close_vs_Avg": st.column_config.NumberColumn("Close vs Avg %", format="%+.2f%%",
                                                  help="Positive = buyers ne end me kharida (bullish). "
                                                       "Negative = sellers aggressive (bearish)."),
    "Bulk_Flag": st.column_config.TextColumn("Bulk/Block today"),
    "Bulk_Net_Cr": st.column_config.NumberColumn("Bulk net", format="₹%+.2f Cr"),
    "Deals_Today": st.column_config.NumberColumn("Deals today", format="%d"),
    "Appearances_120D": st.column_config.NumberColumn("Appears /120D", format="%d"),
    "Days_Since_First": st.column_config.NumberColumn("Days since 1st", format="%d"),
}


def stock_table(d, name, height=560):
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
    lk = f"last_{name}"
    if not rows:
        st.session_state[lk] = None; return None
    sym = view.iloc[rows[0]].Symbol
    if sym != st.session_state.get(lk):
        st.session_state[lk] = sym; return sym
    return None


tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🔎 Screener", "🔄 Sector", "🎯 Stock Plan", "⚖️ Compare",
    "📜 Bulk/Block", "🌊 Market Breadth", "💰 Position Sizing", "🔔 Telegram",
])
open_sym = None

# ---------------------------- Tab 1: Screener ----------------------------- #
with tab1:
    QUICK = {
        "strong": ("Strong acc.", pool[pool.Signal == "Strong Accumulation"]),
        "acc":    ("Accumulation", pool[pool.Signal == "Accumulation"]),
        "cont":   ("Buying continuing", pool[pool.Buying_Status == "Continuing"]),
        "fresh":  ("Fresh activity", pool[pool.Fresh.isin(FRESH)].sort_values("Last5_X", ascending=False)),
        "reentry":("🔁 Re-entry", pool[pool.Reentry.astype(str).str.startswith("🔁", na=False)]),
        "dist":   ("Distribution", pool[pool.Signal == "Distribution"]),
    }
    if "quick" not in st.session_state: st.session_state.quick = None

    def set_quick(k):
        st.session_state.quick = None if (k is None or st.session_state.quick == k) else k

    with st.container(key="kpis"):
        kc = st.columns(7)
        kc[0].button(f"Stocks scanned\n{len(pool)}", key="q_all", on_click=set_quick, args=(None,),
                     type="primary" if st.session_state.quick is None else "secondary")
        labels = {"strong":"🟢 Strong acc.","acc":"🟢 Accumulation","cont":"🟢 Buying cont.",
                  "fresh":"⚡ Fresh","reentry":"🔁 Re-entry","dist":"🔴 Distribution"}
        for i, k in enumerate(QUICK, start=1):
            extra = f"  ({int((pool.Fresh=='Spike today').sum())} today)" if k == "fresh" else ""
            kc[i].button(f"{labels[k]}\n{len(QUICK[k][1])}{extra}", key=f"q_{k}", on_click=set_quick, args=(k,),
                         type="primary" if st.session_state.quick == k else "secondary")

    q = st.multiselect("🔍 Search stock", ALL_SYMS, placeholder="e.g. BAJAJHFL")

    PRESETS = {"Balanced": (1.2, 3), "Strict": (1.5, 6), "Loose": (1.0, 0), "Custom": None}
    p1, p2 = st.columns([1, 2])
    preset = p1.selectbox("Scan preset", list(PRESETS))
    if PRESETS[preset] is None:
        s1, s2 = p2.columns(2)
        min_x = s1.slider("Min delivery qty × (1M÷3M)", 0.5, 4.0, 1.2, 0.1)
        min_pp = s2.slider("Min delivery % rise (pp)", -10, 30, 3)
    else:
        min_x, min_pp = PRESETS[preset]
        p2.info(f"1M delivered qty ≥ **{min_x}x** | 1M delivery % ≥ **+{min_pp}pp**")

    h1, h2, h3 = st.columns(3)
    only_acc = h1.checkbox("Sirf Accumulation / Strong", value=True)
    hide_ext = h2.checkbox("Extended chhupao", value=True)
    only_bulk = h3.checkbox("Sirf Bulk/Block BUY wale", value=False)

    f = st.columns(4)
    sig = f[0].multiselect("Signal", SIGNALS, placeholder="All")
    stg = f[1].multiselect("Stage", STAGES, placeholder="All")
    setup_sel = f[2].multiselect("Setup", SETUPS, placeholder="All")
    buy_sel = f[3].multiselect("Buying status", BUYS, placeholder="All")

    g2 = st.columns(4)
    sec_sel = g2[0].multiselect("Sector", sorted(pool.Sector.unique()), placeholder="All")
    min_wk = g2[1].slider("Min buying weeks", 0, 4, 0)
    fresh_sel = g2[2].multiselect("Fresh activity", FRESH_SEL, placeholder="All")
    reentry_sel = g2[3].multiselect("Re-entry filter", REENTRY_OPTS, placeholder="All")

    fresh_picks = []
    if fresh_sel:
        fresh_picks = FRESH if "All fresh" in fresh_sel else [x for x in fresh_sel if x in FRESH]
    has_fresh = bool(fresh_picks)

    funnel = [("Universe", len(pool))]
    quick = st.session_state.quick
    if q:
        d = scr[scr.Symbol.isin(q)]; funnel = [("Search", len(d))]
    elif quick:
        d = QUICK[quick][1]
        st.success(f"Showing: **{QUICK[quick][0]}** - {len(d)} stocks.")
        funnel = []
    else:
        d = pool
        if only_bulk and "Bulk_Flag" in d.columns:
            d = d[d.Bulk_Flag.astype(str).str.contains("Buy", na=False)]
            funnel.append(("Bulk buy only", len(d)))
        if reentry_sel:
            d = d[d.Reentry.isin(reentry_sel)]; funnel.append(("Re-entry", len(d)))
        if has_fresh:
            d = d[d.Fresh.isin(fresh_picks)]; funnel.append(("Fresh", len(d)))
        elif sig:
            d = d[d.Signal.isin(sig)]; funnel.append(("Signal", len(d)))
        elif only_acc:
            d = d[d.Signal.isin(["Strong Accumulation", "Accumulation"])]
            funnel.append(("Acc signal", len(d)))
        if stg:
            d = d[d.Stage.isin(stg)]; funnel.append(("Stage", len(d)))
        elif hide_ext:
            d = d[d.Stage != STAGES[3]]; funnel.append(("Extended hidden", len(d)))
        if not has_fresh:
            d = d[(d.Deliv_Qty_X >= min_x) & (d.Deliv_Per_Chg >= min_pp)]
            funnel.append(("Scan preset", len(d)))
        if setup_sel: d = d[d.Setup.isin(setup_sel)]
        if buy_sel:   d = d[d.Buying_Status.isin(buy_sel)]
        if sec_sel:   d = d[d.Sector.isin(sec_sel)]
        d = d[d.Buy_Weeks >= min_wk]
        funnel.append(("Final", len(d)))
        if has_fresh: d = d.sort_values("Last5_X", ascending=False)
    st.caption(f"{len(d)} stocks | {asof:%d %b %Y}")
    if funnel:
        st.caption("🔻 " + " → ".join(f"{n}: **{c}**" for n, c in funnel))

    open_sym = stock_table(d, "scr") or open_sym
    st.download_button("⬇️ CSV", d.to_csv(index=False).encode(), f"accumulation_{asof:%Y%m%d}.csv", "text/csv")

# ---------------------------- Tab 2: Sector ------------------------------- #
with tab2:
    try:
        sec = E.sector_rotation(pool)
    except Exception as ex:
        sec = pd.DataFrame(); st.error(f"Sector error: {ex}")
    if sec is None or sec.empty:
        st.warning("Sector data nahi mila.")
    else:
        qc = sec.groupby("Quadrant").size().to_dict() if "Quadrant" in sec.columns else {}
        qf = sec.groupby("Quadrant").Flow_1M.mean().to_dict() if "Quadrant" in sec.columns else {}
        kc = st.columns(4)
        for i, q in enumerate(["Leading", "Improving", "Weakening", "Lagging"]):
            n = int(qc.get(q, 0)); fval = qf.get(q, 0.0)
            cls = {"Leading": "g", "Improving": "g", "Weakening": "y", "Lagging": "r"}[q]
            kpi(kc[i], f"{QICON[q]}", f"{n} sectors", f"Avg flow {fval:+.1f}%" if n else "-", cls)

        st.markdown("##### 🧭 Rotation map")
        try:
            xs = sec.Flow_1M.replace([np.inf, -np.inf], np.nan).dropna()
            ys = sec.Flow_Chg.replace([np.inf, -np.inf], np.nan).dropna()
            if not xs.empty and not ys.empty:
                pad_x = max(abs(xs.min()), abs(xs.max())) * 1.15 + 5
                pad_y = max(abs(ys.min()), abs(ys.max())) * 1.15 + 3
                x0, x1 = -pad_x, pad_x; y0, y1 = -pad_y, pad_y
                fig = go.Figure()
                for xA, xB, yA, yB, col, label in [
                    (0, x1, 0, y1, "#22c55e", "LEADING"), (x0, 0, 0, y1, "#3b82f6", "IMPROVING"),
                    (0, x1, y0, 0, "#f59e0b", "WEAKENING"), (x0, 0, y0, 0, "#ef4444", "LAGGING"),
                ]:
                    fig.add_shape(type="rect", x0=xA, x1=xB, y0=yA, y1=yB,
                                  fillcolor=col, opacity=0.055, line_width=0, layer="below")
                    fig.add_annotation(x=(xA+xB)/2, y=yB*0.92, text=label, showarrow=False,
                                       font=dict(size=11, color=col), opacity=0.6)
                for qn, col in QCOL.items():
                    s = sec[sec.Quadrant == qn]
                    if s.empty: continue
                    cc = []
                    for cn in ["Acc_Pct","Stocks","Fresh","Deliv_Qty_X","Ret_1M"]:
                        cc.append(s[cn].values if cn in s.columns else np.zeros(len(s)))
                    fig.add_trace(go.Scatter(
                        x=s.Flow_1M, y=s.Flow_Chg, mode="markers+text", text=s.Sector,
                        textposition="top center", textfont=dict(size=10), name=QICON[qn],
                        marker=dict(size=np.clip(s.Stocks*1.2+12, 14, 44) if "Stocks" in s.columns else 20,
                                    color=col, opacity=0.85, line=dict(color="#0f172a", width=1.5)),
                        customdata=np.stack(cc, axis=1),
                        hovertemplate="<b>%{text}</b><br>Flow 1M: %{x:+.1f}%<br>Δ vs prev 2M: %{y:+.1f} pp<br>"
                                      "Acc: %{customdata[0]}%% of %{customdata[1]}<extra></extra>"))
                fig.add_vline(x=0, line_color="#475569"); fig.add_hline(y=0, line_color="#475569")
                fig.update_layout(height=560, template="plotly_dark",
                                  margin=dict(l=10,r=10,t=10,b=10),
                                  xaxis=dict(title="Net buy flow 1M (%)", range=[x0,x1]),
                                  yaxis=dict(title="Δ vs prev 2M (pp)", range=[y0,y1]),
                                  legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"))
                st.plotly_chart(fig, width="stretch", key="sec_chart")
        except Exception as ex:
            st.warning(f"Chart: {ex}")

        sv = sec.copy()
        if "Quadrant" in sv.columns: sv["Quadrant"] = sv.Quadrant.map(QICON)
        if "Flow_Chg" in sv.columns: sv = sv.sort_values("Flow_Chg", ascending=False)
        cfg = {"Sector": st.column_config.TextColumn(pinned=True),
               "Acc_Pct": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%"),
               "Flow_1M": st.column_config.NumberColumn(format="%+.1f%%"),
               "Flow_Prev": st.column_config.NumberColumn(format="%+.1f%%"),
               "Flow_Chg": st.column_config.NumberColumn(format="%+.1f pp"),
               "Ret_1W": st.column_config.NumberColumn(format="%+.1f%%"),
               "Ret_1M": st.column_config.NumberColumn(format="%+.1f%%"),
               "Ret_3M": st.column_config.NumberColumn(format="%+.1f%%")}
        ev = st.dataframe(sv, hide_index=True, width="stretch",
                          height=min(560, 40 + 35*len(sv)),
                          on_select="rerun", selection_mode="single-row", key="sec_tbl",
                          column_config=cfg)
        if ev.selection.rows:
            chosen = sv.iloc[ev.selection.rows[0]].Sector
            sd = pool[pool.Sector == chosen].sort_values(["Score","Deliv_Qty_X"], ascending=False)
            st.markdown(f"#### {chosen} — {len(sd)} stocks")
            open_sym = stock_table(sd, "sec", height=420) or open_sym

# ---------------------------- Tab 3: Stock Plan --------------------------- #
with tab3:
    if NEW_LISTINGS:
        with st.expander(f"🆕 Recently listed ({len(NEW_LISTINGS)})", expanded=False):
            st.markdown(", ".join([f"`{s}`" for s in NEW_LISTINGS]))
    idx = ALL_SYMS.index("BAJAJHFL") if "BAJAJHFL" in ALL_SYMS else 0
    sym = st.selectbox("Stock (type karke search)", ALL_SYMS, index=idx)
    render_detail(sym, "tab")

# ---------------------------- Tab 4: Compare ------------------------------ #
with tab4:
    pick = st.multiselect("Select up to 4 stocks", ALL_SYMS,
                          default=[s for s in ["BAJAJHFL","BAJFINANCE"] if s in ALL_SYMS],
                          max_selections=4)
    if pick:
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                            subplot_titles=("Delivery % (5-day smoothed)", "Cumulative net delivery",
                                            "Price rebased to 100"))
        for s in pick:
            gs = E.symbol_view(hist, s).tail(80)
            up, dn = gs.CLOSE_PRICE > gs.PREV_CLOSE, gs.CLOSE_PRICE < gs.PREV_CLOSE
            net = (gs.DELIV_QTY.where(up,0) - gs.DELIV_QTY.where(dn,0)).cumsum()
            fig.add_trace(go.Scatter(x=gs.Date, y=gs.DELIV_PER.rolling(5).mean(), name=s), row=1, col=1)
            fig.add_trace(go.Scatter(x=gs.Date, y=net, name=s, showlegend=False), row=2, col=1)
            fig.add_trace(go.Scatter(x=gs.Date, y=gs.CLOSE_PRICE/gs.CLOSE_PRICE.iloc[0]*100,
                                     name=s, showlegend=False), row=3, col=1)
        fig.update_layout(height=820, template="plotly_dark", hovermode="x unified",
                          margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig, width="stretch", key="cmp_chart")
        cc = [c for c in ["Symbol","Reentry","Price","Entry_Zone","SL","T1","T2","T3","Score","Signal",
                          "Buying_Status","Buy_Weeks","Setup","Stage","Deliv_Qty_X","Deliv_Per_Chg",
                          "Net_Flow_1M","RS_1M","Turnover_1M_Cr","Turnover_X","Trades_per_Cr",
                          "Close_vs_Avg","Bulk_Flag","Bulk_Net_Cr"] if c in scr.columns]
        st.dataframe(scr[scr.Symbol.isin(pick)][cc], hide_index=True, width="stretch")

# ---------------------------- Tab 5: Bulk/Block --------------------------- #
with tab5:
    if deals is None or deals.empty:
        st.info("Aaj ke bulk/block deals NSE se load nahi ho paye. ~6-7 PM IST ke baad try karo.")
    else:
        st.markdown("### 📜 Aaj ke Bulk & Block Deals")
        c1, c2, c3, c4 = st.columns(4)
        nb = int((deals.Deal_Type=="Bulk").sum()); nk = int((deals.Deal_Type=="Block").sum())
        buy_cr = float(deals[deals.Buy_Sell.str.startswith("B")].Value_Cr.sum())
        sell_cr = float(deals[~deals.Buy_Sell.str.startswith("B")].Value_Cr.sum())
        kpi(c1,"Bulk deals",f"{nb}","", ""); kpi(c2,"Block deals",f"{nk}","", "")
        kpi(c3,"Total Buy",f"₹{buy_cr:,.1f} Cr","","g"); kpi(c4,"Total Sell",f"₹{sell_cr:,.1f} Cr","","r")
        st.markdown("---")
        f1,f2,f3 = st.columns(3)
        typ_f = f1.multiselect("Type",["Bulk","Block"],default=["Bulk","Block"])
        side_f = f2.multiselect("Side",["BUY","SELL"],default=["BUY","SELL"])
        min_cr = f3.slider("Min ₹ Cr", 0.0, 100.0, 0.0, 0.5)
        dv = deals[deals.Deal_Type.isin(typ_f) & deals.Buy_Sell.isin(side_f) & (deals.Value_Cr>=min_cr)]
        st.caption(f"{len(dv)} deals match")
        st.dataframe(A.deals_table(dv, limit=500), hide_index=True, width="stretch", height=600,
                     column_config={"Value_Cr": st.column_config.NumberColumn(format="₹%.2f Cr"),
                                    "Qty": st.column_config.NumberColumn(format="%d"),
                                    "Price": st.column_config.NumberColumn(format="₹%.2f")})

# ---------------------------- Tab 6: Market Breadth ----------------------- #
with tab6:
    st.markdown("### 🌊 Market Breadth + Nifty Trend")
    if not breadth:
        st.warning("Breadth data compute nahi ho paya.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        kpi(c1, "Nifty trend", breadth.get("nifty_trend","-"), "", "")
        kpi(c2, "Above 20 DMA", f"{breadth.get('above_20dma',0)}/{breadth.get('total',0)}",
            f"{breadth.get('breadth_pct_20',0)}%", "g" if breadth.get('breadth_pct_20',0)>50 else "r")
        kpi(c3, "Above 50 DMA", f"{breadth.get('above_50dma',0)}/{breadth.get('total',0)}",
            f"{breadth.get('breadth_pct_50',0)}%", "g" if breadth.get('breadth_pct_50',0)>50 else "r")
        kpi(c4, "Above 200 DMA", f"{breadth.get('above_200dma',0)}/{breadth.get('total',0)}",
            f"{breadth.get('breadth_pct_200',0)}%", "g" if breadth.get('breadth_pct_200',0)>50 else "r")

        st.markdown("#### Sentiment interpretation")
        pct50 = breadth.get("breadth_pct_50", 0)
        if pct50 >= 70:
            st.success("🟢 **Strong bullish market** — 70%+ stocks above 50DMA. Risk-on. Accumulation picks me confidence zyada.")
        elif pct50 >= 50:
            st.info("🟡 **Neutral to mildly bullish** — Selective stock picking. Sector rotation ka dhyan rakho.")
        elif pct50 >= 30:
            st.warning("🟡 **Cautious** — 30-50% stocks above 50DMA. Position size chhota rakho.")
        else:
            st.error("🔴 **Bearish market** — 70%+ stocks 50DMA ke neeche. Cash me rehna better. Accumulation picks bhi risky.")

        adv = breadth.get("advances",0); dec = breadth.get("declines",0)
        st.markdown(f"**Today:** Advances: {adv}  |  Declines: {dec}  |  A/D ratio: {breadth.get('ad_ratio',0)}%")
        st.markdown(f"**Nifty proxy:** ₹{breadth.get('nifty_price','-')}  |  "
                    f"20DMA ₹{breadth.get('nifty_20dma','-')}  |  "
                    f"50DMA ₹{breadth.get('nifty_50dma','-')}  |  "
                    f"200DMA ₹{breadth.get('nifty_200dma','-')}")

        if insider is not None and not insider.empty:
            st.markdown("---")
            st.markdown("### 🕵️ Insider / Promoter Trades (last 7 days)")
            st.caption("Promoter ya director ne khud kharida = strong bullish signal. "
                       "Ye NSE public disclosure hai. Kabhi NSE load nahi hota to blank aayega.")
            filt = insider.copy()
            filt["Buy_Sell"] = filt["Buy_Sell"].astype(str).str.upper()
            f1, f2 = st.columns(2)
            sym_f = f1.multiselect("Symbol", sorted(filt.Symbol.unique()), placeholder="All")
            side_f = f2.multiselect("Side", ["BUY","SELL"], default=["BUY","SELL"])
            if sym_f: filt = filt[filt.Symbol.isin(sym_f)]
            if side_f: filt = filt[filt.Buy_Sell.isin(side_f)]
            st.dataframe(filt.head(500), hide_index=True, width="stretch",
                         column_config={"Value_Cr": st.column_config.NumberColumn(format="₹%.2f Cr"),
                                        "Qty": st.column_config.NumberColumn(format="%d")})
        else:
            st.info("Insider trading data aaj available nahi hai (NSE API slow/block). "
                    "Kal try karo.")

# ---------------------------- Tab 7: Position Sizing ---------------------- #
with tab7:
    st.markdown("### 💰 Position Sizing Calculator")
    st.caption("Capital + Risk % + Entry + SL → kitne shares kharido, max loss kitna.")
    c1, c2, c3 = st.columns(3)
    capital = c1.number_input("Total capital (₹)", 1000, 100_000_000, 100_000, 1000)
    risk_pct = c2.slider("Risk per trade (%)", 0.25, 5.0, 1.0, 0.25)
    use_stock = c3.checkbox("Screener se stock pick karo", value=True)

    default_entry = 100.0; default_sl = 92.0
    sym_pick = "--"
    if use_stock:
        c4, c5 = st.columns(2)
        sym_pick = c4.selectbox("Stock", ["--"] + ALL_SYMS, key="ps_sym")
        if sym_pick != "--":
            row = scr[scr.Symbol == sym_pick].iloc[0]
            default_entry = float(row.Entry)
            default_sl = float(row.SL)
            c5.info(f"Auto-fill: Entry ₹{default_entry:.2f}, SL ₹{default_sl:.2f}")

    c6, c7 = st.columns(2)
    entry_px = c6.number_input("Entry price (₹)", 0.01, 1_000_000.0, float(default_entry), 0.05)
    sl_px    = c7.number_input("Stop loss (₹)",  0.01, 1_000_000.0, float(default_sl),   0.05)

    risk_cap = capital * risk_pct / 100
    per_share_risk = entry_px - sl_px
    if per_share_risk <= 0:
        st.error("SL entry se neeche hona chahiye (long trade ke liye).")
    else:
        shares = int(risk_cap / per_share_risk)
        capital_deployed = shares * entry_px
        max_loss = shares * per_share_risk
        pct_capital = capital_deployed / capital * 100 if capital > 0 else 0

        st.markdown("---")
        c8, c9, c10, c11 = st.columns(4)
        kpi(c8, "Shares", f"{shares:,}", "", "")
        kpi(c9, "Capital deployed", f"₹{capital_deployed:,.0f}", f"{pct_capital:.1f}% of capital",
            "y" if pct_capital > 50 else "")
        kpi(c10, "Max loss", f"₹{max_loss:,.0f}", f"{risk_pct}% of capital", "r")
        kpi(c11, "Risk per share", f"₹{per_share_risk:.2f}",
            f"{(per_share_risk/entry_px*100):.1f}% of entry")

        st.markdown("#### Target outcomes")
        r = scr[scr.Symbol == sym_pick].iloc[0] if use_stock and sym_pick != "--" else None
        if r is not None:
            targets = [("T1", float(r.T1)), ("T2", float(r.T2)), ("T3", float(r.T3))]
            tc = st.columns(3)
            for i, (name, tp) in enumerate(targets):
                profit = shares * (tp - entry_px)
                rr = (tp - entry_px) / per_share_risk if per_share_risk else 0
                kpi(tc[i], f"{name} ₹{tp:.2f}", f"+₹{profit:,.0f}", f"R:R {rr:.1f}x", "g")
        st.caption("⚠️ Ye ek calculator hai, recommendation nahi. Actual SL hit hone pe hi loss hoga — "
                   "aur gap-down me SL se zyada loss bhi ho sakta hai.")

# ---------------------------- Tab 8: Telegram ----------------------------- #
with tab8:
    st.markdown("### 🔔 Telegram Alerts")
    st.caption("Telegram bot setup karke apne phone pe daily alerts receive karo.")
    token = st.session_state.get("tg_token", "")
    chat_id = st.session_state.get("tg_chat", "")
    if not token or not chat_id:
        st.warning("Pehle sidebar me Bot Token aur Chat ID save karo (setup instructions sidebar me hain).")
    else:
        st.success(f"Token saved: ...{token[-6:]} | Chat: {chat_id}")
        st.markdown("---")
        top_n = st.slider("Top N stocks in alert", 5, 25, 10)
        if st.button("📤 Send alert now"):
            msg = A.format_telegram_alert(scr, deals, breadth, f"{asof:%d %b %Y}", top_n=top_n)
            ok, info = A.send_telegram_message(token, chat_id, msg)
            if ok:
                st.success("✅ Alert bheja gaya! Phone check karo.")
                with st.expander("Message preview"):
                    st.code(msg)
            else:
                st.error(f"❌ Bhej nahi paya: {info}")

        st.markdown("---")
        st.markdown("#### Preview (bhejne se pehle dekh lo)")
        st.code(A.format_telegram_alert(scr, deals, breadth, f"{asof:%d %b %Y}", top_n=top_n))

        st.markdown("---")
        st.markdown("#### 🔄 Auto daily alert (optional)")
        st.markdown("""
Streamlit Cloud free tier pe cron directly nahi chalta. Options:
- **GitHub Actions** se daily 12:30 UTC (6 PM IST) pe trigger
- **cron-job.org** (free) se daily Streamlit URL ping karo
- Ya roz shaam **"Send alert now"** manually dabao

Batana — auto setup chahiye to GitHub Actions workflow file likh dunga.
        """)

if open_sym:
    detail_dialog(open_sym)
