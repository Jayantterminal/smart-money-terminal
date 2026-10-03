"""
app.py - Smart Money Terminal
Delivery-based accumulation: 1 month vs previous 2 months, fresh spikes, sector rotation, trade plan.
Run: streamlit run app.py
"""
import hashlib

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
.kpi .v{color:#f8fafc;font-size:1.2rem;font-weight:700}
.kpi .d{font-size:.8rem;font-weight:600;color:#94a3b8}
.g{color:#22c55e!important}.r{color:#ef4444!important}.y{color:#f59e0b!important}
.why{background:#0f172a;border-left:3px solid #22c55e;padding:8px 14px;margin:5px 0;
 border-radius:6px;color:#e2e8f0;font-size:.9rem}
/* clickable KPI cards */
.st-key-kpis button{width:100%;height:92px;border-radius:12px;border:1px solid #334155;
 background:#0f172a;white-space:pre-line;line-height:1.35}
.st-key-kpis button p{font-size:.95rem;font-weight:600}
.st-key-kpis button:hover{border-color:#22c55e}
</style>
""", unsafe_allow_html=True)


def kpi(col, label, value, sub="", cls=""):
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="v {cls}">{value}</div>'
                 f'<div class="d">{sub}</div></div>', unsafe_allow_html=True)


@st.cache_data(ttl=1800, show_spinner="Downloading NSE delivery data (first load can take ~30-60 sec)...")
def load():
    hist, info = E.fetch_history(80)
    scr = E.compute_screener(hist, (), 0.0, E.fetch_sector_map()) if not hist.empty else pd.DataFrame()
    return hist, scr, info, E.now_ist()


hist, scr, info, fetched = load()
if hist.empty or scr.empty:
    st.error("NSE data could not be loaded. NSE may be blocking this server or files are not yet "
             f"published (network errors: {info['errors']}). Click Refresh after a few minutes.")
    st.stop()
if "Ret_3M" not in scr.columns:
    st.cache_data.clear()
    st.error("engine.py purana version hai. GitHub pe engine.py aur app.py dono naye upload karo, "
             "phir app reboot karo.")
    st.stop()
ALL_SYMS = sorted(scr.Symbol.tolist())

STAGES = ["Base (not moved)", "Early move", "Rally on", "Extended (already ran)"]
SETUPS = ["In range (base)", "Breakout", "Trending / wide", "Breakdown"]
BUYS = ["Continuing", "Just started", "Fading", "Not buying"]
SIGNALS = ["Strong Accumulation", "Accumulation", "Neutral", "Distribution", "Low volume (ignore)"]
FRESH = list(E.FRESH_SET)
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
        help="My watchlist = sirf wo ~60 stocks jo engine.py ki WATCHLIST me hain + jo tum neeche add karo.\n\n"
             "All liquid NSE = NSE ke saare EQ stocks jinka avg daily turnover niche slider se zyada hai.")
    min_turn = st.slider("Min avg turnover (₹ Cr/day)", 0, 100, 5,
                         help="Sirf 'All liquid NSE' pe lagta hai. 5–10 Cr swing trading ke liye theek hai.")
    extras = st.multiselect("Add stocks to My watchlist", ALL_SYMS, placeholder="Type symbol...")
    st.caption("Source: NSE bhavcopy (end-of-day), delivery data ~6-7 PM IST ke baad aata hai. "
               "Analysis tool only, not investment advice.")

asof = hist.Date.max()
st.markdown(f"""
<div class="topbar">
 <div class="brand">SMART<span>MONEY</span> TERMINAL</div>
 <div class="meta">Data as of <b>{asof:%d %b %Y}</b> (EOD) &nbsp;|&nbsp;
 Fetched <b>{fetched:%d %b %Y, %I:%M %p} IST</b> &nbsp;|&nbsp; Sessions loaded: <b>{info['days']}</b>
 &nbsp;|&nbsp; Window: <b>1M vs previous 2M</b></div>
</div>""", unsafe_allow_html=True)
if info["errors"]:
    st.warning(f"{info['errors']} din ka NSE data download nahi ho paya - Refresh karke dekho.")

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


@st.dialog("Stock detail", width="large")
def detail_dialog(sym: str):
    render_detail(sym, "dlg")


TABLE_COLS = ["Symbol", "Price", "Entry_Zone", "Entry_Status", "SL", "T1", "T2", "T3", "Score", "Signal",
              "Fresh", "Last5", "Buying_Status", "Buy_Weeks", "Setup", "Stage", "Deliv_Qty_X", "Today_X",
              "Deliv_Per_Chg", "Net_Flow_1M", "Deliv_Per_1M", "Deliv_Per_3M", "Acc_Days", "Range_Pct",
              "Chg_Pct", "Sector"]
TABLE_CFG = {
    "Symbol": st.column_config.TextColumn("Symbol", pinned=True),
    "Price": st.column_config.NumberColumn("Price", format="₹%.2f"),
    "Entry_Zone": st.column_config.TextColumn("Entry zone (₹)"),
    "Entry_Status": st.column_config.TextColumn("Price vs zone"),
    "SL": st.column_config.NumberColumn("SL", format="₹%.2f"),
    "T1": st.column_config.NumberColumn("T1", format="₹%.2f"),
    "T2": st.column_config.NumberColumn("T2", format="₹%.2f"),
    "T3": st.column_config.NumberColumn("T3", format="₹%.2f"),
    "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
    "Fresh": st.column_config.TextColumn("Fresh activity"),
    "Last5": st.column_config.TextColumn("Last 5 days", help="Purana → aaj. 🟢 strong delivery + price up, "
                                         "🔴 strong delivery + price down, ⚪ normal"),
    "Buy_Weeks": st.column_config.NumberColumn("Buy weeks /4", format="%d"),
    "Deliv_Qty_X": st.column_config.NumberColumn("Deliv qty 1M÷3M", format="%.2fx"),
    "Today_X": st.column_config.NumberColumn("Today deliv ÷ 3M avg", format="%.2fx"),
    "Deliv_Per_Chg": st.column_config.NumberColumn("Deliv % Δ 1M−3M", format="%+.1f pp"),
    "Net_Flow_1M": st.column_config.NumberColumn("Net buy flow 1M", format="%+.0f%%",
                                                 help="(Up-day delivery − down-day delivery) ÷ total delivery"),
    "Deliv_Per_1M": st.column_config.NumberColumn("Deliv % 1M", format="%.1f%%"),
    "Deliv_Per_3M": st.column_config.NumberColumn("Deliv % prev 2M", format="%.1f%%"),
    "Acc_Days": st.column_config.NumberColumn("Acc days /21", format="%d"),
    "Range_Pct": st.column_config.NumberColumn("30D range", format="%.1f%%"),
    "Chg_Pct": st.column_config.NumberColumn("Chg %", format="%.2f%%"),
}


def stock_table(d: pd.DataFrame, name: str, height: int = 560):
    """Table with row-click -> returns a newly clicked symbol (to open the detail popup)."""
    view = d.copy()
    view["Entry_Status"] = view.Entry_Status.map(ESTAT)
    view["Buying_Status"] = view.Buying_Status.map(BICON)
    view["Fresh"] = view.Fresh.map(FICON)
    sig = hashlib.md5(",".join(view.Symbol).encode()).hexdigest()[:10]
    ev = st.dataframe(view[TABLE_COLS], hide_index=True, width="stretch", height=height,
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


tab1, tab2, tab3, tab4 = st.tabs(["🔎 Accumulation Screener", "🔄 Sector Rotation", "🎯 Stock Plan", "⚖️ Compare"])
open_sym = None

# ---------------------------- Screener ------------------------------------ #
with tab1:
    QUICK = {
        "strong": ("Strong accumulation", pool[pool.Signal == "Strong Accumulation"]),
        "acc": ("Accumulation", pool[pool.Signal == "Accumulation"]),
        "cont": ("Buying continuing", pool[pool.Buying_Status == "Continuing"]),
        "fresh": ("Fresh activity", pool[pool.Fresh.isin(FRESH)].sort_values("Last5_X", ascending=False)),
        "dist": ("Distribution", pool[pool.Signal == "Distribution"]),
    }
    if "quick" not in st.session_state:
        st.session_state.quick = None

    def set_quick(k):
        st.session_state.quick = None if (k is None or st.session_state.quick == k) else k

    with st.container(key="kpis"):
        kc = st.columns(6)
        kc[0].button(f"Stocks scanned\n{len(pool)}", key="q_all", on_click=set_quick, args=(None,),
                     type="primary" if st.session_state.quick is None else "secondary")
        labels = {"strong": "🟢 Strong accumulation", "acc": "🟢 Accumulation", "cont": "🟢 Buying continuing",
                  "fresh": "⚡ Fresh activity", "dist": "🔴 Distribution"}
        for i, k in enumerate(QUICK, start=1):
            extra = f"  (today {int((pool.Fresh == 'Spike today').sum())})" if k == "fresh" else ""
            kc[i].button(f"{labels[k]}\n{len(QUICK[k][1])}{extra}", key=f"q_{k}", on_click=set_quick, args=(k,),
                         type="primary" if st.session_state.quick == k else "secondary")
    st.caption("👆 Card pe click karo - wahi stocks table me aa jayenge (jitna count likha hai utne). "
               "Dobara click = filters pe wapas.")

    q = st.multiselect("🔍 Search stock (type karte hi suggestions)", ALL_SYMS, placeholder="e.g. BAJ ... BAJAJHFL")

    PRESETS = {"Balanced (recommended)": (1.2, 3), "Strict (few, best)": (1.5, 6),
               "Loose (more ideas)": (1.0, 0), "Custom": None}
    p1, p2 = st.columns([1, 2])
    preset = p1.selectbox("Scan preset", list(PRESETS), help=(
        "Delivery qty × = pichle 1 mahine ki avg delivered qty ÷ usse pehle ke 2 mahine ki avg.\n"
        "Delivery % rise = 1M avg delivery % − pichle 2M avg delivery % (pp).\n\n"
        "Balanced = 1.2x aur +3pp. Strict = 1.5x aur +6pp. Loose = 1.0x, % shart nahi."))
    if PRESETS[preset] is None:
        s1, s2 = p2.columns(2)
        min_x = s1.slider("Min delivery qty × (1M ÷ 3M)", 0.5, 4.0, 1.2, 0.1)
        min_pp = s2.slider("Min delivery % rise (pp)", -10, 30, 3)
    else:
        min_x, min_pp = PRESETS[preset]
        p2.info(f"1M delivered qty ≥ **{min_x}x** pichle 2M avg  |  1M delivery % ≥ **+{min_pp}pp**  "
                "(best: Buying 'Continuing' + Setup 'In range' ya 'Breakout' + Stage Base/Early)")

    h1, h2 = st.columns(2)
    only_acc = h1.checkbox("Sirf Accumulation / Strong Accumulation dikhao", value=True)
    hide_ext = h2.checkbox("Extended (already ran) chhupao", value=True)
    f = st.columns(4)
    sig = f[0].multiselect("Signal", SIGNALS, placeholder="All")
    stg = f[1].multiselect("Stage (kitna chal chuka)", STAGES, placeholder="All",
                           help="Base = 20D low se <5% upar. Early = 5–10%. Rally on = 10–18%. "
                                "Extended = 18%+ ya 20 DMA se 10%+ upar.")
    setup_sel = f[2].multiselect("Setup", SETUPS, placeholder="All",
                                 help="In range = pichle 30 din ek range (≤25%) me. Breakout = range ke upar close.")
    buy_sel = f[3].multiselect("Buying status", BUYS, placeholder="All",
                               help="Pichle 4 hafte me kitne hafte net buying hui (up-day delivery > down-day delivery).")
    g2 = st.columns(3)
    sec_sel = g2[0].multiselect("Sector / Industry", sorted(pool.Sector.unique()), placeholder="All")
    min_wk = g2[1].slider("Min buying weeks (last 4 me se)", 0, 4, 0)
    fresh_sel = g2[2].multiselect("Fresh activity", FRESH, placeholder="All",
                                  help="Kisi din achanak delivery qty 3M avg se 2x+ hui to yahan turant dikhega. "
                                       "Ise chuno to Signal aur Scan preset ignore ho jaate hain.")

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
        if fresh_sel:
            d = d[d.Fresh.isin(fresh_sel)]
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
        if not fresh_sel:
            d = d[(d.Deliv_Qty_X >= min_x) & (d.Deliv_Per_Chg >= min_pp)]
            funnel.append(("Scan preset", len(d)))
        if setup_sel: d = d[d.Setup.isin(setup_sel)]
        if buy_sel: d = d[d.Buying_Status.isin(buy_sel)]
        if sec_sel: d = d[d.Sector.isin(sec_sel)]
        d = d[d.Buy_Weeks >= min_wk]
        funnel.append(("Setup/Buying/Sector/Weeks", len(d)))
        if fresh_sel:
            d = d.sort_values("Last5_X", ascending=False)
    st.caption(f"{len(d)} stocks | prices as of {asof:%d %b %Y}  |  👆 Row pe click karo → stock detail khulega")
    if funnel:
        st.caption("🔻 Filter funnel:  " + "  →  ".join(f"{n}: **{c}**" for n, c in funnel))

    open_sym = stock_table(d, "scr") or open_sym
    st.download_button("⬇️ Download CSV", d.to_csv(index=False).encode(), f"accumulation_{asof:%Y%m%d}.csv", "text/csv")
    with st.expander("Score kaise banta hai? (1 month vs pichle 2 month)"):
        st.markdown("""
- **Delivered qty 1M ÷ pichle 2M avg**: ≥1.5x → 20, ≥1.2x → 14, ≥1.05x → 7
- **Delivery % (1M avg − pichle 2M avg)**: ≥8pp → 15, ≥4pp → 10, >0 → 4
- **Net buy flow 1M** (up-day delivery − down-day delivery ÷ total): ≥30% → 20, ≥15% → 14, >0 → 7
- **Buying weeks** (last 4 hafte me kitne net-buy): 4 → 15, 3 → 11, 2 → 6
- **Setup** In range (base) ya Breakout → 10
- **Range hold** (price range ke neeche nahi toota) → 10
- **Aaj ki delivered qty ≥ pichle 2M avg** → 10

**Days + Weeks dono**: *Acc days /21* aur *Last 5 days* daily dikhate hain, *Buy weeks* weekly.
**Fresh activity** achanak aaye spike pakadta hai: aaj ki delivered qty 3M avg se 2x+ (price up, delivery % +5pp)
= Spike today; pichle 3 din me hua = Spike (last 3D); 5 din ki avg 1.5x+ aur net buying = Building.
1M wala Signal slow hota hai, isliye achanak buying ke liye Fresh use karo.

Smart money ek din me nahi kharidta - range ke andar hafton tak dheere dheere. Isliye daily nahi,
**weekly net flow** dekha jata hai. Splits/bonus ke liye data auto-adjust hota hai, ETFs/liquid funds hata diye jate hain.""")

# ------------------------- Sector rotation -------------------------------- #
with tab2:
    sec = E.sector_rotation(pool)
    if sec.empty:
        st.warning("Sector data nahi mila (NSE sector file load nahi hui ya universe chhota hai). "
                   "Universe 'All liquid NSE stocks' rakho aur Refresh karo.")
    else:
        st.caption("Delivery flow se sector rotation: kis sector me paisa aa raha hai (Flow 1M) aur pichle 2 mahine "
                   "se behtar ho raha hai ya nahi (Flow change). Improving → Leading me aane wale sectors pe nazar rakho.")
        fig = go.Figure()
        for qn, col in QCOL.items():
            s = sec[sec.Quadrant == qn]
            if s.empty:
                continue
            fig.add_trace(go.Scatter(
                x=s.Flow_1M, y=s.Flow_Chg, mode="markers+text", text=s.Sector, textposition="top center",
                name=qn, marker=dict(size=np.clip(s.Stocks * 1.2 + 10, 12, 40), color=col, opacity=0.75,
                                     line=dict(color="white", width=1)),
                customdata=np.stack([s.Acc_Pct, s.Stocks, s.Fresh], axis=1),
                hovertemplate="%{text}<br>Flow 1M %{x:+.1f}%<br>Change vs prev 2M %{y:+.1f}<br>"
                              "Accumulating %{customdata[0]}% of %{customdata[1]} stocks<br>"
                              "Fresh %{customdata[2]}<extra></extra>"))
        fig.add_vline(x=0, line_color="#64748b")
        fig.add_hline(y=0, line_color="#64748b")
        fig.update_layout(height=520, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10),
                          xaxis_title="Net buy flow 1M (avg %, up-day − down-day delivery)",
                          yaxis_title="Change vs previous 2M (pp)", legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch", key="sec_chart")

        sv = sec.copy()
        sv["Quadrant"] = sv.Quadrant.map(QICON)
        st.markdown("**Sector pe click karo → uske stocks neeche aayenge**")
        ev = st.dataframe(
            sv, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="sec_tbl",
            column_config={
                "Acc_Pct": st.column_config.ProgressColumn("Accumulating %", min_value=0, max_value=100, format="%d%%"),
                "Stocks": st.column_config.NumberColumn("Stocks", format="%d"),
                "Accumulating": st.column_config.NumberColumn("Accum. stocks", format="%d"),
                "Strong": st.column_config.NumberColumn("Strong", format="%d"),
                "Continuing": st.column_config.NumberColumn("Buying continuing", format="%d"),
                "Fresh": st.column_config.NumberColumn("⚡ Fresh", format="%d"),
                "Flow_1M": st.column_config.NumberColumn("Flow 1M", format="%+.1f%%"),
                "Flow_Prev": st.column_config.NumberColumn("Flow prev 2M", format="%+.1f%%"),
                "Flow_Chg": st.column_config.NumberColumn("Flow change", format="%+.1f pp"),
                "Deliv_Qty_X": st.column_config.NumberColumn("Deliv qty 1M÷3M", format="%.2fx"),
                "Ret_1W": st.column_config.NumberColumn("Ret 1W", format="%+.1f%%"),
                "Ret_1M": st.column_config.NumberColumn("Ret 1M", format="%+.1f%%"),
                "Ret_3M": st.column_config.NumberColumn("Ret 3M", format="%+.1f%%"),
            })
        if ev.selection.rows:
            chosen = sec.iloc[ev.selection.rows[0]].Sector
            sd = pool[pool.Sector == chosen].sort_values(["Score", "Deliv_Qty_X"], ascending=False)
            st.markdown(f"#### {chosen} - {len(sd)} stocks (score ke hisaab se)")
            open_sym = stock_table(sd, "sec", height=420) or open_sym
        st.caption("Returns = sector ke stocks ka median. Flow = sector stocks ka average net buy flow. "
                   "Quadrant: Leading = flow + aur badh raha | Improving = flow abhi - par sudhar raha (early) | "
                   "Weakening = flow + par ghat raha | Lagging = flow - aur bigad raha.")

# ---------------------------- Stock plan ---------------------------------- #
with tab3:
    idx = ALL_SYMS.index("BAJAJHFL") if "BAJAJHFL" in ALL_SYMS else 0
    sym = st.selectbox("Stock (type karke search)", ALL_SYMS, index=idx)
    render_detail(sym, "tab")

# ----------------------------- Compare ------------------------------------ #
with tab4:
    pick = st.multiselect("Select up to 4 stocks (type karke search)", ALL_SYMS,
                          default=[s for s in ["BAJAJHFL", "BAJFINANCE"] if s in ALL_SYMS], max_selections=4)
    if pick:
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                            subplot_titles=("Delivery % (5-day smoothed)", "Cumulative net delivery flow (shares)",
                                            "Price rebased to 100"))
        for s in pick:
            gs = E.symbol_view(hist, s).tail(80)
            up, dn = gs.CLOSE_PRICE > gs.PREV_CLOSE, gs.CLOSE_PRICE < gs.PREV_CLOSE
            net = (gs.DELIV_QTY.where(up, 0) - gs.DELIV_QTY.where(dn, 0)).cumsum()
            fig.add_trace(go.Scatter(x=gs.Date, y=gs.DELIV_PER.rolling(5).mean(), name=s), row=1, col=1)
            fig.add_trace(go.Scatter(x=gs.Date, y=net, name=s, showlegend=False), row=2, col=1)
            fig.add_trace(go.Scatter(x=gs.Date, y=gs.CLOSE_PRICE / gs.CLOSE_PRICE.iloc[0] * 100, name=s,
                                     showlegend=False), row=3, col=1)
        fig.update_layout(height=820, template="plotly_dark", hovermode="x unified",
                          margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width="stretch", key="cmp_chart")
        cmp = scr[scr.Symbol.isin(pick)][["Symbol", "Price", "Entry_Zone", "SL", "T1", "T2", "T3", "Score", "Signal",
                                          "Buying_Status", "Buy_Weeks", "Setup", "Stage", "Deliv_Qty_X",
                                          "Deliv_Per_Chg", "Net_Flow_1M", "Net_Flow_3M"]]
        st.dataframe(cmp, hide_index=True, width="stretch")

# row click anywhere -> popup with full stock detail (only one dialog per run)
if open_sym:
    detail_dialog(open_sym)
