"""
app.py  -  Smart Money Terminal (Streamlit UI)
Run:  streamlit run app.py
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import engine as E

st.set_page_config(page_title="Smart Money Terminal", page_icon="📈", layout="wide")

QCOL = {"Leading": "#22c55e", "Weakening": "#f59e0b", "Lagging": "#ef4444", "Improving": "#3b82f6"}
QICON = {"Leading": "🟢 Leading", "Weakening": "🟡 Weakening", "Lagging": "🔴 Lagging",
         "Improving": "🔵 Improving"}

st.markdown("""
<style>
.block-container{padding-top:1rem;max-width:1500px}
.topbar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;
 padding:12px 18px;border-radius:12px;background:linear-gradient(90deg,#0f172a,#1e293b);
 border:1px solid #334155;margin-bottom:14px}
.brand{font-size:1.35rem;font-weight:800;color:#f8fafc;letter-spacing:.5px}
.brand span{color:#22c55e}
.meta{color:#94a3b8;font-size:.82rem}
.badge{padding:3px 10px;border-radius:99px;font-weight:700;font-size:.75rem;margin-right:8px}
.live{background:#052e16;color:#4ade80;border:1px solid #166534}
.closed{background:#2a0a0a;color:#f87171;border:1px solid #7f1d1d}
.pre{background:#2a1c04;color:#fbbf24;border:1px solid #78350f}
.kpi{background:#0f172a;border:1px solid #334155;border-radius:12px;padding:12px 16px}
.kpi .l{color:#94a3b8;font-size:.72rem;text-transform:uppercase;letter-spacing:.8px}
.kpi .v{color:#f8fafc;font-size:1.45rem;font-weight:700}
.kpi .d{font-size:.85rem;font-weight:600}
.up{color:#22c55e}.dn{color:#ef4444}
.ins{background:#0f172a;border-left:3px solid #22c55e;padding:8px 14px;margin:6px 0;
 border-radius:6px;color:#e2e8f0;font-size:.92rem}
</style>
""", unsafe_allow_html=True)


# ------------------------------- data ------------------------------------- #
@st.cache_data(ttl=300, show_spinner="Fetching market data...")
def load():
    return E.fetch_prices(E.all_tickers()), E.now_ist()


with st.sidebar:
    st.markdown("### ⚙️ Controls")
    if st.button("🔄 Refresh data now"):
        st.cache_data.clear()
        st.rerun()
    auto = st.toggle("Auto-refresh every 5 min (market hours)", value=True)
    tail = st.slider("RRG trail (trading days)", 5, 63, 20)
    st.caption("Data: Yahoo Finance, ~15 min delayed. Not investment advice.")

if auto and E.market_status() == "LIVE":
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=300_000, key="auto")
    except ImportError:
        pass

prices, fetched = load()
sec, tails, missing = E.build_sector_table(prices, 63)
scr = E.build_screener(prices, sec)
nifty = E.nifty_snapshot(prices)

# ------------------------------- header ----------------------------------- #
status = E.market_status()
cls = {"LIVE": "live", "CLOSED": "closed", "PRE-OPEN": "pre"}[status]
asof = nifty["asof"].strftime("%d %b %Y") if nifty else "n/a"
st.markdown(f"""
<div class="topbar">
 <div class="brand">SMART<span>MONEY</span> TERMINAL</div>
 <div class="meta"><span class="badge {cls}">● {status}</span>
 Data as of <b>{asof}</b> &nbsp;|&nbsp; Fetched <b>{fetched.strftime('%d %b %Y, %I:%M:%S %p')} IST</b></div>
</div>""", unsafe_allow_html=True)

if not nifty or sec.empty:
    st.error("Market data could not be loaded (Yahoo Finance issue). Click Refresh in a minute.")
    st.stop()
if missing:
    st.warning(f"No data for: {', '.join(missing)} - excluded from analysis (not shown as blank).")

# snapshot (only complete records are saved)
E.save_snapshot(sec, nifty["asof"])


def kpi(col, label, value, delta=None):
    d = ""
    if delta is not None:
        d = f'<div class="d {"up" if delta >= 0 else "dn"}">{delta:+.2f}%</div>'
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div>{d}</div>',
                 unsafe_allow_html=True)


tabs = st.tabs(["📊 Overview", "🔄 Sector Rotation", "🔎 Screener", "⚖️ Compare",
                "🕯️ Stock Detail", "🗂️ History"])

# ------------------------------ Overview ---------------------------------- #
with tabs[0]:
    c = st.columns(5)
    kpi(c[0], "Nifty 50", f"{nifty['last']:,.2f}", nifty["chg"])
    kpi(c[1], "Nifty 1M", f"{nifty['m1']:+.2f}%")
    kpi(c[2], "Nifty 3M", f"{nifty['m3']:+.2f}%")
    best, worst = sec.sort_values("Ret_1M").iloc[-1], sec.sort_values("Ret_1M").iloc[0]
    kpi(c[3], "Best sector (1M)", best.Sector, best.Ret_1M)
    kpi(c[4], "Weakest sector (1M)", worst.Sector, worst.Ret_1M)

    st.markdown("#### Key takeaways")
    for m in E.build_insights(sec, scr):
        st.markdown(f'<div class="ins">{m}</div>', unsafe_allow_html=True)

    st.markdown("#### Sector returns heatmap (%)")
    cols = ["Ret_1D", "Ret_1W", "Ret_1M", "Ret_3M"]
    z = sec[cols].values
    fig = go.Figure(go.Heatmap(
        z=z, x=["1D", "1W", "1M", "3M"], y=sec.Sector, text=np.round(z, 2), texttemplate="%{text}",
        colorscale="RdYlGn", zmid=0, showscale=False))
    fig.update_layout(height=420, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10),
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")

# --------------------------- Sector Rotation ------------------------------ #
with tabs[1]:
    st.caption("RRG vs Nifty 50: X = RS Ratio (relative trend), Y = RS Momentum. Trail shows recent path.")
    allx = np.concatenate([t.RS_Ratio.tail(tail).values for t in tails.values()])
    ally = np.concatenate([t.RS_Mom.tail(tail).values for t in tails.values()])
    rx = max(1.0, np.abs(allx - 100).max() * 1.15)
    ry = max(1.0, np.abs(ally - 100).max() * 1.15)
    fig = go.Figure()
    for (x0, x1, y0, y1, q) in [(100, 100 + rx, 100, 100 + ry, "Leading"),
                                (100, 100 + rx, 100 - ry, 100, "Weakening"),
                                (100 - rx, 100, 100 - ry, 100, "Lagging"),
                                (100 - rx, 100, 100, 100 + ry, "Improving")]:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, fillcolor=QCOL[q], opacity=0.08, line_width=0)
        fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=q.upper(), showarrow=False,
                           font=dict(color=QCOL[q], size=14), opacity=0.35)
    for name, t in tails.items():
        t = t.tail(tail)
        col = QCOL[t.Quadrant.iloc[-1]]
        fig.add_trace(go.Scatter(x=t.RS_Ratio, y=t.RS_Mom, mode="lines+markers", name=name,
                                 line=dict(color=col, width=1.5), marker=dict(size=4),
                                 hovertemplate=f"{name}<br>Ratio %{{x:.2f}}<br>Mom %{{y:.2f}}<extra></extra>",
                                 showlegend=False))
        fig.add_trace(go.Scatter(x=[t.RS_Ratio.iloc[-1]], y=[t.RS_Mom.iloc[-1]], mode="markers+text",
                                 text=[name], textposition="top center",
                                 marker=dict(size=13, color=col, line=dict(color="white", width=1)),
                                 showlegend=False, hoverinfo="skip"))
    fig.add_vline(x=100, line_color="#64748b"); fig.add_hline(y=100, line_color="#64748b")
    fig.update_layout(height=620, template="plotly_dark", xaxis_title="RS Ratio", yaxis_title="RS Momentum",
                      xaxis=dict(range=[100 - rx, 100 + rx]), yaxis=dict(range=[100 - ry, 100 + ry]),
                      margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, width="stretch")

    show = sec.copy()
    show["Quadrant"] = show.Quadrant.map(QICON)
    show["Prev_Quadrant"] = show.Prev_Quadrant.map(QICON)
    show = show.rename(columns={"Prev_Quadrant": "5D Ago", "Days_In_Quad": "Days in Quad"})
    st.dataframe(show, hide_index=True, width="stretch", column_config={
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
        **{c: st.column_config.NumberColumn(c.replace("_", " "), format="%.2f%%")
           for c in ["Ret_1D", "Ret_1W", "Ret_1M", "Ret_3M", "Rel_1M", "Rel_3M"]}})
    st.info("Tip: Improving -> Leading me jo sector aa rahe hain, unhi ke accumulation stocks Screener me dekho.")

# ------------------------------- Screener --------------------------------- #
with tabs[2]:
    if scr.empty:
        st.warning("No stock data available.")
    else:
        f = st.columns(5)
        sectors_sel = f[0].multiselect("Sector", sorted(scr.Sector.unique()))
        quad_sel = f[1].multiselect("Sector quadrant", ["Leading", "Improving", "Weakening", "Lagging"])
        sig_sel = f[2].multiselect("Signal", scr.Signal.unique().tolist())
        min_score = f[3].slider("Min accumulation score", 0, 100, 0, 5)
        q = f[4].text_input("Search symbol").upper().strip()
        c2 = st.columns(3)
        only50 = c2[0].checkbox("Above 50 DMA only")
        outperf = c2[1].checkbox("Outperforming Nifty (3M)")
        near_hi = c2[2].checkbox("Within 10% of 52W high")

        d = scr.copy()
        if sectors_sel: d = d[d.Sector.isin(sectors_sel)]
        if quad_sel: d = d[d.Sector_Quad.isin(quad_sel)]
        if sig_sel: d = d[d.Signal.isin(sig_sel)]
        d = d[d.Acc_Score >= min_score]
        if q: d = d[d.Symbol.str.contains(q)]
        if only50: d = d[d.Above_50DMA]
        if outperf: d = d[d.Rel_3M > 0]
        if near_hi: d = d[d.From_52W_High >= -10]

        st.caption(f"{len(d)} of {len(scr)} stocks | prices as of {asof}")
        view = d.drop(columns=["Ticker"]).copy()
        view["Sector_Quad"] = view.Sector_Quad.map(lambda x: QICON.get(x, x))
        st.dataframe(view, hide_index=True, width="stretch", height=560, column_config={
            "Acc_Score": st.column_config.ProgressColumn("Acc Score", min_value=0, max_value=100, format="%d"),
            "Price": st.column_config.NumberColumn("Price", format="₹%.2f"),
            **{c: st.column_config.NumberColumn(c.replace("_", " "), format="%.2f%%")
               for c in ["Ret_1D", "Ret_1W", "Ret_1M", "Ret_3M", "Rel_3M", "From_52W_High"]}})
        st.download_button("⬇️ Download CSV", d.to_csv(index=False).encode(),
                           f"screener_{nifty['asof']:%Y%m%d}.csv", "text/csv")
        with st.expander("How is Accumulation Score calculated?"):
            st.markdown("""
- **Up/Down volume (20d)** >=1.3 → 25, >=1.0 → 12
- **OBV rising** (20d) → 20
- **Close > 50 DMA** → 15, **20 DMA > 50 DMA** → 10
- **Outperforming Nifty (3M)** → 15
- **Within 10% of 52W high** → 10
- **RSI between 45–70** → 5

Score >=75 Strong Accumulation, >=55 Accumulation, >=35 Neutral, else Weak/Distribution.""")

# ------------------------------- Compare ---------------------------------- #
with tabs[3]:
    mode = st.radio("Compare", ["Sectors", "Stocks"], horizontal=True)
    span = st.select_slider("Period", ["1M", "2M", "3M", "6M"], value="3M")
    n = {"1M": 21, "2M": 42, "3M": 63, "6M": 126}[span]
    if mode == "Sectors":
        opts = {s: E.SECTORS[s] for s in sec.Sector}
        default = sec.Sector.head(3).tolist()
    else:
        opts = {r.Symbol: r.Ticker for r in scr.itertuples()}
        default = scr.Symbol.head(3).tolist()
    pick = st.multiselect("Select up to 5", list(opts), default=default, max_selections=5)
    pick_items = {"Nifty 50": E.BENCH, **{p: opts[p] for p in pick}}
    fig, rows = go.Figure(), []
    for name, tk in pick_items.items():
        if tk not in prices:
            continue
        c = prices[tk]["Close"].tail(n + 1)
        base = c / c.iloc[0] * 100
        fig.add_trace(go.Scatter(x=base.index, y=base, name=name, mode="lines",
                                 line=dict(width=3 if name == "Nifty 50" else 2,
                                           dash="dot" if name == "Nifty 50" else "solid")))
        full = prices[tk]["Close"]
        rows.append({"Name": name, f"Return {span}": round((c.iloc[-1] / c.iloc[0] - 1) * 100, 2),
                     "Max Drawdown %": round(((c / c.cummax()) - 1).min() * 100, 2),
                     "Volatility % (ann.)": round(full.pct_change().tail(n).std() * np.sqrt(252) * 100, 2),
                     "1W %": round(E.pct(full, 5), 2), "1M %": round(E.pct(full, 21), 2)})
    fig.update_layout(height=480, template="plotly_dark", yaxis_title="Rebased to 100",
                      margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified")
    st.plotly_chart(fig, width="stretch")
    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values(f"Return {span}", ascending=False),
                     hide_index=True, width="stretch")

# ----------------------------- Stock detail ------------------------------- #
with tabs[4]:
    if scr.empty:
        st.warning("No stock data available.")
    else:
        sym = st.selectbox("Stock", scr.Symbol.tolist())
        row = scr[scr.Symbol == sym].iloc[0]
        df = prices[row.Ticker].tail(126)
        c = st.columns(5)
        kpi(c[0], "Price", f"₹{row.Price:,.2f}", row.Ret_1D)
        kpi(c[1], "Acc Score", f"{row.Acc_Score}/100")
        kpi(c[2], "RSI (14)", f"{row.RSI}")
        kpi(c[3], "From 52W High", f"{row.From_52W_High:.1f}%")
        kpi(c[4], "Signal", row.Signal)
        full = prices[row.Ticker]["Close"]
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
        fig.add_trace(go.Candlestick(x=df.index, open=df.Open, high=df.High, low=df.Low, close=df.Close,
                                     name=sym), row=1, col=1)
        for w, col in [(20, "#f59e0b"), (50, "#3b82f6")]:
            fig.add_trace(go.Scatter(x=df.index, y=full.rolling(w).mean().reindex(df.index),
                                     name=f"{w} DMA", line=dict(color=col, width=1.4)), row=1, col=1)
        colors = np.where(df.Close >= df.Open, "#22c55e", "#ef4444")
        fig.add_trace(go.Bar(x=df.index, y=df.Volume, marker_color=colors, name="Volume"), row=2, col=1)
        fig.update_layout(height=620, template="plotly_dark", xaxis_rangeslider_visible=False,
                          margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")

# ------------------------------- History ---------------------------------- #
with tabs[5]:
    st.markdown("#### Quadrant history (last ~3 months)")
    hist = pd.DataFrame({k: v.Quadrant for k, v in tails.items()})
    codes = hist.replace(E.QUAD_CODE).astype(float)
    fig = go.Figure(go.Heatmap(
        z=codes.T.values, x=[d.strftime("%d %b") for d in hist.index], y=hist.columns, text=hist.T.values,
        hovertemplate="%{y} | %{x}<br>%{text}<extra></extra>", showscale=False, zmin=0, zmax=3,
        colorscale=[[0, QCOL["Lagging"]], [.33, QCOL["Improving"]], [.66, QCOL["Weakening"]], [1, QCOL["Leading"]]]))
    fig.update_layout(height=460, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10),
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")
    st.caption("🟢 Leading  🟡 Weakening  🔴 Lagging  🔵 Improving")

    st.markdown("#### Saved daily snapshots")
    snaps = E.load_snapshots()
    if snaps.empty:
        st.info("Snapshots will start accumulating from today (one verified record per trading day).")
    else:
        sel = st.selectbox("Sector", ["All"] + sorted(snaps.Sector.unique()))
        s = snaps if sel == "All" else snaps[snaps.Sector == sel]
        st.dataframe(s.sort_values(["Date", "Rank"], ascending=[False, True]), hide_index=True, width="stretch")
        st.download_button("⬇️ Download all snapshots", snaps.to_csv(index=False).encode(),
                           "sector_snapshots.csv", "text/csv")
