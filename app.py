"""
app.py - Smart Money Terminal: Delivery-based accumulation screener + trade plan
Run: streamlit run app.py
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import engine as E

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
.kpi .v{color:#f8fafc;font-size:1.25rem;font-weight:700}
.kpi .d{font-size:.8rem;font-weight:600;color:#94a3b8}
.g{color:#22c55e!important}.r{color:#ef4444!important}.y{color:#f59e0b!important}
.why{background:#0f172a;border-left:3px solid #22c55e;padding:8px 14px;margin:5px 0;
 border-radius:6px;color:#e2e8f0;font-size:.9rem}
</style>
""", unsafe_allow_html=True)


def kpi(col, label, value, sub="", cls=""):
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="v {cls}">{value}</div>'
                 f'<div class="d">{sub}</div></div>', unsafe_allow_html=True)


@st.cache_data(ttl=1800, show_spinner="Downloading NSE delivery data (first load can take ~30-60 sec)...")
def load():
    hist, info = E.fetch_history(70)
    scr = E.compute_screener(hist, (), 0.0) if not hist.empty else pd.DataFrame()
    return hist, scr, info, E.now_ist()


hist, scr, info, fetched = load()
if hist.empty or scr.empty:
    st.error("NSE data could not be loaded. NSE may be blocking this server or files are not yet "
             f"published (network errors: {info['errors']}). Click Refresh after a few minutes.")
    st.stop()
ALL_SYMS = sorted(scr.Symbol.tolist())

# ------------------------------ sidebar ----------------------------------- #
with st.sidebar:
    st.markdown("### ⚙️ Controls")
    if st.button("🔄 Refresh data now"):
        st.cache_data.clear()
        st.rerun()
    universe = st.radio(
        "Universe", ["My watchlist", "All liquid NSE stocks"], index=1,
        help="My watchlist = sirf wo ~60 stocks jo engine.py ki WATCHLIST me hain + jo tum neeche add karo.\n\n"
             "All liquid NSE = NSE ke saare EQ stocks (~1500+) jinka avg daily turnover niche slider se "
             "zyada hai. Naye ideas dhundhne ke liye ye use karo.")
    min_turn = st.slider("Min avg turnover (₹ Cr/day)", 0, 100, 5,
                         help="Sirf 'All liquid NSE' pe lagta hai. 5–10 Cr swing trading ke liye theek hai. "
                              "100 Cr rakhoge to sirf bade large-caps bachenge.")
    extras = st.multiselect("Add stocks to My watchlist", ALL_SYMS, placeholder="Type symbol...")
    st.caption("Source: NSE bhavcopy (end-of-day), delivery data ~6-7 PM IST ke baad aata hai. "
               "Analysis tool only, not investment advice.")

asof = hist.Date.max()
st.markdown(f"""
<div class="topbar">
 <div class="brand">SMART<span>MONEY</span> TERMINAL</div>
 <div class="meta">Data as of <b>{asof:%d %b %Y}</b> (EOD) &nbsp;|&nbsp;
 Fetched <b>{fetched:%d %b %Y, %I:%M %p} IST</b> &nbsp;|&nbsp; Sessions loaded: <b>{info['days']}</b></div>
</div>""", unsafe_allow_html=True)

watch_all = set(E.SECTOR_OF) | set(extras)
if universe == "My watchlist":
    pool = scr[scr.Symbol.isin(watch_all)]
else:
    pool = scr[(scr.Avg_Turnover_Cr >= min_turn) | scr.Symbol.isin(extras)]

STAGES = ["Base (not moved)", "Early move", "Rally on", "Extended (already ran)"]
tab1, tab2, tab3 = st.tabs(["🔎 Accumulation Screener", "🎯 Stock Plan", "⚖️ Compare"])

# ---------------------------- Screener ------------------------------------ #
with tab1:
    c = st.columns(4)
    kpi(c[0], "Stocks scanned", f"{len(pool)}", f"universe: {universe}")
    kpi(c[1], "Strong accumulation", int((pool.Signal == "Strong Accumulation").sum()), "score ≥ 75", "g")
    kpi(c[2], "Accumulation", int((pool.Signal == "Accumulation").sum()), "score 55–74", "g")
    kpi(c[3], "Distribution", int((pool.Signal == "Distribution").sum()), "high delivery + falling", "r")

    q = st.multiselect("🔍 Search stock (type karte hi suggestions aayenge)", ALL_SYMS,
                       placeholder="e.g. BAJ ... BAJAJHFL")

    PRESETS = {"Balanced (recommended)": (1.5, 5), "Strict (few, best)": (2.0, 8),
               "Loose (more ideas)": (1.2, 0), "Custom": None}
    p1, p2 = st.columns([1, 2])
    preset = p1.selectbox("Scan preset", list(PRESETS), help=(
        "Delivery qty × = aaj ki delivered qty ÷ 20-din ki avg delivered qty.\n"
        "Delivery % rise = aaj ka delivery % − 20-din avg delivery % (percentage points).\n\n"
        "Best scan: Balanced = qty ≥ 1.5x aur rise ≥ +5pp. Strict = 2x aur +8pp. "
        "Loose = 1.2x, koi % shart nahi (noise zyada)."))
    if PRESETS[preset] is None:
        s1, s2 = p2.columns(2)
        min_x = s1.slider("Min delivery qty × avg", 0.0, 5.0, 1.5, 0.1)
        min_pp = s2.slider("Min delivery % rise (pp)", -10, 30, 5)
    else:
        min_x, min_pp = PRESETS[preset]
        p2.info(f"Delivery qty ≥ **{min_x}x** avg  |  Delivery % rise ≥ **+{min_pp}pp**   "
                "(best combo: ye + Acc Days ≥ 2 + Stage 'Base' ya 'Early move')")

    f = st.columns(4)
    sig = f[0].multiselect("Signal", ["Strong Accumulation", "Accumulation", "Neutral", "Distribution",
                                      "Low volume (ignore)"], default=["Strong Accumulation", "Accumulation"])
    stg = f[1].multiselect("Stage (kitna chal chuka)", STAGES, default=STAGES[:3],
                           help="Base = abhi 20D low se <5% upar, rally baki. Early move = 5–10%. "
                                "Rally on = 10–18%. Extended = 18%+ ya 20 DMA se 10%+ upar (chase mat karo).")
    sec_sel = f[2].multiselect("Sector", sorted(pool.Sector.unique()))
    min_acc = f[3].slider("Min accumulation days (of 10)", 0, 10, 0)

    if q:
        d = scr[scr.Symbol.isin(q)]
        st.caption("Search mode: selected stocks dikh rahe hain (filters ignore).")
    else:
        d = pool[pool.Signal.isin(sig) & pool.Stage.isin(stg)]
        d = d[(d.Deliv_Qty_X >= min_x) & (d.Deliv_Per_Chg >= min_pp) & (d.Acc_Days_10D >= min_acc)]
        if sec_sel:
            d = d[d.Sector.isin(sec_sel)]
    st.caption(f"{len(d)} stocks | sorted by score | prices as of {asof:%d %b %Y}")

    cols = ["Symbol", "Price", "Entry", "SL", "T1", "T2", "T3", "Score", "Signal", "Stage", "Chg_Pct",
            "Run_20D", "Deliv_Per", "Avg_Deliv_Per", "Deliv_Per_Chg", "Deliv_Qty_X", "Acc_Days_10D",
            "Vol_X", "Deliv_Qty", "Avg_Deliv_Qty", "Sector"]
    st.dataframe(d[cols], hide_index=True, width="stretch", height=560, column_config={
        "Symbol": st.column_config.TextColumn("Symbol", pinned=True),
        "Price": st.column_config.NumberColumn("Price", format="₹%.2f"),
        "Entry": st.column_config.NumberColumn("Entry", format="₹%.2f"),
        "SL": st.column_config.NumberColumn("SL", format="₹%.2f"),
        "T1": st.column_config.NumberColumn("T1", format="₹%.2f"),
        "T2": st.column_config.NumberColumn("T2", format="₹%.2f"),
        "T3": st.column_config.NumberColumn("T3", format="₹%.2f"),
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
        "Chg_Pct": st.column_config.NumberColumn("Chg %", format="%.2f%%"),
        "Run_20D": st.column_config.NumberColumn("Run from 20D low", format="%.1f%%"),
        "Deliv_Per": st.column_config.NumberColumn("Deliv % Today", format="%.1f%%"),
        "Avg_Deliv_Per": st.column_config.NumberColumn("Deliv % 20D Avg", format="%.1f%%"),
        "Deliv_Per_Chg": st.column_config.NumberColumn("Deliv % Δ (pp)", format="%+.1f"),
        "Deliv_Qty_X": st.column_config.NumberColumn("Deliv Qty ×", format="%.2fx"),
        "Acc_Days_10D": st.column_config.NumberColumn("Acc Days /10", format="%d"),
        "Vol_X": st.column_config.NumberColumn("Volume ×", format="%.2fx"),
        "Deliv_Qty": st.column_config.NumberColumn("Deliv Qty", format="%d"),
        "Avg_Deliv_Qty": st.column_config.NumberColumn("Deliv Qty 20D Avg", format="%d"),
    })
    st.download_button("⬇️ Download CSV", d.to_csv(index=False).encode(), f"accumulation_{asof:%Y%m%d}.csv",
                       "text/csv")
    with st.expander("Score aur Stage kaise bante hain?"):
        st.markdown("""
Baseline = pichle 20 trading days (aaj ko chhodkar).
- **Delivery qty × avg**: ≥2x → 25, ≥1.5x → 18, ≥1.2x → 10
- **Delivery % rise**: ≥10pp → 20, ≥5pp → 12, >0 → 5
- **5-day delivery qty × avg**: ≥1.3x → 15, ≥1.1x → 8
- **Accumulation days (last 10)**: ≥5 → 20, ≥3 → 12, ≥2 → 6
- **Close > 20 DMA** → 10, **aaj price up/flat** → 10

**Stage** = 20-din ke low se price kitna chadh chuka: <5% Base, 5–10% Early move, 10–18% Rally on,
18%+ (ya 20 DMA se 10%+ upar) Extended. Best setup: *high accumulation + Base/Early move*.""")

# ---------------------------- Stock plan ---------------------------------- #
with tab2:
    idx = ALL_SYMS.index("BAJAJHFL") if "BAJAJHFL" in ALL_SYMS else 0
    sym = st.selectbox("Stock (type karke search)", ALL_SYMS, index=idx)
    r = scr[scr.Symbol == sym].iloc[0]
    g = hist[hist.SYMBOL == sym].sort_values("Date").tail(60)

    sc = "g" if r.Score >= 55 else "y" if r.Score >= 35 else "r"
    stc = "g" if r.Stage in STAGES[:2] else "y" if r.Stage == STAGES[2] else "r"
    c = st.columns(6)
    kpi(c[0], "Last price", f"₹{r.Price:,.2f}", f"{r.Chg_Pct:+.2f}% today", "g" if r.Chg_Pct >= 0 else "r")
    kpi(c[1], "Accumulation score", f"{r.Score}/100", r.Signal, sc)
    kpi(c[2], "Stage", r.Stage.split(" (")[0], f"+{r.Run_20D}% from 20D low | {r.From_60D_High}% from 60D high", stc)
    kpi(c[3], "Delivery % today", f"{r.Deliv_Per:.1f}%", f"20D avg {r.Avg_Deliv_Per:.1f}% ({r.Deliv_Per_Chg:+.1f}pp)")
    kpi(c[4], "Delivery qty", f"{r.Deliv_Qty_X:.2f}x", f"{r.Deliv_Qty:,} vs avg {r.Avg_Deliv_Qty:,}")
    kpi(c[5], "Acc / Dist days (10D)", f"{r.Acc_Days_10D} / {r.Dist_Days_10D}", f"Volume {r.Vol_X:.2f}x avg")

    st.markdown("#### Trade plan (ATR based)")
    c = st.columns(5)
    kpi(c[0], "Price → Entry zone", f"₹{r.Price:,.2f} → {r.Entry_Low:,.2f}–{r.Entry_High:,.2f}", r.Plan_Status)
    kpi(c[1], "Stop loss", f"₹{r.SL:,.2f}", f"-{r.Risk_Pct:.1f}% from entry", "r")
    for i, (k, mult) in enumerate([("T1", 1.5), ("T2", 2.5), ("T3", 4.0)]):
        kpi(c[2 + i], f"Target {i + 1}", f"₹{r[k]:,.2f}", f"+{(r[k] / r.Entry - 1) * 100:.1f}% | {mult}R", "g")

    why = []
    if r.Stage.startswith("Extended"):
        why.append("Stock pehle hi kaafi chal chuka hai - naya entry pullback pe hi socho, chase mat karo.")
    elif r.Stage.startswith("Base"):
        why.append("Price abhi 20-din ke low ke paas hai - move shuru hona baki ho sakta hai (best stage).")
    if r.Deliv_Qty_X >= 1.5:
        why.append(f"Delivered quantity {r.Deliv_Qty_X:.1f}x 20-day average - real buying.")
    elif r.Deliv_Qty_X < 1:
        why.append(f"Delivered quantity average se kam ({r.Deliv_Qty_X:.2f}x) - sirf delivery % se dhokha ho sakta hai.")
    if r.Deliv_Per_Chg > 0:
        why.append(f"Delivery % avg se {r.Deliv_Per_Chg:.1f}pp upar.")
    why.append(f"Last 10 sessions: {r.Acc_Days_10D} accumulation day(s) vs {r.Dist_Days_10D} distribution day(s).")
    why.append(f"SL = 10-day swing low (₹{r.Swing_Low10}) ya entry - 1.5 ATR (ATR ₹{r.ATR}), jo neeche ho. "
               "Targets = 1.5R / 2.5R / 4R. Resistance aur news khud check karo.")
    for w in why:
        st.markdown(f'<div class="why">{w}</div>', unsafe_allow_html=True)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.55, 0.22, 0.23],
                        vertical_spacing=0.03, subplot_titles=("Price with plan", "Delivery %", "Delivered quantity"))
    fig.add_trace(go.Candlestick(x=g.Date, open=g.OPEN_PRICE, high=g.HIGH_PRICE, low=g.LOW_PRICE,
                                 close=g.CLOSE_PRICE, name=sym), row=1, col=1)
    fig.add_trace(go.Scatter(x=g.Date, y=g.CLOSE_PRICE.rolling(20).mean(), name="20 DMA",
                             line=dict(color="#f59e0b", width=1.3)), row=1, col=1)
    for lvl, col, name in [(r.Entry, "#38bdf8", "Entry"), (r.SL, "#ef4444", "SL"), (r.T1, "#22c55e", "T1"),
                           (r.T2, "#22c55e", "T2"), (r.T3, "#22c55e", "T3")]:
        fig.add_hline(y=lvl, line_dash="dot", line_color=col, annotation_text=f"{name} {lvl:,.1f}",
                      annotation_position="right", row=1, col=1)
    colors = np.where((g.CLOSE_PRICE >= g.PREV_CLOSE).values, "#22c55e", "#ef4444")
    fig.add_trace(go.Bar(x=g.Date, y=g.DELIV_PER, marker_color=colors), row=2, col=1)
    fig.add_hline(y=r.Avg_Deliv_Per, line_dash="dash", line_color="#94a3b8", row=2, col=1)
    fig.add_trace(go.Bar(x=g.Date, y=g.DELIV_QTY, marker_color=colors), row=3, col=1)
    fig.add_hline(y=r.Avg_Deliv_Qty, line_dash="dash", line_color="#94a3b8", row=3, col=1)
    fig.update_layout(height=800, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=70, t=30, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption("Bar color: green = close up vs previous day, red = down. Dashed line = 20-day average.")

# ----------------------------- Compare ------------------------------------ #
with tab3:
    pick = st.multiselect("Select up to 4 stocks (type karke search)", ALL_SYMS,
                          default=[s for s in ["BAJAJHFL", "BAJFINANCE"] if s in ALL_SYMS], max_selections=4)
    if pick:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                            subplot_titles=("Delivery % (5-day smoothed)", "Price rebased to 100"))
        for s in pick:
            gs = hist[hist.SYMBOL == s].sort_values("Date").tail(60)
            fig.add_trace(go.Scatter(x=gs.Date, y=gs.DELIV_PER.rolling(5).mean(), name=s), row=1, col=1)
            fig.add_trace(go.Scatter(x=gs.Date, y=gs.CLOSE_PRICE / gs.CLOSE_PRICE.iloc[0] * 100, name=s,
                                     showlegend=False), row=2, col=1)
        fig.update_layout(height=640, template="plotly_dark", hovermode="x unified",
                          margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width="stretch")
        cmp = scr[scr.Symbol.isin(pick)][["Symbol", "Price", "Entry", "SL", "T1", "T2", "T3", "Score", "Signal",
                                          "Stage", "Deliv_Per", "Avg_Deliv_Per", "Deliv_Per_Chg",
                                          "Deliv_Qty_X", "Acc_Days_10D", "Dist_Days_10D"]]
        st.dataframe(cmp, hide_index=True, width="stretch")
