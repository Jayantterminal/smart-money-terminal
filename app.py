import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import datetime
from engine import (
    get_sector_fpi_status,
    load_all_subscribers,
    save_all_subscribers,
    dispatch_broadcast_alert
)

# -------------------------------------------------------------------
# 1. APPLICATION SETUP & CUSTOM INJECTED CSS
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Smart Money Swing Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# High-contrast institutional dark CSS styling
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
        letter-spacing: 0.5px;
    }
    div[data-testid="stMetricValue"] {
        color: #F0F6FC;
        font-family: 'JetBrains Mono', monospace;
        font-size: 24px;
        font-weight: 700;
    }
    .stButton>button {
        border-radius: 4px;
        font-weight: 600;
        border: 1px solid #30363D;
    }
</style>
""", unsafe_allow_html=True)

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.datetime.now().strftime("%I:%M:%S %p")

def export_terminal_to_excel(dfs_dict: dict):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        for sheet_name, df in dfs_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return buffer.getvalue()


# -------------------------------------------------------------------
# 2. PERSISTENT SIDEBAR: SEARCH & MEMBER MANAGER
# -------------------------------------------------------------------
st.sidebar.markdown("### ⚡ Terminal Core")

global_ticker = st.sidebar.text_input("🔍 Search Any NSE EQ Stock", value="BEL").strip().upper()
st.sidebar.markdown("---")

with st.sidebar.expander("🔐 Member & Alert Manager (Admin)", expanded=False):
    admin_pin = st.text_input("Admin PIN", type="password", key="admin_pin")
    
    if admin_pin == st.secrets.get("ADMIN_PIN", "1234"):
        st.success("Authorized")
        subscribers = load_all_subscribers()
        
        member_search = st.text_input("Search Member by Name / ID", "").strip().lower()

        st.caption("**Add New Subscriber (Zero Code Change)**")
        with st.form("add_member_form"):
            new_name = st.text_input("Full Name / Label (e.g. Rahul VIP)")
            new_tg = st.text_input("Telegram Chat ID")
            new_wa = st.text_input("WhatsApp Number (+91...)")
            col_add1, col_add2 = st.columns(2)
            tg_pref = col_add1.checkbox("Enable TG", value=True)
            wa_pref = col_add2.checkbox("Enable WA", value=False)
            submitted = st.form_submit_button("➕ Register Member")

            if submitted and new_name:
                subscribers[new_name] = {
                    "telegram_id": new_tg.strip(),
                    "whatsapp_no": new_wa.strip(),
                    "telegram_active": tg_pref,
                    "whatsapp_active": wa_pref,
                    "role": "Subscriber"
                }
                save_all_subscribers(subscribers)
                st.success(f"Added {new_name}!")
                st.rerun()

        st.caption("**Active Members Directory:**")
        for name, data in list(subscribers.items()):
            if member_search and (member_search not in name.lower() and member_search not in data.get('telegram_id', '')):
                continue
            
            c_info, c_action = st.columns([3, 1])
            c_info.text(f"👤 {name} ({'TG' if data.get('telegram_active') else ''} {'WA' if data.get('whatsapp_active') else ''})")
            if c_action.button("❌", key=f"del_{name}"):
                del subscribers[name]
                save_all_subscribers(subscribers)
                st.rerun()

        if st.button("🔔 Send Test Ping to Active Members"):
            bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
            stats = dispatch_broadcast_alert("⚡ *System Verification Ping*: Real-time alerts connected!", bot_token)
            st.info(f"Ping Dispatched: TG ({stats['telegram_sent']}) | WA ({stats['whatsapp_sent']})")
    else:
        st.caption("Enter Admin PIN to manage members.")

st.sidebar.markdown("---")
st.sidebar.caption(f"Last Cache Refresh: **{st.session_state.last_refresh}**")


# -------------------------------------------------------------------
# 3. TOP GLOBAL HEADER BAR & CONTROLS
# -------------------------------------------------------------------
header_col1, header_col2, header_col3 = st.columns([3, 1, 1])
with header_col1:
    st.title("SMART MONEY SWING TERMINAL")
    st.caption("Pure NSE Cash Segment (EQ) | Macro Fortnightly FPI Inflow | 15m CHoCH Breakout")

with header_col2:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.datetime.now().strftime("%I:%M:%S %p")
        st.rerun()

with header_col3:
    quick_export = export_terminal_to_excel({
        "System_Snapshot": pd.DataFrame({"Status": ["Synced"], "Timestamp": [st.session_state.last_refresh]})
    })
    st.download_button(
        "📥 Export XLSX",
        data=quick_export,
        file_name="Smart_Money_Terminal_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

m1, m2, m3, m4 = st.columns(4)
m1.metric("Market Regime", "Bullish Markup", "Nifty 50 Trend Intact")
m2.metric("Leading Sector", "Auto (+₹4,250 Cr)", "2 Consecutive Fortnights")
m3.metric("CHoCH Watchlist", "4 Setups", "Watching 15m Close")
m4.metric("Active Swing Book", "3 Open Trades", "+5.2% Avg Unrealized")

st.markdown("---")


# -------------------------------------------------------------------
# 4. TAB NAVIGATION
# -------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 Live CHoCH Breakout Radar",
    "💼 Active Swing Portfolio",
    "📊 Universal Deep Analytics",
    "🌐 Sector Heatmap & Fortnightly Flow"
])

# TAB 1: RADAR
with tab1:
    st.subheader("15-Minute Change of Character (CHoCH) Breakout Setups")
    st.caption("Filtered by Daily Base Absorption + 9:30 AM Rule + Volume Spike (RVOL ≥ 1.5x)")

    radar_df = pd.DataFrame([
        {
            "Ticker": "BEL",
            "Cap": "🟪 Mid-cap",
            "Nifty500": "Yes",
            "Sector": "Defence & Cap Goods",
            "CMP (₹)": 310.40,
            "15m CHoCH (₹)": 312.50,
            "Dynamic ATR SL (₹)": 302.00,
            "Risk %": "2.70%",
            "Target 1 (1:2)": 333.50,
            "Target 2 (Runner)": 345.00,
            "RVOL": "2.1x",
            "Status": "🟢 CONFIRMED (15m Close)"
        },
        {
            "Ticker": "TATAMOTORS",
            "Cap": "🟦 Large-cap",
            "Nifty500": "Yes",
            "Sector": "Auto",
            "CMP (₹)": 982.50,
            "15m CHoCH (₹)": 985.00,
            "Dynamic ATR SL (₹)": 955.00,
            "Risk %": "2.80%",
            "Target 1 (1:2)": 1045.00,
            "Target 2 (Runner)": 1080.00,
            "RVOL": "1.7x",
            "Status": "🟡 Approaching Level"
        },
        {
            "Ticker": "KIRLOSENG",
            "Cap": "⚪ Broad EQ",
            "Nifty500": "No",
            "Sector": "Capital Goods",
            "CMP (₹)": 842.00,
            "15m CHoCH (₹)": 848.00,
            "Dynamic ATR SL (₹)": 816.00,
            "Risk %": "3.08%",
            "Target 1 (1:2)": 912.00,
            "Target 2 (Runner)": 950.00,
            "RVOL": "1.6x",
            "Status": "🟡 Approaching Level"
        }
    ])

    t1_filter = st.text_input("Filter Radar Table by Symbol / Sector", "", key="t1_filter").strip().upper()
    if t1_filter:
        radar_df = radar_df[radar_df['Ticker'].str.contains(t1_filter) | radar_df['Sector'].str.upper().str.contains(t1_filter)]

    st.dataframe(radar_df, use_container_width=True, hide_index=True)

# TAB 2: PORTFOLIO
with tab2:
    st.subheader("Open Positions & Dynamic Trailing Stop-Loss")
    positions_df = pd.DataFrame([
        {
            "Ticker": "BEL",
            "Entry Date": "2026-09-28",
            "Entry Price": 304.50,
            "CMP (₹)": 310.40,
            "P&L (%)": "+1.93%",
            "Initial SL": 296.00,
            "Trailing SL (Dynamic)": 304.50,
            "Trailing Rule": "🔒 Moved to Cost (Zero Risk)",
            "Days Held": 5
        },
        {
            "Ticker": "POWERGRID",
            "Entry Date": "2026-09-24",
            "Entry Price": 320.00,
            "CMP (₹)": 332.50,
            "P&L (%)": "+3.91%",
            "Initial SL": 311.00,
            "Trailing SL (Dynamic)": 324.00,
            "Trailing Rule": "Trailing 15m Higher-Low",
            "Days Held": 9
        }
    ])
    st.dataframe(positions_df, use_container_width=True, hide_index=True)

# TAB 3: DEEP ANALYTICS
with tab3:
    st.subheader(f"Institutional Profile: {global_ticker}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Delivery Absorption", "2.8x Avg", "+182% vs 20D")
    c2.metric("Promoter Stake", "51.8%", "▲ +0.4% QoQ Buying")
    c3.metric("FII / FPI Holding", "19.2%", "▲ +1.1% QoQ Accumulation")
    c4.metric("Recent Bulk Deal", "₹48.2 Cr", "Bought by Institutional Fund")

    st.markdown("#### Smart Money Candlestick & 15m CHoCH Structure")
    dates = pd.date_range(end=datetime.date.today(), periods=35, freq='D')
    close_prices = 300.0 + np.cumsum(np.random.randn(35) * 3)
    
    fig = go.Figure(data=[go.Candlestick(
        x=dates,
        open=close_prices - 1.5,
        high=close_prices + 3.0,
        low=close_prices - 2.5,
        close=close_prices,
        name=global_ticker
    )])
    fig.add_hline(y=float(close_prices[-1] * 1.015), line_dash="dash", line_color="#00E676", annotation_text="15m CHoCH Level")
    fig.add_hline(y=float(close_prices[-1] * 0.975), line_dash="dash", line_color="#FF5252", annotation_text="ATR Stop-Loss")
    fig.update_layout(template="plotly_dark", height=420, margin=dict(l=20, r=20, t=20, b=20), xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 📰 Recent Corporate Catalysts & Filing News")
    st.info("• **Defence Ministry Contract**: Secured ₹1,150 Cr radar supply order from Indian Navy (4 hours ago) [🟢 Bullish]")

# TAB 4: SECTOR FLOW
with tab4:
    st.subheader("NSDL Fortnightly FPI Inflow & Sector Rotation")
    st.caption("Ranking based on 2 Consecutive Fortnights Accumulation: Flow(T) > Flow(T-1) > Flow(T-2)")

    sector_flows = get_sector_fpi_status()
    sector_rows = []
    for sec_name, sec_meta in sector_flows.items():
        sector_rows.append({
            "Sector": sec_name,
            "Latest Fortnight (₹ Cr)": f"+₹{sec_meta['Current_Flow_Cr']} Cr" if sec_meta['Current_Flow_Cr'] > 0 else f"-₹{abs(sec_meta['Current_Flow_Cr'])} Cr",
            "Prev Fortnight (₹ Cr)": f"+₹{sec_meta['Prev_Flow_Cr']} Cr" if sec_meta['Prev_Flow_Cr'] > 0 else f"-₹{abs(sec_meta['Prev_Flow_Cr'])} Cr",
            "Two Consecutive Increases?": "✅ Confirmed" if sec_meta['Two_Consecutive_Spike'] else "❌ No",
            "Sector Lifecycle": sec_meta['Trend_Phase']
        })

    sec_display_df = pd.DataFrame(sector_rows).sort_values(by="Two Consecutive Increases?", ascending=False)
    st.dataframe(sec_display_df, use_container_width=True, hide_index=True)
