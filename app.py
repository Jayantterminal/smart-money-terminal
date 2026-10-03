import pandas as pd, plotly.graph_objects as go, streamlit as st
from pathlib import Path
import engine as E

st.set_page_config(page_title="Swing Terminal", page_icon="📈", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.2rem} [data-testid="stMetric"]{background:#111827;border:1px solid #1f2937;
border-radius:10px;padding:10px 14px} h1,h2,h3{letter-spacing:.3px}</style>""", unsafe_allow_html=True)

TRADES = Path(__file__).parent / "trades.csv"
if not TRADES.exists():
    pd.DataFrame(columns=["symbol", "date", "entry", "sl", "target"]).to_csv(TRADES, index=False)

# ---- cached loaders (auto daily refresh) ----
@st.cache_data(ttl=6 * 3600)
def bhav_update(): return E.update_bhavcopy()
@st.cache_data(ttl=1800)
def acc(): return E.accumulation_scan()
@st.cache_data(ttl=900)
def rot(): return E.sector_rotation()
@st.cache_data(ttl=3600)
def fii(): return E.fii_dii()
@st.cache_data(ttl=60)
def d15(sym): return E.get_15m(sym)

bhav_update()
st.title("📈 Swing Terminal — Smart Money Footprint")

with st.sidebar:
    st.header("Controls")
    refresh = st.selectbox("Live auto-refresh", ["30s", "60s", "120s", "300s"], index=1)
    min_score = st.slider("Min accumulation score", 40, 90, 55)
    if st.button("🔄 Force refresh data"):
        st.cache_data.clear(); st.rerun()
    st.caption("Data: NSE Bhavcopy (delivery) + Yahoo Finance (15m). Yahoo data ~15 min delayed ho sakta hai.")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🔄 Sector Rotation", "🧠 Smart Money Scanner", "⚡ Live 15m Signals", "📒 My Swing Trades", "🏦 FII / DII"])

# ---- 1. SECTOR ROTATION ----
with tab1:
    r = rot()
    if r.empty: st.warning("Sector data nahi mila.")
    else:
        c = st.columns(4)
        for col, q in zip(c, ["Leading", "Improving", "Weakening", "Lagging"]):
            col.metric(q, ", ".join(r[r.Quadrant == q].Sector) or "-")
        colors = {"Leading": "#22c55e", "Improving": "#3b82f6", "Weakening": "#f59e0b", "Lagging": "#ef4444"}
        fig = go.Figure(go.Scatter(x=r.RS_Ratio, y=r.RS_Mom, mode="markers+text", text=r.Sector,
                        textposition="top center", marker=dict(size=16, color=r.Quadrant.map(colors))))
        fig.add_hline(y=100, line_dash="dot"); fig.add_vline(x=100, line_dash="dot")
        fig.update_layout(template="plotly_dark", height=520, xaxis_title="RS Ratio (vs Nifty)",
                          yaxis_title="RS Momentum")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(r, use_container_width=True, hide_index=True)
        st.caption("Improving → Leading me jo sector aa rahe hain, unhi ke accumulation stocks pakdo.")

# ---- 2. SMART MONEY ----
with tab2:
    a = acc()
    if a.empty: st.warning("Bhavcopy abhi download ho rahi hai / nahi mili. Thodi der baad refresh karo.")
    else:
        view = a[a.Score >= min_score]
        m = st.columns(3)
        m[0].metric("Scanned", len(a)); m[1].metric("Accumulation 🟢", int((a.Score >= 70).sum()))
        m[2].metric("Building 🟡", int(((a.Score >= 55) & (a.Score < 70)).sum()))
        st.dataframe(view, use_container_width=True, hide_index=True, height=520,
                     column_config={"Score": st.column_config.ProgressColumn(min_value=0, max_value=100)})
        with st.expander("Score kaise bana?"):
            st.write("Delivery% vs 20-din avg, delivery qty growth, close > avg price (buyer control), "
                     "up-days, aur price absorb zone (-2% to +6%). Ye footprint hai, guarantee nahi.")

# ---- 3. LIVE 15m ----
@st.fragment(run_every=refresh)
def live():
    a = acc()
    tr = pd.read_csv(TRADES)
    pool = list(dict.fromkeys(tr.symbol.tolist() + (a[a.Score >= 70].Symbol.head(15).tolist() if not a.empty else [])))
    syms = st.multiselect("Watchlist (auto: trades + top accumulation)", pool, default=pool[:12])
    rows = []
    for s in syms:
        d = d15(s)
        if d.empty or len(d) < 25: continue
        x = E.signal_15m(d); last = x.iloc[-1]
        recent = x.tail(4)[x.tail(4).buy]
        rows.append(dict(Symbol=s, LTP=round(last.Close, 2), VWAP=round(last.vwap, 2),
                         Trend="↑" if last.ema9 > last.ema21 else "↓",
                         Signal="🟢 BUY (15m)" if len(recent) else "—",
                         Entry=round(recent.Close.iloc[-1], 2) if len(recent) else None,
                         SL=round(recent.sl.iloc[-1], 2) if len(recent) else None,
                         Target=round(recent.target.iloc[-1], 2) if len(recent) else None,
                         Candle=str(x.index[-1])[5:16]))
    st.caption(f"Auto-refresh {refresh} • last run {pd.Timestamp.now():%H:%M:%S}")
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if syms:
        pick = st.selectbox("Chart", syms)
        d = d15(pick)
        if not d.empty:
            x = E.signal_15m(d)
            f = go.Figure(go.Candlestick(x=x.index, open=x.Open, high=x.High, low=x.Low, close=x.Close))
            f.add_scatter(x=x.index, y=x.vwap, name="VWAP", line=dict(color="#f59e0b"))
            f.add_scatter(x=x.index, y=x.ema21, name="EMA21", line=dict(color="#3b82f6"))
            b = x[x.buy]
            f.add_scatter(x=b.index, y=b.Low * 0.998, mode="markers", name="BUY",
                          marker=dict(symbol="triangle-up", size=14, color="#22c55e"))
            f.update_layout(template="plotly_dark", height=520, xaxis_rangeslider_visible=False)
            st.plotly_chart(f, use_container_width=True)
with tab3: live()

# ---- 4. MY TRADES ----
with tab4:
    st.caption("Apne chal rahe swing trades yahan daalo — SL hit / target / running auto dikhega.")
    tr = st.data_editor(pd.read_csv(TRADES), num_rows="dynamic", use_container_width=True, key="ed")
    if st.button("💾 Save trades"):
        tr.to_csv(TRADES, index=False); st.success("Saved")
    if len(tr.dropna()):
        res = E.track_trades(tr.dropna())
        st.dataframe(res, use_container_width=True, hide_index=True)
        if "PnL_pct" in res:
            c = st.columns(3)
            c[0].metric("Running", int((res.Status.str.contains("RUNNING")).sum()))
            c[1].metric("SL hit", int((res.Status.str.contains("SL")).sum()))
            c[2].metric("Target", int((res.Status.str.contains("TARGET")).sum()))

# ---- 5. FII/DII ----
with tab5:
    f = fii()
    if f.empty: st.info("NSE FII/DII API abhi block/slow hai. Baad me refresh karo.")
    else: st.dataframe(f, use_container_width=True, hide_index=True)
