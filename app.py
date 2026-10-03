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
# TAB 1: INSTITUTIONAL CAPITAL FLOW & SECTOR ROTATION
# ==============================================================================
with tab1:
    st.subheader("NSE Institutional Capital Flow & Sector Rotation")
    st.markdown("Yeh view sectors ke institutional flow shifts (Inflow / Heavy Inflow / Outflow) ko clean format me track karta hai.")

    @st.cache_data(ttl=3600)
    def fetch_institutional_sector_flow():
        """
        NSE indices fetch karke clean sectoral institutional flow format generate karta hai.
        """
        url = "https://www.nseindia.com/api/allIndices"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/"
        }
        session = requests.Session()
        try:
            session.get("https://www.nseindia.com", headers=headers, timeout=10)
            res = session.get(url, headers=headers, timeout=10)
            data = res.json().get('data', [])
            
            # Target clean sectors mapping
            allowed_sectors = [
                'NIFTY FINANCIAL SERVICES', 'NIFTY BANK', 'NIFTY IT', 
                'NIFTY AUTO', 'NIFTY METAL', 'NIFTY PHARMA', 'NIFTY FMCG', 
                'NIFTY REALTY', 'NIFTY ENERGY', 'NIFTY INFRASTRUCTURE', 
                'NIFTY MEDIA', 'NIFTY CONSUMER DURABLES', 'NIFTY OIL & GAS', 
                'NIFTY PSU BANK', 'NIFTY PRIVATE BANK'
            ]
            
            clean_data = []
            for item in data:
                index_name = item.get('index', '')
                if index_name in allowed_sectors:
                    # Clean sector name display
                    sector_display = index_name.replace("NIFTY ", "").title()
                    pct_1d = float(item.get('percentChange', 0))
                    pct_30d = float(item.get('perChange30d', 0))
                    
                    # Flow Shift calculation logic
                    flow_shift = round(pct_1d - (pct_30d / 30), 2)
                    
                    # Assigning Flow Signals
                    if flow_shift >= 1.5:
                        signal = "🟢 Heavy Inflow"
                    elif flow_shift > 0:
                        signal = "🟢 Inflow"
                    elif flow_shift == 0:
                        signal = "⚪ Neutral"
                    else:
                        signal = "🔴 Outflow"

                    clean_data.append({
                        "Sector": sector_display,
                        "Current 1D Change (%)": pct_1d,
                        "30D Change (%)": pct_30d,
                        "Flow Shift (%)": flow_shift,
                        "Flow Signal": signal
                    })
            
            df = pd.DataFrame(clean_data)
            return df
        except Exception:
            return pd.DataFrame()

    df_flow = fetch_institutional_sector_flow()

    if not df_flow.empty:
        # Sort by Flow Shift descending
        df_flow = df_flow.sort_values(by="Flow Shift (%)", ascending=False).reset_index(drop=True)
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.dataframe(
                df_flow,
                use_container_width=True,
                hide_index=True
            )
        with col2:
            st.markdown("#### Flow Summary")
            heavy_inflow = df_flow[df_flow['Flow Signal'] == "🟢 Heavy Inflow"]['Sector'].tolist()
            outflows = df_flow[df_flow['Flow Signal'] == "🔴 Outflow"]['Sector'].tolist()
            
            st.success(f"**Heavy Inflow:** {', '.join(heavy_inflow) if heavy_inflow else 'None'}")
            st.error(f"**Outflow Sectors:** {', '.join(outflows) if outflows else 'None'}")
    else:
        st.warning("Live NSE data connect nahi ho saka. Refresh button dabakar dobara koshish karein.")

# ==============================================================================
# TAB 2 & TAB 3 (PLACEHOLDERS)
# ==============================================================================
with tab2:
    st.info("Tab 2: SMC Swing Screener (Pending)")

with tab3:
    st.info("Tab 3: Institutional Delivery (Pending)")
