import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import datetime
import os
import json
import yfinance as yf

# Page Layout
st.set_page_config(
    page_title="Institutional Smart Money Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Bloomberg/TradingView Styling
st.markdown("""
<style>
    .reportview-container { background: #0D1117; }
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

# Session state setup
now_ist = datetime.datetime.now()
if "last_refresh_dt" not in st.session_state:
    st.session_state.last_refresh_dt = now_ist.strftime("%d-%b-%Y | %I:%M:%S %p IST")

# Master Stock Universe for Autocomplete
NSE_EQ_LIST = [
    "CANBK", "CASTROLIND", "COFORGE", "CONCORDBIO", "CUPID", 
    "ELECTCAST", "EMAMILTD", "GNFC", "IIFLCAPS", "INDHOTEL", 
    "KAJARIACER", "KSCL", "PNCINFRA", "SHREECEM", "STARHEALTH", 
    "TATAMOTORS", "VESUVIUS", "WESTLIFE", "WHIRLPOOL", "BEL", 
    "BAJAJHFL", "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"
]

# 1. RADAR MASTER DATA (Matching Your Excel Top_Accumulation_Radar)
RADAR_MASTER = [
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "STARHEALTH",
        "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 537.70, "BOS Trigger (₹)": 569.50, "Support / TSL (₹)": 513.00,
        "Target 1 (₹)": 595.00, "Target 2 (₹)": 625.00, "Target 3 (₹)": 660.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Headline: Star Health Share Price News: pullback support level pe hold kar raha hai",
        "Volume Spurt": "4.77x", "Recent Deliv %": "59.6%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "PNCINFRA",
        "Sector": "Construction", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 138.16, "BOS Trigger (₹)": 143.90, "Support / TSL (₹)": 116.40,
        "Target 1 (₹)": 152.00, "Target 2 (₹)": 162.00, "Target 3 (₹)": 175.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Brokerage houses se target upgrade & heavy buying pressure",
        "Volume Spurt": "3.77x", "Recent Deliv %": "45.4%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "SHREECEM",
        "Sector": "Construction Materials", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 21900.00, "BOS Trigger (₹)": 23000.00, "Support / TSL (₹)": 21355.00,
        "Target 1 (₹)": 24200.00, "Target 2 (₹)": 25500.00, "Target 3 (₹)": 27000.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Share price near low with mixed valuation, high accumulation",
        "Volume Spurt": "3.47x", "Recent Deliv %": "51.9%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "KAJARIACER",
        "Sector": "Consumer Durables", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 1225.10, "BOS Trigger (₹)": 1265.90, "Support / TSL (₹)": 1167.00,
        "Target 1 (₹)": 1315.00, "Target 2 (₹)": 1380.00, "Target 3 (₹)": 1450.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Fundamentals & sector valuation expansion",
        "Volume Spurt": "3.28x", "Recent Deliv %": "63.5%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "VESUVIUS",
        "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 404.10, "BOS Trigger (₹)": 453.80, "Support / TSL (₹)": 383.00,
        "Target 1 (₹)": 485.00, "Target 2 (₹)": 515.00, "Target 3 (₹)": 550.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "REG - American Century Inv Vesuvius plc Form 8.3 filing, heavy stake accumulation",
        "Volume Spurt": "2.55x", "Recent Deliv %": "48.9%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "INDHOTEL",
        "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 718.00, "BOS Trigger (₹)": 755.00, "Support / TSL (₹)": 704.60,
        "Target 1 (₹)": 790.00, "Target 2 (₹)": 825.00, "Target 3 (₹)": 860.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Share price rises 2.2%, valuation & sector rotation positive",
        "Volume Spurt": "2.49x", "Recent Deliv %": "60.6%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "ELECTCAST",
        "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 74.54, "BOS Trigger (₹)": 79.00, "Support / TSL (₹)": 70.10,
        "Target 1 (₹)": 84.00, "Target 2 (₹)": 89.00, "Target 3 (₹)": 96.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Brokerage houses se target upgrade & buy call",
        "Volume Spurt": "2.46x", "Recent Deliv %": "47.4%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "IIFLCAPS",
        "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 345.60, "BOS Trigger (₹)": 356.40, "Support / TSL (₹)": 335.05,
        "Target 1 (₹)": 375.00, "Target 2 (₹)": 395.00, "Target 3 (₹)": 420.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Institutional block deal / heavy stake accumulation",
        "Volume Spurt": "2.40x", "Recent Deliv %": "66.4%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "EMAMILTD",
        "Sector": "FMCG", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 372.65, "BOS Trigger (₹)": 407.65, "Support / TSL (₹)": 365.80,
        "Target 1 (₹)": 425.00, "Target 2 (₹)": 445.00, "Target 3 (₹)": 470.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Price rise, valuation support at lower levels",
        "Volume Spurt": "2.32x", "Recent Deliv %": "52.9%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "WESTLIFE",
        "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 588.05, "BOS Trigger (₹)": 612.00, "Support / TSL (₹)": 540.20,
        "Target 1 (₹)": 645.00, "Target 2 (₹)": 680.00, "Target 3 (₹)": 720.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Institutional block deal / heavy stake accumulation",
        "Volume Spurt": "2.18x", "Recent Deliv %": "49.9%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY", "Symbol": "CASTROLIND",
        "Sector": "Oil Gas & Fuels", "Sector Alignment": "☑️️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)",
        "Trade Action": "WATCHLIST", "CMP (₹)": 199.04, "BOS Trigger (₹)": 203.40, "Support / TSL (₹)": 187.05,
        "Target 1 (₹)": 215.00, "Target 2 (₹)": 226.00, "Target 3 (₹)": 240.00, "Trade Signal": "WAIT FOR BOS TRIGGER",
        "Hinglish News & Catalyst Remark": "Deserve a spot on your watchlist: Strong cash delivery",
        "Volume Spurt": "2.12x", "Recent Deliv %": "57.4%", "Bias": "Bullish"
    },
    {
        "Report Date": "01-Oct-2026", "Live Status": "🔴 CONFIRMED BREAKDOWN", "Symbol": "COHANCE",
        "Sector": "Healthcare", "Sector Alignment": "⚠️️ Outflow Aligned", "SMC Structure": "🔻 DISTRIBUTION BREAKDOWN",
        "Trade Action": "AVOID / SHORT", "CMP (₹)": 451.30, "BOS Trigger (₹)": 440.00, "Support / TSL (₹)": 465.00,
        "Target 1 (₹)": 430.00, "Target 2 (₹)": 415.00, "Target 3 (₹)": 395.00, "Trade Signal": "BEARISH STRUCTURE CHoCH",
        "Hinglish News & Catalyst Remark": "Volume Spurt khatam hua (Spurt 1.28x par gir gaya), Delivery percentage gir rahi hai",
        "Volume Spurt": "1.28x", "Recent Deliv %": "29.4%", "Bias": "Bearish"
    }
]

# 2. 6-FORTNIGHTS (3 MONTHS) SECTOR ROTATION DATA (Matching Sector_Rotation)
FORTNIGHT_SECTORS = [
    {"Sector": "Financial Services", "Latest 12D Share (%)": "29.01%", "Base Share (%)": "26.50%", "Flow Shift (%)": "+2.51%", "Flow Signal": "🟢 Heavy Inflow", "FN-1 (₹ Cr)": 4250, "FN-2 (₹ Cr)": 3100, "FN-3 (₹ Cr)": 2200, "FN-4 (₹ Cr)": 1850, "FN-5 (₹ Cr)": 1200, "FN-6 (₹ Cr)": 950},
    {"Sector": "Healthcare", "Latest 12D Share (%)": "8.13%", "Base Share (%)": "7.45%", "Flow Shift (%)": "+0.68%", "Flow Signal": "🟢 Heavy Inflow", "FN-1 (₹ Cr)": 1650, "FN-2 (₹ Cr)": 1400, "FN-3 (₹ Cr)": 1100, "FN-4 (₹ Cr)": 950, "FN-5 (₹ Cr)": 800, "FN-6 (₹ Cr)": 600},
    {"Sector": "Construction Materials", "Latest 12D Share (%)": "1.23%", "Base Share (%)": "1.14%", "Flow Shift (%)": "+0.09%", "Flow Signal": "🟢 Inflow", "FN-1 (₹ Cr)": 750, "FN-2 (₹ Cr)": 620, "FN-3 (₹ Cr)": 450, "FN-4 (₹ Cr)": 380, "FN-5 (₹ Cr)": 290, "FN-6 (₹ Cr)": 210},
    {"Sector": "Power", "Latest 12D Share (%)": "3.03%", "Base Share (%)": "2.97%", "Flow Shift (%)": "+0.06%", "Flow Signal": "🟢 Inflow", "FN-1 (₹ Cr)": 890, "FN-2 (₹ Cr)": 820, "FN-3 (₹ Cr)": 750, "FN-4 (₹ Cr)": 690, "FN-5 (₹ Cr)": 500, "FN-6 (₹ Cr)": 420},
    {"Sector": "Consumer Services", "Latest 12D Share (%)": "5.86%", "Base Share (%)": "5.81%", "Flow Shift (%)": "+0.05%", "Flow Signal": "🟢 Inflow", "FN-1 (₹ Cr)": 1200, "FN-2 (₹ Cr)": 1150, "FN-3 (₹ Cr)": 980, "FN-4 (₹ Cr)": 850, "FN-5 (₹ Cr)": 720, "FN-6 (₹ Cr)": 600},
    {"Sector": "Oil Gas & Consumable Fuels", "Latest 12D Share (%)": "4.74%", "Base Share (%)": "4.69%", "Flow Shift (%)": "+0.05%", "Flow Signal": "🟢 Inflow", "FN-1 (₹ Cr)": 950, "FN-2 (₹ Cr)": 900, "FN-3 (₹ Cr)": 820, "FN-4 (₹ Cr)": 790, "FN-5 (₹ Cr)": 650, "FN-6 (₹ Cr)": 500},
    {"Sector": "Construction", "Latest 12D Share (%)": "1.62%", "Base Share (%)": "1.59%", "Flow Shift (%)": "+0.03%", "Flow Signal": "🟢 Inflow", "FN-1 (₹ Cr)": 420, "FN-2 (₹ Cr)": 390, "FN-3 (₹ Cr)": 350, "FN-4 (₹ Cr)": 300, "FN-5 (₹ Cr)": 240, "FN-6 (₹ Cr)": 180},
    {"Sector": "Forest Materials", "Latest 12D Share (%)": "0.02%", "Base Share (%)": "0.02%", "Flow Shift (%)": "0.00%", "Flow Signal": "🟡 Outflow", "FN-1 (₹ Cr)": -15, "FN-2 (₹ Cr)": 5, "FN-3 (₹ Cr)": 10, "FN-4 (₹ Cr)": -8, "FN-5 (₹ Cr)": 12, "FN-6 (₹ Cr)": 20},
    {"Sector": "Diversified", "Latest 12D Share (%)": "0.01%", "Base Share (%)": "0.02%", "Flow Shift (%)": "-0.01%", "Flow Signal": "🟡 Outflow", "FN-1 (₹ Cr)": -45, "FN-2 (₹ Cr)": -30, "FN-3 (₹ Cr)": 15, "FN-4 (₹ Cr)": 20, "FN-5 (₹ Cr)": -10, "FN-6 (₹ Cr)": 5},
    {"Sector": "Textiles", "Latest 12D Share (%)": "0.38%", "Base Share (%)": "0.39%", "Flow Shift (%)": "-0.01%", "Flow Signal": "🟡 Outflow", "FN-1 (₹ Cr)": -85, "FN-2 (₹ Cr)": -60, "FN-3 (₹ Cr)": -20, "FN-4 (₹ Cr)": 40, "FN-5 (₹ Cr)": 50, "FN-6 (₹ Cr)": 80},
    {"Sector": "Media Entertainment & Publication", "Latest 12D Share (%)": "0.42%", "Base Share (%)": "0.45%", "Flow Shift (%)": "-0.03%", "Flow Signal": "🔴 Outflow", "FN-1 (₹ Cr)": -140, "FN-2 (₹ Cr)": -110, "FN-3 (₹ Cr)": -80, "FN-4 (₹ Cr)": -50, "FN-5 (₹ Cr)": 20, "FN-6 (₹ Cr)": 60},
    {"Sector": "Chemicals", "Latest 12D Share (%)": "2.50%", "Base Share (%)": "2.56%", "Flow Shift (%)": "-0.06%", "Flow Signal": "🔴 Outflow", "FN-1 (₹ Cr)": -520, "FN-2 (₹ Cr)": -410, "FN-3 (₹ Cr)": -290, "FN-4 (₹ Cr)": -150, "FN-5 (₹ Cr)": 100, "FN-6 (₹ Cr)": 220},
    {"Sector": "Utilities", "Latest 12D Share (%)": "0.12%", "Base Share (%)": "0.21%", "Flow Shift (%)": "-0.09%", "Flow Signal": "🔴 Outflow", "FN-1 (₹ Cr)": -260, "FN-2 (₹ Cr)": -210, "FN-3 (₹ Cr)": -150, "FN-4 (₹ Cr)": -80, "FN-5 (₹ Cr)": 40, "FN-6 (₹ Cr)": 90},
    {"Sector": "Telecommunication", "Latest 12D Share (%)": "2.88%", "Base Share (%)": "2.99%", "Flow Shift (%)": "-0.11%", "Flow Signal": "🔴 Outflow", "FN-1 (₹ Cr)": -890, "FN-2 (₹ Cr)": -750, "FN-3 (₹ Cr)": -540, "FN-4 (₹ Cr)": -320, "FN-5 (₹ Cr)": 150, "FN-6 (₹ Cr)": 300}
]

# 3. EXITED STOCKS LOG (Matching Your Excel Exited_Stocks_Log)
EXITED_STOCKS = [
    {"Symbol": "WHIRLPOOL", "Exit Date": "25-Sep-2026", "Current Price (₹)": 861.65, "Recent Return (%)": "+17.75%", "Last Spurt Ratio": "3.23x", "Hinglish Exit Reason": "🎯 Target Hit / Breakout Complete (+17.8% move aa gaya)"},
    {"Symbol": "GNFC", "Exit Date": "25-Sep-2026", "Current Price (₹)": 589.15, "Recent Return (%)": "+9.15%", "Last Spurt Ratio": "2.19x", "Hinglish Exit Reason": "⚠️ Delivery percentage threshold se niche chala gaya"},
    {"Symbol": "COHANCE", "Exit Date": "25-Sep-2026", "Current Price (₹)": 451.30, "Recent Return (%)": "+4.24%", "Last Spurt Ratio": "1.28x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.28x par gir gaya)"},
    {"Symbol": "KSCL", "Exit Date": "25-Sep-2026", "Current Price (₹)": 715.10, "Recent Return (%)": "+3.57%", "Last Spurt Ratio": "2.72x", "Hinglish Exit Reason": "⚠️ Delivery percentage threshold se niche chala gaya"},
    {"Symbol": "BANDHANBNK", "Exit Date": "25-Sep-2026", "Current Price (₹)": 176.00, "Recent Return (%)": "+2.03%", "Last Spurt Ratio": "1.25x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.25x par gir gaya)"},
    {"Symbol": "SAILIFE", "Exit Date": "25-Sep-2026", "Current Price (₹)": 1541.20, "Recent Return (%)": "+0.14%", "Last Spurt Ratio": "0.82x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 0.82x par gir gaya)"},
    {"Symbol": "KEI", "Exit Date": "25-Sep-2026", "Current Price (₹)": 4502.00, "Recent Return (%)": "-0.09%", "Last Spurt Ratio": "0.74x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 0.74x par gir gaya)"},
    {"Symbol": "SARDAEN", "Exit Date": "25-Sep-2026", "Current Price (₹)": 494.75, "Recent Return (%)": "-0.52%", "Last Spurt Ratio": "0.75x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 0.75x par gir gaya)"},
    {"Symbol": "GSFC", "Exit Date": "25-Sep-2026", "Current Price (₹)": 146.90, "Recent Return (%)": "-1.52%", "Last Spurt Ratio": "0.93x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 0.93x par gir gaya)"},
    {"Symbol": "BLACKBUCK", "Exit Date": "25-Sep-2026", "Current Price (₹)": 606.15, "Recent Return (%)": "-2.08%", "Last Spurt Ratio": "1.37x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.37x par gir gaya)"},
    {"Symbol": "UBL", "Exit Date": "25-Sep-2026", "Current Price (₹)": 1188.80, "Recent Return (%)": "-3.14%", "Last Spurt Ratio": "1.09x", "Hinglish Exit Reason": "📉 Volume Spurt khatam hua (Spurt 1.09x par gir gaya)"},
    {"Symbol": "CONCORDBIO", "Exit Date": "25-Sep-2026", "Current Price (₹)": 1374.10, "Recent Return (%)": "-5.48%", "Last Spurt Ratio": "1.03x", "Hinglish Exit Reason": "🛑 Support Broken / Structure Fail (-5.5% drawdown)"},
    {"Symbol": "ONESOURCE", "Exit Date": "25-Sep-2026", "Current Price (₹)": 1508.00, "Recent Return (%)": "-5.55%", "Last Spurt Ratio": "0.93x", "Hinglish Exit Reason": "🛑 Support Broken / Structure Fail (-5.5% drawdown)"},
    {"Symbol": "LICHSGFIN", "Exit Date": "25-Sep-2026", "Current Price (₹)": 509.00, "Recent Return (%)": "-6.26%", "Last Spurt Ratio": "1.24x", "Hinglish Exit Reason": "🛑 Support Broken / Structure Fail (-6.3% drawdown)"}
]

# MULTI-TRADE PORTFOLIO STORAGE
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

# Excel Generator (3 Sheets matching user workbook)
def create_excel_workbook():
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        pd.DataFrame(RADAR_MASTER).to_excel(writer, sheet_name='Top_Accumulation_Radar', index=False)
        pd.DataFrame(FORTNIGHT_SECTORS).to_excel(writer, sheet_name='Sector_Rotation', index=False)
        pd.DataFrame(EXITED_STOCKS).to_excel(writer, sheet_name='Exited_Stocks_Log', index=False)
    buffer.seek(0)
    return buffer

# SIDEBAR: Autocomplete Stock Search
st.sidebar.markdown("### ⚡ Terminal Core")
selected_stock = st.sidebar.selectbox(
    "🔍 Search Any NSE EQ Stock (Type letters)",
    options=["-- None (Terminal Overview) --"] + sorted(NSE_EQ_LIST),
    index=0
)
st.sidebar.markdown("---")

# Refresh details in Sidebar bottom
st.sidebar.markdown(f"**Last Sync Date & Time:**")
st.sidebar.info(f"🕒 {st.session_state.last_refresh_dt}")

# HEADER
col_title, col_actions = st.columns([3, 2])
with col_title:
    st.title("SMART MONEY SWING TERMINAL")
    st.caption(f"NSE Cash Segment (EQ) | Macro FPI Flow & Delivery Absorption | Last Refreshed: {st.session_state.last_refresh_dt}")

with col_actions:
    c_btn1, c_btn2 = st.columns([1, 1])
    with c_btn1:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.session_state.last_refresh_dt = datetime.datetime.now().strftime("%d-%b-%Y | %I:%M:%S %p IST")
            st.rerun()
    with c_btn2:
        excel_file = create_excel_workbook()
        st.download_button(
            label="📥 Download Excel (.xlsx)",
            data=excel_file,
            file_name=f"SmartMoney_Live_Dashboard_{datetime.date.today()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

# TOP METRICS
bullish_cnt = len([s for s in RADAR_MASTER if s.get("Bias") == "Bullish"])
bearish_cnt = len([s for s in RADAR_MASTER if s.get("Bias") == "Bearish"])
open_trades_cnt = len(st.session_state.trades)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Market Regime", "Bullish Markup", "Nifty Uptrend Intact")
m2.metric("Leading Sector", "Financial Services (+2.51%)", "Heavy Inflow Shift")
m3.metric("CHoCH Radar", f"{bullish_cnt} Bull / {bearish_cnt} Bear", "Absorption Breakouts")
m4.metric("Active Book", f"{open_trades_cnt} Open Swings", "Dynamic TSL Active")
st.markdown("---")

# DYNAMIC DIRECT STOCK DETAIL VIEW (If stock selected in search)
if selected_stock != "-- None (Terminal Overview) --":
    st.markdown(f"## 🔎 Deep Technical & Institutional Profile: **{selected_stock}**")
    
    # Check if stock exists in Radar for exact targets and remark
    radar_info = next((item for item in RADAR_MASTER if item["Symbol"] == selected_stock), None)
    
    try:
        ticker_obj = yf.Ticker(f"{selected_stock}.NS")
        hist = ticker_obj.history(period="3mo", interval="1d")
        
        if not hist.empty:
            cmp_price = round(hist['Close'].iloc[-1], 2)
            prev_price = round(hist['Close'].iloc[-2], 2) if len(hist) > 1 else cmp_price
            day_chg = round(((cmp_price - prev_price) / prev_price) * 100, 2)
            
            # Daily and Monthly accumulation amounts
            daily_vol = int(hist['Volume'].iloc[-1])
            avg_vol_20 = int(hist['Volume'].tail(20).mean())
            spurt_ratio = round(daily_vol / avg_vol_20, 2) if avg_vol_20 > 0 else 1.0
            daily_turnover_cr = round((daily_vol * cmp_price) / 10000000, 2)
            monthly_vol_cr = round((hist['Volume'].tail(22).sum() * cmp_price) / 10000000, 2)
            
            # Setup Levels
            bos_level = radar_info["BOS Trigger (₹)"] if radar_info else round(hist['High'].tail(15).max(), 2)
            support_sl = radar_info["Support / TSL (₹)"] if radar_info else round(hist['Low'].tail(15).min(), 2)
            t1 = radar_info["Target 1 (₹)"] if radar_info else round(bos_level * 1.05, 2)
            t2 = radar_info["Target 2 (₹)"] if radar_info else round(bos_level * 1.10, 2)
            t3 = radar_info["Target 3 (₹)"] if radar_info else round(bos_level * 1.18, 2)

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("CMP (NSE Cash)", f"₹{cmp_price}", f"{'+' if day_chg >= 0 else ''}{day_chg}% Today")
            k2.metric("Daily Volume Spurt", f"{spurt_ratio}x Avg", f"₹{daily_turnover_cr} Cr Daily")
            k3.metric("Monthly Accumulation", f"₹{monthly_vol_cr} Cr", "Past 22 Sessions")
            k4.metric("Support / Base SL", f"₹{support_sl}", "Risk Floor")
            k5.metric("BOS Trigger Level", f"₹{bos_level}", "15m Breakout Target")

            if radar_info:
                st.info(f"💡 **Trade Signal:** `{radar_info['Trade Signal']}` | **Catalyst Remark:** {radar_info['Hinglish News & Catalyst Remark']}")

            # Candle Chart with marked SL, BOS, T1, T2, T3
            fig = go.Figure(data=[go.Candlestick(
                x=hist.index,
                open=hist['Open'], high=hist['High'],
                low=hist['Low'], close=hist['Close'],
                name=selected_stock
            )])
            
            # Level Lines
            fig.add_hline(y=support_sl, line_dash="dot", line_color="#FF5252", annotation_text=f"Base SL (₹{support_sl})", annotation_position="bottom right")
            fig.add_hline(y=bos_level, line_dash="dash", line_color="#FFD600", annotation_text=f"BOS Trigger (₹{bos_level})", annotation_position="top right")
            fig.add_hline(y=t1, line_dash="dash", line_color="#00E676", annotation_text=f"Target 1 (₹{t1})", annotation_position="top right")
            fig.add_hline(y=t2, line_dash="dash", line_color="#00E676", annotation_text=f"Target 2 (₹{t2})", annotation_position="top right")
            fig.add_hline(y=t3, line_dash="dash", line_color="#00B0FF", annotation_text=f"Target 3 (₹{t3})", annotation_position="top right")

            fig.update_layout(template="plotly_dark", height=480, margin=dict(l=20, r=20, t=30, b=20), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("---")
        else:
            st.warning(f"Could not load data for {selected_stock}. Make sure it is actively traded on NSE.")
    except Exception as e:
        st.error(f"Error fetching live stock details: {e}")

# MAIN TABS (Deep Analytics Tab Removed as requested - Direct Search Replaces it)
tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 Institutional Accumulation Radar",
    "💼 Active Swing Portfolio",
    "🌐 6-Fortnights Sector Rotation",
    "📜 Exited Stocks Audit Log"
])

# TAB 1: RADAR WITH BULLISH & BEARISH FILTERS & 3 TARGETS
with tab1:
    st.subheader("🎯 Institutional Accumulation & SMC Breakout Radar")
    st.caption("Pure Delivery Spurt + Base Absorption + 15m BOS Trigger & 3 Targets")
    
    col_f1, col_f2 = st.columns([2, 4])
    with col_f1:
        setup_filter = st.radio("Display Setups:", ["All Setups", "Bullish Markup Only", "Bearish Breakdown Only"], horizontal=True)
    
    filtered_radar = RADAR_MASTER
    if setup_filter == "Bullish Markup Only":
        filtered_radar = [x for x in RADAR_MASTER if x.get("Bias") == "Bullish"]
    elif setup_filter == "Bearish Breakdown Only":
        filtered_radar = [x for x in RADAR_MASTER if x.get("Bias") == "Bearish"]

    st.dataframe(pd.DataFrame(filtered_radar), use_container_width=True, hide_index=True)

# TAB 2: MULTI-STOCK ACTIVE SWING PORTFOLIO & TRADE MANAGER
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
        
        # Trailing SL Logic
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
        with st.expander("➕ Add New Swing Trade Position"):
            with st.form("add_trade_form"):
                in_sym = st.selectbox("Stock Symbol", sorted(NSE_EQ_LIST))
                in_sec = st.text_input("Sector", value="NSE Cash EQ")
                in_entry = st.number_input("Entry Price (₹)", min_value=1.0, value=100.0, step=0.5)
                in_sl = st.number_input("Stop Loss (₹)", min_value=1.0, value=95.0, step=0.5)
                in_t1 = st.number_input("Target 1 (₹)", min_value=1.0, value=106.0, step=0.5)
                in_t2 = st.number_input("Target 2 (₹)", min_value=1.0, value=112.0, step=0.5)
                in_t3 = st.number_input("Target 3 (₹)", min_value=1.0, value=120.0, step=0.5)
                add_sub = st.form_submit_button("Confirm Entry")
                if add_sub and in_sym:
                    st.session_state.trades.append({
                        "Ticker": in_sym, "Sector": in_sec, "Entry": float(in_entry),
                        "SL": float(in_sl), "Target 1": float(in_t1), "Target 2": float(in_t2),
                        "Target 3": float(in_t3), "Date": str(datetime.date.today())
                    })
                    save_trades(st.session_state.trades)
                    st.success(f"{in_sym} added to active portfolio!")
                    st.rerun()

    with c_del:
        with st.expander("🗑️ Close / Exit Position"):
            trade_names = [t["Ticker"] for t in st.session_state.trades]
            if trade_names:
                sel_close = st.selectbox("Select Trade to Close", trade_names)
                if st.button("Close Position Now", type="primary"):
                    st.session_state.trades = [t for t in st.session_state.trades if t["Ticker"] != sel_close]
                    save_trades(st.session_state.trades)
                    st.success(f"Position {sel_close} closed!")
                    st.rerun()

# TAB 3: 3 MONTHS (6 FORTNIGHTS) SECTOR ROTATION
with tab3:
    st.subheader("🌐 NSE Institutional Capital Flow & Sector Rotation")
    st.caption("Complete 3-Month View (6 Consecutive Fortnights Trend Analysis)")
    
    sec_df = pd.DataFrame(FORTNIGHT_SECTORS)
    st.dataframe(sec_df, use_container_width=True, hide_index=True)

# TAB 4: EXITED STOCKS AUDIT LOG
with tab4:
    st.subheader("📜 Removed / Exited Stocks Audit Log")
    st.caption("Last 1-Week Analysis & Hinglish Rationale")
    
    exit_df = pd.DataFrame(EXITED_STOCKS)
    st.dataframe(exit_df, use_container_width=True, hide_index=True)
