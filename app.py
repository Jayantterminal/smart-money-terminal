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
MASTER_PASSWORD = "2000"

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
# ACTIVE PORTFOLIO BOOK STORAGE
# ==========================================
TRADE_BOOK_PATH = "data/active_trades.json"
def load_trades():
    if os.path.exists(TRADE_BOOK_PATH):
        try:
            with open(TRADE_BOOK_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_trades(trades):
    os.makedirs(os.path.dirname(TRADE_BOOK_PATH), exist_ok=True)
    with open(TRADE_BOOK_PATH, "w") as f:
        json.dump(trades, f, indent=4)

if "trades" not in st.session_state:
    st.session_state.trades = load_trades()

# ==========================================
# 2. COMPLETE ACCUMULATION UNIVERSE BASE
# ==========================================
EXCEL_ACCUMULATION_RAW = [
    {"Symbol": "CASTROLIND", "Company": "Castrol India Ltd.", "Sector": "Oil Gas & Consumable Fuels", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 199.04, "Buy Range Low": 196.00, "Buy Range High": 201.00, "CHoCH Trigger (Rs)": 204.50, "Support / TSL (Rs)": 191.00, "Target 1": 215.00, "Target 2": 226.00, "Target 3": 240.00, "Hinglish News & Catalyst Remark": "Strong cash delivery, deserve a spot on watchlist", "Volume Spurt": "2.12x", "Recent Deliv %": "57.4%", "Radar Age": "1 Day"},
    {"Symbol": "AIAENG", "Company": "AIA Engineering Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 3824.40, "Buy Range Low": 3790.00, "Buy Range High": 3845.00, "CHoCH Trigger (Rs)": 3950.00, "Support / TSL (Rs)": 3710.00, "Target 1": 4180.00, "Target 2": 4350.00, "Target 3": 4580.00, "Hinglish News & Catalyst Remark": "Mining consumables order expansion, heavy block deals", "Volume Spurt": "2.25x", "Recent Deliv %": "52.4%", "Radar Age": "1 Day"},
    {"Symbol": "ANURAS", "Company": "Anuras Chemicals Ltd.", "Sector": "Chemicals", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 1163.70, "Buy Range Low": 1150.00, "Buy Range High": 1175.00, "CHoCH Trigger (Rs)": 1195.00, "Support / TSL (Rs)": 1135.00, "Target 1": 1280.00, "Target 2": 1340.00, "Target 3": 1410.00, "Hinglish News & Catalyst Remark": "Specialty chemical demand & base level institutional support", "Volume Spurt": "3.12x", "Recent Deliv %": "58.1%", "Radar Age": "1 Day"},
    {"Symbol": "ATHERENERG", "Company": "Ather Energy Ltd.", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 1406.10, "Buy Range Low": 1385.00, "Buy Range High": 1420.00, "CHoCH Trigger (Rs)": 1455.00, "Support / TSL (Rs)": 1350.00, "Target 1": 1560.00, "Target 2": 1640.00, "Target 3": 1740.00, "Hinglish News & Catalyst Remark": "EV 2W delivery volume spike at baseline support", "Volume Spurt": "2.05x", "Recent Deliv %": "49.5%", "Radar Age": "1 Day"},
    {"Symbol": "BAJAJ-AUTO", "Company": "Bajaj Auto Ltd.", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 10045.00, "Buy Range Low": 9950.00, "Buy Range High": 10120.00, "CHoCH Trigger (Rs)": 10350.00, "Support / TSL (Rs)": 9750.00, "Target 1": 11200.00, "Target 2": 11800.00, "Target 3": 12500.00, "Hinglish News & Catalyst Remark": "Premium 2W exports rise, institutional base building", "Volume Spurt": "2.25x", "Recent Deliv %": "53.0%", "Radar Age": "1 Day"},
    {"Symbol": "BAJAJFINSV", "Company": "Bajaj Finserv Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 1732.60, "Buy Range Low": 1715.00, "Buy Range High": 1745.00, "CHoCH Trigger (Rs)": 1785.00, "Support / TSL (Rs)": 1680.00, "Target 1": 1920.00, "Target 2": 2040.00, "Target 3": 2180.00, "Hinglish News & Catalyst Remark": "Lending & insurance premium growth momentum", "Volume Spurt": "2.35x", "Recent Deliv %": "62.0%", "Radar Age": "1 Day"},
    {"Symbol": "BAJAJHFL", "Company": "Bajaj Housing Finance Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 82.91, "Buy Range Low": 81.80, "Buy Range High": 83.60, "CHoCH Trigger (Rs)": 86.40, "Support / TSL (Rs)": 79.50, "Target 1": 95.00, "Target 2": 102.00, "Target 3": 110.00, "Hinglish News & Catalyst Remark": "Institutional absorption post-listing consolidation", "Volume Spurt": "2.90x", "Recent Deliv %": "61.2%", "Radar Age": "1 Day"},
    {"Symbol": "BAJFINANCE", "Company": "Bajaj Finance Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 7250.00, "Buy Range Low": 7180.00, "Buy Range High": 7290.00, "CHoCH Trigger (Rs)": 7450.00, "Support / TSL (Rs)": 7020.00, "Target 1": 7900.00, "Target 2": 8250.00, "Target 3": 8650.00, "Hinglish News & Catalyst Remark": "AUM expansion & consumer finance delivery spurt", "Volume Spurt": "2.70x", "Recent Deliv %": "65.0%", "Radar Age": "1 Day"},
    {"Symbol": "BEL", "Company": "Bharat Electronics Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️️ Sector Outflow", "CMP (Rs)": 383.10, "Buy Range Low": 380.00, "Buy Range High": 386.00, "CHoCH Trigger (Rs)": 392.50, "Support / TSL (Rs)": 375.00, "Target 1": 416.00, "Target 2": 435.00, "Target 3": 465.00, "Hinglish News & Catalyst Remark": "Defence order book surge, awaiting 15m breakout above 392.5", "Volume Spurt": "2.80x", "Recent Deliv %": "55.4%", "Radar Age": "4 Days"},
    {"Symbol": "CANBK", "Company": "Canara Bank", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 118.36, "Buy Range Low": 116.50, "Buy Range High": 119.50, "CHoCH Trigger (Rs)": 123.50, "Support / TSL (Rs)": 113.00, "Target 1": 132.00, "Target 2": 142.00, "Target 3": 154.00, "Hinglish News & Catalyst Remark": "PSU Bank credit expansion & low credit cost accumulation", "Volume Spurt": "2.45x", "Recent Deliv %": "57.0%", "Radar Age": "1 Day"},
    {"Symbol": "COFORGE", "Company": "Coforge Ltd.", "Sector": "Information Technology", "Sector Alignment": "⚠️️ Sector Outflow", "CMP (Rs)": 7850.00, "Buy Range Low": 7780.00, "Buy Range High": 7920.00, "CHoCH Trigger (Rs)": 8080.00, "Support / TSL (Rs)": 7580.00, "Target 1": 8500.00, "Target 2": 8900.00, "Target 3": 9300.00, "Hinglish News & Catalyst Remark": "Midcap IT client deal signing & delivery expansion", "Volume Spurt": "2.30x", "Recent Deliv %": "50.5%", "Radar Age": "1 Day"},
    {"Symbol": "CUPID", "Company": "Cupid Ltd.", "Sector": "Consumer Durables", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 92.40, "Buy Range Low": 91.00, "Buy Range High": 93.50, "CHoCH Trigger (Rs)": 96.50, "Support / TSL (Rs)": 88.50, "Target 1": 105.00, "Target 2": 112.00, "Target 3": 120.00, "Hinglish News & Catalyst Remark": "Capacity expansion & retail distribution ramp-up", "Volume Spurt": "2.20x", "Recent Deliv %": "52.8%", "Radar Age": "1 Day"},
    {"Symbol": "EIHOTEL", "Company": "EIH Associated Hotels", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 880.00, "Buy Range Low": 868.00, "Buy Range High": 890.00, "CHoCH Trigger (Rs)": 908.00, "Support / TSL (Rs)": 850.00, "Target 1": 965.00, "Target 2": 1020.00, "Target 3": 1090.00, "Hinglish News & Catalyst Remark": "Hospitality sector inflow shift, delivery build-up", "Volume Spurt": "2.35x", "Recent Deliv %": "55.0%", "Radar Age": "1 Day"},
    {"Symbol": "ELECTCAST", "Company": "Electrosteel Castings Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 74.54, "Buy Range Low": 73.00, "Buy Range High": 75.50, "CHoCH Trigger (Rs)": 77.80, "Support / TSL (Rs)": 71.50, "Target 1": 84.00, "Target 2": 89.00, "Target 3": 96.00, "Hinglish News & Catalyst Remark": "Brokerage houses se target upgrade & buy call", "Volume Spurt": "2.46x", "Recent Deliv %": "47.4%", "Radar Age": "1 Day"},
    {"Symbol": "EMAMILTD", "Company": "Emami Ltd.", "Sector": "Fast Moving Consumer Goods", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 372.65, "Buy Range Low": 368.00, "Buy Range High": 375.00, "CHoCH Trigger (Rs)": 386.00, "Support / TSL (Rs)": 361.00, "Target 1": 425.00, "Target 2": 445.00, "Target 3": 470.00, "Hinglish News & Catalyst Remark": "Price rise, lower level valuation support", "Volume Spurt": "2.32x", "Recent Deliv %": "52.9%", "Radar Age": "1 Day"},
    {"Symbol": "ENTERO", "Company": "Entero Healthcare Solutions", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 1145.00, "Buy Range Low": 1130.00, "Buy Range High": 1155.00, "CHoCH Trigger (Rs)": 1175.00, "Support / TSL (Rs)": 1105.00, "Target 1": 1240.00, "Target 2": 1300.00, "Target 3": 1380.00, "Hinglish News & Catalyst Remark": "Healthcare logistics expansion & institutional absorption", "Volume Spurt": "2.65x", "Recent Deliv %": "58.2%", "Radar Age": "1 Day"},
    {"Symbol": "HDFCBANK", "Company": "HDFC Bank Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 1680.00, "Buy Range Low": 1665.00, "Buy Range High": 1692.00, "CHoCH Trigger (Rs)": 1718.00, "Support / TSL (Rs)": 1635.00, "Target 1": 1790.00, "Target 2": 1850.00, "Target 3": 1920.00, "Hinglish News & Catalyst Remark": "Deposit growth uptick, heavy FPI absorption", "Volume Spurt": "3.40x", "Recent Deliv %": "72.1%", "Radar Age": "1 Day"},
    {"Symbol": "ICICIBANK", "Company": "ICICI Bank Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 1285.00, "Buy Range Low": 1272.00, "Buy Range High": 1294.00, "CHoCH Trigger (Rs)": 1315.00, "Support / TSL (Rs)": 1250.00, "Target 1": 1380.00, "Target 2": 1430.00, "Target 3": 1490.00, "Hinglish News & Catalyst Remark": "Strong NIMs stability & sustained institutional delivery", "Volume Spurt": "2.95x", "Recent Deliv %": "69.0%", "Radar Age": "1 Day"},
    {"Symbol": "IIFLCAPS", "Company": "IIFL Capital Services Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 345.60, "Buy Range Low": 340.00, "Buy Range High": 348.00, "CHoCH Trigger (Rs)": 354.00, "Support / TSL (Rs)": 332.00, "Target 1": 375.00, "Target 2": 395.00, "Target 3": 420.00, "Hinglish News & Catalyst Remark": "Institutional block deal / heavy stake accumulation", "Volume Spurt": "2.40x", "Recent Deliv %": "66.4%", "Radar Age": "1 Day"},
    {"Symbol": "IKS", "Company": "IKS Health", "Sector": "Information Technology", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 1420.00, "Buy Range Low": 1400.00, "Buy Range High": 1435.00, "CHoCH Trigger (Rs)": 1465.00, "Support / TSL (Rs)": 1370.00, "Target 1": 1560.00, "Target 2": 1640.00, "Target 3": 1720.00, "Hinglish News & Catalyst Remark": "IT healthcare services steady institutional base", "Volume Spurt": "2.20x", "Recent Deliv %": "48.1%", "Radar Age": "1 Day"},
    {"Symbol": "INDHOTEL", "Company": "Indian Hotels Co Ltd.", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 718.00, "Buy Range Low": 710.00, "Buy Range High": 724.00, "CHoCH Trigger (Rs)": 738.00, "Support / TSL (Rs)": 698.00, "Target 1": 785.00, "Target 2": 820.00, "Target 3": 855.00, "Hinglish News & Catalyst Remark": "Share price rise 2.2%: valuation and sector rotation positive", "Volume Spurt": "2.40x", "Recent Deliv %": "61.3%", "Radar Age": "1 Day"},
    {"Symbol": "JKCEMENT", "Company": "JK Cement Ltd.", "Sector": "Construction Materials", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 4350.00, "Buy Range Low": 4310.00, "Buy Range High": 4390.00, "CHoCH Trigger (Rs)": 4465.00, "Support / TSL (Rs)": 4220.00, "Target 1": 4700.00, "Target 2": 4900.00, "Target 3": 5150.00, "Hinglish News & Catalyst Remark": "Capacity commissioning and strong regional pricing", "Volume Spurt": "2.40x", "Recent Deliv %": "63.5%", "Radar Age": "1 Day"},
    {"Symbol": "KAJARIACER", "Company": "Kajaria Ceramics Ltd.", "Sector": "Consumer Durables", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 1225.10, "Buy Range Low": 1210.00, "Buy Range High": 1235.00, "CHoCH Trigger (Rs)": 1255.00, "Support / TSL (Rs)": 1180.00, "Target 1": 1315.00, "Target 2": 1380.00, "Target 3": 1450.00, "Hinglish News & Catalyst Remark": "Fundamentals & sector valuation expansion", "Volume Spurt": "3.10x", "Recent Deliv %": "68.5%", "Radar Age": "1 Day"},
    {"Symbol": "KOTAKBANK", "Company": "Kotak Mahindra Bank", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 1820.00, "Buy Range Low": 1805.00, "Buy Range High": 1835.00, "CHoCH Trigger (Rs)": 1858.00, "Support / TSL (Rs)": 1775.00, "Target 1": 1940.00, "Target 2": 2010.00, "Target 3": 2100.00, "Hinglish News & Catalyst Remark": "Tech embargo resolution benefits & loan growth pickup", "Volume Spurt": "2.75x", "Recent Deliv %": "62.1%", "Radar Age": "1 Day"},
    {"Symbol": "LENSKART", "Company": "Lenskart Solutions", "Sector": "Consumer Durables", "Sector Alignment": "⚠️️ Sector Outflow", "CMP (Rs)": 385.00, "Buy Range Low": 380.00, "Buy Range High": 389.00, "CHoCH Trigger (Rs)": 398.00, "Support / TSL (Rs)": 368.00, "Target 1": 430.00, "Target 2": 455.00, "Target 3": 485.00, "Hinglish News & Catalyst Remark": "Retail expansion footprint & strong offline same-store sales", "Volume Spurt": "2.85x", "Recent Deliv %": "64.0%", "Radar Age": "1 Day"},
    {"Symbol": "NATCOPHARM", "Company": "Natco Pharma Ltd.", "Sector": "Healthcare", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 1410.00, "Buy Range Low": 1395.00, "Buy Range High": 1425.00, "CHoCH Trigger (Rs)": 1450.00, "Support / TSL (Rs)": 1365.00, "Target 1": 1540.00, "Target 2": 1620.00, "Target 3": 1700.00, "Hinglish News & Catalyst Remark": "US generic approvals and steady formulation cash flows", "Volume Spurt": "2.85x", "Recent Deliv %": "61.0%", "Radar Age": "1 Day"},
    {"Symbol": "PNCINFRA", "Company": "PNC Infratech Ltd.", "Sector": "Construction", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 138.16, "Buy Range Low": 136.00, "Buy Range High": 139.50, "CHoCH Trigger (Rs)": 143.90, "Support / TSL (Rs)": 128.40, "Target 1": 152.00, "Target 2": 162.00, "Target 3": 175.00, "Hinglish News & Catalyst Remark": "Brokerage houses se target upgrade & heavy buying pressure", "Volume Spurt": "3.77x", "Recent Deliv %": "45.4%", "Radar Age": "1 Day"},
    {"Symbol": "SANSERA", "Company": "Sansera Engineering Ltd.", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 1320.00, "Buy Range Low": 1305.00, "Buy Range High": 1335.00, "CHoCH Trigger (Rs)": 1358.00, "Support / TSL (Rs)": 1275.00, "Target 1": 1430.00, "Target 2": 1500.00, "Target 3": 1580.00, "Hinglish News & Catalyst Remark": "EV aerospace components order book expansion", "Volume Spurt": "2.45x", "Recent Deliv %": "46.7%", "Radar Age": "1 Day"},
    {"Symbol": "SHREECEM", "Company": "Shree Cement Ltd.", "Sector": "Construction Materials", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 21900.00, "Buy Range Low": 21700.00, "Buy Range High": 22100.00, "CHoCH Trigger (Rs)": 22650.00, "Support / TSL (Rs)": 21350.00, "Target 1": 23800.00, "Target 2": 24900.00, "Target 3": 26200.00, "Hinglish News & Catalyst Remark": "Share Price Near Low With Mixed Valuation, institutional accumulation", "Volume Spurt": "3.47x", "Recent Deliv %": "51.9%", "Radar Age": "1 Day"},
    {"Symbol": "SHRIPISTON", "Company": "Shriram Pistons & Rings", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 2040.00, "Buy Range Low": 2015.00, "Buy Range High": 2060.00, "CHoCH Trigger (Rs)": 2110.00, "Support / TSL (Rs)": 1965.00, "Target 1": 2240.00, "Target 2": 2350.00, "Target 3": 2480.00, "Hinglish News & Catalyst Remark": "Strong cash delivery absorption at support band", "Volume Spurt": "2.15x", "Recent Deliv %": "54.2%", "Radar Age": "1 Day"},
    {"Symbol": "STARHEALTH", "Company": "Star Health and Allied Insurance", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 537.70, "Buy Range Low": 530.00, "Buy Range High": 542.00, "CHoCH Trigger (Rs)": 558.00, "Support / TSL (Rs)": 513.00, "Target 1": 595.00, "Target 2": 625.00, "Target 3": 660.00, "Hinglish News & Catalyst Remark": "Pullback support level hold kar raha hai, delivery 59.6%", "Volume Spurt": "4.77x", "Recent Deliv %": "59.6%", "Radar Age": "1 Day"},
    {"Symbol": "VESUVIUS", "Company": "Vesuvius India Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "CMP (Rs)": 404.10, "Buy Range Low": 398.00, "Buy Range High": 408.00, "CHoCH Trigger (Rs)": 422.00, "Support / TSL (Rs)": 388.00, "Target 1": 465.00, "Target 2": 495.00, "Target 3": 530.00, "Hinglish News & Catalyst Remark": "REG - American Century Inv Vesuvius plc Form 8.3 heavy stake filing", "Volume Spurt": "2.55x", "Recent Deliv %": "48.9%", "Radar Age": "1 Day"},
    {"Symbol": "WESTLIFE", "Company": "Westlife Foodworld Ltd.", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "CMP (Rs)": 588.05, "Buy Range Low": 580.00, "Buy Range High": 594.00, "CHoCH Trigger (Rs)": 605.00, "Support / TSL (Rs)": 568.00, "Target 1": 645.00, "Target 2": 680.00, "Target 3": 720.00, "Hinglish News & Catalyst Remark": "Institutional block deal / heavy stake accumulation", "Volume Spurt": "2.18x", "Recent Deliv %": "49.9%", "Radar Age": "1 Day"}
]

# ==========================================
# 3. DYNAMIC STATUS & TRIGGER CALCULATOR
# ==========================================
processed_stocks = []
for item in EXCEL_ACCUMULATION_RAW:
    row = item.copy()
    cmp = row["CMP (Rs)"]
    choch = row["CHoCH Trigger (Rs)"]
    b_low = row["Buy Range Low"]
    b_high = row["Buy Range High"]
    
    # Range String Format for Display
    row["Smart Money Buy Range (Rs)"] = f"₹{b_low:.2f} – ₹{b_high:.2f}"
    
    # STRICT INSTITUTIONAL EXECUTION RULE:
    # Entry sirf tabhi valid hoti hai jab CMP >= CHoCH Trigger ho
    if cmp >= choch:
        row["Live Status"] = "⚡ ACTIVE"
        row["Trade Action"] = "ACT: ENTERED"
        row["SMC Structure"] = "CONFIRMED CHoCH (BUY)"
        row["Trade Signal"] = "BUY TRIGGER CONFIRMED"
    elif b_low <= cmp <= b_high:
        row["Live Status"] = "🟢 IN ACCUMULATION"
        row["Trade Action"] = "NEW WATCHLIST"
        row["SMC Structure"] = "⌛ ABSORPTION (WAIT)"
        row["Trade Signal"] = "WAIT FOR CHoCH TRIGGER"
    else:
        row["Live Status"] = "⚪ TRACKING"
        row["Trade Action"] = "NEW WATCHLIST"
        row["SMC Structure"] = "⌛ ABSORPTION (WAIT)"
        row["Trade Signal"] = "WAIT FOR CHoCH TRIGGER"
        
    processed_stocks.append(row)

df_terminal = pd.DataFrame(processed_stocks)

# ==========================================
# 4. EXCEL EXPORT BUILDER (EXACT STYLING)
# ==========================================
def generate_excel_export(df):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SMC_Accumulation_Radar"
    
    export_cols = [
        "Symbol", "Company", "Sector", "CMP (Rs)", "Smart Money Buy Range (Rs)",
        "CHoCH Trigger (Rs)", "Support / TSL (Rs)", "Target 1", "Target 2", "Target 3",
        "Volume Spurt", "Recent Deliv %", "Radar Age", "Live Status", "Trade Action", "SMC Structure"
    ]
    
    ws.append(export_cols)
    
    header_fill = PatternFill(start_color="161B22", end_color="161B22", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    
    for col_num, col_name in enumerate(export_cols, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    for r_idx, row_data in df.iterrows():
        row_vals = [row_data[c] for c in export_cols]
        ws.append(row_vals)
        current_row = r_idx + 2
        
        # Color coding rows based on active trigger
        is_entered = row_data["Trade Action"] == "ACT: ENTERED"
        row_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid") if is_entered else None
        
        for col_num in range(1, len(export_cols) + 1):
            cell = ws.cell(row=current_row, column=col_num)
            if row_fill:
                cell.fill = row_fill
            cell.alignment = Alignment(vertical="center")

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
        
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

# ==========================================
# 5. UI DISPLAY & DASHBOARD
# ==========================================
st.title("⚡ Institutional Smart Money Terminal")
st.markdown(f"**Last Sync:** `{st.session_state.last_refresh_dt}` | **Market Regime:** `{regime_title}` ({regime_sub})")

# Summary Metrics Bar
m1, m2, m3, m4 = st.columns(4)
total_stocks = len(df_terminal)
entered_stocks = len(df_terminal[df_terminal["Trade Action"] == "ACT: ENTERED"])
waiting_stocks = len(df_terminal[df_terminal["Trade Action"] == "NEW WATCHLIST"])
inflow_aligned = len(df_terminal[df_terminal["Sector Alignment"].str.contains("Inflow", na=False)])

m1.metric("Tracked Stocks", total_stocks)
m2.metric("CHoCH Triggered", entered_stocks)
m3.metric("Absorption (Wait)", waiting_stocks)
m4.metric("Inflow Aligned", inflow_aligned)

st.markdown("---")

tab1, tab2 = st.tabs(["📊 Live Accumulation Radar", "📥 Export & Reports"])

with tab1:
    st.subheader("Smart Money Delivery Spurt & Trigger Radar")
    
    display_df = df_terminal[[
        "Symbol", "Company", "Sector", "CMP (Rs)", "Smart Money Buy Range (Rs)",
        "CHoCH Trigger (Rs)", "Support / TSL (Rs)", "Target 1", "Target 2", "Target 3",
        "Volume Spurt", "Recent Deliv %", "Live Status", "Trade Action", "SMC Structure"
    ]]
    
    st.dataframe(display_df, use_container_width=True, height=550)

with tab2:
    st.subheader("Download Audited Radar Data")
    excel_data = generate_excel_export(df_terminal)
    st.download_button(
        label="📥 Download Excel (.xlsx)",
        data=excel_data,
        file_name=f"SMC_Institutional_Radar_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
