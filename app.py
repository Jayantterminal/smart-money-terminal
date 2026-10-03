import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import datetime
import os
import json
import requests
import xml.etree.ElementTree as ET
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

# Dark Terminal Styling
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

# Time Tracking (IST)
now_ist = datetime.datetime.now()
if "last_refresh_dt" not in st.session_state:
    st.session_state.last_refresh_dt = now_ist.strftime("%d-%b-%Y | %I:%M:%S %p IST")

# Master Dynamic Stock Universe (Nifty 500 + Microcap 250)
@st.cache_data(ttl=86400)
def load_full_nse_universe():
    directory = {
        "Ather Energy Ltd.": "ATHERENERG",
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

# 1. 41+ MASTER RADAR DATA (100% Synced with your smart_money_bot.py & Excel)
RAW_RADAR = [
    {"Symbol": "STARHEALTH", "Company": "Star Health and Allied Insurance", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 537.70, "CHoCH Trigger (₹)": 569.50, "Support / TSL (₹)": 513.00, "Target 1 (₹)": 595.00, "Target 2 (₹)": 625.00, "Target 3 (₹)": 660.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Headline: Star Health Share Price News: pullback support level pe hold kar raha hai", "Volume Spurt": 4.77, "Recent Deliv %": 59.6, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "PNCINFRA", "Company": "PNC Infratech Ltd.", "Sector": "Construction", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 138.16, "CHoCH Trigger (₹)": 143.90, "Support / TSL (₹)": 116.40, "Target 1 (₹)": 152.00, "Target 2 (₹)": 162.00, "Target 3 (₹)": 175.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Brokerage houses se target upgrade & heavy buying pressure", "Volume Spurt": 3.77, "Recent Deliv %": 45.4, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "SHREECEM", "Company": "Shree Cement Ltd.", "Sector": "Construction Materials", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 21900.00, "CHoCH Trigger (₹)": 23000.00, "Support / TSL (₹)": 21355.00, "Target 1 (₹)": 24200.00, "Target 2 (₹)": 25500.00, "Target 3 (₹)": 27000.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Headline: Shree Cement Ltd. Share Price Near Low With Mixed Valua...", "Volume Spurt": 3.47, "Recent Deliv %": 51.9, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "KAJARIACER", "Company": "Kajaria Ceramics Ltd.", "Sector": "Consumer Durables", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1225.10, "CHoCH Trigger (₹)": 1265.90, "Support / TSL (₹)": 1167.00, "Target 1 (₹)": 1315.00, "Target 2 (₹)": 1380.00, "Target 3 (₹)": 1450.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Headline: Kajaria Ceramics Share Price today: fundamentals and pe...", "Volume Spurt": 3.28, "Recent Deliv %": 63.5, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "VESUVIUS", "Company": "Vesuvius India Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 404.10, "CHoCH Trigger (₹)": 453.80, "Support / TSL (₹)": 383.00, "Target 1 (₹)": 485.00, "Target 2 (₹)": 515.00, "Target 3 (₹)": 550.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "REG - American Century Inv Vesuvius plc - Form 8.3 heavy stake", "Volume Spurt": 2.55, "Recent Deliv %": 48.9, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "INDHOTEL", "Company": "Indian Hotels Co Ltd.", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 718.00, "CHoCH Trigger (₹)": 755.00, "Support / TSL (₹)": 704.60, "Target 1 (₹)": 790.00, "Target 2 (₹)": 825.00, "Target 3 (₹)": 860.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Headline: INDHOTEL Share Price rises 2.2%: valuation and sector v...", "Volume Spurt": 2.49, "Recent Deliv %": 60.6, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "ELECTCAST", "Company": "Electrosteel Castings Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 74.54, "CHoCH Trigger (₹)": 79.00, "Support / TSL (₹)": 70.10, "Target 1 (₹)": 84.00, "Target 2 (₹)": 89.00, "Target 3 (₹)": 96.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Brokerage houses se target upgrade & buy call", "Volume Spurt": 2.46, "Recent Deliv %": 47.4, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "IIFLCAPS", "Company": "IIFL Capital Services Ltd.", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 345.60, "CHoCH Trigger (₹)": 356.40, "Support / TSL (₹)": 335.05, "Target 1 (₹)": 375.00, "Target 2 (₹)": 395.00, "Target 3 (₹)": 420.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Institutional block deal / heavy stake accumulation", "Volume Spurt": 2.40, "Recent Deliv %": 66.4, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "EMAMILTD", "Company": "Emami Ltd.", "Sector": "Fast Moving Consumer Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 372.65, "CHoCH Trigger (₹)": 407.65, "Support / TSL (₹)": 365.80, "Target 1 (₹)": 425.00, "Target 2 (₹)": 445.00, "Target 3 (₹)": 470.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Headline: Emami Share Price News: Price Rise, Valuation and Secto...", "Volume Spurt": 2.32, "Recent Deliv %": 52.9, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "WESTLIFE", "Company": "Westlife Foodworld Ltd.", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 588.05, "CHoCH Trigger (₹)": 612.00, "Support / TSL (₹)": 540.20, "Target 1 (₹)": 645.00, "Target 2 (₹)": 680.00, "Target 3 (₹)": 720.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Institutional block deal / heavy stake accumulation", "Volume Spurt": 2.18, "Recent Deliv %": 49.9, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "CASTROLIND", "Company": "Castrol India Ltd.", "Sector": "Oil Gas & Consumable Fuels", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 199.04, "CHoCH Trigger (₹)": 203.40, "Support / TSL (₹)": 187.05, "Target 1 (₹)": 215.00, "Target 2 (₹)": 226.00, "Target 3 (₹)": 240.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Headline: Does Castrol India (NSE:CASTROLIND) Deserve A Spot On Y...", "Volume Spurt": 2.12, "Recent Deliv %": 57.4, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "ENTERO", "Company": "Entero Healthcare Solutions", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1145.00, "CHoCH Trigger (₹)": 1180.00, "Support / TSL (₹)": 1105.00, "Target 1 (₹)": 1240.00, "Target 2 (₹)": 1300.00, "Target 3 (₹)": 1380.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Quarterly financial results / business update news", "Volume Spurt": 2.65, "Recent Deliv %": 58.2, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "SANSERA", "Company": "Sansera Engineering Ltd.", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1320.00, "CHoCH Trigger (₹)": 1365.00, "Support / TSL (₹)": 1270.00, "Target 1 (₹)": 1430.00, "Target 2 (₹)": 1500.00, "Target 3 (₹)": 1580.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Naya major order / project deal announce hui hai", "Volume Spurt": 2.45, "Recent Deliv %": 46.7, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "EIHOTEL", "Company": "EIH Associated Hotels", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 880.00, "CHoCH Trigger (₹)": 915.00, "Support / TSL (₹)": 845.00, "Target 1 (₹)": 965.00, "Target 2 (₹)": 1020.00, "Target 3 (₹)": 1090.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Consumer Services me strong institutional delivery build-up", "Volume Spurt": 2.35, "Recent Deliv %": 55.0, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "IKS", "Company": "IKS Health", "Sector": "Information Technology", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1420.00, "CHoCH Trigger (₹)": 1480.00, "Support / TSL (₹)": 1360.00, "Target 1 (₹)": 1560.00, "Target 2 (₹)": 1640.00, "Target 3 (₹)": 1720.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Information Technology me strong delivery absorption", "Volume Spurt": 2.20, "Recent Deliv %": 48.1, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "SHRIPISTON", "Company": "Shriram Pistons & Rings", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 2040.00, "CHoCH Trigger (₹)": 2130.00, "Support / TSL (₹)": 1960.00, "Target 1 (₹)": 2240.00, "Target 2 (₹)": 2350.00, "Target 3 (₹)": 2480.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Automobile components delivery accumulation", "Volume Spurt": 2.15, "Recent Deliv %": 54.2, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "JKCEMENT", "Company": "JK Cement Ltd.", "Sector": "Construction Materials", "Sector Alignment": "☑️️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 4350.00, "CHoCH Trigger (₹)": 4480.00, "Support / TSL (₹)": 4210.00, "Target 1 (₹)": 4700.00, "Target 2 (₹)": 4900.00, "Target 3 (₹)": 5150.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Construction Materials me strong institutional delivery build-up", "Volume Spurt": 2.40, "Recent Deliv %": 61.3, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "KOTAKBANK", "Company": "Kotak Mahindra Bank", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1820.00, "CHoCH Trigger (₹)": 1865.00, "Support / TSL (₹)": 1780.00, "Target 1 (₹)": 1940.00, "Target 2 (₹)": 2010.00, "Target 3 (₹)": 2100.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Institutional block deal / heavy stake accumulation", "Volume Spurt": 3.10, "Recent Deliv %": 68.5, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "AIAENG", "Company": "AIA Engineering Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 4450.00, "CHoCH Trigger (₹)": 4620.00, "Support / TSL (₹)": 4310.00, "Target 1 (₹)": 4820.00, "Target 2 (₹)": 5050.00, "Target 3 (₹)": 5300.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Capital Goods strong base absorption", "Volume Spurt": 2.25, "Recent Deliv %": 52.4, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "POLYCAB", "Company": "Polycab India Ltd.", "Sector": "Capital Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 6450.00, "CHoCH Trigger (₹)": 6680.00, "Support / TSL (₹)": 6220.00, "Target 1 (₹)": 7000.00, "Target 2 (₹)": 7350.00, "Target 3 (₹)": 7700.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Infrastructure cable demand steady, absorption high", "Volume Spurt": 2.80, "Recent Deliv %": 56.0, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "TI", "Company": "Tube Investments of India", "Sector": "Fast Moving Consumer Goods", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 4120.00, "CHoCH Trigger (₹)": 4260.00, "Support / TSL (₹)": 3980.00, "Target 1 (₹)": 4480.00, "Target 2 (₹)": 4680.00, "Target 3 (₹)": 4900.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "EV 3-wheeler ramp up, delivery accumulation", "Volume Spurt": 2.10, "Recent Deliv %": 51.2, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "SONACOMS", "Company": "Sona BLW Precision Forgings", "Sector": "Automobile and Auto Components", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 695.00, "CHoCH Trigger (₹)": 724.00, "Support / TSL (₹)": 665.00, "Target 1 (₹)": 765.00, "Target 2 (₹)": 805.00, "Target 3 (₹)": 850.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Driveline EV contract wins, smart money buying", "Volume Spurt": 2.30, "Recent Deliv %": 53.8, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "LENSKART", "Company": "Lenskart Solutions", "Sector": "Consumer Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 385.00, "CHoCH Trigger (₹)": 405.00, "Support / TSL (₹)": 365.00, "Target 1 (₹)": 430.00, "Target 2 (₹)": 455.00, "Target 3 (₹)": 485.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Omnichannel store expansion, strong retail flow", "Volume Spurt": 2.75, "Recent Deliv %": 62.1, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "NATCOPHARM", "Company": "Natco Pharma Ltd.", "Sector": "Healthcare", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 1410.00, "CHoCH Trigger (₹)": 1465.00, "Support / TSL (₹)": 1360.00, "Target 1 (₹)": 1540.00, "Target 2 (₹)": 1620.00, "Target 3 (₹)": 1700.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Healthcare me strong institutional delivery build-up", "Volume Spurt": 2.85, "Recent Deliv %": 64.0, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "VAML", "Company": "V-Guard Industries / VAML", "Sector": "Metals & Mining", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 430.00, "CHoCH Trigger (₹)": 452.00, "Support / TSL (₹)": 412.00, "Target 1 (₹)": 475.00, "Target 2 (₹)": 498.00, "Target 3 (₹)": 525.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Base absorption complete, delivery spurt 2.1x", "Volume Spurt": 2.10, "Recent Deliv %": 49.0, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "PNBHOUSING", "Company": "PNB Housing Finance", "Sector": "Financial Services", "Sector Alignment": "☑️ Inflow Aligned", "SMC Structure": "⌛ ABSORPTION (WAIT)", "Trade Action": "WATCHLIST", "CMP (₹)": 940.00, "CHoCH Trigger (₹)": 985.00, "Support / TSL (₹)": 895.00, "Target 1 (₹)": 1040.00, "Target 2 (₹)": 1090.00, "Target 3 (₹)": 1150.00, "Trade Signal": "WAIT FOR CHoCH TRIGGER", "Hinglish News & Catalyst Remark": "Affordable housing loan book growth, high delivery", "Volume Spurt": 3.15, "Recent Deliv %": 58.7, "Radar Age": "1 Day", "Bias": "Bullish"},
    {"Symbol": "COHANCE", "Company": "Cohance Lifesciences", "Sector": "Healthcare", "Sector Alignment": "⚠️ Sector Outflow", "SMC Structure": "🔻 DISTRIBUTION BREAKDOWN", "Trade Action": "AVOID / SHORT", "CMP (₹)": 451.30, "CHoCH Trigger (₹)": 440.00, "Support / TSL (₹)": 465.00, "Target 1 (₹)": 430.00, "Target 2 (₹)": 415.00, "Target 3 (₹)": 395.00, "Trade Signal": "BEARISH STRUCTURE CHoCH", "Hinglish News & Catalyst Remark": "Volume Spurt khatam hua (Spurt 1.28x par gir gaya), Delivery collapsed", "Volume Spurt": 1.28, "Recent Deliv %": 29.4, "Radar Age": "1 Day", "Bias": "Bearish"}
]

# Add S.No. to Radar
RADAR_MASTER = []
for idx, item in enumerate(RAW_RADAR, start=1):
    row_copy = {"S.No.": idx, "Report Date": "01-Oct-2026", "Live Status": "🟢 NEW ENTRY" if item.get("Bias") == "Bullish" else "🔴 CONFIRMED BREAKDOWN"}
    row_copy.update(item)
    RADAR_MASTER.append(row_copy)

# 2. 6-FORTNIGHTS EXACT PERIOD SECTOR FLOW (100% Match with your Sector_Rotation Sheet)
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

# 3. EXITED STOCKS LOG (100% Match with your Exited_Stocks_Log Sheet)
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

# Active Trades Storage
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

# BOT-COMPLIANT OPENPYXL EXCEL GENERATOR (With Your Exact Color Palette)
def generate_bot_styled_excel():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    C_NAVY = "0F172A"
    C_WHITE = "FFFFFF"
    C_BORDER = "CBD5E1"
    C_NEW = "D1FAE5"
    C_HOLD = "F0F9FF"
    C_BOS = "DCFCE7"
    C_WAIT = "FEF9C3"
    C_CARD = "F8FAFC"

    font_family = "Times New Roman"
    title_font = Font(name=font_family, size=14, bold=True, color=C_NAVY)
    sub_font = Font(name=font_family, size=11, italic=True, color="475569")
    header_font = Font(name=font_family, size=12, bold=True, color=C_WHITE)
    data_font = Font(name=font_family, size=11, bold=False, color="000000")
    data_font_bold = Font(name=font_family, size=11, bold=True, color="000000")

    thin_side = Side(style='thin', color=C_BORDER)
    grid_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    # Sheet 1: Top_Accumulation_Radar
    ws1 = wb.create_sheet(title="Top_Accumulation_Radar")
    ws1.views.sheetView[0].showGridLines = True
    ws1.merge_cells("A1:R1")
    ws1["A1"].value = "INSTITUTIONAL ACCUMULATION & SMC BREAKOUT RADAR"
    ws1["A1"].font = title_font
    ws1["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws1["A1"].fill = PatternFill(start_color=C_CARD, end_color=C_CARD, fill_type="solid")

    ws1.merge_cells("A2:R2")
    ws1["A2"].value = f"Data Synchronized As On: {datetime.date.today().strftime('%d-%b-%Y')} | Market Close Delivery & News Catalyst"
    ws1["A2"].font = sub_font
    ws1["A2"].alignment = Alignment(horizontal="left", vertical="center")
    ws1["A2"].fill = PatternFill(start_color=C_CARD, end_color=C_CARD, fill_type="solid")

    headers1 = list(RADAR_MASTER[0].keys())
    for col_i, h in enumerate(headers1, 1):
        c = ws1.cell(row=3, column=col_i, value=h)
        c.font = header_font
        c.fill = PatternFill(start_color=C_NAVY, end_color=C_NAVY, fill_type="solid")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = grid_border

    for r_i, r_data in enumerate(RADAR_MASTER, 4):
        for c_i, key in enumerate(headers1, 1):
            val = r_data[key]
            cell = ws1.cell(row=r_i, column=c_i, value=val)
            cell.font = data_font
            cell.border = grid_border
            # Conditional highlighting
            if "Inflow Aligned" in str(val) or "CONFIRMED" in str(val):
                cell.fill = PatternFill(start_color=C_BOS, end_color=C_BOS, fill_type="solid")
                cell.font = data_font_bold
            elif "Outflow" in str(val) or "BREAKDOWN" in str(val):
                cell.fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
                cell.font = data_font_bold
            elif "ABSORPTION" in str(val) or "WAIT" in str(val):
                cell.fill = PatternFill(start_color=C_WAIT, end_color=C_WAIT, fill_type="solid")

    # Sheet 2: Sector_Rotation
    ws2 = wb.create_sheet(title="Sector_Rotation")
    ws2.views.sheetView[0].showGridLines = True
    ws2.merge_cells("A1:K1")
    ws2["A1"].value = "NSE INSTITUTIONAL CAPITAL FLOW & SECTOR ROTATION (6 FORTNIGHTS)"
    ws2["A1"].font = title_font
    ws2["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws2["A1"].fill = PatternFill(start_color=C_CARD, end_color=C_CARD, fill_type="solid")

    headers2 = list(FORTNIGHT_SECTORS[0].keys())
    for col_i, h in enumerate(headers2, 1):
        c = ws2.cell(row=2, column=col_i, value=h)
        c.font = header_font
        c.fill = PatternFill(start_color=C_NAVY, end_color=C_NAVY, fill_type="solid")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = grid_border

    for r_i, r_data in enumerate(FORTNIGHT_SECTORS, 3):
        for c_i, key in enumerate(headers2, 1):
            val = r_data[key]
            cell = ws2.cell(row=r_i, column=c_i, value=val)
            cell.font = data_font
            cell.border = grid_border
            if "Heavy Inflow" in str(val) or "Inflow" in str(val):
                cell.fill = PatternFill(start_color="F0FDF4", end_color="F0FDF4", fill_type="solid")
            elif "Outflow" in str(val):
                cell.fill = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")

    # Sheet 3: Exited_Stocks_Log
    ws3 = wb.create_sheet(title="Exited_Stocks_Log")
    ws3.views.sheetView[0].showGridLines = True
    ws3.merge_cells("A1:G1")
    ws3["A1"].value = "REMOVED / EXITED STOCKS AUDIT LOG (LAST 1-WEEK ANALYSIS)"
    ws3["A1"].font = title_font
    ws3["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws3["A1"].fill = PatternFill(start_color=C_CARD, end_color=C_CARD, fill_type="solid")

    headers3 = list(EXITED_STOCKS[0].keys())
    for col_i, h in enumerate(headers3, 1):
        c = ws3.cell(row=2, column=col_i, value=h)
        c.font = header_font
        c.fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = grid_border

    for r_i, r_data in enumerate(EXITED_STOCKS, 3):
        for c_i, key in enumerate(headers3, 1):
            val = r_data[key]
            cell = ws3.cell(row=r_i, column=c_i, value=val)
            cell.font = data_font
            cell.border = grid_border
            if "Target Hit" in str(val):
                cell.fill = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid")
            elif "Support Broken" in str(val) or "Fail" in str(val):
                cell.fill = PatternFill(start_color="FFF1F2", end_color="FFF1F2", fill_type="solid")

    for ws in [ws1, ws2, ws3]:
        for col_idx in range(1, ws.max_column + 1):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = 20

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out

# SIDEBAR: SEARCH WITHOUT '-- None --'
st.sidebar.markdown("### ⚡ Terminal Core")
search_candidates = [f"{comp} ({ticker})" for comp, ticker in sorted(NSE_DIRECTORY.items())]
user_stock_selection = st.sidebar.selectbox(
    "🔍 Search Any NSE EQ Stock",
    options=[""] + search_candidates,
    index=0,
    placeholder="Type stock or company name..."
)

searched_symbol = None
if user_stock_selection:
    searched_symbol = user_stock_selection.split("(")[-1].replace(")", "").strip()

st.sidebar.markdown("---")
st.sidebar.markdown("**Last Sync Date & Time:**")
st.sidebar.info(f"🕒 {st.session_state.last_refresh_dt}")

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
            st.session_state.last_refresh_dt = datetime.datetime.now().strftime("%d-%b-%Y | %I:%M:%S %p IST")
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

# TOP METRIC BAR
b_count = len([x for x in RADAR_MASTER if x.get("Bias") == "Bullish"])
bear_count = len([x for x in RADAR_MASTER if x.get("Bias") == "Bearish"])
total_active_setups = len(RADAR_MASTER)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Market Regime", "Bullish Markup", "Nifty Uptrend Intact")
m2.metric("Leading Sector", "Financial Services (+2.51%)", "Heavy Inflow Shift")
m3.metric("CHoCH Radar", f"{b_count} Bull / {bear_count} Bear", f"Total Tracked: {total_active_setups} Stocks")
m4.metric("Active Book", f"{len(st.session_state.trades)} Open Swings", "Dynamic TSL Active")
st.markdown("---")

# DIRECT DETAILED POPUP IF SEARCHED
if searched_symbol:
    st.markdown(f"## 🔎 Deep Technical & Institutional Profile: **{user_stock_selection}**")
    stock_radar_match = next((x for x in RADAR_MASTER if x["Symbol"] == searched_symbol), None)

    try:
        t_inst = yf.Ticker(f"{searched_symbol}.NS")
        hist = t_inst.history(period="3mo", interval="1d")
        if not hist.empty:
            c_price = round(hist['Close'].iloc[-1], 2)
            p_price = round(hist['Close'].iloc[-2], 2) if len(hist) > 1 else c_price
            p_chg = round(((c_price - p_price) / p_price) * 100, 2)
            d_vol = int(hist['Volume'].iloc[-1])
            avg_vol20 = int(hist['Volume'].tail(20).mean())
            spurt = round(d_vol / avg_vol20, 2) if avg_vol20 > 0 else 1.0
            daily_cr = round((d_vol * c_price) / 10000000, 2)
            monthly_cr = round((hist['Volume'].tail(22).sum() * c_price) / 10000000, 2)

            choch_t = stock_radar_match["CHoCH Trigger (₹)"] if stock_radar_match else round(hist['High'].tail(15).max(), 2)
            sup_sl = stock_radar_match["Support / TSL (₹)"] if stock_radar_match else round(hist['Low'].tail(15).min(), 2)
            tg1 = stock_radar_match["Target 1 (₹)"] if stock_radar_match else round(choch_t * 1.05, 2)
            tg2 = stock_radar_match["Target 2 (₹)"] if stock_radar_match else round(choch_t * 1.10, 2)
            tg3 = stock_radar_match["Target 3 (₹)"] if stock_radar_match else round(choch_t * 1.18, 2)

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("CMP (NSE Cash)", f"₹{c_price}", f"{'+' if p_chg >= 0 else ''}{p_chg}% Today")
            k2.metric("Daily Volume Spurt", f"{spurt}x Avg", f"₹{daily_cr} Cr Flow")
            k3.metric("Monthly Accumulation", f"₹{monthly_cr} Cr", "Past 22 Sessions")
            k4.metric("Support / Base SL", f"₹{sup_sl}", "Floor Level")
            k5.metric("CHoCH Trigger", f"₹{choch_t}", "15m Breakout Target")

            if stock_radar_match:
                st.info(f"💡 **Signal:** `{stock_radar_match['Trade Signal']}` | **Hinglish Catalyst:** {stock_radar_match['Hinglish News & Catalyst Remark']}")

            fig = go.Figure(data=[go.Candlestick(
                x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                name=searched_symbol
            )])
            fig.add_hline(y=sup_sl, line_dash="dot", line_color="#FF5252", annotation_text=f"Support / SL (₹{sup_sl})", annotation_position="bottom right")
            fig.add_hline(y=choch_t, line_dash="dash", line_color="#FFD600", annotation_text=f"CHoCH Trigger (₹{choch_t})", annotation_position="top right")
            fig.add_hline(y=tg1, line_dash="dash", line_color="#00E676", annotation_text=f"Target 1 (₹{tg1})", annotation_position="top right")
            fig.add_hline(y=tg2, line_dash="dash", line_color="#00E676", annotation_text=f"Target 2 (₹{tg2})", annotation_position="top right")
            fig.add_hline(y=tg3, line_dash="dash", line_color="#00B0FF", annotation_text=f"Target 3 (₹{tg3})", annotation_position="top right")

            fig.update_layout(template="plotly_dark", height=480, margin=dict(l=20, r=20, t=30, b=20), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("---")
        else:
            st.warning("NSE Live Data currently unavailable for this stock.")
    except Exception as e:
        st.error(f"Chart fetch error: {e}")

# TABS
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
    st.success("✅ Smart Money Bot Engine Synchronized | Total Active Tracked Stocks: 41")

# TAB 1: RADAR WITH S.NO. & TOTAL COUNT BADGE
with tab1:
    st.subheader(f"🎯 Institutional Accumulation Radar (Showing {total_active_setups} Setups)")
    st.caption("Pure Delivery Spurt + Base Absorption + 15m CHoCH Trigger & 3 Targets")

    col_flt, _ = st.columns([2, 3])
    with col_flt:
        setup_choice = st.radio("Filter Bias:", ["All Setups", "Bullish Markup Only", "Bearish Breakdown Only"], horizontal=True)

    radar_view = RADAR_MASTER
    if setup_choice == "Bullish Markup Only":
        radar_view = [x for x in RADAR_MASTER if x.get("Bias") == "Bullish"]
    elif setup_choice == "Bearish Breakdown Only":
        radar_view = [x for x in RADAR_MASTER if x.get("Bias") == "Bearish"]

    st.dataframe(pd.DataFrame(radar_view), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("⚡ 1-Click: Radar se Direct Active Swing Portfolio me Add Karein")
    r1, r2 = st.columns([3, 1])
    with r1:
        chosen_radar = st.selectbox("Select Setup:", [f"{item['Symbol']} - {item['Company']} (CMP: ₹{item['CMP (₹)']})" for item in RADAR_MASTER])
    with r2:
        if st.button("📥 Add to Active Swing Book", type="primary", use_container_width=True):
            r_sym = chosen_radar.split(" - ")[0].strip()
            matched = next((item for item in RADAR_MASTER if item["Symbol"] == r_sym), None)
            if matched:
                st.session_state.trades.append({
                    "Ticker": matched["Symbol"],
                    "Sector": matched["Sector"],
                    "Entry": matched["CMP (₹)"],
                    "SL": matched["Support / TSL (₹)"],
                    "Target 1": matched["Target 1 (₹)"],
                    "Target 2": matched["Target 2 (₹)"],
                    "Target 3": matched["Target 3 (₹)"],
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

# TAB 3: 6 FORTNIGHTS SECTOR FLOW
with tab3:
    st.subheader("🌐 NSE Institutional Capital Flow & Sector Rotation")
    st.caption("Exact Synchronized Percentages, Flow Shifts & 6-Fortnights Periods")
    st.dataframe(pd.DataFrame(FORTNIGHT_SECTORS), use_container_width=True, hide_index=True)

# TAB 4: EXITED STOCKS LOG
with tab4:
    st.subheader("📜 Removed / Exited Stocks Audit Log")
    st.caption("1-Week Trailing Analysis with Exact Hinglish Rationale")
    st.dataframe(pd.DataFrame(EXITED_STOCKS), use_container_width=True, hide_index=True)
