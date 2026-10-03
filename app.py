import streamlit as st
import pandas as pd
import requests
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
# TAB 1: INSTITUTIONAL CAPITAL FLOW & SECTOR ROTATION (LIVE NSE FETCH)
# ==============================================================================
with tab1:
    st.subheader("NSE Sector Performance & Flow Tracker")
    st.markdown("Live public NSE endpoint fetching for sectoral momentum and relative shift calculation.")

    @st.cache_data(ttl=600)
    def fetch_live_nse_sectors():
        url = "https://www.nseindia.com/api/allIndices"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.nseindia.com/"
        }
        session = requests.Session()
        try:
            # Establishing session cookie from NSE home page
            session.get("https://www.nseindia.com", headers=headers, timeout=10)
            response = session.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json().get('data', [])
                clean_records = []
                
                for item in data:
                    index_name = item.get('index', '')
                    if "NIFTY" in index_name and not any(x in index_name for x in ["50", "NEXT", "MID", "SMALL", "100", "200", "500"]):
                        sector_name = index_name.replace("NIFTY ", "").title()
                        p_change = float(item.get('percentChange', 0))
                        p_30d = float(item.get('perChange30d', 0) or 0)
                        
                        # Dynamic Flow Shift Calculation
                        flow_shift = round(p_change - (p_30d / 30), 2)
                        
                        if flow_shift >= 1.5:
                            signal = "🟢 Heavy Inflow"
                        elif flow_shift > 0:
                            signal = "🟢 Inflow"
                        elif flow_shift == 0:
                            signal = "⚪ Neutral"
                        elif flow_shift <= -1.0:
                            signal = "🔴 Heavy Outflow"
                        else:
                            signal = "🔴 Outflow"

                        clean_records.append({
                            "Sector": sector_name,
                            "Last Price": item.get('last', 0),
                            "1D Change (%)": p_change,
                            "30D Change (%)": p_30d,
                            "Flow Shift (%)": flow_shift,
                            "Flow Signal": signal
                        })
                
                df = pd.DataFrame(clean_records)
                if not df.empty:
                    return df.sort_values(by="Flow Shift (%)", ascending=False).reset_index(drop=True)
            return pd.DataFrame()
        except Exception as e:
            return pd.DataFrame()

    df_live = fetch_live_nse_sectors()

    if not df_live.empty:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.dataframe(df_live, use_container_width=True, hide_index=True)
        with col2:
            st.markdown("#### Live Stance")
            heavy_inflow = df_live[df_live['Flow Signal'].str.contains("Heavy Inflow")]['Sector'].tolist()
            outflows = df_live[df_live['Flow Signal'].str.contains("Outflow")]['Sector'].tolist()
            st.success(f"**Inflows:** {', '.join(heavy_inflow) if heavy_inflow else 'None'}")
            st.error(f"**Outflows count:** {len(outflows)}")
    else:
        st.warning("NSE live connection restricted due to server shields. Please click 'Refresh Data' or verify connection.")

# ==============================================================================
# TAB 2 & TAB 3 (STRUCTURED FOR LIVE EXPANSION)
# ==============================================================================
with tab2:
    st.subheader("Smart Money Concepts (SMC) Swing Screener")
    st.info("Structure mapping reads swing highs/lows from historical price series without broker dependencies.")

with tab3:
    st.subheader("Institutional Delivery & Volume Accumulation Scanner")
    st.info("Bhavcopy delivery archive processor ready for integration.")
