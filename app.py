import streamlit as st
import pandas as pd
import requests
import datetime

# ----------------- PAGE CONFIG -----------------
st.set_page_config(
    page_title="Smart Money Terminal",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏛️ Institutional Smart Money Terminal")

# ----------------- TABS SETUP -----------------
tab1, tab2, tab3 = st.tabs([
    "📊 Tab 1: Sector Rotation", 
    "🎯 Tab 2: SMC Swing Screener", 
    "📦 Tab 3: Institutional Delivery"
])

# ==============================================================================
# TAB 1: SECTOR ROTATION & RELATIVE STRENGTH
# ==============================================================================
with tab1:
    st.subheader("Sector Performance & Momentum Tracker (Daily EOD)")

    @st.cache_data(ttl=3600)
    def fetch_nse_sector_indices():
        """
        Direct NSE API se sectoral indices ka latest EOD snapshot fetch karta hai.
        """
        url = "https://www.nseindia.com/api/allIndices"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/"
        }
        session = requests.Session()
        try:
            # Base hit for cookies
            session.get("https://www.nseindia.com", headers=headers, timeout=10)
            res = session.get(url, headers=headers, timeout=10)
            data = res.json().get('data', [])
            
            sectors = [
                'NIFTY 50', 'NIFTY BANK', 'NIFTY IT', 'NIFTY AUTO', 
                'NIFTY METAL', 'NIFTY PHARMA', 'NIFTY FMCG', 
                'NIFTY REALTY', 'NIFTY ENERGY', 'NIFTY PSU BANK'
            ]
            
            clean_data = []
            for item in data:
                index_name = item.get('index')
                if index_name in sectors:
                    clean_data.append({
                        "Sector": index_name,
                        "Last": float(item.get('last', 0)),
                        "1D % Change": float(item.get('percentChange', 0)),
                        "30D % Change": float(item.get('perChange30d', 0)),
                        "365D % Change": float(item.get('perChange365d', 0))
                    })
            
            df = pd.DataFrame(clean_data)
            return df
        except Exception:
            return pd.DataFrame()

    df_sectors = fetch_nse_sector_indices()

    if not df_sectors.empty:
        # Benchmark Nifty 50 relative strength
        nifty_1d = df_sectors.loc[df_sectors['Sector'] == 'NIFTY 50', '1D % Change'].values
        nifty_30d = df_sectors.loc[df_sectors['Sector'] == 'NIFTY 50', '30D % Change'].values
        
        bench_1d = nifty_1d[0] if len(nifty_1d) > 0 else 0.0
        bench_30d = nifty_30d[0] if len(nifty_30d) > 0 else 0.0

        df_sectors['RS vs Nifty (1D)'] = (df_sectors['1D % Change'] - bench_1d).round(2)
        df_sectors['RS vs Nifty (30D)'] = (df_sectors['30D % Change'] - bench_30d).round(2)

        def assign_quadrant(row):
            if row['Sector'] == 'NIFTY 50':
                return "Benchmark"
            if row['RS vs Nifty (30D)'] >= 0 and row['RS vs Nifty (1D)'] >= 0:
                return "🟢 Leading"
            elif row['RS vs Nifty (30D)'] >= 0 and row['RS vs Nifty (1D)'] < 0:
                return "🟡 Weakening"
            elif row['RS vs Nifty (30D)'] < 0 and row['RS vs Nifty (1D)'] >= 0:
                return "🔵 Improving"
            else:
                return "🔴 Lagging"

        df_sectors['Status'] = df_sectors.apply(assign_quadrant, axis=1)

        # UI Metrics Display
        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(
                df_sectors.sort_values(by="RS vs Nifty (30D)", ascending=False),
                use_container_width=True,
                hide_index=True
            )
        with col2:
            st.markdown("#### Market Stance Summary")
            leading_sectors = df_sectors[df_sectors['Status'] == "🟢 Leading"]['Sector'].tolist()
            improving_sectors = df_sectors[df_sectors['Status'] == "🔵 Improving"]['Sector'].tolist()
            st.success(f"**Leading Sectors:** {', '.join(leading_sectors) if leading_sectors else 'None'}")
            st.info(f"**Improving (Rotation In):** {', '.join(improving_sectors) if improving_sectors else 'None'}")
    else:
        st.warning("NSE Indices data connect nahi ho saka. Refresh karke try karein.")

# ==============================================================================
# TAB 2 & TAB 3 (PLACEHOLDERS)
# ==============================================================================
with tab2:
    st.info("Tab 1 verify hone ke baad Tab 2 ka SMC Screener code yahan add karenge.")

with tab3:
    st.info("Tab 3 ka Delivery Analytics code Tab 2 ke baad integrate hoga.")
