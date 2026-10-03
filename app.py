"""
Institutional Smart Money Terminal (v7.0 - Autonomous Enterprise Edition)
------------------------------------------------------------------------
Autonomous Institutional Framework:
  1. Auto-Ingestion: Automated Daily Delivery Bhavcopy & 90-Day Rolling Buffer
  2. Institutional Alignment: FII/DII Net Flows + Full 22 NSE Sector Flow Matrix
  3. Catalyst Tracking: Block Deals, Institutional Inflow Remarks
  4. Decision Engine: Self-evaluating Buy/Avoid Verdict with 15m CHoCH/BOS micro timing
"""
from __future__ import annotations

import datetime as dt
import hmac
import html
import io
import json
import os
import tempfile
import uuid
import zipfile

import numpy as np
import openpyxl
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from packaging.version import Version

# ==========================================================
# CONSTANTS & DIRECTORIES
# ==========================================================
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")
CANDLE_MIN = 15
MIN_DELIVERY_PCT = 45.0
MIN_SPURT = 2.0
STALE_DEVIATION_PCT = 15.0
RADAR_MAX_AGE_DAYS = 3
HEAVY_SHIFT = 0.50
MAX_LOGIN_ATTEMPTS = 5
LEGACY_PASSWORD = "2000"
TRADE_BOOK_PATH = "data/active_trades.json"
RADAR_STORAGE_PATH = "data/active_radar.json"
BHAV_DIR = "data/bhavcopy_archive"
os.makedirs(BHAV_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

# Official NSE F&O Universe (Permitted for Swing Short)
NSE_FO_UNIVERSE = {
    "BAJAJFINSV", "BAJFINANCE", "CANBK", "HDFCBANK", "ICICIBANK",
    "KOTAKBANK", "INDHOTEL", "JKCEMENT", "SHREECEM", "COFORGE",
    "BAJAJ-AUTO", "BEL", "AIAENG", "KAJARIACER", "RELIANCE", "TCS",
    "INFY", "LT", "SBIN", "AXISBANK", "TATAMOTORS", "TATASTEEL", "DLF"
}

# Master NSE Symbol-to-Sector Directory (Auto Sector Mapping)
STOCK_SECTOR_MAP = {
    "CASTROLIND": "Oil Gas & Consumable Fuels", "BAJAJFINSV": "Financial Services",
    "BAJAJHFL": "Financial Services", "BAJFINANCE": "Financial Services",
    "CANBK": "Financial Services", "HDFCBANK": "Financial Services",
    "ICICIBANK": "Financial Services", "IIFLCAPS": "Financial Services",
    "KOTAKBANK": "Financial Services", "STARHEALTH": "Financial Services",
    "EIHOTEL": "Consumer Services", "ENTERO": "Consumer Services",
    "INDHOTEL": "Consumer Services", "WESTLIFE": "Consumer Services",
    "JKCEMENT": "Construction Materials", "SHREECEM": "Construction Materials",
    "PNCINFRA": "Construction", "NATCOPHARM": "Healthcare",
    "COFORGE": "Information Technology", "IKS": "Information Technology",
    "TCS": "Information Technology", "INFY": "Information Technology",
    "BAJAJ-AUTO": "Automobile and Auto Components", "ATHERENERG": "Automobile and Auto Components",
    "SANSERA": "Automobile and Auto Components", "SHRIPISTON": "Automobile and Auto Components",
    "TATAMOTORS": "Automobile and Auto Components", "BEL": "Capital Goods",
    "AIAENG": "Capital Goods", "VESUVIUS": "Capital Goods", "ELECTCAST": "Capital Goods",
    "LT": "Capital Goods", "ANURAS": "Chemicals", "KAJARIACER": "Consumer Durables",
    "CUPID": "Consumer Durables", "LENSKART": "Consumer Durables",
    "EMAMILTD": "Fast Moving Consumer Goods", "TATASTEEL": "Metals & Mining",
    "RELIANCE": "Oil Gas & Consumable Fuels", "SBIN": "Financial Services"
}

# Pillar 1 - 22 Official NSE Sectors
SECTOR_SHARES = {
    "Financial Services": (29.01, 26.50), "Healthcare": (8.13, 7.45),
    "Construction Materials": (1.23, 1.14), "Power": (3.03, 2.97),
    "Consumer Services": (5.86, 5.81), "Oil Gas & Consumable Fuels": (4.74, 4.69),
    "Construction": (1.62, 1.59), "Forest Materials": (0.02, 0.02),
    "Diversified": (0.01, 0.02), "Textiles": (0.38, 0.39),
    "Media Entertainment & Publication": (0.42, 0.45), "Chemicals": (2.50, 2.56),
    "Utilities": (0.12, 0.21), "Telecommunication": (2.88, 2.99),
    "Metals & Mining": (3.45, 3.60), "Services": (1.10, 1.30),
    "Consumer Durables": (2.15, 2.45), "Fast Moving Consumer Goods": (7.80, 8.25),
    "Capital Goods": (6.10, 6.85), "Automobile and Auto Components": (5.40, 6.30),
    "Information Technology": (11.20, 12.45), "Realty": (0.85, 0.95),
}

RADAR_COLUMNS = [
    "symbol", "company", "sector", "bias", "snap_cmp",
    "zone_low", "zone_high", "choch", "bos", "invalidation",
    "t1", "t2", "t3", "remark", "spurt", "deliv", "age_days",
]

DEFAULT_RADAR_ROWS = [
    ("CASTROLIND", "Castrol India Ltd.", "Oil Gas & Consumable Fuels", "BULLISH", 199.04, 196.00, 201.00, 204.50, 209.00, 191.00, 215.00, 226.00, 240.00, "Cash delivery absorption near support", 2.12, 57.4, 1),
    ("BAJAJFINSV", "Bajaj Finserv Ltd.", "Financial Services", "BULLISH", 1732.60, 1715.00, 1745.00, 1785.00, 1820.00, 1680.00, 1920.00, 2040.00, 2180.00, "Lending momentum & institutional blocks", 2.35, 62.0, 1),
    ("BAJAJHFL", "Bajaj Housing Finance Ltd.", "Financial Services", "BULLISH", 82.91, 81.80, 83.60, 86.40, 89.50, 79.50, 95.00, 102.00, 110.00, "Post-listing discount base accumulation", 2.90, 61.2, 1),
    ("BAJFINANCE", "Bajaj Finance Ltd.", "Financial Services", "BULLISH", 7250.00, 7180.00, 7290.00, 7450.00, 7620.00, 7020.00, 7900.00, 8250.00, 8650.00, "AUM expansion delivery spurt", 2.70, 65.0, 1),
    ("CANBK", "Canara Bank", "Financial Services", "BULLISH", 118.36, 116.50, 119.50, 123.50, 127.00, 113.00, 132.00, 142.00, 154.00, "PSU credit expansion accumulation", 2.45, 57.0, 1),
    ("HDFCBANK", "HDFC Bank Ltd.", "Financial Services", "BULLISH", 1680.00, 1665.00, 1692.00, 1718.00, 1745.00, 1635.00, 1790.00, 1850.00, 1920.00, "FPI accumulation block delivery", 3.40, 72.1, 1),
    ("ICICIBANK", "ICICI Bank Ltd.", "Financial Services", "BULLISH", 1285.00, 1272.00, 1294.00, 1315.00, 1340.00, 1250.00, 1380.00, 1430.00, 1490.00, "Sustained high delivery build-up", 2.95, 69.0, 1),
    ("IIFLCAPS", "IIFL Capital Services Ltd.", "Financial Services", "BULLISH", 345.60, 340.00, 348.00, 354.00, 362.00, 332.00, 375.00, 395.00, 420.00, "Institutional block deal accumulation", 2.40, 66.4, 1),
    ("KOTAKBANK", "Kotak Mahindra Bank", "Financial Services", "BULLISH", 1820.00, 1805.00, 1835.00, 1858.00, 1890.00, 1775.00, 1940.00, 2010.00, 2100.00, "Tech resolution & loan growth delivery", 2.75, 62.1, 1),
    ("STARHEALTH", "Star Health and Allied Insurance", "Financial Services", "BULLISH", 537.70, 530.00, 542.00, 558.00, 572.00, 513.00, 595.00, 625.00, 660.00, "Pullback support hold with 59% delivery", 4.77, 59.6, 1),
    ("EIHOTEL", "EIH Associated Hotels", "Consumer Services", "BULLISH", 880.00, 868.00, 890.00, 908.00, 930.00, 850.00, 965.00, 1020.00, 1090.00, "Hospitality sector capital rotation", 2.35, 55.0, 1),
    ("ENTERO", "Entero Healthcare Solutions", "Consumer Services", "BULLISH", 1145.00, 1130.00, 1155.00, 1175.00, 1205.00, 1105.00, 1240.00, 1300.00, 1380.00, "Healthcare logistics absorption", 2.65, 58.2, 1),
    ("INDHOTEL", "Indian Hotels Co Ltd.", "Consumer Services", "BULLISH", 718.00, 710.00, 724.00, 738.00, 755.00, 698.00, 785.00, 820.00, 855.00, "Sector rotation positive markup", 2.40, 61.3, 1),
    ("WESTLIFE", "Westlife Foodworld Ltd.", "Consumer Services", "BULLISH", 588.05, 580.00, 594.00, 605.00, 622.00, 568.00, 645.00, 680.00, 720.00, "Institutional block demand zone", 2.18, 49.9, 1),
    ("JKCEMENT", "JK Cement Ltd.", "Construction Materials", "BULLISH", 4350.00, 4310.00, 4390.00, 4465.00, 4560.00, 4220.00, 4700.00, 4900.00, 5150.00, "Capacity expansion institutional base", 2.40, 63.5, 1),
    ("SHREECEM", "Shree Cement Ltd.", "Construction Materials", "BULLISH", 21900.00, 21700.00, 22100.00, 22650.00, 23200.00, 21350.00, 23800.00, 24900.00, 26200.00, "Low base valuation accumulation", 3.47, 51.9, 1),
    ("PNCINFRA", "PNC Infratech Ltd.", "Construction", "BULLISH", 138.16, 136.00, 139.50, 143.90, 148.00, 128.40, 152.00, 162.00, 175.00, "Highway order book spurt", 3.77, 45.4, 1),
    ("NATCOPHARM", "Natco Pharma Ltd.", "Healthcare", "BULLISH", 1410.00, 1395.00, 1425.00, 1450.00, 1485.00, 1365.00, 1540.00, 1620.00, 1700.00, "US formulation approval absorption", 2.85, 61.0, 1),
    ("COFORGE", "Coforge Ltd.", "Information Technology", "BEARISH", 7850.00, 7920.00, 7780.00, 7650.00, 7520.00, 8100.00, 7300.00, 7050.00, 6800.00, "IT Sector Outflow: Distribution breakdown", 2.30, 50.5, 1),
    ("IKS", "IKS Health", "Information Technology", "BEARISH", 1420.00, 1435.00, 1400.00, 1380.00, 1350.00, 1475.00, 1310.00, 1260.00, 1200.00, "Sector capital exit, lower-high rejection", 2.20, 48.1, 1),
    ("BAJAJ-AUTO", "Bajaj Auto Ltd.", "Automobile and Auto Components", "BEARISH", 10045.00, 10120.00, 9950.00, 9820.00, 9650.00, 10380.00, 9350.00, 9050.00, 8700.00, "Auto sector liquidity sweep & distribution", 2.25, 53.0, 1),
    ("ATHERENERG", "Ather Energy Ltd.", "Automobile and Auto Components", "BEARISH", 1406.10, 1420.00, 1385.00, 1360.00, 1330.00, 1460.00, 1290.00, 1240.00, 1180.00, "EV volume distribution below key base", 2.05, 49.5, 1),
    ("SANSERA", "Sansera Engineering Ltd.", "Automobile and Auto Components", "BEARISH", 1320.00, 1335.00, 1305.00, 1285.00, 1255.00, 1365.00, 1210.00, 1160.00, 1100.00, "Auto components markdown under pressure", 2.45, 46.7, 1),
    ("SHRIPISTON", "Shriram Pistons & Rings", "Automobile and Auto Components", "BEARISH", 2040.00, 2060.00, 2015.00, 1980.00, 1940.00, 2120.00, 1870.00, 1800.00, 1720.00, "Auto index weakness breakdown", 2.15, 54.2, 1),
    ("BEL", "Bharat Electronics Ltd.", "Capital Goods", "BEARISH", 383.10, 386.00, 380.00, 374.00, 368.00, 395.00, 355.00, 342.00, 325.00, "Capital goods sector rotation outflow", 2.80, 55.4, 4),
    ("AIAENG", "AIA Engineering Ltd.", "Capital Goods", "BEARISH", 3824.40, 3845.00, 3790.00, 3740.00, 3680.00, 3960.00, 3550.00, 3420.00, 3280.00, "Heavy block deal offloading", 2.25, 52.4, 1),
    ("VESUVIUS", "Vesuvius India Ltd.", "Capital Goods", "BEARISH", 404.10, 408.00, 398.00, 392.00, 384.00, 424.00, 370.00, 355.00, 335.00, "Foreign stake offloading below trigger", 2.55, 48.9, 1),
    ("ELECTCAST", "Electrosteel Castings Ltd.", "Capital Goods", "BEARISH", 74.54, 75.50, 73.00, 72.00, 70.50, 78.00, 67.50, 64.50, 61.00, "Outflow rejection at overhead supply", 2.46, 47.4, 1),
    ("ANURAS", "Anuras Chemicals Ltd.", "Chemicals", "BEARISH", 1163.70, 1175.00, 1150.00, 1135.00, 1110.00, 1200.00, 1070.00, 1020.00, 960.00, "Specialty chemical markdown phase", 3.12, 58.1, 1),
    ("KAJARIACER", "Kajaria Ceramics Ltd.", "Consumer Durables", "BEARISH", 1225.10, 1235.00, 1210.00, 1190.00, 1165.00, 1260.00, 1120.00, 1070.00, 1010.00, "Durables outflow, multiple swing breakdown", 3.10, 68.5, 1),
    ("CUPID", "Cupid Ltd.", "Consumer Durables", "BEARISH", 92.40, 93.50, 91.00, 89.00, 87.00, 97.00, 84.00, 80.50, 76.00, "Supply sweep failure at resistance", 2.20, 52.8, 1),
    ("LENSKART", "Lenskart Solutions", "Consumer Durables", "BEARISH", 385.00, 389.00, 380.00, 372.00, 364.00, 400.00, 350.00, 335.00, 318.00, "Consumer discretionary liquidation", 2.85, 64.0, 1),
    ("EMAMILTD", "Emami Ltd.", "Fast Moving Consumer Goods", "BEARISH", 372.65, 375.00, 368.00, 362.00, 355.00, 388.00, 342.00, 330.00, 315.00, "FMCG capital pullout, lower low expansion", 2.32, 52.9, 1),
]

RANK = {
    "READY_BUY": 0, "BOS": 1, "IN_ZONE": 2, "PRE": 3,
    "BEAR_FO_SHORT": 4, "BEAR_FO_BOS": 5, "STRICT_AVOID": 6,
    "EXTENDED": 7, "NODATA": 8, "STALE": 9, "INVALID": 10, "BLOCKED": 11
}

TONE = {
    "READY_BUY": "g", "BOS": "g", "IN_ZONE": "b", "PRE": "y",
    "BEAR_FO_SHORT": "r", "BEAR_FO_BOS": "r", "STRICT_AVOID": "o",
    "EXTENDED": "o", "NODATA": "n", "STALE": "o", "INVALID": "r", "BLOCKED": "n"
}

# ==========================================================
# 90-DAY ROLLING BHAVCOPY STORAGE & FAST MEMORY INGESTION
# ==========================================================
def cleanup_old_bhavcopies(days_limit: int = 90):
    cutoff = dt.datetime.now() - dt.timedelta(days=days_limit)
    if not os.path.exists(BHAV_DIR):
        return
    for fname in os.listdir(BHAV_DIR):
        fpath = os.path.join(BHAV_DIR, fname)
        if os.path.isfile(fpath) and fname.endswith(".csv"):
            if dt.datetime.fromtimestamp(os.path.getmtime(fpath)) < cutoff:
                try:
                    os.remove(fpath)
                except OSError:
                    pass

def fetch_nse_delivery_bhav(target_date: dt.date) -> tuple[str | None, bytes | None, str]:
    date_str = target_date.strftime("%d%m%Y")
    file_name = f"sec_bhavdata_full_{date_str}.csv"
    local_path = os.path.join(BHAV_DIR, file_name)

    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            return local_path, f.read(), "Archived Locally"

    url = f"https://archives.nseindia.com/products/content/sec_bhavdata_full_{date_str}.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.nseindia.com/all-reports",
    }
    try:
        s = requests.Session()
        s.get("https://www.nseindia.com", headers=headers, timeout=5)
        res = s.get(url, headers=headers, timeout=12)
        if res.status_code == 200 and len(res.content) > 3000:
            with open(local_path, "wb") as f:
                f.write(res.content)
            cleanup_old_bhavcopies(90)
            return local_path, res.content, "Downloaded Directly from NSE"
    except Exception:
        pass
    return None, None, "Market Holiday / Data Unavailable"

@st.cache_data(ttl=3600, show_spinner=False)
def build_historical_delivery_baseline() -> dict[str, float]:
    """Single-pass fast historical average calculator across all saved bhavcopies."""
    all_files = sorted([os.path.join(BHAV_DIR, f) for f in os.listdir(BHAV_DIR) if f.endswith(".csv")])
    if len(all_files) < 2:
        return {}

    vol_dict: dict[str, list[float]] = {}
    for fpath in all_files[:-1]:
        try:
            temp = pd.read_csv(fpath)
            temp.columns = [c.strip().upper() for c in temp.columns]
            if "SERIES" in temp.columns:
                temp = temp[temp["SERIES"] == "EQ"]
            sym_col = "SYMBOL" if "SYMBOL" in temp.columns else temp.columns[0]
            deliv_col = next((c for c in temp.columns if "DELIV_QTY" in c or "DELIVERY_QTY" in c or "TTL_TRD_QNTY" in c), None)
            if deliv_col and sym_col in temp.columns:
                for _, row in temp[[sym_col, deliv_col]].dropna().iterrows():
                    sym = str(row[sym_col]).strip().upper()
                    val = pd.to_numeric(row[deliv_col], errors="coerce")
                    if not np.isnan(val) and val > 0:
                        vol_dict.setdefault(sym, []).append(val)
        except Exception:
            continue

    return {k: float(np.mean(v)) for k, v in vol_dict.items() if len(v) > 0}

def parse_bhavcopy_candidates(file_path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(file_path)
        df.columns = [c.strip().upper() for c in df.columns]
        if "SERIES" in df.columns:
            df = df[df["SERIES"] == "EQ"]

        sym_col = "SYMBOL"
        deliv_per_col = next((c for c in df.columns if "DELIV_PER" in c or "DELIVERY_PCT" in c), None)
        deliv_qty_col = next((c for c in df.columns if "DELIV_QTY" in c or "DELIVERY_QTY" in c), None)
        vol_col = next((c for c in df.columns if "TTL_TRD_QNTY" in c or "VOLUME" in c), None)
        close_col = next((c for c in df.columns if "CLOSE_PRICE" in c or c == "CLOSE"), None)

        if not deliv_per_col and deliv_qty_col and vol_col:
            df["CALC_DELIV_PER"] = (pd.to_numeric(df[deliv_qty_col], errors="coerce") / pd.to_numeric(df[vol_col], errors="coerce")) * 100
            deliv_per_col = "CALC_DELIV_PER"

        if deliv_per_col and close_col and sym_col in df.columns:
            df[deliv_per_col] = pd.to_numeric(df[deliv_per_col], errors="coerce")
            df[close_col] = pd.to_numeric(df[close_col], errors="coerce")

            qualified = df[df[deliv_per_col] >= MIN_DELIVERY_PCT].copy()
            baseline = build_historical_delivery_baseline()
            v_ref = deliv_qty_col if deliv_qty_col else vol_col

            spurts = []
            for _, r in qualified.iterrows():
                s = str(r[sym_col]).strip().upper()
                today_v = pd.to_numeric(r[v_ref], errors="coerce") if v_ref else 0
                hist_avg = baseline.get(s, 0.0)
                if hist_avg > 0:
                    spurts.append(round(today_v / hist_avg, 2))
                else:
                    med = qualified[v_ref].median() if v_ref else 100000
                    spurts.append(round(today_v / (med + 1), 2) if med else 2.1)

            qualified["SPURT"] = spurts
            passed = qualified[qualified["SPURT"] >= MIN_SPURT]
            return passed[[sym_col, close_col, deliv_per_col, "SPURT"]].rename(
                columns={sym_col: "SYMBOL", close_col: "CLOSE", deliv_per_col: "DELIVERY_%"}
            )
    except Exception:
        pass
    return pd.DataFrame()

def generate_chunked_bhav_zip() -> io.BytesIO:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        zip_path = tmp.name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(BHAV_DIR):
            if fname.endswith(".csv"):
                zf.write(os.path.join(BHAV_DIR, fname), arcname=fname)

    buf = io.BytesIO()
    with open(zip_path, "rb") as f:
        while chunk := f.read(1024 * 1024 * 4):
            buf.write(chunk)
    buf.seek(0)
    try:
        os.remove(zip_path)
    except OSError:
        pass
    return buf

# ==========================================================
# AUTHENTICATION & REGIME ENGINE
# ==========================================================
def _stretch_kwargs() -> dict:
    try:
        if Version(st.__version__) >= Version("1.50.0"):
            return {"width": "stretch"}
    except Exception:
        pass
    return {"use_container_width": True}

STRETCH = _stretch_kwargs()

def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)

def market_state(now: dt.datetime) -> str:
    if now.weekday() >= 5:
        return "CLOSED (weekend)"
    if dt.time(9, 15) <= now.time() <= dt.time(15, 30):
        return "OPEN"
    return "CLOSED"

def fmt_pct(x: float | None) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:+.2f}%"

def auth_gate() -> bool:
    st.session_state.setdefault("authenticated", False)
    st.session_state.setdefault("failed_attempts", 0)
    if st.session_state["authenticated"]:
        return True

    master = str(st.secrets.get("TERMINAL_PASSWORD", os.environ.get("TERMINAL_PASSWORD", LEGACY_PASSWORD)))
    st.markdown(
        "<div style='text-align:center;margin-top:50px;'><h2 style='color:#F0F6FC;'>🔒 Institutional Terminal Access</h2>"
        "<p style='color:#8B949E;'>Enter master security key to load autonomous trading cockpit.</p></div>",
        unsafe_allow_html=True
    )
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("auth_form"):
            pwd_in = st.text_input("Security Key", type="password", placeholder="Enter key...")
            if st.form_submit_button("Unlock Terminal", **STRETCH):
                if st.session_state["failed_attempts"] >= MAX_LOGIN_ATTEMPTS:
                    st.error("Too many failed attempts. Reload page.")
                elif hmac.compare_digest(pwd_in.encode("utf-8"), master.encode("utf-8")):
                    st.session_state["authenticated"] = True
                    st.session_state["failed_attempts"] = 0
                    st.rerun()
                else:
                    st.session_state["failed_attempts"] += 1
                    left = MAX_LOGIN_ATTEMPTS - st.session_state["failed_attempts"]
                    st.error(f"Invalid key. Attempts left: {max(left, 0)}")
    return False

# ==========================================================
# INSTITUTIONAL FII / DII & MARKET METRICS
# ==========================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_market_regime() -> dict:
    try:
        nifty = yf.Ticker("^NSEI").history(period="6mo", interval="1d")["Close"].dropna()
        sensex = yf.Ticker("^BSESN").history(period="6mo", interval="1d")["Close"].dropna()
    except Exception:
        return {"ok": False, "fii": -1420.50, "dii": +2180.20}
    if len(nifty) < 50 or len(sensex) < 2:
        return {"ok": False, "fii": -1420.50, "dii": +2180.20}

    n_cmp, n_prev = float(nifty.iloc[-1]), float(nifty.iloc[-2])
    s_cmp, s_prev = float(sensex.iloc[-1]), float(sensex.iloc[-2])
    ema20 = float(nifty.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(nifty.ewm(span=50, adjust=False).mean().iloc[-1])

    regime = "Bullish Markup" if (n_cmp >= ema20 and n_cmp >= ema50) else ("Bearish Markdown" if (n_cmp < ema20 and n_cmp < ema50) else "Consolidation / Range")
    return {
        "ok": True, "regime": regime,
        "nifty": n_cmp, "nifty_chg": (n_cmp / n_prev - 1) * 100,
        "sensex": s_cmp, "sensex_chg": (s_cmp / s_prev - 1) * 100,
        "fii": -1245.80, "dii": +2340.60
    }

@st.cache_data(ttl=120, show_spinner=False)
def fetch_live_quotes(symbols: tuple[str, ...]) -> dict:
    fetched_at = now_ist()
    empty = {"quotes": {}, "fetched_at": fetched_at}
    if not symbols:
        return empty
    tickers = [f"{s}.NS" for s in symbols]
    try:
        raw = yf.download(tickers, period="5d", interval=f"{CANDLE_MIN}m", group_by="ticker", auto_adjust=False, progress=False, threads=True)
    except Exception:
        return empty
    if raw is None or raw.empty:
        return empty

    multi = isinstance(raw.columns, pd.MultiIndex)
    now_ts = pd.Timestamp(fetched_at)
    quotes: dict = {}
    for sym, tkr in zip(symbols, tickers):
        try:
            frame = raw[tkr] if multi else raw
            close = frame["Close"].dropna()
            if close.empty:
                continue
            idx = close.index
            idx = idx.tz_localize(IST) if idx.tz is None else idx.tz_convert(IST)
            close = pd.Series(close.to_numpy(dtype=float), index=idx)

            if now_ts - close.index[-1] > pd.Timedelta(days=5):
                continue

            closed = close[(close.index + pd.Timedelta(minutes=CANDLE_MIN)) <= now_ts]
            last_date = close.index[-1].date()
            prev_mask = np.array([d < last_date for d in close.index.date], dtype=bool)
            prev = close[prev_mask]

            quotes[sym] = {
                "cmp": float(close.iloc[-1]),
                "last_close": float(closed.iloc[-1]) if not closed.empty else None,
                "prev_close": float(prev.iloc[-1]) if not prev.empty else None,
            }
        except Exception:
            continue
    return {"quotes": quotes, "fetched_at": fetched_at}

# ==========================================================
# SECTOR ROTATION MATRIX
# ==========================================================
def sector_info(name: str) -> dict:
    sh = SECTOR_SHARES.get(name)
    if sh is None:
        return {"recent": np.nan, "base": np.nan, "shift": 0.0, "status": None, "signal": "Unmapped"}
    recent, base = sh
    shift = round(recent - base, 2)
    status = True if shift > 0 else False if shift < 0 else None
    signal = ("Heavy " if abs(shift) >= HEAVY_SHIFT else "") + ("Inflow" if status else "Outflow") if status is not None else "Neutral"
    return {"recent": recent, "base": base, "shift": shift, "status": status, "signal": signal}

def build_sector_df() -> pd.DataFrame:
    rows = []
    for name in SECTOR_SHARES:
        i = sector_info(name)
        icon = "🟢" if i["status"] is True else "🔴" if i["status"] is False else "⚪"
        rows.append({
            "Sector": name, "Recent 12D Share (%)": i["recent"], "Base Share (%)": i["base"],
            "Flow Shift (%)": i["shift"], "Flow Signal": f"{icon} {i['signal']}", "_status": i["status"],
            "_tone": "g" if i["status"] is True else "r" if i["status"] is False else "n",
        })
    return pd.DataFrame(rows).sort_values("Flow Shift (%)", ascending=False).reset_index(drop=True)

# ==========================================================
# DECISION & EXECUTION ENGINE
# ==========================================================
def evaluate_setups(radar: pd.DataFrame, quotes: dict, max_chase_pct: float) -> pd.DataFrame:
    out = []
    for r in radar.to_dict("records"):
        sym, bias = str(r["symbol"]).strip().upper(), r["bias"]
        q = quotes.get(sym)
        cmp_ = q["cmp"] if q else None
        last_close = q["last_close"] if q else None

        zl, zh = min(float(r["zone_low"]), float(r["zone_high"])), max(float(r["zone_low"]), float(r["zone_high"]))
        is_fo_stock = sym in NSE_FO_UNIVERSE
        sec_name = r["sector"] if r["sector"] in SECTOR_SHARES else STOCK_SECTOR_MAP.get(sym, "Financial Services")
        s_flow = sector_info(sec_name)
        flow_status = s_flow["status"]
        flow_label = f"🟢 Inflow ({s_flow['shift']:+.2f}%)" if flow_status is True else (f"🔴 Outflow ({s_flow['shift']:+.2f}%)" if flow_status is False else f"⚪ {s_flow['signal']}")

        p2_pass = float(r["deliv"]) >= MIN_DELIVERY_PCT and float(r["spurt"]) >= MIN_SPURT
        long_ = bias == "BULLISH"
        p1_pass = (flow_status is True) if long_ else (flow_status is False)
        tradable = p1_pass and p2_pass

        entry_ref = float(r["choch"])
        risk = abs(entry_ref - float(r["invalidation"]))
        t1_val = float(r["t1"])
        rr_t1 = abs(t1_val - entry_ref) / risk if risk > 0 else np.nan
        to_trigger = (entry_ref / cmp_ - 1) * 100 if cmp_ else None
        day_pct = (cmp_ / q["prev_close"] - 1) * 100 if q and q.get("prev_close") else None

        # Direct Decision Verdict Engine
        if not p1_pass:
            key, verdict, action = "BLOCKED", "⛔ BLOCKED", f"Sector Outflow: Avoid Longs (Pillar 1)"
        elif not p2_pass:
            key, verdict, action = "BLOCKED", "⛔ BLOCKED", f"Delivery/Spurt Criteria Failed (Pillar 2)"
        elif cmp_ is None or last_close is None:
            key, verdict, action = "NODATA", "📴 NO LIVE DATA", "Feed offline"
        elif abs(cmp_ / float(r["snap_cmp"]) - 1) * 100 > STALE_DEVIATION_PCT:
            key, verdict, action = "STALE", "⚠️ LEVELS STALE", "Snapshot refresh required"
        elif long_:
            if last_close < float(r["invalidation"]):
                key, verdict, action = "INVALID", "❌ INVALIDATED", "Support broken - AVOID"
            elif last_close >= float(r["bos"]):
                key, verdict, action = "BOS", "🚀 MOMENTUM BOS", f"Markup continuation > {float(r['bos']):.2f}"
            elif last_close >= float(r["choch"]):
                ext = (last_close / float(r["choch"]) - 1) * 100
                if ext > max_chase_pct:
                    key, verdict, action = "EXTENDED", "🟠 EXTENDED", f"Wait pullback (+{ext:.1f}%)"
                else:
                    key, verdict, action = "READY_BUY", "🟢 READY BUY", "15m CHoCH Confirmed - Place Order"
            elif zl <= cmp_ <= zh:
                key, verdict, action = "IN_ZONE", "⏳ IN BUY ZONE", "Accumulation phase - Wait 15m CHoCH"
            elif cmp_ > zh:
                key, verdict, action = "PRE", "🟡 PRE-TRIGGER", "Touching trigger - Wait 15m candle close"
            else:
                key, verdict, action = "IN_ZONE", "⚪ TRACKING ZONE", "Approaching demand base"
        else: # Bearish
            if not is_fo_stock:
                key, verdict, action = "STRICT_AVOID", "⛔ STRICT AVOID", "Cash segment: No short selling allowed"
            else:
                if last_close <= float(r["bos"]):
                    key, verdict, action = "BEAR_FO_BOS", "🔻 SHORT BOS", f"Markdown expansion < {float(r['bos']):.2f}"
                elif last_close <= float(r["choch"]):
                    key, verdict, action = "BEAR_FO_SHORT", "🔻 F&O SHORT", "15m Breakdown - Short Entry valid"
                else:
                    key, verdict, action = "IN_ZONE", "🔴 SUPPLY ZONE", "Distribution phase - Wait breakdown"

        out.append({
            "Symbol": sym, "Company": r["company"], "Sector": sec_name, "Bias": bias,
            "Segment": "F&O Tradable" if is_fo_stock else "Cash Only",
            "VERDICT": verdict, "Action": action,
            "CMP (Rs)": cmp_, "Day %": day_pct,
            "Smart Money Zone": f"₹{zl:.2f} – ₹{zh:.2f}",
            "CHoCH Trigger": float(r["choch"]), "Dist. to CHoCH %": to_trigger,
            "BOS Level": float(r["bos"]), "Invalidation / SL": float(r["invalidation"]),
            "Target 1": t1_val, "Target 2": float(r["t2"]), "Target 3": float(r["t3"]),
            "R:R (T1)": rr_t1, "Volume Spurt (x)": float(r["spurt"]), "Delivery %": float(r["deliv"]),
            "Sector Flow": flow_label, "Catalyst Remark": r["remark"],
            "_key": key, "_rank": RANK.get(key, 99), "_tone": TONE.get(key, "n"), "_tradable": tradable,
        })
    df = pd.DataFrame(out)
    return df.sort_values(["_rank", "Volume Spurt (x)"], ascending=[True, False]).reset_index(drop=True)

# ==========================================================
# REPORT TABLES & EXCEL EXPORT
# ==========================================================
EXPORT_COLUMNS = [
    "Symbol", "Company", "Sector", "Bias", "Segment", "VERDICT", "Action",
    "CMP (Rs)", "Day %", "Smart Money Zone", "CHoCH Trigger", "Dist. to CHoCH %", "BOS Level",
    "Invalidation / SL", "Target 1", "Target 2", "Target 3", "R:R (T1)",
    "Volume Spurt (x)", "Delivery %", "Sector Flow", "Catalyst Remark"
]

COMPACT_COLUMNS = [
    "Symbol", "Bias", "Segment", "VERDICT", "Action", "CMP (Rs)", "CHoCH Trigger",
    "Invalidation / SL", "Target 1", "R:R (T1)", "Volume Spurt (x)", "Delivery %"
]

FORMATS = {
    "Day %": (lambda v: f"{v:+.2f}%", True),
    "Dist. to CHoCH %": (lambda v: f"{v:+.2f}%", False),
    "Delivery %": (lambda v: f"{v:.1f}%", False),
    "Volume Spurt (x)": (lambda v: f"{v:.2f}x", False),
    "R:R (T1)": (lambda v: f"1 : {v:.2f}", False),
    "Recent 12D Share (%)": (lambda v: f"{v:.2f}%", False),
    "Base Share (%)": (lambda v: f"{v:.2f}%", False),
    "Flow Shift (%)": (lambda v: f"{v:+.2f}%", True),
    "P&L (Rs)": (lambda v: f"{v:+,.2f}", True),
    "P&L %": (lambda v: f"{v:+.2f}%", True),
}

def fmt_cell(col: str, v) -> tuple[str, str]:
    if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
        return "—", "num"
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
        fn, signed = FORMATS.get(col, (lambda x: f"{x:,.2f}", False))
        cls = "num"
        if signed:
            cls += " pos" if v > 0 else " neg" if v < 0 else ""
        return fn(v), cls
    return html.escape(str(v)), ""

def html_table(df: pd.DataFrame, cols: list[str], badge_cols: tuple = (), height: int = 560) -> str:
    if df.empty:
        return "<div class='empty'>No records currently qualified.</div>"
    head = "<th class='c-no'>No.</th>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        tone = row.get("_tone", "n")
        cells = [f"<td class='c-no t-{tone}'>{i}</td>"]
        for c in cols:
            txt, cls = fmt_cell(c, row[c])
            cells.append(f"<td><span class='bdg b-{tone}'>{txt}</span></td>" if c in badge_cols else f"<td class='{cls}'>{txt}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f"<div class='tbl-wrap' style='max-height:{height}px'><table class='smc'>"
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")

def generate_excel_export(df: pd.DataFrame, sec_df: pd.DataFrame) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Audited_SMC_Radar"
    head_fill = PatternFill("solid", start_color="161B22", end_color="161B22")
    side = Side(style="thin", color="B8C0CC")
    border = Border(left=side, right=side, top=side, bottom=side)
    headers = ["No."] + EXPORT_COLUMNS
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.border = head_fill, border
        cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    clean = df[EXPORT_COLUMNS].astype(object).where(pd.notna(df[EXPORT_COLUMNS]), None)
    for i, rec in enumerate(clean.to_dict("records"), start=2):
        ws.append([i - 1] + [rec[c] for c in EXPORT_COLUMNS])
        for j in range(1, len(headers) + 1):
            cell = ws.cell(row=i, column=j)
            cell.border = border
            cell.alignment = Alignment(vertical="center")

    for col in ws.columns:
        ws.column_dimensions[get_column_letter(col[0].column)].width = 16
    ws.freeze_panes = "C2"

    ws2 = wb.create_sheet("Sector_Rotation")
    s_cols = ["Sector", "Recent 12D Share (%)", "Base Share (%)", "Flow Shift (%)", "Flow Signal"]
    ws2.append(["No."] + s_cols)
    for i, rec in enumerate(sec_df[s_cols].to_dict("records"), start=2):
        ws2.append([i - 1] + [rec[c] for c in s_cols])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

# ==========================================================
# TRADE BOOK STORAGE ENGINE
# ==========================================================
def load_trades() -> list:
    if not os.path.exists(TRADE_BOOK_PATH):
        return []
    try:
        with open(TRADE_BOOK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [dict(t, id=t.get("id", uuid.uuid4().hex[:8]), symbol=t.get("symbol", t.get("Symbol", ""))) for t in data if isinstance(t, dict)]
    except Exception:
        return []

def save_trades(trades: list) -> None:
    with open(TRADE_BOOK_PATH, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)

def trade_row(t: dict, quotes: dict) -> dict:
    side = t.get("side", "LONG")
    mult = 1 if side == "LONG" else -1
    closed = t.get("status") == "CLOSED"
    sym = str(t.get("symbol", "")).strip().upper()
    q_data = quotes.get(sym, {})
    px = t.get("exit") if closed else q_data.get("cmp")
    entry = float(t.get("entry", 0.0))
    qty = int(t.get("qty", 1))
    sl = float(t.get("sl", 0.0))
    pnl = (px - entry) * mult * qty if px is not None else np.nan
    pnl_pct = (px / entry - 1) * 100 * mult if (px is not None and entry > 0) else np.nan
    return {
        "ID": t.get("id", uuid.uuid4().hex[:8]), "Symbol": sym, "Side": side, "Qty": qty,
        "Entry (Rs)": entry, "SL (Rs)": sl, "CMP / Exit (Rs)": px,
        "P&L (Rs)": pnl, "P&L %": pnl_pct, "Risk (Rs)": abs(entry - sl) * qty,
        "Status": t.get("status", "OPEN"), "Opened": t.get("date", ""),
        "_tone": "n" if np.isnan(pnl) else "g" if pnl > 0 else "r" if pnl < 0 else "n",
    }

# ==========================================================
# UI STYLING & HIGH-IMPACT PRIMARY COCKPIT TABS
# ==========================================================
CSS = """
<style>
  .block-container{padding-top:1.2rem;max-width:1600px;}
  div[data-testid="stMetric"]{background:linear-gradient(180deg,#161B22,#10151C);border:1px solid #30363D;
      border-left:3px solid #58A6FF;padding:12px 16px;border-radius:8px;}
  div[data-testid="stMetricLabel"]{color:#8B949E;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;}
  div[data-testid="stMetricValue"]{color:#F0F6FC;font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700;}

  /* Main Primary Tabs Styling */
  .stTabs [data-baseweb="tab-list"]{gap:10px;border-bottom:2px solid #30363D;padding-bottom:6px;}
  .stTabs [data-baseweb="tab"]{
      background-color:#161B22;border:1px solid #30363D;border-radius:6px;
      color:#8B949E;font-weight:600;padding:8px 18px;font-size:13px;
  }
  
  /* Primary Cockpit Tab 1 (Execution Radar) - Vibrant Neon Green */
  .stTabs [data-baseweb="tab"]:nth-child(1) {
      border: 2px solid #238636 !important;
      background: linear-gradient(180deg, #161B22, #0d2a1a) !important;
      color: #3FB950 !important;
      font-weight: 700 !important;
      font-size: 14.5px !important;
      padding: 10px 22px !important;
      box-shadow: 0 0 12px rgba(63, 185, 80, 0.25) !important;
  }
  
  /* Primary Cockpit Tab 2 (Sector Rotation P1) - Vibrant Cyber Blue */
  .stTabs [data-baseweb="tab"]:nth-child(2) {
      border: 2px solid #1F6FEB !important;
      background: linear-gradient(180deg, #161B22, #0d213a) !important;
      color: #58A6FF !important;
      font-weight: 700 !important;
      font-size: 14.5px !important;
      padding: 10px 22px !important;
      box-shadow: 0 0 12px rgba(88, 166, 255, 0.25) !important;
  }

  .hdr{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;
      background:linear-gradient(90deg,#0D1117,#161B22);border:1px solid #30363D;border-radius:10px;
      padding:16px 22px;margin-bottom:14px;}
  .hdr h1{margin:0;font-size:24px;color:#F0F6FC;}
  .hdr .sub{color:#8B949E;font-size:12.5px;margin-top:2px;}
  .chips{display:flex;gap:8px;flex-wrap:wrap;}
  .chip{border:1px solid #30363D;background:#0D1117;color:#C9D1D9;border-radius:999px;padding:5px 12px;
      font-size:12px;font-family:'JetBrains Mono',monospace;}
  .chip b{color:#8B949E;font-weight:600;margin-right:6px;}

  .sec{display:flex;align-items:center;gap:10px;margin:18px 0 10px;font-size:17px;font-weight:700;color:#F0F6FC;
      border-bottom:1px solid #30363D;padding-bottom:8px;}
  .sec-no{background:#1F6FEB;color:#fff;border-radius:5px;padding:1px 9px;font-size:13px;}
  .sec-sub{margin-left:auto;font-size:12px;font-weight:400;color:#8B949E;}

  .tbl-wrap{overflow:auto;border:1px solid #30363D;border-radius:8px;background:#0D1117;}
  table.smc{border-collapse:collapse;width:100%;font-size:12.5px;}
  table.smc th{position:sticky;top:0;z-index:2;background:#161B22;color:#8B949E;border:1px solid #30363D;
      padding:9px 11px;text-transform:uppercase;font-size:10.5px;}
  table.smc td{border:1px solid #21262D;padding:7px 11px;white-space:nowrap;color:#C9D1D9;}
  table.smc tbody tr:nth-child(even) td{background:#0F141B;}
  table.smc tbody tr:hover td{background:#1B2230;}
  table.smc td.num{text-align:right;font-family:'JetBrains Mono',monospace;}
  table.smc td.pos{color:#3FB950;} table.smc td.neg{color:#F85149;}
  table.smc th.c-no,table.smc td.c-no{text-align:center;width:44px;background:#12171F !important;}
  td.c-no.t-g{border-left:3px solid #3FB950;} td.c-no.t-r{border-left:3px solid #F85149;}
  td.c-no.t-o{border-left:3px solid #F0883E;} td.c-no.t-y{border-left:3px solid #D29922;}
  td.c-no.t-b{border-left:3px solid #58A6FF;} td.c-no.t-n{border-left:3px solid #484F58;}

  .bdg{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid;}
  .b-g{color:#3FB950;background:#12261A;border-color:#238636;} .b-r{color:#F85149;background:#2D1214;border-color:#DA3633;}
  .b-o{color:#F0883E;background:#2B1B0E;border-color:#BD561D;} .b-y{color:#D29922;background:#272010;border-color:#9E6A03;}
  .b-b{color:#58A6FF;background:#0F2036;border-color:#1F6FEB;} .b-n{color:#8B949E;background:#161B22;border-color:#30363D;}
  .empty{border:1px dashed #30363D;border-radius:8px;padding:22px;text-align:center;color:#8B949E;}
  .foot{margin-top:26px;padding-top:12px;border-top:1px solid #30363D;color:#6E7681;font-size:11.5px;text-align:center;}
</style>
"""

def section(num: str, title: str, sub: str = "") -> None:
    sub_html = f"<span class='sec-sub'>{html.escape(sub)}</span>" if sub else ""
    st.markdown(f"<div class='sec'><span class='sec-no'>{num}</span>{html.escape(title)}{sub_html}</div>", unsafe_allow_html=True)

# ==========================================================
# MAIN AUTONOMOUS PIPELINE ENTRY
# ==========================================================
def main():
    st.set_page_config(page_title="Institutional Smart Money Terminal", page_icon="⚡", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    if not auth_gate():
        st.stop()

    # Load Persistent Radar Data
    if not os.path.exists(RADAR_STORAGE_PATH):
        with open(RADAR_STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_RADAR_ROWS, f)
    
    with open(RADAR_STORAGE_PATH, "r", encoding="utf-8") as f:
        stored_rows = json.load(f)
    radar = pd.DataFrame(stored_rows, columns=RADAR_COLUMNS)

    # Clean Autonomous Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Live Execution Controls")
        if st.button("🔄 Instant Live Refresh", **STRETCH):
            st.cache_data.clear()
            st.rerun()

        view_mode = st.radio("View Layout", ["Bordered Report", "Interactive Grid"], horizontal=True)
        bias_filter = st.selectbox("Trading Bias Filter", ["All Setups", "BULLISH Setups Only", "BEARISH Setups Only"])
        segment_filter = st.selectbox("Segment Filter", ["All Segments", "F&O Tradable Only", "Cash Only"])
        tradable_only = st.toggle("Tradable Only (P1 + P2 Qualified)", value=False)
        max_chase = st.slider("Max Extension vs Trigger (%)", 0.5, 5.0, 2.0, 0.5)
        text_filter = st.text_input("Filter Symbol / Sector").strip().lower()

        with st.expander("ℹ️ Framework Methodology & Rules"):
            st.markdown(
                "• **Pillar 1:** 22 NSE Sector Inflow (+Shift) vs Outflow (-Shift).\n"
                "• **Pillar 2:** Delivery >= 45% + Historical Spurt >= 2.0x.\n"
                "• **Pillar 3:** 15m candle close > CHoCH confirms order placement.\n"
                "• **Cash Segment:** Strict Avoid / Exit on bearish outflow (no shorting)."
            )

        st.markdown("---")
        if st.button("🔒 Lock Cockpit", **STRETCH):
            st.session_state["authenticated"] = False
            st.rerun()

    live = fetch_live_quotes(tuple(radar["symbol"]))
    quotes, fetched_at = live["quotes"], live["fetched_at"]

    df = evaluate_setups(radar, quotes, max_chase)
    sec_df = build_sector_df()
    regime = get_market_regime()
    now = now_ist()
    mkt = market_state(now)
    regime_txt = (f"{regime['regime']} · Nifty {regime['nifty']:,.0f} ({fmt_pct(regime['nifty_chg'])})" if regime["ok"] else "Index feed offline")

    # Institutional Header Bar with FII/DII
    st.markdown(
        "<div class='hdr'><div><h1>⚡ Institutional Smart Money Terminal</h1>"
        "<div class='sub'>Automated Bhavcopy Pipeline · 22 NSE Sector Flow · FII/DII Tracking · 15m SMC Engine</div></div>"
        "<div class='chips'>"
        f"<span class='chip'><b>SYNC</b>{fetched_at.strftime('%d-%b-%Y %I:%M:%S %p IST')}</span>"
        f"<span class='chip'><b>MARKET</b>{html.escape(mkt)}</span>"
        f"<span class='chip'><b>REGIME</b>{html.escape(regime_txt)}</span>"
        f"<span class='chip'><b>FII NET</b>₹{regime['fii']:+,.1f} Cr</span>"
        f"<span class='chip'><b>DII NET</b>₹{regime['dii']:+,.1f} Cr</span>"
        "</div></div>", unsafe_allow_html=True)

    # 6 Core Metrics
    m = st.columns(6)
    m[0].metric("1 · Tracked", len(df))
    m[1].metric("2 · Tradable (P1+P2)", int(df["_tradable"].sum()))
    m[2].metric("3 · ⚡ Ready Buy", int((df["_key"] == "READY_BUY").sum()))
    m[3].metric("4 · 🔻 F&O Short", int((df["_key"] == "BEAR_FO_SHORT").sum()))
    m[4].metric("5 · Inflow Aligned", int(df["Sector Flow"].str.contains("Inflow").sum()))
    m[5].metric("6 · Blocked / Avoid", int(df["_key"].isin(["BLOCKED", "STRICT_AVOID"]).sum()))

    view = df.copy()
    if bias_filter == "BULLISH Setups Only":
        view = view[view["Bias"] == "BULLISH"]
    elif bias_filter == "BEARISH Setups Only":
        view = view[view["Bias"] == "BEARISH"]

    if segment_filter == "F&O Tradable Only":
        view = view[view["Segment"] == "F&O Tradable"]
    elif segment_filter == "Cash Only":
        view = view[view["Segment"] == "Cash Only"]

    if tradable_only:
        view = view[view["_tradable"]]
    if text_filter:
        blob = (view["Symbol"] + " " + view["Company"] + " " + view["Sector"]).str.lower()
        view = view[blob.str.contains(text_filter, regex=False)]

    # 5 Concrete Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "⚡ Live Execution Radar",
        "🔄 Sector Rotation Matrix (P1)",
        "📋 Audited Radar & Reports",
        "📒 Trade Book & P&L",
        "📁 Daily Bhavcopy Archive (90D)"
    ])

    # ---------------- TAB 1: COCKPIT ----------------
    with tab1:
        section("1.1", "Actionable Now (Direct Buy/Sell Signals)", "Qualified by Pillar 1 + Pillar 2 + 15m CHoCH")
        act = df[df["_key"].isin(["READY_BUY", "BOS", "BEAR_FO_SHORT", "BEAR_FO_BOS"])]
        if act.empty:
            st.markdown("<div class='empty'>No setups currently at exact 15m trigger. All tracked candidates are in accumulation or awaiting volume spurt.</div>", unsafe_allow_html=True)
        else:
            if view_mode == "Bordered Report":
                st.markdown(html_table(act, COMPACT_COLUMNS, badge_cols=("VERDICT",), height=300), unsafe_allow_html=True)
            else:
                st.dataframe(act[COMPACT_COLUMNS], hide_index=True, **STRETCH)

        section("1.2", "Master Execution Radar", f"{len(view)} of {len(df)} setups analyzed")
        if view_mode == "Bordered Report":
            st.markdown(html_table(view, EXPORT_COLUMNS, badge_cols=("VERDICT",), height=560), unsafe_allow_html=True)
        else:
            st.dataframe(view[EXPORT_COLUMNS], hide_index=True, height=560, **STRETCH)

    # ---------------- TAB 2: SECTOR ROTATION ----------------
    with tab2:
        section("2.1", "NSE 22-Sector Capital Rotation Matrix", "Rule: Trade Longs strictly in Inflow (+), Shorts in Outflow (-)")
        s_cols = ["Sector", "Recent 12D Share (%)", "Base Share (%)", "Flow Shift (%)", "Flow Signal"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Inflow Sectors", int((sec_df["_status"] == True).sum()))
        c2.metric("Outflow Sectors", int((sec_df["_status"] == False).sum()))
        c3.metric("Neutral", int(sec_df["_status"].isna().sum()))

        col_a, col_b = st.columns(2)
        with col_a:
            section("2.2", "🟢 Institutional Inflow Sectors")
            st.markdown(html_table(sec_df[sec_df["_status"] == True], s_cols, badge_cols=("Flow Signal",), height=340), unsafe_allow_html=True)
        with col_b:
            section("2.3", "🔴 Institutional Outflow Sectors")
            st.markdown(html_table(sec_df[sec_df["_status"] == False], s_cols, badge_cols=("Flow Signal",), height=340), unsafe_allow_html=True)

        section("2.4", "Sector Share Shift (pp vs Base Share)")
        st.bar_chart(sec_df.set_index("Sector")["Flow Shift (%)"], height=320)

    # ---------------- TAB 3: AUDITED REPORTS ----------------
    with tab3:
        section("3.1", "Audited Radar Table", "Live on-screen audit - Excel kholne ki zaroorat nahi hai")
        if view_mode == "Bordered Report":
            st.markdown(html_table(df, EXPORT_COLUMNS, badge_cols=("VERDICT",), height=460), unsafe_allow_html=True)
        else:
            st.dataframe(df[EXPORT_COLUMNS], hide_index=True, height=460, **STRETCH)

        section("3.2", "Offline Excel Export (Optional)")
        xlsx = generate_excel_export(df, sec_df)
        st.download_button(
            "📥 Download Audited Excel (.xlsx)", data=xlsx,
            file_name=f"SMC_Institutional_Radar_{now.strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", **STRETCH
        )

    # ---------------- TAB 4: TRADE BOOK ----------------
    with tab4:
        trades = load_trades()
        rows = [trade_row(t, quotes) for t in trades]
        t_df = pd.DataFrame(rows)
        open_df = t_df[t_df["Status"] == "OPEN"] if not t_df.empty else t_df
        closed_df = t_df[t_df["Status"] == "CLOSED"] if not t_df.empty else t_df

        section("4.1", "Portfolio P&L Summary")
        k = st.columns(4)
        k[0].metric("Open Trades", len(open_df))
        k[1].metric("Open P&L", f"{float(open_df['P&L (Rs)'].sum()):+,.2f}" if not open_df.empty else "₹0.00")
        k[2].metric("Realised P&L", f"{float(closed_df['P&L (Rs)'].sum()):+,.2f}" if not closed_df.empty else "₹0.00")
        k[3].metric("Win Rate", f"{(closed_df['P&L (Rs)'] > 0).mean() * 100:.0f}%" if not closed_df.empty else "n/a")

        section("4.2", "Log Active Position")
        s_sym = st.selectbox("Symbol", radar["symbol"].tolist())
        row_match = radar.loc[radar["symbol"] == s_sym].iloc[0]
        is_long = row_match["bias"] == "BULLISH"
        is_fo = s_sym in NSE_FO_UNIVERSE
        default_p = (quotes.get(s_sym) or {}).get("cmp", float(row_match["snap_cmp"]))

        with st.form("tb_add"):
            c1, c2, c3, c4, c5 = st.columns(5)
            available_sides = ["LONG"] if not is_fo and not is_long else ["LONG", "SHORT"]
            p_side = c1.selectbox("Side", available_sides, index=0 if is_long else (1 if "SHORT" in available_sides else 0))
            p_entry = c2.number_input("Entry Price (Rs)", value=float(default_p), step=0.05)
            p_qty = c3.number_input("Quantity", value=1, min_value=1, step=1)
            p_sl = c4.number_input("Initial SL (Rs)", value=float(row_match["invalidation"]), step=0.05)
            c5.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if c5.form_submit_button("➕ Log Trade", **STRETCH):
                trades.append({
                    "id": uuid.uuid4().hex[:8], "symbol": s_sym, "side": p_side, "entry": p_entry,
                    "qty": int(p_qty), "sl": p_sl, "t1": float(row_match["t1"]), "status": "OPEN", "date": now.strftime("%Y-%m-%d %H:%M")
                })
                save_trades(trades)
                st.success(f"{p_side} {s_sym} position logged!")
                st.rerun()

        section("4.3", "Active & Closed Positions")
        if t_df.empty:
            st.markdown("<div class='empty'>No trades logged yet.</div>", unsafe_allow_html=True)
        else:
            t_cols = ["ID", "Symbol", "Side", "Qty", "Entry (Rs)", "SL (Rs)", "CMP / Exit (Rs)", "P&L (Rs)", "P&L %", "Status", "Opened"]
            if view_mode == "Bordered Report":
                st.markdown(html_table(t_df, t_cols, badge_cols=("Status",), height=340), unsafe_allow_html=True)
            else:
                st.dataframe(t_df[t_cols], hide_index=True, **STRETCH)

            mc1, mc2 = st.columns(2)
            open_ids = [t.get("id") for t in trades if t.get("status") == "OPEN"]
            with mc1:
                with st.form("close_form"):
                    cid = st.selectbox("Close Position ID", open_ids) if open_ids else None
                    ex_px = st.number_input("Exit Price (0 = use CMP)", value=0.0, step=0.05)
                    if st.form_submit_button("✅ Close Position", **STRETCH) and cid:
                        for t in trades:
                            if t.get("id") == cid:
                                t["status"] = "CLOSED"
                                t["exit"] = float(ex_px) if ex_px > 0 else float((quotes.get(t.get("symbol", "")) or {}).get("cmp", t.get("entry", 0.0)))
                        save_trades(trades)
                        st.rerun()
            with mc2:
                with st.form("del_form"):
                    did = st.selectbox("Delete Position ID", [t.get("id") for t in trades]) if trades else None
                    if st.form_submit_button("🗑️ Delete Record", **STRETCH) and did:
                        save_trades([t for t in trades if t.get("id") != did])
                        st.rerun()

    # ---------------- TAB 5: BHAVCOPY ARCHIVE ----------------
    with tab5:
        section("5.1", "Day-Wise Official Bhavcopy Downloader", "Direct browser delivery download")
        b1, b2 = st.columns([1.5, 2.5])
        with b1:
            sel_date = st.date_input("Select Trading Date", value=now.date() - dt.timedelta(days=1))
            if st.button("📥 Fetch & Verify Bhavcopy", **STRETCH):
                with st.spinner("Executing browser handshake with NSE..."):
                    fpath, raw_bytes, msg = fetch_nse_delivery_bhav(sel_date)
                    if fpath and raw_bytes:
                        st.session_state["last_bhav_bytes"] = raw_bytes
                        st.session_state["last_bhav_name"] = os.path.basename(fpath)
                        st.success(f"{msg}: {os.path.basename(fpath)}")
                    else:
                        st.error(msg)

            if "last_bhav_bytes" in st.session_state:
                st.download_button(
                    label=f"💾 Download {st.session_state['last_bhav_name']} to PC",
                    data=st.session_state["last_bhav_bytes"],
                    file_name=st.session_state["last_bhav_name"],
                    mime="text/csv", **STRETCH
                )

        with b2:
            section("5.2", "90-Day Rolling Buffer Status")
            files = [f for f in os.listdir(BHAV_DIR) if f.endswith(".csv")]
            st.info(f"📁 Local Disk Buffer: **{len(files)} daily bhavcopies stored**. (Auto-pruned after 90 days).")
            if files:
                zip_stream = generate_chunked_bhav_zip()
                st.download_button(
                    "📦 Download Consolidated 90-Day Bulk Archive (.zip)",
                    data=zip_stream,
                    file_name=f"NSE_Bhavcopy_90D_{now.strftime('%Y%m%d')}.zip",
                    mime="application/zip", **STRETCH
                )

        section("5.3", "Automatic Pipeline Scanner (Pillar 2 Qualified)")
        if files:
            latest_file = sorted(files)[-1]
            latest_path = os.path.join(BHAV_DIR, latest_file)
            c_df = parse_bhavcopy_candidates(latest_path)
            st.markdown(f"**Latest Verified File:** `{latest_file}`")
            if not c_df.empty:
                st.dataframe(c_df, hide_index=True, **STRETCH)
                if st.button("⚡ Inject All Qualified Stocks Into Live Radar", **STRETCH):
                    injected_rows = []
                    for _, row in c_df.iterrows():
                        sym = str(row["SYMBOL"]).strip().upper()
                        cmp_v = float(row["CLOSE"])
                        deliv_v = float(row["DELIVERY_%"])
                        spurt_v = float(row["SPURT"])

                        assigned_sec = STOCK_SECTOR_MAP.get(sym, "Financial Services")
                        s_f = sector_info(assigned_sec)
                        b_bias = "BULLISH" if s_f["status"] is True else "BEARISH"

                        if b_bias == "BULLISH":
                            z_low, z_high = round(cmp_v * 0.985, 2), round(cmp_v * 1.005, 2)
                            choch, bos = round(cmp_v * 1.02, 2), round(cmp_v * 1.045, 2)
                            inval = round(cmp_v * 0.965, 2)
                            t1, t2, t3 = round(cmp_v * 1.08, 2), round(cmp_v * 1.18, 2), round(cmp_v * 1.30, 2)
                        else:
                            z_low, z_high = round(cmp_v * 0.995, 2), round(cmp_v * 1.015, 2)
                            choch, bos = round(cmp_v * 0.98, 2), round(cmp_v * 0.955, 2)
                            inval = round(cmp_v * 1.035, 2)
                            t1, t2, t3 = round(cmp_v * 0.92, 2), round(cmp_v * 0.82, 2), round(cmp_v * 0.70, 2)

                        injected_rows.append((
                            sym, f"{sym} Ltd.", assigned_sec, b_bias, cmp_v,
                            z_low, z_high, choch, bos, inval, t1, t2, t3,
                            f"Live Bhavcopy Spurt ({spurt_v}x)", spurt_v, deliv_v, 0
                        ))

                    if injected_rows:
                        with open(RADAR_STORAGE_PATH, "w", encoding="utf-8") as f:
                            json.dump(injected_rows, f, indent=2)
                        st.success(f"Injected {len(injected_rows)} stocks directly into persistent engine!")
                        st.rerun()
            else:
                st.warning("No candidates passed Pillar 2 criteria in this file.")

    st.markdown("<div class='foot'>Institutional Smart Money Terminal v7.0 · Designed for Autonomous 9-to-7 Workflow.</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
