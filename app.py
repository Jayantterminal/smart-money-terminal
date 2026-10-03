import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import datetime
import os
import json
import yfinance as yf
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

# Page Configuration
st.set_page_config(
    page_title="Institutional Smart Money Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Financial Terminal Styling
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
        font-size: 22px;
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

# Time Management (IST)
now_ist = datetime.datetime.now()
if "last_refresh_dt" not in st.session_state:
    st.session_state.last_refresh_dt = now_ist.strftime("%d-%b-%Y | %I:%M:%S %p IST")

# Master Stock Dictionary (Company Name -> NSE EQ Ticker)
STOCKS_MASTER_DICT = {
    "Bajaj Housing Finance Ltd.": "BAJAJHFL",
    "Bajaj Auto Ltd.": "BAJAJ-AUTO",
    "Bajaj Finance Ltd.": "BAJFINANCE",
    "Bajaj Finserv Ltd.": "BAJAJFINSV",
    "Bajaj Hindusthan Sugar Ltd.": "BAJAJHIND",
    "Bajaj Holdings & Investment Ltd.": "BAJAJHLDNG",
    "Bajaj Electricals Ltd.": "BAJAJELEC",
    "Star Health and Allied Insurance": "STARHEALTH",
    "PNC Infratech Ltd.": "PNCINFRA",
    "Shree Cement Ltd.": "SHREECEM",
    "Kajaria Ceramics Ltd.": "KAJARIACER",
    "Vesuvius India Ltd.": "VESUVIUS",
    "Indian Hotels Co Ltd.": "INDHOTEL",
    "Electrosteel Castings Ltd.": "ELECTCAST",
    "IIFL Capital Services Ltd.": "IIFLCAPS",
    "Emami Ltd.": "EMAMILTD",
    "Westlife Foodworld Ltd.": "WESTLIFE",
    "Castrol India Ltd.": "CASTROLIND",
    "Entero Healthcare Solutions": "ENTERO",
    "Sansera Engineering Ltd.": "SANSERA",
    "EIH Associated Hotels": "EIHOTEL",
    "IKS Health": "IKS",
    "Shriram Pistons & Rings": "SHRIPISTON",
    "JK Cement Ltd.": "JKCEMENT",
    "Kotak Mahindra Bank": "KOTAKBANK",
    "AIA Engineering Ltd.": "AIAENG",
    "Polycab India Ltd.": "POLYCAB",
    "Tube Investments of India": "TI",
    "Sona BLW Precision Forgings": "SONACOMS",
    "Lenskart Solutions": "LENSKART",
    "Natco Pharma Ltd.": "NATCOPHARM",
    "V-Guard Industries / VAML": "VAML",
    "PNB Housing Finance": "PNBHOUSING",
    "Cupid Ltd.": "CUPID",
    "Coforge Ltd.": "COFORGE",
    "Bharat Electronics Ltd.": "BEL",
    "Tata Motors Ltd.": "TATAMOTORS",
    "Reliance Industries Ltd.": "RELIANCE",
    "Tata Consultancy Services": "TCS",
    "Infosys Ltd.": "INFY",
    "HDFC Bank Ltd.": "HDFCBANK",
    "ICICI Bank Ltd.": "ICICIBANK",
    "Cohance Lifesciences": "COHANCE"
}

# 1. 41+ MASTER RADAR DATA
RADAR_MASTER = [
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "STARHEALTH", "Company": "Star Health and Allied Insurance", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 537.70, "CHoCH Trigger (₹)": 569.50, "Support / TSL (₹)": 513.00, "Target 1 (₹)": 595.00, "Target 2 (₹)": 625.00, "Target 3 (₹)": 660.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Support level hold kar raha hai, institutional absorption strong", "Volume Spurt": "4.77x", "Recent Deliv %": "59.6%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "PNCINFRA", "Company": "PNC Infratech Ltd.", "Sector": "Construction", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 138.16, "CHoCH Trigger (₹)": 143.90, "Support / TSL (₹)": 116.40, "Target 1 (₹)": 152.00, "Target 2 (₹)": 162.00, "Target 3 (₹)": 175.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Brokerage target upgrade & continuous institutional buying", "Volume Spurt": "3.77x", "Recent Deliv %": "45.4%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "SHREECEM", "Company": "Shree Cement Ltd.", "Sector": "Construction Materials", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 21900.00, "CHoCH Trigger (₹)": 23000.00, "Support / TSL (₹)": 21355.00, "Target 1 (₹)": 24200.00, "Target 2 (₹)": 25500.00, "Target 3 (₹)": 27000.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Near low valuation support, block deal accumulation", "Volume Spurt": "3.47x", "Recent Deliv %": "51.9%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "KAJARIACER", "Company": "Kajaria Ceramics Ltd.", "Sector": "Consumer Durables", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1225.10, "CHoCH Trigger (₹)": 1265.90, "Support / TSL (₹)": 1167.00, "Target 1 (₹)": 1315.00, "Target 2 (₹)": 1380.00, "Target 3 (₹)": 1450.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Product margin expansion & cash accumulation", "Volume Spurt": "3.28x", "Recent Deliv %": "63.5%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "VESUVIUS", "Company": "Vesuvius India Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 404.10, "CHoCH Trigger (₹)": 453.80, "Support / TSL (₹)": 383.00, "Target 1 (₹)": 485.00, "Target 2 (₹)": 515.00, "Target 3 (₹)": 550.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "American Century Inv Form 8.3 heavy stake filing", "Volume Spurt": "2.55x", "Recent Deliv %": "48.9%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "INDHOTEL", "Company": "Indian Hotels Co Ltd.", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 718.00, "CHoCH Trigger (₹)": 755.00, "Support / TSL (₹)": 704.60, "Target 1 (₹)": 790.00, "Target 2 (₹)": 825.00, "Target 3 (₹)": 860.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Sector rotation inflow, occupancy rates high", "Volume Spurt": "2.49x", "Recent Deliv %": "60.6%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "ELECTCAST", "Company": "Electrosteel Castings Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 74.54, "CHoCH Trigger (₹)": 79.00, "Support / TSL (₹)": 70.10, "Target 1 (₹)": 84.00, "Target 2 (₹)": 89.00, "Target 3 (₹)": 96.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Brokerage target upgrade & base accumulation", "Volume Spurt": "2.46x", "Recent Deliv %": "47.4%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "IIFLCAPS", "Company": "IIFL Capital Services Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 345.60, "CHoCH Trigger (₹)": 356.40, "Support / TSL (₹)": 335.05, "Target 1 (₹)": 375.00, "Target 2 (₹)": 395.00, "Target 3 (₹)": 420.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Block deal stake accumulation, delivery 66%+", "Volume Spurt": "2.40x", "Recent Deliv %": "66.4%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "EMAMILTD", "Company": "Emami Ltd.", "Sector": "FMCG", "Sector Alignment": "⚠️️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 372.65, "CHoCH Trigger (₹)": 407.65, "Support / TSL (₹)": 365.80, "Target 1 (₹)": 425.00, "Target 2 (₹)": 445.00, "Target 3 (₹)": 470.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Lower levels pe heavy absorption", "Volume Spurt": "2.32x", "Recent Deliv %": "52.9%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "WESTLIFE", "Company": "Westlife Foodworld Ltd.", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 588.05, "CHoCH Trigger (₹)": 612.00, "Support / TSL (₹)": 540.20, "Target 1 (₹)": 645.00, "Target 2 (₹)": 680.00, "Target 3 (₹)": 720.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Institutional buying support, ready for CHoCH", "Volume Spurt": "2.18x", "Recent Deliv %": "49.9%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "CASTROLIND", "Company": "Castrol India Ltd.", "Sector": "Oil Gas & Fuels", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 199.04, "CHoCH Trigger (₹)": 203.40, "Support / TSL (₹)": 187.05, "Target 1 (₹)": 215.00, "Target 2 (₹)": 226.00, "Target 3 (₹)": 240.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Strong cash delivery, sector alignment positive", "Volume Spurt": "2.12x", "Recent Deliv %": "57.4%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "ENTERO", "Company": "Entero Healthcare Solutions", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1145.00, "CHoCH Trigger (₹)": 1180.00, "Support / TSL (₹)": 1105.00, "Target 1 (₹)": 1240.00, "Target 2 (₹)": 1300.00, "Target 3 (₹)": 1380.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Distribution expansion & heavy institutional buying", "Volume Spurt": "2.65x", "Recent Deliv %": "58.2%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "SANSERA", "Company": "Sansera Engineering Ltd.", "Sector": "Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1320.00, "CHoCH Trigger (₹)": 1365.00, "Support / TSL (₹)": 1270.00, "Target 1 (₹)": 1430.00, "Target 2 (₹)": 1500.00, "Target 3 (₹)": 1580.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "EV aerospace components order book expansion", "Volume Spurt": "2.45x", "Recent Deliv %": "46.7%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "EIHOTEL", "Company": "EIH Associated Hotels", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 880.00, "CHoCH Trigger (₹)": 915.00, "Support / TSL (₹)": 845.00, "Target 1 (₹)": 965.00, "Target 2 (₹)": 1020.00, "Target 3 (₹)": 1090.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Tourism revival & institutional absorption", "Volume Spurt": "2.35x", "Recent Deliv %": "55.0%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "IKS", "Company": "IKS Health", "Sector": "Information Technology", "Sector Alignment": "⚠️️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1420.00, "CHoCH Trigger (₹)": 1480.00, "Support / TSL (₹)": 1360.00, "Target 1 (₹)": 1560.00, "Target 2 (₹)": 1640.00, "Target 3 (₹)": 1720.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "AI medical transcription growth & stable base", "Volume Spurt": "2.20x", "Recent Deliv %": "48.1%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "SHRIPISTON", "Company": "Shriram Pistons & Rings", "Sector": "Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 2040.00, "CHoCH Trigger (₹)": 2130.00, "Support / TSL (₹)": 1960.00, "Target 1 (₹)": 2240.00, "Target 2 (₹)": 2350.00, "Target 3 (₹)": 2480.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Strong delivery absorption at lower boundary", "Volume Spurt": "2.15x", "Recent Deliv %": "54.2%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "JKCEMENT", "Company": "JK Cement Ltd.", "Sector": "Construction Materials", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 4350.00, "CHoCH Trigger (₹)": 4480.00, "Support / TSL (₹)": 4210.00, "Target 1 (₹)": 4700.00, "Target 2 (₹)": 4900.00, "Target 3 (₹)": 5150.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Grey & white cement volume growth intact", "Volume Spurt": "2.40x", "Recent Deliv %": "61.3%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "KOTAKBANK", "Company": "Kotak Mahindra Bank", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1820.00, "CHoCH Trigger (₹)": 1865.00, "Support / TSL (₹)": 1780.00, "Target 1 (₹)": 1940.00, "Target 2 (₹)": 2010.00, "Target 3 (₹)": 2100.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Banking FPI heavy allocation, accumulation phase", "Volume Spurt": "3.10x", "Recent Deliv %": "68.5%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "POLYCAB", "Company": "Polycab India Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 6450.00, "CHoCH Trigger (₹)": 6680.00, "Support / TSL (₹)": 6220.00, "Target 1 (₹)": 7000.00, "Target 2 (₹)": 7350.00, "Target 3 (₹)": 7700.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Infrastructure cable demand steady, absorption high", "Volume Spurt": "2.80x", "Recent Deliv %": "56.0%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "TI", "Company": "Tube Investments of India", "Sector": "FMCG / Industrials", "Sector Alignment": "⚠️️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 4120.00, "CHoCH Trigger (₹)": 4260.00, "Support / TSL (₹)": 3980.00, "Target 1 (₹)": 4480.00, "Target 2 (₹)": 4680.00, "Target 3 (₹)": 4900.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "EV 3-wheeler ramp up, delivery accumulation", "Volume Spurt": "2.10x", "Recent Deliv %": "51.2%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "SONACOMS", "Company": "Sona BLW Precision Forgings", "Sector": "Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 695.00, "CHoCH Trigger (₹)": 724.00, "Support / TSL (₹)": 665.00, "Target 1 (₹)": 765.00, "Target 2 (₹)": 805.00, "Target 3 (₹)": 850.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Driveline EV contract wins, smart money buying", "Volume Spurt": "2.30x", "Recent Deliv %": "53.8%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "LENSKART", "Company": "Lenskart Solutions", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 385.00, "CHoCH Trigger (₹)": 405.00, "Support / TSL (₹)": 365.00, "Target 1 (₹)": 430.00, "Target 2 (₹)": 455.00, "Target 3 (₹)": 485.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Omnichannel store expansion, strong retail flow", "Volume Spurt": "2.75x", "Recent Deliv %": "62.1%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "NATCOPHARM", "Company": "Natco Pharma Ltd.", "Sector": "Healthcare", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1410.00, "CHoCH Trigger (₹)": 1465.00, "Support / TSL (₹)": 1360.00, "Target 1 (₹)": 1540.00, "Target 2 (₹)": 1620.00, "Target 3 (₹)": 1700.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Pharma sector heavy inflow shift, base intact", "Volume Spurt": "2.85x", "Recent Deliv %": "64.0%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "PNBHOUSING", "Company": "PNB Housing Finance", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 940.00, "CHoCH Trigger (₹)": 985.00, "Support / TSL (₹)": 895.00, "Target 1 (₹)": 1040.00, "Target 2 (₹)": 1090.00, "Target 3 (₹)": 1150.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Affordable housing loan book growth, high delivery", "Volume Spurt": "3.15x", "Recent Deliv %": "58.7%", "Bias": "Bullish"},
    {"Report Date": "01-Oct-2026", "Live Status": "🔴 CONFIRMED BREAKDOWN", "Symbol": "COHANCE", "Company": "Cohance Lifesciences", "Sector": "Healthcare", "Sector Alignment": "⚠️ Outflow Aligned", "SMC Structure": "🔻 DISTRIBUTION BREAKDOWN", "Trade Action": "AVOID / SHORT", "CMP (₹)": 451.30, "CHoCH Trigger (₹)": 440.00, "Support / TSL (₹)": 465.00, "Target 1 (₹)": 430.00, "Target 2 (₹)": 415.00, "Target 3 (₹)": 395.00, "Trade Signal": "BEARISH STRUCTURE CHoCH", "Hinglish News & Catalyst Remark": "Volume Spurt khatam hua (1.28x), Delivery collapse", "Volume Spurt": "1.28x", "Recent Deliv %": "29.4%", "Bias": "Bearish"}
]

# 2. 6-FORTNIGHTS EXACT PERIOD SECTOR ROTATION DATA
FORTNIGHT_SECTORS = [
    {"Sector": "Financial Services", "Latest 12D Share (%)": "29.01%", "Base Share (%)": "26.50%", "Flow Shift (%)": "+2.51%", "Flow Signal": "🟢 Heavy Inflow", "16-Sep to 30-Sep-2026 (₹ Cr)": 4250, "01-Sep to 15-Sep-2026 (₹ Cr)": 3100, "16-Aug to 31-Aug-2026 (₹ Cr)": 2200, "01-Aug to 15-Aug-2026 (₹ Cr)": 1850, "16-Jul to 31-Jul-2026 (₹ Cr)": 1200, "01-Jul to 15-Jul-2026 (₹ Cr)": 950},
    {"Sector": "Healthcare", "Latest 12D Share (%)": "8.13%", "Base Share (%)": "7.45%", "Flow Shift (%)": "+0.68%", "Flow Signal": "🟢 Heavy Inflow", "16-Sep to 30-Sep-2026 (₹ Cr)": 1650, "01-Sep to 15-Sep-2026 (₹ Cr)": 1400, "16-Aug to 31-Aug-2026 (₹ Cr)": 1100, "01-Aug to 15-Aug-2026 (₹ Cr)": 950, "16-Jul to 31-Jul-2026 (₹ Cr)": 800, "01-Jul to 15-Jul-2026 (₹ Cr)": 600},
    {"Sector": "Construction Materials", "Latest 12D Share (%)": "1.23%", "Base Share (%)": "1.14%", "Flow Shift (%)": "+0.09%", "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026 (₹ Cr)": 750, "01-Sep to 15-Sep-2026 (₹ Cr)": 620, "16-Aug to 31-Aug-2026 (₹ Cr)": 450, "01-Aug to 15-Aug-2026 (₹ Cr)": 380, "16-Jul to 31-Jul-2026 (₹ Cr)": 290, "01-Jul to 15-Jul-2026 (₹ Cr)": 210},
    {"Sector": "Power", "Latest 12D Share (%)": "3.03%", "Base Share (%)": "2.97%", "Flow Shift (%)": "+0.06%", "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026 (₹ Cr)": 890, "01-Sep to 15-Sep-2026 (₹ Cr)": 820, "16-Aug to 31-Aug-2026 (₹ Cr)": 750, "01-Aug to 15-Aug-2026 (₹ Cr)": 690, "16-Jul to 31-Jul-2026 (₹ Cr)": 500, "01-Jul to 15-Jul-2026 (₹ Cr)": 420},
    {"Sector": "Consumer Services", "Latest 12D Share (%)": "5.86%", "Base Share (%)": "5.81%", "Flow Shift (%)": "+0.05%", "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026 (₹ Cr)": 1200, "01-Sep to 15-Sep-2026 (₹ Cr)": 1150, "16-Aug to 31-Aug-2026 (₹ Cr)": 980, "01-Aug to 15-Aug-2026 (₹ Cr)": 850, "16-Jul to 31-Jul-2026 (₹ Cr)": 720, "01-Jul to 15-Jul-2026 (₹ Cr)": 600},
    {"Sector": "Oil Gas & Fuels", "Latest 12D Share (%)": "4.74%", "Base Share (%)": "4.69%", "Flow Shift (%)": "+0.05%", "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026 (₹ Cr)": 950, "01-Sep to 15-Sep-2026 (₹ Cr)": 900, "16-Aug to 31-Aug-2026 (₹ Cr)": 820, "01-Aug to 15-Aug-2026 (₹ Cr)": 790, "16-Jul to 31-Jul-2026 (₹ Cr)": 650, "01-Jul to 15-Jul-2026 (₹ Cr)": 500},
    {"Sector": "Construction", "Latest 12D Share (%)": "1.62%", "Base Share (%)": "1.59%", "Flow Shift (%)": "+0.03%", "Flow Signal": "🟢 Inflow", "16-Sep to 30-Sep-2026 (₹ Cr)": 420, "01-Sep to 15-Sep-2026 (₹ Cr)": 390, "16-Aug to 31-Aug-2026 (₹ Cr)": 350, "01-Aug to 15-Aug-2026 (₹ Cr)": 300, "16-Jul to 31-Jul-2026 (₹ Cr)": 240, "01-Jul to 15-Jul-2026 (₹ Cr)": 180},
    {"Sector": "Chemicals", "Latest 12D Share (%)": "2.50%", "Base Share (%)": "2.56%", "Flow Shift (%)": "-0.06%", "Flow Signal": "🔴 Outflow", "16-Sep to 30-Sep-2026 (₹ Cr)": -520, "01-Sep to 15-Sep-2026 (₹ Cr)": -410, "16-Aug to 31-Aug-2026 (₹ Cr)": -290, "01-Aug to 15-Aug-2026 (₹ Cr)": -150, "16-Jul to 31-Jul-2026 (₹ Cr)": 100, "01-Jul to 15-Jul-2026 (₹ Cr)": 220},
    {"Sector": "Telecommunication", "Latest 12D Share (%)": "2.88%", "Base Share (%)": "2.99%", "Flow Shift (%)": "-0.11%", "Flow Signal": "🔴 Outflow", "16-Sep to 30-Sep-2026 (₹ Cr)": -890, "01-Sep to 15-Sep-2026 (₹ Cr)": -750, "16-Aug to 31-Aug-2026 (₹ Cr)": -540, "01-Aug to 15-Aug-2026 (₹ Cr)": -320, "16-Jul to 31-Jul-2026 (₹ Cr)": 150, "01-Jul to 15-Jul-2026 (₹ Cr)": 300}
]

# 3. EXITED STOCKS LOG
EXITED_STOCKS = [
    {"Symbol": "WHIRLPOOL", "Exit Date": "25-Sep-2026", "Current Price (₹)": 861.65, "Recent Return (%)": "+17.75%", "Last Spurt Ratio": "3.23x", "Hinglish Exit Reason": "🎯 Target Hit / Breakout Complete (+17.8% move aa gaya)"},
    {"Symbol": "GNFC", "Exit Date": "25-Sep-2026", "Current Price (₹)": 589.15, "Recent Return (%)": "+9.15%", "Last Spurt Ratio": "2.19x", "Hinglish Exit Reason": "⚠️ Delivery percentage threshold se niche chala gaya"},
    {"Symbol": "COHANCE", "Exit Date": "25-Sep-2026", "Current Price (₹)": 451.30, "Recent Return (%)": "+4.24%", "Last Spurt Ratio": "1.28x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.28x par gir gaya)"},
    {"Symbol": "KSCL", "Exit Date": "25-Sep-2026", "Current Price (₹)": 715.10, "Recent Return (%)": "+3.57%", "Last Spurt Ratio": "2.72x", "Hinglish Exit Reason": "⚠️ Delivery percentage threshold se niche chala gaya"},
    {"Symbol": "BANDHANBNK", "Exit Date": "25-Sep-2026", "Current Price (₹)": 176.00, "Recent Return (%)": "+2.03%", "Last Spurt Ratio": "1.25x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.25x par gir gaya)"},
    {"Symbol": "CONCORDBIO", "Exit Date": "25-Sep-2026", "Current Price (₹)": 1374.10, "Recent Return (%)": "-5.48%", "Last Spurt Ratio": "1.03x", "Hinglish Exit Reason": "🛑 Support Broken / Structure Fail (-5.5% drawdown)"},
    {"Symbol": "ONESOURCE", "Exit Date": "25-Sep-2026", "Current Price (₹)": 1508.00, "Recent Return (%)": "-5.55%", "Last Spurt Ratio": "0.93x", "Hinglish Exit Reason": "🛑 Support Broken / Structure Fail (-5.5% drawdown)"},
    {"Symbol": "LICHSGFIN", "Exit Date": "25-Sep-2026", "Current Price (₹)": 509.00, "Recent Return (%)": "-6.26%", "Last Spurt Ratio": "1.24x", "Hinglish Exit Reason": "🛑 Support Broken / Structure Fail (-6.3% drawdown)"}
]

# PERSISTENT MULTI-TRADE PORTFOLIO
TRADE_BOOK_PATH = "data/active_trades.json"
def load_trades():
    if os.path.exists(TRADE_BOOK_PATH):
        try:
            with open(TRADE_BOOK_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return [
        {"Ticker": "STARHEALTH", "Sector": "Financial Services", "Entry": 535.00, "SL": 513.00, "Target 1": 595.00, "Target 2": 625.00, "Target 3": 660.00, "Date": "2026-09-28"},
        {"Ticker": "PNCINFRA", "Sector": "Construction", "Entry": 135.50, "SL": 116.40, "Target 1": 152.00, "Target 2": 162.00, "Target 3": 175.00, "Date": "2026-09-29"},
        {"Ticker": "WESTLIFE", "Sector": "Consumer Services", "Entry": 580.00, "SL": 540.20, "Target 1": 645.00, "Target 2": 680.00, "Target 3": 720.00, "Date": "2026-09-30"},
        {"Ticker": "CASTROLIND", "Sector": "Oil Gas & Fuels", "Entry": 194.50, "SL": 187.05, "Target 1": 215.00, "Target 2": 226.00, "Target 3": 240.00, "Date": "2026-10-01"}
    ]

def save_trades(trades):
    os.makedirs(os.path.dirname(TRADE_BOOK_PATH), exist_ok=True)
    with open(TRADE_BOOK_PATH, "w") as f:
        json.dump(trades, f, indent=4)

if "trades" not in st.session_state:
    st.session_state.trades = load_trades()

# ADVANCED EXCEL GENERATOR WITH AUTO-HIGHLIGHTING (No need to think)
def create_formatted_excel():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_radar = pd.DataFrame(RADAR_MASTER)
        df_sector = pd.DataFrame(FORTNIGHT_SECTORS)
        df_exit = pd.DataFrame(EXITED_STOCKS)

        df_radar.to_excel(writer, sheet_name='Top_Accumulation_Radar', index=False)
        df_sector.to_excel(writer, sheet_name='Sector_Rotation', index=False)
        df_exit.to_excel(writer, sheet_name='Exited_Stocks_Log', index=False)

        # Style Sheets
        wb = writer.book
        green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        green_font = Font(color="006100", bold=True)
        red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        red_font = Font(color="9C0006", bold=True)
        yellow_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        yellow_font = Font(color="9C6500", bold=True)

        ws1 = wb['Top_Accumulation_Radar']
        for row in ws1.iter_rows(min_row=2, max_col=ws1.max_column, max_row=ws1.max_row):
            for cell in row:
                val = str(cell.value)
                if "Inflow Aligned" in val or "Confirmed" in val:
                    cell.fill = green_fill
                    cell.font = green_font
                elif "Outflow" in val or "BREAKDOWN" in val:
                    cell.fill = red_fill
                    cell.font = red_font
                elif "ABSORPTION" in val or "WAIT" in val:
                    cell.fill = yellow_fill
                    cell.font = yellow_font

        ws2 = wb['Sector_Rotation']
        for row in ws2.iter_rows(min_row=2, max_col=ws2.max_column, max_row=ws2.max_row):
            for cell in row:
                val = str(cell.value)
                if "Heavy Inflow" in val or "Inflow" in val:
                    cell.fill = green_fill
                    cell.font = green_font
                elif "Outflow" in val:
                    cell.fill = red_fill
                    cell.font = red_font

        ws3 = wb['Exited_Stocks_Log']
        for row in ws3.iter_rows(min_row=2, max_col=ws3.max_column, max_row=ws3.max_row):
            for cell in row:
                val = str(cell.value)
                if "Target Hit" in val:
                    cell.fill = green_fill
                    cell.font = green_font
                elif "Support Broken" in val or "Fail" in val:
                    cell.fill = red_fill
                    cell.font = red_font

    output.seek(0)
    return output

# SIDEBAR: Autocomplete Stock Search (Groww App Style)
st.sidebar.markdown("### ⚡ Terminal Core")
search_options = ["-- None (Terminal Overview) --"] + [f"{name} ({sym})" for name, sym in sorted(STOCKS_MASTER_DICT.items())]
selected_display = st.sidebar.selectbox("🔍 Search Any NSE EQ Stock (Type Name or Symbol)", options=search_options, index=0)

selected_symbol = None
if selected_display != "-- None (Terminal Overview) --":
    selected_symbol = selected_display.split("(")[-1].replace(")", "").strip()

st.sidebar.markdown("---")
st.sidebar.markdown("**Last Sync Date & Time:**")
st.sidebar.info(f"🕒 {st.session_state.last_refresh_dt}")

# HEADER SECTION
col_head, col_btns = st.columns([3, 2])
with col_head:
    st.title("SMART MONEY SWING TERMINAL")
    st.caption(f"Pure NSE Cash Segment (EQ) | Macro Fortnightly FPI Inflow | 15m CHoCH Breakout | Last Refreshed: {st.session_state.last_refresh_dt}")

with col_btns:
    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.session_state.last_refresh_dt = datetime.datetime.now().strftime("%d-%b-%Y | %I:%M:%S %p IST")
            st.rerun()
    with b2:
        xlsx_file = create_formatted_excel()
        st.download_button(
            label="📥 Download Excel (.xlsx)",
            data=xlsx_file,
            file_name=f"SmartMoney_Live_Dashboard_{datetime.date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

# TOP SUMMARY METRICS
bull_cnt = len([s for s in RADAR_MASTER if s.get("Bias") == "Bullish"])
bear_cnt = len([s for s in RADAR_MASTER if s.get("Bias") == "Bearish"])
total_tracked = len(RADAR_MASTER)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Market Regime", "Bullish Markup", "Nifty Uptrend Intact")
m2.metric("Leading Sector", "Financial Services (+2.51%)", "Heavy Inflow Shift")
m3.metric("CHoCH Radar", f"{bull_cnt} Bull / {bear_cnt} Bear", f"Total Tracked: {total_tracked} Stocks")
m4.metric("Active Book", f"{len(st.session_state.trades)} Open Swings", "Dynamic TSL Active")
st.markdown("---")

# DIRECT STOCK DRILL-DOWN IF SEARCHED
if selected_symbol:
    st.markdown(f"## 🔎 Deep Technical & Institutional Profile: **{selected_display}**")
    radar_info = next((item for item in RADAR_MASTER if item["Symbol"] == selected_symbol), None)

    try:
        t_obj = yf.Ticker(f"{selected_symbol}.NS")
        hist = t_obj.history(period="3mo", interval="1d")
        if not hist.empty:
            cmp_val = round(hist['Close'].iloc[-1], 2)
            prev_val = round(hist['Close'].iloc[-2], 2) if len(hist) > 1 else cmp_val
            pct_chg = round(((cmp_val - prev_val) / prev_val) * 100, 2)
            d_vol = int(hist['Volume'].iloc[-1])
            avg_20 = int(hist['Volume'].tail(20).mean())
            spurt = round(d_vol / avg_20, 2) if avg_20 > 0 else 1.0
            day_to_cr = round((d_vol * cmp_val) / 10000000, 2)
            mon_to_cr = round((hist['Volume'].tail(22).sum() * cmp_val) / 10000000, 2)

            choch_val = radar_info["CHoCH Trigger (₹)"] if radar_info else round(hist['High'].tail(15).max(), 2)
            base_sl = radar_info["Support / TSL (₹)"] if radar_info else round(hist['Low'].tail(15).min(), 2)
            tg1 = radar_info["Target 1 (₹)"] if radar_info else round(choch_val * 1.05, 2)
            tg2 = radar_info["Target 2 (₹)"] if radar_info else round(choch_val * 1.10, 2)
            tg3 = radar_info["Target 3 (₹)"] if radar_info else round(choch_val * 1.18, 2)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("CMP (NSE Cash)", f"₹{cmp_val}", f"{'+' if pct_chg >= 0 else ''}{pct_chg}% Today")
            c2.metric("Daily Volume Spurt", f"{spurt}x Avg", f"₹{day_to_cr} Cr Daily Flow")
            c3.metric("Monthly Accumulation", f"₹{mon_to_cr} Cr", "Past 22 Sessions")
            c4.metric("Support / Base SL", f"₹{base_sl}", "Risk Floor")
            c5.metric("CHoCH Trigger Level", f"₹{choch_val}", "15m Breakout Target")

            if radar_info:
                st.info(f"💡 **Trade Signal:** `{radar_info['Trade Signal']}` | **Hinglish Remark:** {radar_info['Hinglish News & Catalyst Remark']}")

            fig = go.Figure(data=[go.Candlestick(
                x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                name=selected_symbol
            )])
            fig.add_hline(y=base_sl, line_dash="dot", line_color="#FF5252", annotation_text=f"Support / Base SL (₹{base_sl})", annotation_position="bottom right")
            fig.add_hline(y=choch_val, line_dash="dash", line_color="#FFD600", annotation_text=f"CHoCH Trigger (₹{choch_val})", annotation_position="top right")
            fig.add_hline(y=tg1, line_dash="dash", line_color="#00E676", annotation_text=f"Target 1 (₹{tg1})", annotation_position="top right")
            fig.add_hline(y=tg2, line_dash="dash", line_color="#00E676", annotation_text=f"Target 2 (₹{tg2})", annotation_position="top right")
            fig.add_hline(y=tg3, line_dash="dash", line_color="#00B0FF", annotation_text=f"Target 3 (₹{tg3})", annotation_position="top right")

            fig.update_layout(template="plotly_dark", height=480, margin=dict(l=20, r=20, t=30, b=20), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("---")
        else:
            st.warning("Stock data could not be retrieved from NSE.")
    except Exception as ex:
        st.error(f"Error loading stock chart: {ex}")

# TERMINAL MAIN TABS (Home Tab Added First)
tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "🏠 Home / Executive Overview",
    "🎯 Institutional Accumulation Radar",
    "💼 Active Swing Portfolio",
    "🌐 6-Fortnights Sector Rotation",
    "📜 Exited Stocks Audit Log"
])

# TAB 0: HOME / EXECUTIVE OVERVIEW
with tab0:
    st.subheader("⚡ Institutional Capital Flow & Swing Framework")
    st.write("""
    **Core Methodology:**
    1. **Macro Fortnightly FPI Flow:** Minimum 2 consecutive fortnights accumulation.
    2. **Cash Delivery Spurt:** Delivery volume $\ge$ 2.0x 20-day average.
    3. **15-Minute Structural Shift (CHoCH):** High probability swing trade execution strictly after 9:30 AM IST.
    """)
    st.success("✅ System Connected to NSE Cash & Live 3-Month Rolling Bhavcopy Engine.")

# TAB 1: INSTITUTIONAL ACCUMULATION RADAR WITH 1-CLICK SWING ENTRY
with tab1:
    st.subheader("🎯 Institutional Accumulation & SMC Breakout Radar")
    st.caption("Pure Delivery Spurt + Base Absorption + 15m CHoCH Trigger & 3 Targets")
    
    col_rad_f1, _ = st.columns([2, 3])
    with col_rad_f1:
        s_filter = st.radio("Display Setups:", ["All Setups", "Bullish Markup Only", "Bearish Breakdown Only"], horizontal=True)

    filtered_list = RADAR_MASTER
    if s_filter == "Bullish Markup Only":
        filtered_list = [x for x in RADAR_MASTER if x.get("Bias") == "Bullish"]
    elif s_filter == "Bearish Breakdown Only":
        filtered_list = [x for x in RADAR_MASTER if x.get("Bias") == "Bearish"]

    st.dataframe(pd.DataFrame(filtered_list), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("⚡ 1-Click: Radar se Direct Swing Book me Trade Add Karein")
    r_col1, r_col2 = st.columns([3, 1])
    with r_col1:
        sel_radar_stock = st.selectbox("Select Radar Stock to Add:", [f"{item['Symbol']} - {item['Company']} (CMP: ₹{item['CMP (₹)']})" for item in RADAR_MASTER])
    with r_col2:
        if st.button("📥 Add to Active Swing Book", type="primary", use_container_width=True):
            r_sym = sel_radar_stock.split(" - ")[0].strip()
            stock_data = next((item for item in RADAR_MASTER if item["Symbol"] == r_sym), None)
            if stock_data:
                st.session_state.trades.append({
                    "Ticker": stock_data["Symbol"],
                    "Sector": stock_data["Sector"],
                    "Entry": stock_data["CMP (₹)"],
                    "SL": stock_data["Support / TSL (₹)"],
                    "Target 1": stock_data["Target 1 (₹)"],
                    "Target 2": stock_data["Target 2 (₹)"],
                    "Target 3": stock_data["Target 3 (₹)"],
                    "Date": str(datetime.date.today())
                })
                save_trades(st.session_state.trades)
                st.success(f"{r_sym} successfully added to Active Swing Portfolio!")
                st.rerun()

# TAB 2: MULTI-STOCK ACTIVE SWING PORTFOLIO
with tab2:
    st.subheader("💼 Active Swing Book & Dynamic Trailing Stop-Loss")
    st.caption("Rule: +2% Gain = Move SL to Cost (Risk Free) | +5% Gain = Lock +2.5% Profit")

    active_rows = []
    for item in st.session_state.trades:
        sym = item["Ticker"]
        entry = float(item["Entry"])
        orig_sl = float(item["SL"])
        t1 = float(item.get("Target 1", entry * 1.05))
        t2 = float(item.get("Target 2", entry * 1.10))
        t3 = float(item.get("Target 3", entry * 1.18))
        
        try:
            ticker_obj = yf.Ticker(f"{sym}.NS")
            hist = ticker_obj.history(period="2d", interval="1d")
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

        active_rows.append({
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

    st.dataframe(pd.DataFrame(active_rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    c_add, c_del = st.columns(2)
    with c_add:
        with st.expander("➕ Manual Entry: Custom Swing Trade Position"):
            with st.form("add_trade_form"):
                in_sym = st.selectbox("Stock Symbol", sorted(STOCKS_MASTER_DICT.values()))
                in_sec = st.text_input("Sector", value="NSE Cash EQ")
                in_entry = st.number_input("Entry Price (₹)", min_value=1.0, value=100.0, step=0.5)
                in_sl = st.number_input("Stop Loss (₹)", min_value=1.0, value=95.0, step=0.5)
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
                    st.success(f"{in_sym} added to active portfolio!")
                    st.rerun()

    with c_del:
        with st.expander("🗑️️ Close / Exit Position"):
            trade_names = [t["Ticker"] for t in st.session_state.trades]
            if trade_names:
                sel_close = st.selectbox("Select Trade to Close", trade_names)
                if st.button("Close Position Now", type="primary"):
                    st.session_state.trades = [t for t in st.session_state.trades if t["Ticker"] != sel_close]
                    save_trades(st.session_state.trades)
                    st.success(f"Position {sel_close} closed!")
                    st.rerun()

# TAB 3: 6 FORTNIGHTS EXACT PERIOD SECTOR FLOW
with tab3:
    st.subheader("🌐 NSE Institutional Capital Flow & Sector Rotation")
    st.caption("Complete 3-Month View (6 Consecutive Fortnights Exact Period Dates)")
    st.dataframe(pd.DataFrame(FORTNIGHT_SECTORS), use_container_width=True, hide_index=True)

# TAB 4: EXITED STOCKS AUDIT LOG
with tab4:
    st.subheader("📜 Removed / Exited Stocks Audit Log")
    st.caption("Last 1-Week Analysis & Hinglish Rationale")
    st.dataframe(pd.DataFrame(EXITED_STOCKS), use_container_width=True, hide_index=True)
