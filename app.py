import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import datetime
import yfinance as yf
from engine import (
    get_sector_fpi_status,
    load_all_subscribers,
    save_all_subscribers,
    dispatch_broadcast_alert
)

st.set_page_config(
    page_title="Smart Money Swing Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        padding: 14px 18px;
        border-radius: 6px;
    }
    div[data-testid="stMetricLabel"] {
        color: #8B949E;
        font-size: 13px;
        font-weight: 500;
        text-transform: uppercase;
    }
    div[data-testid="stMetricValue"] {
        color: #F0F6FC;
        font-family: 'JetBrains Mono', monospace;
        font-size: 24px;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.datetime.now().strftime("%I:%M:%S %p")

# Sidebar Search
st.sidebar.markdown("### ⚡ Terminal Core")
global_ticker = st.sidebar.text_input("🔍 Search Any NSE EQ Stock", value="CUPID").strip().upper()
st.sidebar.markdown("---")

# Admin Pin
with st.sidebar.expander("🔐 Member & Alert Manager (Admin)", expanded=False):
    admin_pin = st.text_input("Admin PIN", type="password", key="admin_pin")
    if admin_pin == st.secrets.get("ADMIN_PIN", "2000"):
        st.success("Authorized")
        subscribers = load_all_subscribers()
        with st.form("add_member_form"):
            new_name = st.text_input("Full Name")
            new_tg = st.text_input("Telegram Chat ID")
            new_wa = st.text_input("WhatsApp Number")
            tg_pref = st.checkbox("Enable TG", value=True)
            submitted = st.form_submit_button("Register Member")
            if submitted and new_name:
                subscribers[new_name] = {"telegram_id": new_tg, "whatsapp_no": new_wa, "telegram_active": tg_pref, "whatsapp_active": False}
                save_all_subscribers(subscribers)
                st.rerun()

st.sidebar.caption(f"Last Cache Refresh: **{st.session_state.last_refresh}**")

# Header
h1, h2 = st.columns([4, 1])
with h1:
    st.title("SMART MONEY SWING TERMINAL")
    st.caption("Pure NSE Cash Segment (EQ) | Macro Fortnightly FPI Inflow | 15m CHoCH Breakout")
with h2:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.datetime.now().strftime("%I:%M:%S %p")
        st.rerun()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Market Regime", "Bullish Markup", "Nifty Trend Intact")
m2.metric("Leading Sector", "Auto (+₹4,250 Cr)", "2 Fortnights Inflow")
m3.metric("CHoCH Radar", "4 Breakouts", "15m Structural Shift")
m4.metric("Active Book", "3 Open Swings", "+5.2% Avg Unrealized")
st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 Live CHoCH Breakout Radar",
    "💼 Active Swing Portfolio",
    "📊 Universal Deep Analytics",
    "🌐 Sector Heatmap & Fortnightly Flow"
])

with tab1:
    st.subheader("15-Minute Change of Character (CHoCH) Breakout Setups")
    radar_df = pd.DataFrame([
        {"Ticker": "BEL", "Sector": "Defence & Cap Goods", "CMP (₹)": 310.40, "15m CHoCH (₹)": 312.50, "SL (₹)": 302.00, "Target 1": 333.50, "Status": "🟢 Confirmed (15m Close)"},
        {"Ticker": "TATAMOTORS", "Sector": "Auto", "CMP (₹)": 982.50, "15m CHoCH (₹)": 985.00, "SL (₹)": 955.00, "Target 1": 1045.00, "Status": "🟡 Approaching Level"},
        {"Ticker": "CUPID", "Sector": "Personal Care", "CMP (₹)": 92.40, "15m CHoCH (₹)": 94.00, "SL (₹)": 88.50, "Target 1": 105.00, "Status": "🟡 Testing Breakout Level"}
    ])
    st.dataframe(radar_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Open Positions & Dynamic Trailing Stop-Loss")
    pos_df = pd.DataFrame([
        {"Ticker": "BEL", "Entry": 304.50, "CMP (₹)": 310.40, "P&L": "+1.93%", "Trailing SL": 304.50, "Rule": "🔒 Moved to Cost (Zero Risk)"}
    ])
    st.dataframe(pos_df, use_container_width=True, hide_index=True)

with tab3:
    st.subheader(f"Institutional Profile & Technical Chart: {global_ticker}")
    
    # Live NSE Fetch
    symbol_ns = f"{global_ticker}.NS"
    try:
        stock = yf.Ticker(symbol_ns)
        hist = stock.history(period="3mo", interval="1d")
        
        if not hist.empty:
            cmp_price = round(hist['Close'].iloc[-1], 2)
            prev_price = round(hist['Close'].iloc[-2], 2)
            chg = round(((cmp_price - prev_price) / prev_price) * 100, 2)
            vol_ratio = round(hist['Volume'].iloc[-1] / hist['Volume'].tail(20).mean(), 2)

            c1, c2, c3 = st.columns(3)
            c1.metric("CMP (NSE Cash)", f"₹{cmp_price}", f"{chg}% Today")
            c2.metric("Volume Absorption", f"{vol_ratio}x Avg", "20-Day Relative Vol")
            c3.metric("Status", "EQ Cash Active", symbol_ns)

            fig = go.Figure(data=[go.Candlestick(
                x=hist.index,
                open=hist['Open'],
                high=hist['High'],
                low=hist['Low'],
                close=hist['Close'],
                name=global_ticker
            )])
            recent_high = hist['High'].tail(15).max()
            fig.add_hline(y=recent_high, line_dash="dash", line_color="#00E676", annotation_text=f"Swing High / CHoCH Level (₹{recent_high:.1f})")
            fig.update_layout(template="plotly_dark", height=450, margin=dict(l=20, r=20, t=20, b=20), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"Ticker '{global_ticker}' not found on NSE. Make sure it is an active NSE symbol.")
    except Exception as e:
        st.error(f"Error fetching data: {e}")

with tab4:
    st.subheader("NSDL Fortnightly FPI Inflow & Sector Rotation")
    sec_flows = get_sector_fpi_status()
    st.json(sec_flows)
