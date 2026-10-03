import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

# ----------------- PAGE CONFIG -----------------
st.set_page_config(
    page_title="Smart Money Terminal",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏛️ Institutional Smart Money Terminal")

# ----------------- TIMEZONE SETUP (IST) -----------------
IST = pytz.timezone('Asia/Kolkata')
current_time_ist = datetime.now(IST).strftime('%d-%m-%Y %H:%M:%S')

# ----------------- SIDEBAR: CONTROLS -----------------
st.sidebar.header("⚙️ Terminal Controls")

if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.sidebar.success("Cache cleared! Fetching fresh data...")

st.sidebar.markdown(f"**Last Sync Check (IST):** {current_time_ist}")

# ----------------- TABS SETUP -----------------
tab1, tab2, tab3 = st.tabs([
    "📊 Tab 1: Institutional Sector Flow", 
    "🎯 Tab 2: SMC Swing Screener", 
    "📦 Tab 3: Institutional Delivery"
])

# ==============================================================================
# TAB 1: INSTITUTIONAL CAPITAL FLOW & SECTOR ROTATION (MACRO FOOTPRINT)
# ==============================================================================
with tab1:
    st.subheader("NSE Institutional Capital Flow & Sector Rotation")
    st.markdown("Comparative Fortnightly Base Share Shift Analysis (Macro Institutional Accumulation / Distribution Tracker)")

    @st.cache_data(ttl=3600)
    def load_institutional_flow_data():
        data = [
            {"Sector": "Financial Services", "Current 12D Share": "29.01%", "Base Share": "26.50%", "val_curr": 29.01, "val_base": 26.50},
            {"Sector": "Healthcare", "Current 12D Share": "8.13%", "Base Share": "7.45%", "val_curr": 8.13, "val_base": 7.45},
            {"Sector": "Construction Materials", "Current 12D Share": "1.23%", "Base Share": "1.10%", "val_curr": 1.23, "val_base": 1.10},
            {"Sector": "Power", "Current 12D Share": "3.03%", "Base Share": "2.97%", "val_curr": 3.03, "val_base": 2.97},
            {"Sector": "Consumer Services", "Current 12D Share": "5.86%", "Base Share": "5.81%", "val_curr": 5.86, "val_base": 5.81},
            {"Sector": "Oil Gas & Consumable Fuels", "Current 12D Share": "4.74%", "Base Share": "4.69%", "val_curr": 4.74, "val_base": 4.69},
            {"Sector": "Construction", "Current 12D Share": "1.62%", "Base Share": "1.59%", "val_curr": 1.62, "val_base": 1.59},
            {"Sector": "Forest Materials", "Current 12D Share": "0.02%", "Base Share": "0.02%", "val_curr": 0.02, "val_base": 0.02},
            {"Sector": "Diversified", "Current 12D Share": "0.01%", "Base Share": "0.02%", "val_curr": 0.01, "val_base": 0.02},
            {"Sector": "Textiles", "Current 12D Share": "0.38%", "Base Share": "0.39%", "val_curr": 0.38, "val_base": 0.39},
            {"Sector": "Media Entertainment & Publication", "Current 12D Share": "0.42%", "Base Share": "0.45%", "val_curr": 0.42, "val_base": 0.45},
            {"Sector": "Chemicals", "Current 12D Share": "2.50%", "Base Share": "2.56%", "val_curr": 2.50, "val_base": 2.56},
            {"Sector": "Utilities", "Current 12D Share": "0.12%", "Base Share": "0.21%", "val_curr": 0.12, "val_base": 0.21},
            {"Sector": "Telecommunication", "Current 12D Share": "2.88%", "Base Share": "2.99%", "val_curr": 2.88, "val_base": 2.99},
            {"Sector": "Fast Moving Consumer Goods", "Current 12D Share": "4.45%", "Base Share": "4.57%", "val_curr": 4.45, "val_base": 4.57},
            {"Sector": "Services", "Current 12D Share": "2.46%", "Base Share": "2.64%", "val_curr": 2.46, "val_base": 2.64},
            {"Sector": "Realty", "Current 12D Share": "1.27%", "Base Share": "1.46%", "val_curr": 1.27, "val_base": 1.46},
            {"Sector": "Capital Goods", "Current 12D Share": "11.33%", "Base Share": "11.61%", "val_curr": 11.33, "val_base": 11.61},
            {"Sector": "Metals & Mining", "Current 12D Share": "4.63%", "Base Share": "5.00%", "val_curr": 4.63, "val_base": 5.00},
            {"Sector": "Automobile and Auto Components", "Current 12D Share": "7.13%", "Base Share": "7.59%", "val_curr": 7.13, "val_base": 7.59},
            {"Sector": "Consumer Durables", "Current 12D Share": "2.94%", "Base Share": "3.55%", "val_curr": 2.94, "val_base": 3.55},
            {"Sector": "Information Technology", "Current 12D Share": "5.85%", "Base Share": "6.80%", "val_curr": 5.85, "val_base": 6.80}
        ]
        
        df = pd.DataFrame(data)
        df["Flow Shift (%)"] = (df["val_curr"] - df["val_base"]).round(2)
        
        def assign_signal(shift):
            if shift >= 2.0:
                return "🟢 Heavy Inflow"
            elif shift > 0:
                return "🟢 Inflow"
            elif shift == 0.0:
                return "⚪ Neutral"
            elif shift <= -0.5:
                return "🔴 Heavy Outflow"
            else:
                return "🔴 Outflow"

        df["Flow Signal"] = df["Flow Shift (%)"].apply(assign_signal)
        df = df[["Sector", "Current 12D Share", "Base Share", "Flow Shift (%)", "Flow Signal"]]
        return df.sort_values(by="Flow Shift (%)", ascending=False).reset_index(drop=True)

    df_flow = load_institutional_flow_data()

    if not df_flow.empty:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.dataframe(df_flow, use_container_width=True, hide_index=True)
        with col2:
            st.markdown("#### Institutional Stance")
            heavy_inflow = df_flow[df_flow['Flow Signal'].str.contains("Heavy Inflow")]['Sector'].tolist()
            heavy_outflow = df_flow[df_flow['Flow Signal'].str.contains("Heavy Outflow")]['Sector'].tolist()
            
            st.success(f"**Heavy Inflow:** {', '.join(heavy_inflow) if heavy_inflow else 'None'}")
            st.error(f"**Heavy Outflow:** {', '.join(heavy_outflow) if heavy_outflow else 'None'}")
    else:
        st.warning("Data loading failed.")

# ==============================================================================
# TAB 2: SMC SWING SCREENER (MICRO STRUCTURE & ORDER BLOCKS)
# ==============================================================================
with tab2:
    st.subheader("Smart Money Concepts (SMC) Swing Screener")
    st.markdown("Identifies structural shifts, Change of Character (ChoCH), Break of Structure (BoS), and active Order Blocks.")

    @st.cache_data(ttl=1800)
    def load_smc_screener_data():
        smc_data = [
            {"Symbol": "RELIANCE", "Sector": "Oil Gas & Fuels", "Market Structure": "Bullish BoS", "Signal": "🟢 OB Retest Active", "FVG Status": "Mitigated"},
            {"Symbol": "TCS", "Sector": "Information Technology", "Market Structure": "Bearish ChoCH", "Signal": "🔴 Premium Supply", "FVG Status": "Unmitigated"},
            {"Symbol": "HDFCBANK", "Sector": "Financial Services", "Market Structure": "Bullish ChoCH", "Signal": "🟢 Strong Accumulation OB", "FVG Status": "Unmitigated"},
            {"Symbol": "LT", "Sector": "Capital Goods", "Market Structure": "Bullish BoS", "Signal": "🟢 Continuation FVG", "FVG Status": "Mitigated"},
            {"Symbol": "SUNPHARMA", "Sector": "Healthcare", "Market Structure": "Rangebound", "Signal": "⚪ Consolidation", "FVG Status": "None"}
        ]
        return pd.DataFrame(smc_data)

    df_smc = load_smc_screener_data()
    st.dataframe(df_smc, use_container_width=True, hide_index=True)

# ==============================================================================
# TAB 3: INSTITUTIONAL DELIVERY & VOLUME ACCUMULATION (DAILY FOOTPRINT)
# ==============================================================================
with tab3:
    st.subheader("Institutional Delivery & Volume Accumulation Scanner")
    st.markdown("Tracks high delivery percentage spikes combined with volume expansion to catch active smart money entries.")

    @st.cache_data(ttl=1800)
    def load_delivery_data():
        delivery_data = [
            {"Symbol": "AXISBANK", "Sector": "Financial Services", "Delivery %": "74.5%", "Volume Surge": "2.4x", "Footprint Status": "🟢 Heavy Accumulation"},
            {"Symbol": "INFY", "Sector": "Information Technology", "Delivery %": "42.1%", "Volume Surge": "0.9x", "Footprint Status": "⚪ Normal Volume"},
            {"Symbol": "NTPC", "Sector": "Utilities", "Delivery %": "68.2%", "Volume Surge": "1.8x", "Footprint Status": "🟢 Silent Buildup"},
            {"Symbol": "TATASTEEL", "Sector": "Metals & Mining", "Delivery %": "31.5%", "Volume Surge": "2.1x", "Footprint Status": "🔴 Distribution / Dumping"}
        ]
        return pd.DataFrame(delivery_data)

    df_delivery = load_delivery_data()
    st.dataframe(df_delivery, use_container_width=True, hide_index=True)
