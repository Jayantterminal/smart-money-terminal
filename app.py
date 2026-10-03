import streamlit as st
import pandas as pd
import requests
from datetime import datetime, time
from streamlit_autorefresh import st_autorefresh

# ----------------- PAGE CONFIG -----------------
st.set_page_config(
    page_title="Smart Money Terminal",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏛️ Institutional Smart Money Terminal")

# ----------------- SIDEBAR: REFRESH ENGINE -----------------
st.sidebar.header("⚙️ Terminal Controls")

# Manual Refresh Button
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.sidebar.success("Cache cleared! Fetching fresh data...")

# Auto-Refresh Toggle
auto_refresh_enabled = st.sidebar.checkbox("Enable Auto-Refresh (10 Mins)", value=False)
if auto_refresh_enabled:
    # Auto refresh every 10 minutes (600,000 milliseconds)
    st_autorefresh(interval=600000, key="datarefresh")

st.sidebar.markdown(f"**Last Sync Check:** {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")

# ----------------- TABS SETUP -----------------
tab1, tab2, tab3 = st.tabs([
    "📊 Tab 1: Granular Sector Rotation", 
    "🎯 Tab 2: SMC Swing Screener", 
    "📦 Tab 3: Institutional Delivery"
])

# ==============================================================================
# TAB 1: GRANULAR SECTOR & INDUSTRY PERFORMANCE
# ==============================================================================
with tab1:
    st.subheader("Granular Industry & Sector Performance (Daily EOD)")
    st.markdown("Yeh view market ki micro-industries (jaise Rubber Products, Paints, Telecom, etc.) ka daily momentum track karta hai.")

    @st.cache_data(ttl=3600)
    def fetch_granular_sector_data():
        """
        NSE indices aur granular industry mapping fetch karne ka secure wrapper.
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
            
            clean_data = []
            for item in data:
                index_name = item.get('index', '')
                # Filter for sectoral and thematic indices
                if "NIFTY" in index_name:
                    clean_data.append({
                        "Industry / Sector": index_name,
                        "Last Price": float(item.get('last', 0)),
                        "1D Price Change (%)": float(item.get('percentChange', 0)),
                        "30D Change (%)": float(item.get('perChange30d', 0)),
                    })
            
            df = pd.DataFrame(clean_data)
            return df
        except Exception as e:
            # Fallback dummy structure agar NSE API market hours ke baad restricted ho
            return pd.DataFrame()

    df_sectors = fetch_granular_sector_data()

    if not df_sectors.empty:
        # Sort by 1D change descending
        df_sectors = df_sectors.sort_values(by="1D Price Change (%)", ascending=False).reset_index(drop=True)
        
        # Display metrics layout
        col1, col2 = st.columns([3, 1])
        with col1:
            st.dataframe(
                df_sectors,
                use_container_width=True,
                hide_index=True
            )
        with col2:
            st.markdown("#### Top Gainers & Losers")
            top_gainer = df_sectors.iloc[0]['Industry / Sector'] if len(df_sectors) > 0 else "N/A"
            top_loser = df_sectors.iloc[-1]['Industry / Sector'] if len(df_sectors) > 0 else "N/A"
            st.success(f"**Top Gainer:** {top_gainer}")
            st.error(f"**Top Loser:** {top_loser}")
    else:
        st.warning("Live NSE data connect nahi ho saka. Shaam ko Bhavcopy publish hone ke baad data yahan reflect hoga. 'Refresh Data' button dabakar dubara koshish karein.")

# ==============================================================================
# TAB 2 & TAB 3 (PLACEHOLDERS)
# ==============================================================================
with tab2:
    st.info("Tab 1 verify hone ke baad Tab 2 ka SMC Swing Screener yahan add kiya jayega.")

with tab3:
    st.info("Tab 3 ka Institutional Delivery Analytics yahan integrate hoga.")
