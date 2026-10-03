import streamlit as st
import pandas as pd
from engine import calculate_sector_flow, detect_silent_accumulation

# ----------------- PAGE CONFIG -----------------
st.set_page_config(
    page_title="Smart Money Terminal",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏛️ Institutional Smart Money & Swing Terminal")
st.markdown("Zero-Broker, Rule-Based Institutional Footprint & Sector Rotation Tracker")

# ----------------- TABS SETUP -----------------
tab1, tab2 = st.tabs([
    "📊 Tab 1: Sector Rotation & Fortnightly Flow", 
    "🎯 Tab 2: Stock Silent Accumulation & Swing"
])

# ==============================================================================
# TAB 1: SECTOR ROTATION
# ==============================================================================
with tab1:
    st.subheader("Comparative Fortnightly Sector Shift")
    st.markdown("Tracks institutional capital movement across sectors based on comparative base share shifts.")

    # Sample data structure representing clean NSDL/Sector flow inputs
    raw_sectors = [
        {"Sector": "Financial Services", "val_curr": 29.01, "val_base": 26.50},
        {"Sector": "Healthcare", "val_curr": 8.13, "val_base": 7.45},
        {"Sector": "Information Technology", "val_curr": 5.85, "val_base": 6.80},
        {"Sector": "Automobile and Auto Components", "val_curr": 7.13, "val_base": 7.59},
        {"Sector": "Capital Goods", "val_curr": 11.33, "val_base": 11.61},
        {"Sector": "Metals & Mining", "val_curr": 4.63, "val_base": 5.00}
    ]
    
    df_sec = pd.DataFrame(raw_sectors)
    df_processed_sec = calculate_sector_flow(df_sec)
    
    st.dataframe(df_processed_sec, use_container_width=True, hide_index=True)

# ==============================================================================
# TAB 2: SILENT ACCUMULATION & SWING SCREENER
# ==============================================================================
with tab2:
    st.subheader("Silent Accumulation & Relative Strength Scanner")
    st.markdown("Identifies stocks holding tight ranges or showing strength even when sectors/markets are consolidating.")

    # Sample stock structure mimicking Bhavcopy delivery and price movement analysis
    raw_stocks = [
        {"Symbol": "AXISBANK", "Sector": "Financial Services", "Stock_Change (%)": -0.20, "Delivery (%)": 72.5},
        {"Symbol": "INFY", "Sector": "Information Technology", "Stock_Change (%)": 2.40, "Delivery (%)": 45.0},
        {"Symbol": "NTPC", "Sector": "Power", "Stock_Change (%)": 0.10, "Delivery (%)": 68.0},
        {"Symbol": "TATASTEEL", "Sector": "Metals & Mining", "Stock_Change (%)": -1.80, "Delivery (%)": 32.0}
    ]

    df_stk = pd.DataFrame(raw_stocks)
    df_processed_stk = detect_silent_accumulation(df_stk)

    st.dataframe(df_processed_stk, use_container_width=True, hide_index=True)
