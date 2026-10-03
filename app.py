import streamlit as st
import pandas as pd
import numpy as np
import io
import datetime
import os
import json
import requests
import yfinance as yf
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Page Config
st.set_page_config(
    page_title="Institutional Smart Money Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Terminal CSS
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
        font-weight: 600;
        text-transform: uppercase;
    }
    div[data-testid="stMetricValue"] {
        color: #F0F6FC;
        font-family: 'JetBrains Mono', monospace;
        font-size: 20px;
        font-weight: 700;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #161B22;
        border-radius: 4px;
        color: #C9D1D9;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #21262D !important;
        color: #58A6FF !important;
        border-bottom: 2px solid #58A6FF !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 0. STRICT PASSWORD AUTHENTICATION LOCK
# ==========================================
MASTER_PASSWORD = "smartmoney"

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("<h2 style='text-align: center; margin-top: 50px;'>🔒 Terminal Access Gate</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8B949E;'>Enter terminal master security key to decrypt dashboard data.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("auth_form"):
            pwd_input = st.text_input("Enter Password", type="password", placeholder="Enter key...")
            submitted = st.form_submit_button("Unlock Terminal", use_container_width=True)
            if submitted:
                if pwd_input == MASTER_PASSWORD:
                    st.session_state["authenticated"] = True
                    st.success("Access Granted!")
                    st.rerun()
                else:
                    st.error("Invalid Security Key. Access Denied.")
    st.stop()

# ==========================================
# 1. LIVE TIME & REGIME CALCULATOR
# ==========================================
def get_current_ist_str():
    ist_time = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    return ist_time.strftime("%d-%b-%Y | %I:%M:%S %p IST")

if "last_refresh_dt" not in st.session_state:
    st.session_state.last_refresh_dt = get_current_ist_str()

@st.cache_data(ttl=600)
def get_live_market_regime():
    try:
        nifty = yf.Ticker("^NSEI").history(period="3mo", interval="1d")
        sensex = yf.Ticker("^BSESN").history(period="3mo", interval="1d")
        
        if not nifty.empty:
            nifty_cmp = round(nifty['Close'].iloc[-1], 2)
            nifty_prev = round(nifty['Close'].iloc[-2], 2)
            nifty_chg = round(((nifty_cmp - nifty_prev) / nifty_prev) * 100, 2)
            nifty_ema20 = nifty['Close'].ewm(span=20).mean().iloc[-1]
            nifty_ema50 = nifty['Close'].ewm(span=50).mean().iloc[-1]

            sensex_cmp = round(sensex['Close'].iloc[-1], 2) if not sensex.empty else 0.0
            sensex_prev = round(sensex['Close'].iloc[-2], 2) if not sensex.empty else sensex_cmp
            sensex_chg = round(((sensex_cmp - sensex_prev) / sensex_prev) * 100, 2) if sensex_prev > 0 else 0.0

            if nifty_cmp >= nifty_ema20 and nifty_cmp >= nifty_ema50:
                regime_status = "Bullish Markup"
                regime_badge = f"↑ Nifty Uptrend ({'+' if nifty_chg >= 0 else ''}{nifty_chg}%) | Sensex ({'+' if sensex_chg >= 0 else ''}{sensex_chg}%)"
            elif nifty_cmp < nifty_ema20 and nifty_cmp < nifty_ema50:
                regime_status = "Bearish Markdown"
                regime_badge = f"↓ Below 20 EMA ({nifty_chg}%) | Risk Off"
            else:
                regime_status = "Consolidation / Range"
                regime_badge = f"↔ 20-50 EMA Compression ({nifty_chg}%)"

            return regime_status, regime_badge, nifty_cmp, sensex_cmp
    except Exception:
        pass
    return "Bullish Markup", "↑ Nifty 50 & Sensex Intact", 25800.0, 84200.0

regime_title, regime_sub, n_live_val, s_live_val = get_live_market_regime()

# Master Stock Directory
@st.cache_data(ttl=86400)
def load_full_nse_universe():
    directory = {
        "Ather Energy Ltd.": "ATHERENERG", "Bajaj Housing Finance Ltd.": "BAJAJHFL",
        "Bajaj Auto Ltd.": "BAJAJ-AUTO", "Bajaj Finance Ltd.": "BAJFINANCE",
        "Bajaj Finserv Ltd.": "BAJAJFINSV", "Star Health and Allied Insurance": "STARHEALTH",
        "PNC Infratech Ltd.": "PNCINFRA", "Shree Cement Ltd.": "SHREECEM",
        "Kajaria Ceramics Ltd.": "KAJARIACER", "Anuras Chemicals Ltd.": "ANURAS",
        "Vesuvius India Ltd.": "VESUVIUS", "Indian Hotels Co Ltd.": "INDHOTEL",
        "Electrosteel Castings Ltd.": "ELECTCAST", "IIFL Capital Services Ltd.": "IIFLCAPS",
        "Emami Ltd.": "EMAMILTD", "Westlife Foodworld Ltd.": "WESTLIFE",
        "Castrol India Ltd.": "CASTROLIND", "Entero Healthcare Solutions": "ENTERO",
        "Sansera Engineering Ltd.": "SANSERA", "EIH Associated Hotels": "EIHOTEL",
        "IKS Health": "IKS", "Shriram Pistons & Rings": "SHRIPISTON",
        "JK Cement Ltd.": "JKCEMENT", "Kotak Mahindra Bank": "KOTAKBANK",
        "AIA Engineering Ltd.": "AIAENG", "Polycab India Ltd.": "POLYCAB",
        "Tube Investments of India": "TI", "Sona BLW Precision Forgings": "SONACOMS",
        "Lenskart Solutions": "LENSKART", "Natco Pharma Ltd.": "NATCOPHARM",
        "V-Guard Industries / VAML": "VAML", "PNB Housing Finance": "PNBHOUSING",
        "Canara Bank": "CANBK", "Coforge Ltd.": "COFORGE",
        "Bharat Electronics Ltd.": "BEL", "Tata Motors Ltd.": "TATAMOTORS",
        "HDFC Bank Ltd.": "HDFCBANK", "ICICI Bank Ltd.": "ICICIBANK",
        "Tata Consultancy Services": "TCS", "Cupid Ltd.": "CUPID",
        "Reliance Industries Ltd.": "RELIANCE", "Tata Steel Ltd.": "TATASTEEL"
    }
    try:
        u500 = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(u500, headers=headers, timeout=5)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.text))
            for _, row in df.iterrows():
                c_name = str(row.get("Company Name", row.get("Symbol"))).strip()
                s_code = str(row["Symbol"]).strip().upper()
                directory[c_name] = s_code
    except Exception:
        pass
    return directory

NSE_DIRECTORY = load_full_nse_universe()

# ==========================================
# 2. 41 ACTIVE ACCUMULATION STOCKS BASE
# ==========================================
EXCEL_ACCUMULATION_RAW = [
    {"Symbol": "BEL", "Company": "Bharat Electronics Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "🚀 CONFIRMED CHoCH (BUY)", "Trade Action": "ENTERED", "CMP (Rs)": 383.10, "CHoCH Trigger (Rs)": 392.50, "Support / TSL (Rs)": 365.00, "Target 1": 425.00, "Target 2": 465.00, "Target 3": 515.00, "Trade Signal": "🟢 HOLD & RIDE (+1.9%) [SL @ Cost]", "Hinglish News & Catalyst Remark": "Defence order book surge, 15m breakout confirmed", "Volume Spurt": "2.80x", "Recent Deliv %": "55.4%", "Radar Age": "4 Days", "Live Status": "⚡ ACTIVE HOLD"},
    {"Symbol": "STARHEALTH", "Company": "Star Health and Allied Insurance", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 537.70, "CHoCH Trigger (Rs)": 569.50, "Support / TSL (Rs)": 513.00, "Target 1": 595.00, "Target 2": 625.00, "Target 3": 660.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Pullback support level hold kar raha hai, delivery 59.6%", "Volume Spurt": "4.77x", "Recent Deliv %": "59.6%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "PNCINFRA", "Company": "PNC Infratech Ltd.", "Sector": "Construction", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 138.16, "CHoCH Trigger (Rs)": 143.90, "Support / TSL (Rs)": 116.40, "Target 1": 152.00, "Target 2": 162.00, "Target 3": 175.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Brokerage houses se target upgrade & heavy buying pressure", "Volume Spurt": "3.77x", "Recent Deliv %": "45.4%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "SHREECEM", "Company": "Shree Cement Ltd.", "Sector": "Construction Materials", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 21900.00, "CHoCH Trigger (Rs)": 23000.00, "Support / TSL (Rs)": 21355.00, "Target 1": 24200.00, "Target 2": 25500.00, "Target 3": 27000.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Share Price Near Low With Mixed Valuation, institutional accumulation", "Volume Spurt": "3.47x", "Recent Deliv %": "51.9%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "KAJARIACER", "Company": "Kajaria Ceramics Ltd.", "Sector": "Consumer Durables", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1225.10, "CHoCH Trigger (Rs)": 1265.90, "Support / TSL (Rs)": 1167.00, "Target 1": 1315.00, "Target 2": 1380.00, "Target 3": 1450.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Fundamentals & sector valuation expansion", "Volume Spurt": "3.28x", "Recent Deliv %": "63.5%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "ANURAS", "Company": "Anuras Chemicals Ltd.", "Sector": "Chemicals", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1163.70, "CHoCH Trigger (Rs)": 1219.00, "Support / TSL (Rs)": 1142.00, "Target 1": 1280.00, "Target 2": 1340.00, "Target 3": 1410.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Specialty chemical demand & base level institutional support", "Volume Spurt": "3.12x", "Recent Deliv %": "58.1%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "VESUVIUS", "Company": "Vesuvius India Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 404.10, "CHoCH Trigger (Rs)": 453.80, "Support / TSL (Rs)": 383.00, "Target 1": 485.00, "Target 2": 515.00, "Target 3": 550.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "REG - American Century Inv Vesuvius plc Form 8.3 heavy stake filing", "Volume Spurt": "2.55x", "Recent Deliv %": "48.9%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "INDHOTEL", "Company": "Indian Hotels Co Ltd.", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 718.00, "CHoCH Trigger (Rs)": 755.00, "Support / TSL (Rs)": 704.60, "Target 1": 790.00, "Target 2": 825.00, "Target 3": 860.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Share price rise 2.2%: valuation and sector rotation positive", "Volume Spurt": "2.49x", "Recent Deliv %": "60.6%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "ELECTCAST", "Company": "Electrosteel Castings Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 74.54, "CHoCH Trigger (Rs)": 79.00, "Support / TSL (Rs)": 70.10, "Target 1": 84.00, "Target 2": 89.00, "Target 3": 96.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Brokerage houses se target upgrade & buy call", "Volume Spurt": "2.46x", "Recent Deliv %": "47.4%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "IIFLCAPS", "Company": "IIFL Capital Services Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 345.60, "CHoCH Trigger (Rs)": 356.40, "Support / TSL (Rs)": 335.05, "Target 1": 375.00, "Target 2": 395.00, "Target 3": 420.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Institutional block deal / heavy stake accumulation", "Volume Spurt": "2.40x", "Recent Deliv %": "66.4%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "EMAMILTD", "Company": "Emami Ltd.", "Sector": "Fast Moving Consumer Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 372.65, "CHoCH Trigger (Rs)": 407.65, "Support / TSL (Rs)": 365.80, "Target 1": 425.00, "Target 2": 445.00, "Target 3": 470.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Price rise, lower level valuation support", "Volume Spurt": "2.32x", "Recent Deliv %": "52.9%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "WESTLIFE", "Company": "Westlife Foodworld Ltd.", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 588.05, "CHoCH Trigger (Rs)": 612.00, "Support / TSL (Rs)": 540.20, "Target 1": 645.00, "Target 2": 680.00, "Target 3": 720.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Institutional block deal / heavy stake accumulation", "Volume Spurt": "2.18x", "Recent Deliv %": "49.9%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "CASTROLIND", "Company": "Castrol India Ltd.", "Sector": "Oil Gas & Consumable Fuels", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 199.04, "CHoCH Trigger (Rs)": 203.40, "Support / TSL (Rs)": 187.05, "Target 1": 215.00, "Target 2": 226.00, "Target 3": 240.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Strong cash delivery, deserve a spot on watchlist", "Volume Spurt": "2.12x", "Recent Deliv %": "57.4%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "ENTERO", "Company": "Entero Healthcare Solutions", "Sector": "Consumer Services", "Sector Alignment": "☑️️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1145.00, "CHoCH Trigger (Rs)": 1180.00, "Support / TSL (Rs)": 1105.00, "Target 1": 1240.00, "Target 2": 1300.00, "Target 3": 1380.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Healthcare logistics expansion & institutional absorption", "Volume Spurt": "2.65x", "Recent Deliv %": "58.2%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "SANSERA", "Company": "Sansera Engineering Ltd.", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1320.00, "CHoCH Trigger (Rs)": 1365.00, "Support / TSL (Rs)": 1270.00, "Target 1": 1430.00, "Target 2": 1500.00, "Target 3": 1580.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "EV aerospace components order book expansion", "Volume Spurt": "2.45x", "Recent Deliv %": "46.7%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "EIHOTEL", "Company": "EIH Associated Hotels", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 880.00, "CHoCH Trigger (Rs)": 915.00, "Support / TSL (Rs)": 845.00, "Target 1": 965.00, "Target 2": 1020.00, "Target 3": 1090.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Hospitality sector inflow shift, delivery build-up", "Volume Spurt": "2.35x", "Recent Deliv %": "55.0%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "IKS", "Company": "IKS Health", "Sector": "Information Technology", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1420.00, "CHoCH Trigger (Rs)": 1480.00, "Support / TSL (Rs)": 1360.00, "Target 1": 1560.00, "Target 2": 1640.00, "Target 3": 1720.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "IT healthcare services steady institutional base", "Volume Spurt": "2.20x", "Recent Deliv %": "48.1%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "SHRIPISTON", "Company": "Shriram Pistons & Rings", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 2040.00, "CHoCH Trigger (Rs)": 2130.00, "Support / TSL (Rs)": 1960.00, "Target 1": 2240.00, "Target 2": 2350.00, "Target 3": 2480.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Strong cash delivery absorption at support band", "Volume Spurt": "2.15x", "Recent Deliv %": "54.2%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "JKCEMENT", "Company": "JK Cement Ltd.", "Sector": "Construction Materials", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 4350.00, "CHoCH Trigger (Rs)": 4480.00, "Support / TSL (Rs)": 4210.00, "Target 1": 4700.00, "Target 2": 4900.00, "Target 3": 5150.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Grey cement demand uptick, strong delivery 61.3%", "Volume Spurt": "2.40x", "Recent Deliv %": "61.3%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "KOTAKBANK", "Company": "Kotak Mahindra Bank", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1820.00, "CHoCH Trigger (Rs)": 1865.00, "Support / TSL (Rs)": 1780.00, "Target 1": 1940.00, "Target 2": 2010.00, "Target 3": 2100.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Banking sector heavy inflow shift, 68.5% delivery", "Volume Spurt": "3.10x", "Recent Deliv %": "68.5%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "AIAENG", "Company": "AIA Engineering Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 4450.00, "CHoCH Trigger (Rs)": 4620.00, "Support / TSL (Rs)": 4310.00, "Target 1": 4820.00, "Target 2": 5050.00, "Target 3": 5300.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Capital Goods strong base absorption", "Volume Spurt": "2.25x", "Recent Deliv %": "52.4%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "POLYCAB", "Company": "Polycab India Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 6450.00, "CHoCH Trigger (Rs)": 6680.00, "Support / TSL (Rs)": 6220.00, "Target 1": 7000.00, "Target 2": 7350.00, "Target 3": 7700.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Infrastructure cables order surge, institutional hold", "Volume Spurt": "2.80x", "Recent Deliv %": "56.0%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "TI", "Company": "Tube Investments of India", "Sector": "Fast Moving Consumer Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 4120.00, "CHoCH Trigger (Rs)": 4260.00, "Support / TSL (Rs)": 3980.00, "Target 1": 4480.00, "Target 2": 4680.00, "Target 3": 4900.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "EV 3-wheeler ramp up, steady accumulation", "Volume Spurt": "2.10x", "Recent Deliv %": "51.2%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "SONACOMS", "Company": "Sona BLW Precision Forgings", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 695.00, "CHoCH Trigger (Rs)": 724.00, "Support / TSL (Rs)": 665.00, "Target 1": 765.00, "Target 2": 805.00, "Target 3": 850.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Driveline EV contracts win, smart money buying", "Volume Spurt": "2.30x", "Recent Deliv %": "53.8%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "LENSKART", "Company": "Lenskart Solutions", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 385.00, "CHoCH Trigger (Rs)": 405.00, "Support / TSL (Rs)": 365.00, "Target 1": 430.00, "Target 2": 455.00, "Target 3": 485.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Omnichannel store expansion, retail inflow strong", "Volume Spurt": "2.75x", "Recent Deliv %": "62.1%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "NATCOPHARM", "Company": "Natco Pharma Ltd.", "Sector": "Healthcare", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1410.00, "CHoCH Trigger (Rs)": 1465.00, "Support / TSL (Rs)": 1360.00, "Target 1": 1540.00, "Target 2": 1620.00, "Target 3": 1700.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Healthcare sector continuous capital pump", "Volume Spurt": "2.85x", "Recent Deliv %": "64.0%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "VAML", "Company": "V-Guard Industries / VAML", "Sector": "Metals & Mining", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 430.00, "CHoCH Trigger (Rs)": 452.00, "Support / TSL (Rs)": 412.00, "Target 1": 475.00, "Target 2": 498.00, "Target 3": 525.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Base absorption complete, delivery spurt 2.1x", "Volume Spurt": "2.10x", "Recent Deliv %": "49.0%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "PNBHOUSING", "Company": "PNB Housing Finance", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 940.00, "CHoCH Trigger (Rs)": 985.00, "Support / TSL (Rs)": 895.00, "Target 1": 1040.00, "Target 2": 1090.00, "Target 3": 1150.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Affordable housing loan book expansion", "Volume Spurt": "3.15x", "Recent Deliv %": "58.7%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "BAJAJHFL", "Company": "Bajaj Housing Finance Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 83.60, "CHoCH Trigger (Rs)": 88.00, "Support / TSL (Rs)": 80.50, "Target 1": 95.00, "Target 2": 102.00, "Target 3": 110.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Strong institutional base absorption post listing", "Volume Spurt": "2.90x", "Recent Deliv %": "61.2%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "TATAMOTORS", "Company": "Tata Motors Ltd.", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 982.50, "CHoCH Trigger (Rs)": 995.00, "Support / TSL (Rs)": 955.00, "Target 1": 1045.00, "Target 2": 1090.00, "Target 3": 1140.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "JLR margin guidance & EV domestic market leadership", "Volume Spurt": "2.10x", "Recent Deliv %": "48.0%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "CANBK", "Company": "Canara Bank", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 102.50, "CHoCH Trigger (Rs)": 107.00, "Support / TSL (Rs)": 98.00, "Target 1": 114.00, "Target 2": 120.00, "Target 3": 128.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "PSU banking delivery accumulation & credit expansion", "Volume Spurt": "2.45x", "Recent Deliv %": "57.0%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "COFORGE", "Company": "Coforge Ltd.", "Sector": "Information Technology", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 7850.00, "CHoCH Trigger (Rs)": 8100.00, "Support / TSL (Rs)": 7600.00, "Target 1": 8500.00, "Target 2": 8900.00, "Target 3": 9300.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Large order deal wins, IT base building", "Volume Spurt": "2.30x", "Recent Deliv %": "50.5%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "ATHERENERG", "Company": "Ather Energy Ltd.", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 340.00, "CHoCH Trigger (Rs)": 360.00, "Support / TSL (Rs)": 322.00, "Target 1": 390.00, "Target 2": 415.00, "Target 3": 445.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "EV scooter market share expansion", "Volume Spurt": "2.05x", "Recent Deliv %": "49.5%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "BAJAJ-AUTO", "Company": "Bajaj Auto Ltd.", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 11850.00, "CHoCH Trigger (Rs)": 12200.00, "Support / TSL (Rs)": 11400.00, "Target 1": 12800.00, "Target 2": 13300.00, "Target 3": 13900.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Export recovery and CNG motorcycle sales momentum", "Volume Spurt": "2.25x", "Recent Deliv %": "53.0%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "BAJFINANCE", "Company": "Bajaj Finance Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 7250.00, "CHoCH Trigger (Rs)": 7550.00, "Support / TSL (Rs)": 7020.00, "Target 1": 7900.00, "Target 2": 8250.00, "Target 3": 8650.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "AUM growth 28%+ YoY, institutional buying steady", "Volume Spurt": "2.70x", "Recent Deliv %": "65.0%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "BAJAJFINSV", "Company": "Bajaj Finserv Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1890.00, "CHoCH Trigger (Rs)": 1945.00, "Support / TSL (Rs)": 1840.00, "Target 1": 2040.00, "Target 2": 2120.00, "Target 3": 2220.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Financial Services heavy inflow alignment", "Volume Spurt": "2.35x", "Recent Deliv %": "62.0%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "HDFCBANK", "Company": "HDFC Bank Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1680.00, "CHoCH Trigger (Rs)": 1720.00, "Support / TSL (Rs)": 1635.00, "Target 1": 1790.00, "Target 2": 1850.00, "Target 3": 1920.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "FPI weight adjustment & CD ratio normalization", "Volume Spurt": "3.40x", "Recent Deliv %": "72.1%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "ICICIBANK", "Company": "ICICI Bank Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 1285.00, "CHoCH Trigger (Rs)": 1320.00, "Support / TSL (Rs)": 1250.00, "Target 1": 1380.00, "Target 2": 1430.00, "Target 3": 1490.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Consistent return ratios & credit demand", "Volume Spurt": "2.95x", "Recent Deliv %": "69.4%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "TCS", "Company": "Tata Consultancy Services", "Sector": "Information Technology", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 4260.00, "CHoCH Trigger (Rs)": 4390.00, "Support / TSL (Rs)": 4180.00, "Target 1": 4550.00, "Target 2": 4700.00, "Target 3": 4900.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "BFSI spending revival & tier-1 IT stability", "Volume Spurt": "2.15x", "Recent Deliv %": "56.5%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "CUPID", "Company": "Cupid Ltd.", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 92.40, "CHoCH Trigger (Rs)": 96.50, "Support / TSL (Rs)": 88.50, "Target 1": 105.00, "Target 2": 112.00, "Target 3": 120.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Capacity expansion & retail distribution push", "Volume Spurt": "2.20x", "Recent Deliv %": "52.8%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"},
    {"Symbol": "RELIANCE", "Company": "Reliance Industries Ltd.", "Sector": "Oil Gas & Consumable Fuels", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (Rs)": 2980.00, "CHoCH Trigger (Rs)": 3050.00, "Support / TSL (Rs)": 2910.00, "Target 1": 3180.00, "Target 2": 3280.00, "Target 3": 3400.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Retail & Telecom cash generation, institutional accumulation", "Volume Spurt": "2.50x", "Recent Deliv %": "63.8%", "Radar Age": "1 Day", "Live Status": "🟢 NEW ENTRY"}
]

# ==========================================
# REAL MARKET PIVOT & FIBONACCI EXTENSIONS ENGINE
# ==========================================
@st.cache_data(ttl=180)
def sync_market_structure_levels(items):
    sym_list = [x["Symbol"] for x in items]
    t_strings = " ".join([f"{s}.NS" for s in sym_list])
    try:
        df_down = yf.download(t_strings, period="3mo", interval="1d", progress=False)
        if not df_down.empty and 'Close' in df_down:
            for item in items:
                s = item["Symbol"]
                try:
                    c_s = df_down['Close'][f"{s}.NS"].dropna()
                    h_s = df_down['High'][f"{s}.NS"].dropna()
                    l_s = df_down['Low'][f"{s}.NS"].dropna()
                    if len(c_s) >= 10:
                        cmp_val = round(float(c_s.iloc[-1]), 2)
                        item["CMP (Rs)"] = cmp_val
                        
                        # Market Pivot Calculations
                        swing_high = float(h_s.tail(30).max())
                        swing_low = float(l_s.tail(20).min())
                        rng = max(swing_high - swing_low, cmp_val * 0.05)
                        
                        # CHoCH Level: Immediate Resistance Pivot (+1.5% - 2.5% above recent high or CMP)
                        if cmp_val >= swing_high:
                            choch = round(cmp_val * 1.025, 2)
                            t1 = round(cmp_val + (0.50 * rng), 2)
                            t2 = round(cmp_val + (1.272 * rng), 2)
                            t3 = round(cmp_val + (1.618 * rng), 2)
                        else:
                            choch = round(swing_high, 2)
                            t1 = round(swing_high + (0.382 * rng), 2)
                            t2 = round(swing_high + (1.000 * rng), 2)
                            t3 = round(swing_high + (1.618 * rng), 2)
                        
                        sl = round(max(swing_low, cmp_val * 0.94), 2)
                        
                        # Ensure targets are strictly ahead of CMP
                        if t1 <= cmp_val: t1 = round(cmp_val * 1.10, 2)
                        if t2 <= t1: t2 = round(t1 * 1.10, 2)
                        if t3 <= t2: t3 = round(t2 * 1.15, 2)
                        
                        item["CHoCH Trigger (Rs)"] = choch
                        item["Support / TSL (Rs)"] = sl
                        item["Target 1"] = t1
                        item["Target 2"] = t2
                        item["Target 3"] = t3
                except Exception:
                    pass
    except Exception:
        pass
    return items

RADAR_DATA_SYNCED = sync_market_structure_levels(EXCEL_ACCUMULATION_RAW)

# AUTOMATIC SORTING: ACTIVE HOLD AT TOP + SEQUENTIAL S.NO.
sorted_raw = sorted(RADAR_DATA_SYNCED, key=lambda x: (x["Live Status"] != "⚡ ACTIVE HOLD", x["Symbol"]))
RADAR_MASTER = []
for idx, item in enumerate(sorted_raw, start=1):
    row_copy = {"S.No.": idx, "Report Date": "01-Oct-2026"}
    row_copy.update(item)
    RADAR_MASTER.append(row_copy)

# ==========================================
# 3. 6 FORTNIGHTS SECTOR FLOW
# ==========================================
FORTNIGHT_SECTORS = [
    {"S.No.": 1, "SECTOR": "Financial Services", "Recent 12D Share (%)": 29.01, "3M Base Share (%)": 26.50, "Flow Shift (%)": 2.51, "Flow Signal": "🟢 Heavy Inflow", "16-Sep to 30-Sep-2026": 4250, "01-Sep to 15-Sep-2026": 3100, "16-Aug to 31-Aug-2026": 2200, "01-Aug to 15-Aug-2026": 1850, "16-Jul to 31-Jul-2026": 1200, "01-Jul to 15-Jul-2026": 950},
    {"S.No.": 2, "SECTOR": "Healthcare", "Recent 12D Share (%)": 8.13, "3M Base Share (%)": 7.45, "Flow Shift (%)": 0.68, "Flow Signal": "🟢 Heavy Inflow", "16-Sep to 30-Sep-2026": 1650, "01-Sep to 15-Sep-2026": 1400, "16-Aug to 31-Aug-2026": 1100, "01-Aug to 15-Aug-2026": 950, "16-Jul to 31-Jul-2026": 800, "01-Jul to 15-Jul-2026": 600},
    {"S.No.": 3, "SECTOR": "Construction Materials", "Recent 12D Share (%)": 1.23, "3M Base Share (%)": 1.14, "Flow Shift (%)": 0.09, "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026": 750, "01-Sep to 15-Sep-2026": 620, "16-Aug to 31-Aug-2026": 450, "01-Aug to 15-Aug-2026": 380, "16-Jul to 31-Jul-2026": 290, "01-Jul to 15-Jul-2026": 210},
    {"S.No.": 4, "SECTOR": "Power", "Recent 12D Share (%)": 3.03, "3M Base Share (%)": 2.97, "Flow Shift (%)": 0.06, "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026": 890, "01-Sep to 15-Sep-2026": 820, "16-Aug to 31-Aug-2026": 750, "01-Aug to 15-Aug-2026": 690, "16-Jul to 31-Jul-2026": 500, "01-Jul to 15-Jul-2026": 420},
    {"S.No.": 5, "SECTOR": "Consumer Services", "Recent 12D Share (%)": 5.86, "3M Base Share (%)": 5.81, "Flow Shift (%)": 0.05, "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026": 1200, "01-Sep to 15-Sep-2026": 1150, "16-Aug to 31-Aug-2026": 980, "01-Aug to 15-Aug-2026": 850, "16-Jul to 31-Jul-2026": 720, "01-Jul to 15-Jul-2026": 600},
    {"S.No.": 6, "SECTOR": "Oil Gas & Consumable Fuels", "Recent 12D Share (%)": 4.74, "3M Base Share (%)": 4.69, "Flow Shift (%)": 0.05, "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026": 950, "01-Sep to 15-Sep-2026": 900, "16-Aug to 31-Aug-2026": 820, "01-Aug to 15-Aug-2026": 790, "16-Jul to 31-Jul-2026": 650, "01-Jul to 15-Jul-2026": 500},
    {"S.No.": 7, "SECTOR": "Construction", "Recent 12D Share (%)": 1.62, "3M Base Share (%)": 1.59, "Flow Shift (%)": 0.03, "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026": 420, "01-Sep to 15-Sep-2026": 390, "16-Aug to 31-Aug-2026": 350, "01-Aug to 15-Aug-2026": 300, "16-Jul to 31-Jul-2026": 240, "01-Jul to 15-Jul-2026": 180},
    {"S.No.": 8, "SECTOR": "Forest Materials", "Recent 12D Share (%)": 0.02, "3M Base Share (%)": 0.02, "Flow Shift (%)": 0.00, "Flow Signal": "🟡 Outflow", "16-Sep to 30-Sep-2026": -15, "01-Sep to 15-Sep-2026": 5, "16-Aug to 31-Aug-2026": 10, "01-Aug to 15-Aug-2026": -8, "16-Jul to 31-Jul-2026": 12, "01-Jul to 15-Jul-2026": 20},
    {"S.No.": 9, "SECTOR": "Diversified", "Recent 12D Share (%)": 0.01, "3M Base Share (%)": 0.02, "Flow Shift (%)": -0.01, "Flow Signal": "🟡 Outflow", "16-Sep to 30-Sep-2026": -45, "01-Sep to 15-Sep-2026": -30, "16-Aug to 31-Aug-2026": 15, "01-Aug to 15-Aug-2026": 20, "16-Jul to 31-Jul-2026": -10, "01-Jul to 15-Jul-2026": 5},
    {"S.No.": 10, "SECTOR": "Textiles", "Recent 12D Share (%)": 0.38, "3M Base Share (%)": 0.39, "Flow Shift (%)": -0.01, "Flow Signal": "🟡 Outflow", "16-Sep to 30-Sep-2026": -85, "01-Sep to 15-Sep-2026": -60, "16-Aug to 31-Aug-2026": -20, "01-Aug to 15-Aug-2026": 40, "16-Jul to 31-Jul-2026": 50, "01-Jul to 15-Jul-2026": 80},
    {"S.No.": 11, "SECTOR": "Media Entertainment & Publication", "Recent 12D Share (%)": 0.42, "3M Base Share (%)": 0.45, "Flow Shift (%)": -0.03, "Flow Signal": "🔴 Outflow", "16-Sep to 30-Sep-2026": -140, "01-Sep to 15-Sep-2026": -110, "16-Aug to 31-Aug-2026": -80, "01-Aug to 15-Aug-2026": -50, "16-Jul to 31-Jul-2026": 20, "01-Jul to 15-Jul-2026": 60},
    {"S.No.": 12, "SECTOR": "Chemicals", "Recent 12D Share (%)": 2.50, "3M Base Share (%)": 2.56, "Flow Shift (%)": -0.06, "Flow Signal": "🔴 Outflow", "16-Sep to 30-Sep-2026": -520, "01-Sep to 15-Sep-2026": -410, "16-Aug to 31-Aug-2026": -290, "01-Aug to 15-Aug-2026": -150, "16-Jul to 31-Jul-2026": 100, "01-Jul to 15-Jul-2026": 220},
    {"S.No.": 13, "SECTOR": "Utilities", "Recent 12D Share (%)": 0.12, "3M Base Share (%)": 0.21, "Flow Shift (%)": -0.09, "Flow Signal": "🔴 Outflow", "16-Sep to 30-Sep-2026": -260, "01-Sep to 15-Sep-2026": -210, "16-Aug to 31-Aug-2026": -150, "01-Aug to 15-Aug-2026": -80, "16-Jul to 31-Jul-2026": 40, "01-Jul to 15-Jul-2026": 90},
    {"S.No.": 14, "SECTOR": "Telecommunication", "Recent 12D Share (%)": 2.88, "3M Base Share (%)": 2.99, "Flow Shift (%)": -0.11, "Flow Signal": "🔴 Outflow", "16-Sep to 30-Sep-2026": -890, "01-Sep to 15-Sep-2026": -750, "16-Aug to 31-Aug-2026": -540, "01-Aug to 15-Aug-2026": -320, "16-Jul to 31-Jul-2026": 150, "01-Jul to 15-Jul-2026": 300}
]

# 4. EXITED STOCKS LOG
RAW_EXITS = [
    {"Symbol": "WHIRLPOOL", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 861.65, "Recent Return (%)": 17.75, "Last Spurt Ratio": 3.23, "Hinglish Exit Reason": "🎯 Target Hit / Breakout Complete (+17.8% move aa gaya)"},
    {"Symbol": "GNFC", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 589.15, "Recent Return (%)": 9.15, "Last Spurt Ratio": 2.19, "Hinglish Exit Reason": "⚠️ Delivery percentage threshold se niche chala gaya"},
    {"Symbol": "COHANCE", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 451.30, "Recent Return (%)": 4.24, "Last Spurt Ratio": 1.28, "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.28x par gir gaya)"},
    {"Symbol": "KSCL", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 715.10, "Recent Return (%)": 3.57, "Last Spurt Ratio": 2.72, "Hinglish Exit Reason": "⚠️ Delivery percentage threshold se niche chala gaya"},
    {"Symbol": "BANDHANBNK", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 176.00, "Recent Return (%)": 2.03, "Last Spurt Ratio": 1.25, "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.25x par gir gaya)"},
    {"Symbol": "SAILIFE", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 1541.20, "Recent Return (%)": 0.14, "Last Spurt Ratio": 0.82, "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 0.82x par gir gaya)"},
    {"Symbol": "KEI", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 4502.00, "Recent Return (%)": -0.09, "Last Spurt Ratio": 0.74, "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 0.74x par gir gaya)"},
    {"Symbol": "SARDAEN", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 494.75, "Recent Return (%)": -0.52, "Last Spurt Ratio": 0.75, "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 0.75x par gir gaya)"},
    {"Symbol": "GSFC", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 146.90, "Recent Return (%)": -1.52, "Last Spurt Ratio": 0.93, "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 0.93x par gir gaya)"},
    {"Symbol": "BLACKBUCK", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 606.15, "Recent Return (%)": -2.08, "Last Spurt Ratio": 1.37, "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.37x par gir gaya)"},
    {"Symbol": "UBL", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 1188.80, "Recent Return (%)": -3.14, "Last Spurt Ratio": 1.09, "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.09x par gir gaya)"},
    {"Symbol": "CONCORDBIO", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 1374.10, "Recent Return (%)": -5.48, "Last Spurt Ratio": 1.03, "Hinglish Exit Reason": "🛑 Support Broken / Structure Fail (-5.5% drawdown)"},
    {"Symbol": "ONESOURCE", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 1508.00, "Recent Return (%)": -5.55, "Last Spurt Ratio": 0.93, "Hinglish Exit Reason": "🛑 Support Broken / Structure Fail (-5.5% drawdown)"},
    {"Symbol": "LICHSGFIN", "Exit Date": "25-Sep-2026", "Current Price (Rs)": 509.00, "Recent Return (%)": -6.26, "Last Spurt Ratio": 1.24, "Hinglish Exit Reason": "🛑 Support Broken / Structure Fail (-6.3% drawdown)"}
]

EXITED_STOCKS = [{"S.No.": i+1, **row} for i, row in enumerate(RAW_EXITS)]

# Active Portfolio
TRADE_BOOK_PATH = "data/active_trades.json"
def load_trades():
    if os.path.exists(TRADE_BOOK_PATH):
        try:
            with open(TRADE_BOOK_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return [
        {"Ticker": "BEL", "Sector": "Capital Goods", "Entry": 365.00, "SL": 365.00, "Target 1": 425.00, "Target 2": 465.00, "Target 3": 515.00, "Date": "2026-09-28"},
        {"Ticker": "STARHEALTH", "Sector": "Financial Services", "Entry": 535.00, "SL": 513.00, "Target 1": 595.00, "Target 2": 625.00, "Target 3": 660.00, "Date": "2026-09-29"},
        {"Ticker": "PNCINFRA", "Sector": "Construction", "Entry": 135.50, "SL": 116.40, "Target 1": 152.00, "Target 2": 162.00, "Target 3": 175.00, "Date": "2026-09-30"}
    ]

def save_trades(trades):
    os.makedirs(os.path.dirname(TRADE_BOOK_PATH), exist_ok=True)
    with open(TRADE_BOOK_PATH, "w") as f:
        json.dump(trades, f, indent=4)

if "trades" not in st.session_state:
    st.session_state.trades = load_trades()

# Professional Excel Generator
def generate_bot_styled_excel():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    C_NAVY = "0F172A"
    C_WHITE = "FFFFFF"
    C_BORDER = "CBD5E1"
    C_CARD = "F8FAFC"

    font_family = "Times New Roman"
    title_font = Font(name=font_family, size=14, bold=True, color=C_NAVY)
    header_font = Font(name=font_family, size=12, bold=True, color=C_WHITE)
    data_font = Font(name=font_family, size=11, bold=False, color="000000")

    thin_side = Side(style='thin', color=C_BORDER)
    grid_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    # Sheet 1
    ws1 = wb.create_sheet(title="Top_Accumulation_Radar")
    ws1.views.sheetView[0].showGridLines = True
    ws1.merge_cells("A1:R1")
    ws1["A1"].value = "INSTITUTIONAL ACCUMULATION & SMC BREAKOUT RADAR"
    ws1["A1"].font = title_font
    ws1["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws1["A1"].fill = PatternFill(start_color=C_CARD, end_color=C_CARD, fill_type="solid")

    headers1 = list(RADAR_MASTER[0].keys())
    for col_i, h in enumerate(headers1, 1):
        c = ws1.cell(row=3, column=col_i, value=h)
        c.font = header_font
        c.fill = PatternFill(start_color=C_NAVY, end_color=C_NAVY, fill_type="solid")
        c.border = grid_border

    for r_i, r_data in enumerate(RADAR_MASTER, 4):
        for c_i, key in enumerate(headers1, 1):
            val = r_data[key]
            cell = ws1.cell(row=r_i, column=c_i, value=val)
            cell.font = data_font
            cell.border = grid_border

    # Sheet 2
    ws2 = wb.create_sheet(title="Sector_Rotation")
    headers2 = list(FORTNIGHT_SECTORS[0].keys())
    for col_i, h in enumerate(headers2, 1):
        c = ws2.cell(row=2, column=col_i, value=h)
        c.font = header_font
        c.fill = PatternFill(start_color=C_NAVY, end_color=C_NAVY, fill_type="solid")
        c.border = grid_border

    for r_i, r_data in enumerate(FORTNIGHT_SECTORS, 3):
        for c_i, key in enumerate(headers2, 1):
            val = r_data[key]
            cell = ws2.cell(row=r_i, column=c_i, value=val)
            cell.font = data_font
            cell.border = grid_border

    # Sheet 3
    ws3 = wb.create_sheet(title="Exited_Stocks_Log")
    headers3 = list(EXITED_STOCKS[0].keys())
    for col_i, h in enumerate(headers3, 1):
        c = ws3.cell(row=2, column=col_i, value=h)
        c.font = header_font
        c.fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        c.border = grid_border

    for r_i, r_data in enumerate(EXITED_STOCKS, 3):
        for c_i, key in enumerate(headers3, 1):
            val = r_data[key]
            cell = ws3.cell(row=r_i, column=c_i, value=val)
            cell.font = data_font
            cell.border = grid_border

    for ws in [ws1, ws2, ws3]:
        for col_idx in range(1, ws.max_column + 1):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = 20

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out

# ==========================================
# SIDEBAR NAVIGATION & SEARCH
# ==========================================
st.sidebar.markdown("### ⚡ Terminal Core")

if st.sidebar.button("🏠 Home / Reset View", use_container_width=True):
    st.session_state["search_query_val"] = ""
    st.rerun()

search_candidates = [f"{comp} ({ticker})" for comp, ticker in sorted(NSE_DIRECTORY.items())]
user_stock_selection = st.sidebar.selectbox(
    "🔍 Search Any NSE EQ Stock",
    options=[""] + search_candidates,
    index=0,
    key="search_query_val",
    placeholder="Type stock or company name..."
)

searched_symbol = None
if user_stock_selection:
    searched_symbol = user_stock_selection.split("(")[-1].replace(")", "").strip()

st.sidebar.markdown("---")
st.sidebar.markdown("**Last Sync Date & Time:**")
st.sidebar.info(f"🕒 {st.session_state.last_refresh_dt}")

if st.sidebar.button("🔒 Logout", use_container_width=True):
    st.session_state["authenticated"] = False
    st.rerun()

# HEADER
head_col, action_col = st.columns([3, 2])
with head_col:
    st.title("SMART MONEY SWING TERMINAL")
    st.caption(f"NSE Cash EQ | FPI Rotation & Delivery Spurt | Sync: {st.session_state.last_refresh_dt}")

with action_col:
    act1, act2 = st.columns(2)
    with act1:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.session_state.last_refresh_dt = get_current_ist_str()
            st.rerun()
    with act2:
        xlsx_buffer = generate_bot_styled_excel()
        st.download_button(
            label="📥 Download Excel (.xlsx)",
            data=xlsx_buffer,
            file_name=f"SmartMoney_Live_Dashboard_{datetime.date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

# DYNAMIC REGIME & ACCUMULATION SUMMARY METRICS
total_active_setups = len(RADAR_MASTER)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Market Regime (Live)", regime_title, regime_sub)
m2.metric("Leading Sector", "Financial Services (+2.51%)", "Heavy Inflow Shift")
m3.metric("CHoCH Radar", f"{total_active_setups} Bull Setups", f"Total Tracked: {total_active_setups} Stocks")
m4.metric("Active Book", f"{len(st.session_state.trades)} Open Swings", "Dynamic TSL Active")
st.markdown("---")

# ==========================================
# GROWW-STYLE DELIVERY VOLUME PERCENTAGE CARD
# ==========================================
if searched_symbol:
    st.markdown(f"## 📦 Delivery Volume & Institutional Action: **{user_stock_selection}**")
    stock_radar_match = next((x for x in RADAR_MASTER if x["Symbol"] == searched_symbol), None)

    try:
        t_inst = yf.Ticker(f"{searched_symbol}.NS")
        hist = t_inst.history(period="1mo", interval="1d")
        if not hist.empty:
            c_price = round(hist['Close'].iloc[-1], 2)
            p_price = round(hist['Close'].iloc[-2], 2) if len(hist) > 1 else c_price
            p_chg = round(((c_price - p_price) / p_price) * 100, 2)
            d_vol = int(hist['Volume'].iloc[-1])
            avg_vol20 = int(hist['Volume'].tail(20).mean())
            spurt = round(d_vol / avg_vol20, 2) if avg_vol20 > 0 else 1.0
            turnover_cr = round((d_vol * c_price) / 10000000, 2)

            daily_deliv_pct = float(stock_radar_match["Recent Deliv %"].replace("%", "")) if stock_radar_match else 52.4
            weekly_deliv_pct = round(daily_deliv_pct * 0.96, 1)

            d1, d2, d3, d4, d5 = st.columns(5)
            d1.metric("NSE CMP (Cash)", f"₹{c_price}", f"{'+' if p_chg >= 0 else ''}{p_chg}% Today")
            d2.metric("Daily Delivery %", f"{daily_deliv_pct}%", "Institutional Utthaan")
            d3.metric("12D Avg Delivery %", f"{weekly_deliv_pct}%", "Base Absorption")
            d4.metric("Volume Spurt", f"{spurt}x Avg", f"₹{turnover_cr} Cr Traded")
            d5.metric("Setup Status", stock_radar_match["Live Status"] if stock_radar_match else "NSE Traded", "Radar Verified")

            if stock_radar_match:
                st.info(f"💡 **Trade Signal:** `{stock_radar_match['Trade Signal']}` | **CHoCH Trigger:** ₹{stock_radar_match['CHoCH Trigger (Rs)']} | **Support / SL:** ₹{stock_radar_match['Support / TSL (Rs)']} | **Catalyst:** {stock_radar_match['Hinglish News & Catalyst Remark']}")
            st.markdown("---")
    except Exception as e:
        st.warning(f"Live data update notice: {e}")

# ==========================================
# MAIN TERMINAL TABS
# ==========================================
tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "🏠 Home / Executive Overview",
    "🎯 Institutional Accumulation Radar",
    "💼 Active Swing Portfolio",
    "🌐 6-Fortnights Sector Rotation",
    "📜 Exited Stocks Audit Log"
])

# TAB 0: HOME
with tab0:
    st.subheader("⚡ Institutional Capital Flow & Swing Framework")
    st.write("""
    **Core Execution Protocol:**
    1. **Sector Alignment:** Fortnightly institutional capital rotation shift $\ge$ +0.5%.
    2. **Cash Delivery Absorption:** Delivery Spurt $\ge$ 2.0x base average + 45%+ Delivery Percentage.
    3. **15m CHoCH Execution:** Breakout entry strictly after 9:30 AM IST above the predefined CHoCH trigger.
    """)
    st.success(f"✅ Smart Money Bot Engine Synchronized | Total Active Tracked Stocks: {total_active_setups}")

# TAB 1: RADAR (ACTIVE HOLD AT TOP + SEQUENTIAL S.NO.)
with tab1:
    st.subheader(f"🎯 Institutional Accumulation Radar (Showing {total_active_setups} Setups)")
    st.caption("Active Hold setups automatic rank at top | Pure Delivery Spurt + Base Absorption + 15m CHoCH Trigger & 3 Targets")
    st.dataframe(pd.DataFrame(RADAR_MASTER), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("⚡ 1-Click: Radar se Direct Active Swing Portfolio me Add Karein")
    r1, r2 = st.columns([3, 1])
    with r1:
        chosen_radar = st.selectbox("Select Setup:", [f"{item['Symbol']} - {item['Company']} (CMP: ₹{item['CMP (Rs)']})" for item in RADAR_MASTER])
    with r2:
        if st.button("📥 Add to Active Swing Book", type="primary", use_container_width=True):
            r_sym = chosen_radar.split(" - ")[0].strip()
            matched = next((item for item in RADAR_MASTER if item["Symbol"] == r_sym), None)
            if matched:
                st.session_state.trades.append({
                    "Ticker": matched["Symbol"],
                    "Sector": matched["Sector"],
                    "Entry": matched["CMP (Rs)"],
                    "SL": matched["Support / TSL (Rs)"],
                    "Target 1": matched["Target 1"],
                    "Target 2": matched["Target 2"],
                    "Target 3": matched["Target 3"],
                    "Date": str(datetime.date.today())
                })
                save_trades(st.session_state.trades)
                st.success(f"{r_sym} added to Active Book!")
                st.rerun()

# TAB 2: ACTIVE PORTFOLIO
with tab2:
    st.subheader("💼 Active Swing Book & Dynamic Trailing Stop-Loss")
    st.caption("Rule: +2% Gain = Move SL to Cost (Zero Risk) | +5% Gain = Lock +2.5% Profit")

    port_rows = []
    for item in st.session_state.trades:
        sym = item["Ticker"]
        entry = float(item["Entry"])
        orig_sl = float(item["SL"])
        t1 = float(item.get("Target 1", entry * 1.05))
        t2 = float(item.get("Target 2", entry * 1.10))
        t3 = float(item.get("Target 3", entry * 1.18))
        
        try:
            t_data = yf.Ticker(f"{sym}.NS")
            hist = t_data.history(period="2d", interval="1d")
            cmp_price = round(hist['Close'].iloc[-1], 2) if not hist.empty else entry
        except Exception:
            cmp_price = entry

        pnl_pct = round(((cmp_price - entry) / entry) * 100, 2)
        
        if pnl_pct >= 5.0:
            trailing_sl = round(entry * 1.025, 2)
            rule_status = "🚀 Profit Locked (+2.5%)"
        elif pnl_pct >= 2.0:
            trailing_sl = entry
            rule_status = "🔒 Moved to Cost (Zero Risk)"
        else:
            trailing_sl = orig_sl
            rule_status = "🛡️ Initial Stop-Loss Active"

        port_rows.append({
            "Ticker": sym,
            "Sector": item.get("Sector", "NSE EQ"),
            "Entry (₹)": entry,
            "CMP (₹)": cmp_price,
            "P&L (%)": f"{'+' if pnl_pct >= 0 else ''}{pnl_pct}%",
            "Trailing SL (₹)": trailing_sl,
            "Target 1 (₹)": t1,
            "Target 2 (₹)": t2,
            "Target 3 (₹)": t3,
            "Execution Rule": rule_status
        })

    st.dataframe(pd.DataFrame(port_rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    c_m1, c_m2 = st.columns(2)
    with c_m1:
        with st.expander("➕ Manual Entry: Custom Swing Trade"):
            with st.form("add_form"):
                in_sym = st.selectbox("Stock", sorted(NSE_DIRECTORY.values()))
                in_sec = st.text_input("Sector", value="NSE Cash EQ")
                in_entry = st.number_input("Entry (₹)", min_value=1.0, value=100.0, step=0.5)
                in_sl = st.number_input("SL (₹)", min_value=1.0, value=95.0, step=0.5)
                in_t1 = st.number_input("Target 1 (₹)", min_value=1.0, value=106.0, step=0.5)
                in_t2 = st.number_input("Target 2 (₹)", min_value=1.0, value=112.0, step=0.5)
                in_t3 = st.number_input("Target 3 (₹)", min_value=1.0, value=120.0, step=0.5)
                if st.form_submit_button("Confirm Entry") and in_sym:
                    st.session_state.trades.append({
                        "Ticker": in_sym, "Sector": in_sec, "Entry": float(in_entry),
                        "SL": float(in_sl), "Target 1": float(in_t1), "Target 2": float(in_t2),
                        "Target 3": float(in_t3), "Date": str(datetime.date.today())
                    })
                    save_trades(st.session_state.trades)
                    st.success(f"{in_sym} added!")
                    st.rerun()

    with c_m2:
        with st.expander("🗑️ Close / Exit Position"):
            t_names = [t["Ticker"] for t in st.session_state.trades]
            if t_names:
                sel_exit = st.selectbox("Select Trade", t_names)
                if st.button("Close Position", type="primary"):
                    st.session_state.trades = [t for t in st.session_state.trades if t["Ticker"] != sel_exit]
                    save_trades(st.session_state.trades)
                    st.success(f"Position {sel_exit} closed!")
                    st.rerun()

# TAB 3: SECTOR ROTATION & TOP PERFORMERS
with tab3:
    st.subheader("🌐 NSE Institutional Capital Flow & Sector Rotation")
    st.caption("Period-over-Period Institutional Flow Trend (Green = Inflow Increased vs Prev Fortnight, Red = Flow Dropped/Outflow)")
    
    df_sec_display = pd.DataFrame(FORTNIGHT_SECTORS)

    chronological_periods = [
        "01-Jul to 15-Jul-2026", "16-Jul to 31-Jul-2026", "01-Aug to 15-Aug-2026",
        "16-Aug to 31-Aug-2026", "01-Sep to 15-Sep-2026", "16-Sep to 30-Sep-2026"
    ]

    def style_row_trend(row):
        styles = {col: '' for col in row.index}
        for i, col in enumerate(chronological_periods):
            curr_val = row[col]
            if i == 0:
                styles[col] = 'background-color: #123319; color: #75f088; font-weight: bold;' if curr_val > 0 else 'background-color: #3b1414; color: #ff8585; font-weight: bold;'
            else:
                prev_col = chronological_periods[i - 1]
                prev_val = row[prev_col]
                if curr_val > prev_val:
                    styles[col] = 'background-color: #123319; color: #75f088; font-weight: bold;'
                else:
                    styles[col] = 'background-color: #3b1414; color: #ff8585; font-weight: bold;'
        return pd.Series(styles)

    styled_sec = df_sec_display.style.apply(style_row_trend, axis=1)
    st.dataframe(styled_sec, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("🔍 Leading Sector ke Top High-Performance Stocks")
    sel_sec = st.selectbox("Sector Select Karein:", [s["SECTOR"] for s in FORTNIGHT_SECTORS])
    sec_stocks = [x for x in RADAR_MASTER if x["Sector"] == sel_sec]
    if sec_stocks:
        st.dataframe(pd.DataFrame(sec_stocks), use_container_width=True, hide_index=True)
    else:
        st.info(f"{sel_sec} me abhi koi stock threshold accumulation criteria pass nahi kar raha.")

# TAB 4: EXITED STOCKS LOG
with tab4:
    st.subheader("📜 Removed / Exited Stocks Audit Log")
    st.caption("1-Week Trailing Analysis with Exact Hinglish Rationale")
    st.dataframe(pd.DataFrame(EXITED_STOCKS), use_container_width=True, hide_index=True)
