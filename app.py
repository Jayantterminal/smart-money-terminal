"""
Institutional Smart Money Terminal (v3.0 - Full Suite)
---------------------------------------------------------
Framework (Three-Pillar Institutional SMC):
  Pillar 1: Sector Capital Rotation Matrix (Inflow vs Outflow)
  Pillar 2: Cash Delivery Spurt Filter (Deliv >= 45%, Spurt >= 2.0x)
  Pillar 3: Micro Execution Engine:
            - Bullish: Smart Money Accumulation Zone, 15m CHoCH, Bullish BOS
            - Bearish: Distribution Zone, Bearish Breakdown / BOS
"""
from __future__ import annotations

import datetime as dt
import hmac
import io
import json
import os
import uuid

import numpy as np
import openpyxl
import pandas as pd
import streamlit as st
import yfinance as yf
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from packaging.version import Version

# ==========================================================
# CONSTANTS & CONFIGURATION
# ==========================================================
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")
CANDLE_MIN = 15
MIN_DELIVERY_PCT = 45.0
MIN_SPURT = 2.0
STALE_DEVIATION_PCT = 15.0
MAX_LOGIN_ATTEMPTS = 5
LEGACY_PASSWORD = "2000"
TRADE_BOOK_PATH = "data/active_trades.json"

# Pillar 1 - 6-Fortnight Institutional Capital Shift Tracker
SECTOR_FLOW_MATRIX = {
    "Financial Services": {"status": True, "shift": "+2.8x Inflow", "fortnights_trend": "Inflow Accumulation"},
    "Oil Gas & Consumable Fuels": {"status": True, "shift": "+2.1x Inflow", "fortnights_trend": "Sustained Inflow"},
    "Consumer Services": {"status": True, "shift": "+1.9x Inflow", "fortnights_trend": "New Rotation Entry"},
    "Construction Materials": {"status": True, "shift": "+1.7x Inflow", "fortnights_trend": "Inflow Accumulation"},
    "Construction": {"status": True, "shift": "+1.5x Inflow", "fortnights_trend": "Early Inflow Stage"},
    "Healthcare": {"status": True, "shift": "+1.4x Inflow", "fortnights_trend": "Defensive Inflow"},
    "Capital Goods": {"status": False, "shift": "-1.8x Outflow", "fortnights_trend": "Capital Outflow"},
    "Automobile and Auto Components": {"status": False, "shift": "-2.2x Outflow", "fortnights_trend": "Distribution Phase"},
    "Chemicals": {"status": False, "shift": "-1.5x Outflow", "fortnights_trend": "Outflow Markdown"},
    "Consumer Durables": {"status": False, "shift": "-1.3x Outflow", "fortnights_trend": "Outflow Phase"},
    "Information Technology": {"status": False, "shift": "-2.6x Outflow", "fortnights_trend": "Aggressive Outflow"},
    "Fast Moving Consumer Goods": {"status": False, "shift": "-1.1x Outflow", "fortnights_trend": "Capital Pullout"},
}

SECTOR_FLOW = {k: v["status"] for k, v in SECTOR_FLOW_MATRIX.items()}

# Master Universe (Bullish & Bearish SMC Parameters)
RADAR_COLUMNS = [
    "symbol", "company", "sector", "bias", "snap_cmp", 
    "zone_low", "zone_high", "choch", "bos", "invalidation",
    "t1", "t2", "t3", "remark", "spurt", "deliv", "age_days"
]

RADAR_ROWS = [
    # Bullish Inflow Aligned Setups
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

    # Bearish / Outflow Breakdown Setups
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
    ("EMAMILTD", "Emami Ltd.", "Fast Moving Consumer Goods", "BEARISH", 372.65, 375.00, 368.00, 362.00, 355.00, 388.00, 342.00, 330.00, 315.00, "FMCG capital pullout, lower low expansion", 2.32, 52.9, 1)
]

RANK = {
    "ACTIVE": 0, "BOS": 1, "EXTENDED": 2, "ZONE": 3, "PRE": 4,
    "BELOW": 5, "BEAR_ACTIVE": 6, "BEAR_BOS": 7, "NODATA": 8, "STALE": 9, "INVALID": 10, "BLOCKED": 11
}

# ==========================================================
# HELPERS & AUTH
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

    st.markdown("<h2 style='text-align:center;margin-top:50px;'>🔒 Terminal Access Gate</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#8B949E;'>Enter terminal master security key.</p>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("auth_form"):
            pwd_in = st.text_input("Password", type="password", placeholder="Enter key...")
            submitted = st.form_submit_button("Unlock Terminal", **STRETCH)
        if submitted:
            master = str(st.secrets.get("TERMINAL_PASSWORD", os.environ.get("TERMINAL_PASSWORD", LEGACY_PASSWORD)))
            if st.session_state["failed_attempts"] >= MAX_LOGIN_ATTEMPTS:
                st.error("Too many failed attempts. Reload page.")
            elif hmac.compare_digest(pwd_in.encode("utf-8"), master.encode("utf-8")):
                st.session_state["authenticated"] = True
                st.session_state["failed_attempts"] = 0
                st.rerun()
            else:
                st.session_state["failed_attempts"] += 1
                left = MAX_LOGIN_ATTEMPTS - st.session_state["failed_attempts"]
                st.error(f"Invalid security key. Attempts left: {max(left, 0)}")
    return False

# ==========================================================
# MARKET REGIME & QUOTE FETCHER
# ==========================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_market_regime() -> dict:
    try:
        nifty = yf.Ticker("^NSEI").history(period="6mo", interval="1d")["Close"].dropna()
        sensex = yf.Ticker("^BSESN").history(period="6mo", interval="1d")["Close"].dropna()
    except Exception:
        return {"ok": False}
    if len(nifty) < 50 or len(sensex) < 2:
        return {"ok": False}

    n_cmp, n_prev = float(nifty.iloc[-1]), float(nifty.iloc[-2])
    s_cmp, s_prev = float(sensex.iloc[-1]), float(sensex.iloc[-2])
    ema20 = float(nifty.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(nifty.ewm(span=50, adjust=False).mean().iloc[-1])

    if n_cmp >= ema20 and n_cmp >= ema50:
        regime = "Bullish Markup"
    elif n_cmp < ema20 and n_cmp < ema50:
        regime = "Bearish Markdown"
    else:
        regime = "Consolidation / Range"
    return {
        "ok": True, "regime": regime,
        "nifty": n_cmp, "nifty_chg": (n_cmp / n_prev - 1) * 100,
        "sensex": s_cmp, "sensex_chg": (s_cmp / s_prev - 1) * 100,
        "ema20": ema20, "ema50": ema50,
    }

@st.cache_data(ttl=120, show_spinner=False)
def fetch_live_quotes(symbols: tuple[str, ...]) -> dict:
    fetched_at = now_ist()
    empty = {"quotes": {}, "fetched_at": fetched_at}
    if not symbols:
        return empty
    tickers = [f"{s}.NS" for s in symbols]
    try:
        raw = yf.download(
            tickers, period="5d", interval=f"{CANDLE_MIN}m", group_by="ticker",
            auto_adjust=False, progress=False, threads=True,
        )
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
# EVALUATION CORE (BULLISH & BEARISH CHoCH + BOS)
# ==========================================================
def build_radar() -> pd.DataFrame:
    return pd.DataFrame(RADAR_ROWS, columns=RADAR_COLUMNS)

def evaluate_setups(radar: pd.DataFrame, quotes: dict, max_chase_pct: float,
                    stale_pct: float = STALE_DEVIATION_PCT) -> pd.DataFrame:
    out = []
    for r in radar.to_dict("records"):
        sym = r["symbol"]
        bias = r["bias"]
        q = quotes.get(sym)
        cmp_ = q["cmp"] if q else None
        last_close = q["last_close"] if q else None

        flow_info = SECTOR_FLOW_MATRIX.get(r["sector"], {"status": None, "shift": "Unmapped"})
        flow_status = flow_info["status"]
        flow_label = f"☑️ Inflow ({flow_info['shift']})" if flow_status is True else f"⚠️ Outflow ({flow_info['shift']})"
        
        p2_pass = r["deliv"] >= MIN_DELIVERY_PCT and r["spurt"] >= MIN_SPURT
        # Bullish setups require Sector Inflow; Bearish setups track Sector Outflow
        tradable = (flow_status is True and p2_pass) if bias == "BULLISH" else (flow_status is False and p2_pass)

        entry_ref = r["choch"]
        risk = abs(entry_ref - r["invalidation"])
        t1_pct = abs((r["t1"] / entry_ref - 1) * 100)
        t2_pct = abs((r["t2"] / entry_ref - 1) * 100)
        t3_pct = abs((r["t3"] / entry_ref - 1) * 100)
        rr_t1 = abs(r["t1"] - entry_ref) / risk if risk > 0 else np.nan

        dev_pct = (cmp_ / r["snap_cmp"] - 1) * 100 if cmp_ is not None else None
        day_pct = (cmp_ / q["prev_close"] - 1) * 100 if q and q.get("prev_close") else None

        # Logic for Bullish vs Bearish Structure
        if cmp_ is None or last_close is None:
            key, status, action = "NODATA", "📴 NO LIVE DATA", "WAIT – FEED UNAVAILABLE"
        elif abs(cmp_ / r["snap_cmp"] - 1) * 100 > stale_pct:
            key, status, action = "STALE", "⚠️ LEVELS STALE", "REFRESH RADAR SNAPSHOT"
        
        elif bias == "BULLISH":
            if flow_status is not True:
                key, status, action = "BLOCKED", "⛔ BLOCKED – Sector Outflow", "AVOID LONGS (Pillar 1)"
            elif not p2_pass:
                key, status, action = "BLOCKED", "⛔ BLOCKED – Delivery Spurt", "AVOID LONGS (Pillar 2)"
            elif last_close < r["invalidation"]:
                key, status, action = "INVALID", "❌ INVALIDATED", "AVOID – SUPPORT BROKEN"
            elif last_close >= r["bos"]:
                key, status, action = "BOS", "🚀 MOMENTUM (BULLISH BOS)", f"TREND EXPANSION > {r['bos']:.2f}"
            elif last_close >= r["choch"]:
                ext = (last_close / r["choch"] - 1) * 100
                if ext > max_chase_pct:
                    key, status, action = "EXTENDED", "🟠 EXTENDED – NO CHASE", f"PULLBACK WAIT (+{ext:.1f}%)"
                else:
                    key, status, action = "ACTIVE", "⚡ ACTIVE (BULLISH CHoCH)", "BUY ENTRY (15m CHoCH CONFIRMED)"
            elif r["zone_low"] <= cmp_ <= r["zone_high"]:
                key, status, action = "ZONE", "🟢 IN BUY ZONE", "ACCUMULATING – WAIT CHoCH"
            elif cmp_ > r["zone_high"]:
                key, status = "PRE", "🟡 PRE-TRIGGER"
                action = "CHoCH TOUCHED – WAIT 15m CLOSE" if cmp_ >= r["choch"] else "WATCHING NEAR TRIGGER"
            else:
                key, status, action = "BELOW", "⚪ BELOW BUY ZONE", "TRACKING"

        else: # BEARISH
            if flow_status is not False:
                key, status, action = "BLOCKED", "⛔ BLOCKED – Sector Inflow", "AVOID SHORTS (Pillar 1)"
            elif not p2_pass:
                key, status, action = "BLOCKED", "⛔ BLOCKED – Distribution Spurt", "AVOID SHORTS (Pillar 2)"
            elif last_close > r["invalidation"]:
                key, status, action = "INVALID", "❌ INVALIDATED", "AVOID – RESISTANCE SWEPT"
            elif last_close <= r["bos"]:
                key, status, action = "BEAR_BOS", "🔻 SHORT/EXIT (BEARISH BOS)", f"MARKDOWN EXPANSION < {r['bos']:.2f}"
            elif last_close <= r["choch"]:
                key, status, action = "BEAR_ACTIVE", "🔻 ACTIVE (BEARISH CHoCH)", "EXIT / SHORT (15m BREAKDOWN)"
            elif r["zone_high"] >= cmp_ >= r["zone_low"]:
                key, status, action = "ZONE", "🔴 IN DISTRIBUTION ZONE", "DISTRIBUTING – WAIT BREAKDOWN"
            else:
                key, status, action = "PRE", "⚪ TRACKING SUPPLY", "SUPPLY RESISTANCE INTACT"

        out.append({
            "Symbol": sym, "Company": r["company"], "Sector": r["sector"], "Bias": bias,
            "Sector Flow": flow_label, "Tradable (3-Pillar)": "✅" if tradable else "—",
            "Status": status, "Action": action,
            "CMP (Rs)": cmp_, "Day %": day_pct,
            "Smart Money Zone (Rs)": f"₹{r['zone_low']:.2f} – ₹{r['zone_high']:.2f}",
            "CHoCH Trigger (Rs)": r["choch"], "BOS Level (Rs)": r["bos"],
            "Last 15m Close (Rs)": last_close, "Invalidation / SL (Rs)": r["invalidation"],
            "Target 1": r["t1"], "Target 2": r["t2"], "Target 3": r["t3"],
            "T1 %": t1_pct, "T2 %": t2_pct, "T3 %": t3_pct, "R:R (T1)": rr_t1,
            "Volume Spurt (x)": r["spurt"], "Delivery %": r["deliv"], "Radar Age (Days)": r["age_days"],
            "Catalyst Remark": r["remark"], "Radar Snapshot CMP (Rs)": r["snap_cmp"],
            "_key": key, "_rank": RANK.get(key, 99), "_tradable": tradable,
        })
    df = pd.DataFrame(out)
    return df.sort_values(["_rank", "Volume Spurt (x)"], ascending=[True, False]).reset_index(drop=True)

# ==========================================================
# EXCEL GENERATOR (MAINTAINED AS AN OPTION)
# ==========================================================
EXPORT_COLUMNS = [
    "Symbol", "Company", "Sector", "Bias", "Sector Flow", "Tradable (3-Pillar)", "Status", "Action",
    "CMP (Rs)", "Day %", "Smart Money Zone (Rs)", "CHoCH Trigger (Rs)", "BOS Level (Rs)", "Last 15m Close (Rs)",
    "Invalidation / SL (Rs)", "Target 1", "Target 2", "Target 3", "T1 %", "T2 %", "T3 %", "R:R (T1)",
    "Volume Spurt (x)", "Delivery %", "Radar Age (Days)", "Catalyst Remark"
]

def generate_excel_export(df: pd.DataFrame) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Audited_SMC_Radar"
    ws.append(EXPORT_COLUMNS)

    head_fill = PatternFill(start_color="161B22", end_color="161B22", fill_type="solid")
    head_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    for c in range(1, len(EXPORT_COLUMNS) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = head_fill, head_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    clean = df.astype(object).where(pd.notna(df), None)
    for i, rec in enumerate(clean.to_dict("records"), start=2):
        ws.append([rec[c] for c in EXPORT_COLUMNS])
        for j in range(1, len(EXPORT_COLUMNS) + 1):
            cell = ws.cell(row=i, column=j)
            cell.alignment = Alignment(vertical="center")

    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[letter].width = min(max(longest + 3, 11), 50)
    ws.freeze_panes = "C2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

# ==========================================================
# TRADE BOOK ENGINE
# ==========================================================
def load_trades():
    if os.path.exists(TRADE_BOOK_PATH):
        try:
            with open(TRADE_BOOK_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_trades(trades):
    os.makedirs(os.path.dirname(TRADE_BOOK_PATH), exist_ok=True)
    with open(TRADE_BOOK_PATH, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)

# ==========================================================
# USER INTERFACE
# ==========================================================
CSS = """
<style>
  div[data-testid="stMetric"]{background:#161B22;border:1px solid #30363D;padding:14px 18px;border-radius:6px;}
  div[data-testid="stMetricLabel"]{color:#8B949E;font-size:13px;font-weight:600;text-transform:uppercase;}
  div[data-testid="stMetricValue"]{color:#F0F6FC;font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;}
  .stTabs [data-baseweb="tab-list"]{gap:8px;}
  .stTabs [data-baseweb="tab"]{background-color:#161B22;border-radius:4px;color:#C9D1D9;padding:8px 16px;}
  .stTabs [aria-selected="true"]{background-color:#21262D !important;color:#58A6FF !important;border-bottom:2px solid #58A6FF !important;}
</style>
"""

COLUMN_CONFIG = {
    "CMP (Rs)": st.column_config.NumberColumn(format="%.2f"),
    "Day %": st.column_config.NumberColumn(format="%.2f"),
    "CHoCH Trigger (Rs)": st.column_config.NumberColumn(format="%.2f"),
    "BOS Level (Rs)": st.column_config.NumberColumn(format="%.2f"),
    "Last 15m Close (Rs)": st.column_config.NumberColumn(format="%.2f"),
    "Invalidation / SL (Rs)": st.column_config.NumberColumn(format="%.2f"),
    "Target 1": st.column_config.NumberColumn(format="%.2f"),
    "Target 2": st.column_config.NumberColumn(format="%.2f"),
    "Target 3": st.column_config.NumberColumn(format="%.2f"),
    "T1 %": st.column_config.NumberColumn(format="%.1f"),
    "T2 %": st.column_config.NumberColumn(format="%.1f"),
    "T3 %": st.column_config.NumberColumn(format="%.1f"),
    "R:R (T1)": st.column_config.NumberColumn(format="%.2f"),
    "Volume Spurt (x)": st.column_config.NumberColumn(format="%.2f"),
    "Delivery %": st.column_config.NumberColumn(format="%.1f"),
}

def main():
    st.set_page_config(page_title="Institutional Smart Money Terminal", page_icon="⚡", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    if not auth_gate():
        st.stop()

    radar = build_radar()
    live = fetch_live_quotes(tuple(radar["symbol"]))
    quotes, fetched_at = live["quotes"], live["fetched_at"]
    
    with st.sidebar:
        st.header("⚙️ Controls")
        if st.button("🔄 Refresh Live Data", **STRETCH):
            st.cache_data.clear()
            st.rerun()
        bias_filter = st.selectbox("Trading Bias Filter", ["All Setups", "BULLISH Setups Only", "BEARISH Setups Only"])
        tradable_only = st.toggle("Tradable Only (P1 + P2 Pass)", value=False)
        max_chase = st.slider("Max Extension Above Trigger (%)", 0.5, 5.0, 2.0, 0.5)
        text_filter = st.text_input("Search Symbol / Sector").strip().lower()
        if st.button("🔒 Lock Terminal", **STRETCH):
            st.session_state["authenticated"] = False
            st.rerun()

    df = evaluate_setups(radar, quotes, max_chase)
    regime = get_market_regime()
    now = now_ist()
    mkt = market_state(now)
    regime_txt = f"{regime['regime']} | Nifty {regime['nifty']:,.0f} ({fmt_pct(regime['nifty_chg'])})" if regime["ok"] else "Index feed offline"

    # Terminal Header
    st.title("⚡ Institutional Smart Money Terminal")
    st.markdown(f"**Last Sync:** `{fetched_at.strftime('%d-%b-%Y | %I:%M:%S %p IST')}` | **Market:** `{mkt}` | **Regime:** `{regime_txt}`")

    # Metric Row (Preserving Layout)
    m = st.columns(6)
    m[0].metric("Tracked", len(df))
    m[1].metric("Tradable (P1+P2)", int(df["_tradable"].sum()))
    m[2].metric("⚡ Active Triggers", int((df["_key"].isin(["ACTIVE", "BEAR_ACTIVE"])).sum()))
    m[3].metric("🚀 BOS Momentum", int((df["_key"].isin(["BOS", "BEAR_BOS"])).sum()))
    m[4].metric("Inflow Aligned", int(df["Sector Flow"].str.contains("Inflow").sum()))
    m[5].metric("Blocked", int((df["_key"] == "BLOCKED").sum()))
    st.markdown("---")

    # Filtered DataFrame
    view = df.copy()
    if bias_filter == "BULLISH Setups Only":
        view = view[view["Bias"] == "BULLISH"]
    elif bias_filter == "BEARISH Setups Only":
        view = view[view["Bias"] == "BEARISH"]
    if tradable_only:
        view = view[view["_tradable"]]
    if text_filter:
        blob = (view["Symbol"] + " " + view["Company"] + " " + view["Sector"]).str.lower()
        view = view[blob.str.contains(text_filter, regex=False)]

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Live Accumulation Radar",
        "🔄 Sector Capital Rotation (Pillar 1)",
        "📋 Audited Radar & Reports",
        "📒 Trade Book"
    ])

    with tab1:
        st.subheader("Smart Money Delivery Spurt & 15m CHoCH / BOS Radar")
        st.caption("Pillar 3 Rule: Bullish entry requires closed 15m candle > CHoCH. Bullish BOS marks continuation. Bearish marks markdown distribution.")
        show_cols = [c for c in EXPORT_COLUMNS if c in view.columns]
        st.dataframe(view[show_cols], hide_index=True, height=560, column_config=COLUMN_CONFIG, **STRETCH)

    with tab2:
        st.subheader("Pillar 1: 6-Fortnights Sector Capital Rotation Matrix")
        st.caption("Capital flow dictates market trend. Only plan Longs in Net Inflow sectors and Shorts/Exits in Net Outflow sectors.")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🟢 Institutional INFLOW Sectors (+Shift)")
            inflow_data = [{"Sector": k, "Flow Shift": v["shift"], "Institutional Trend": v["fortnights_trend"]} 
                           for k, v in SECTOR_FLOW_MATRIX.items() if v["status"]]
            st.dataframe(pd.DataFrame(inflow_data), hide_index=True, **STRETCH)
        with c2:
            st.markdown("#### 🔴 Institutional OUTFLOW Sectors (-Shift)")
            outflow_data = [{"Sector": k, "Flow Shift": v["shift"], "Institutional Trend": v["fortnights_trend"]} 
                            for k, v in SECTOR_FLOW_MATRIX.items() if not v["status"]]
            st.dataframe(pd.DataFrame(outflow_data), hide_index=True, **STRETCH)

    with tab3:
        st.subheader("📋 Audited Radar Data (Live On-Screen Audit)")
        st.markdown("Complete audited institutional data. Aapko Excel download karne ki zaroorat nahi hai, sabhi parameters neeche live accessible hain:")
        st.dataframe(df[EXPORT_COLUMNS], hide_index=True, height=450, column_config=COLUMN_CONFIG, **STRETCH)
        
        st.markdown("---")
        st.markdown("#### Optional Offline Export")
        xlsx = generate_excel_export(df)
        st.download_button(
            "📥 Download Audited Excel (.xlsx)", data=xlsx,
            file_name=f"SMC_Institutional_Radar_{now.strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", **STRETCH
        )

    with tab4:
        st.subheader("Position Tracker & Trade Book")
        if "trades" not in st.session_state:
            st.session_state.trades = load_trades()
        trades = st.session_state.trades
        
        with st.form("tb_add"):
            c1, c2, c3, c4 = st.columns(4)
            s_sym = c1.selectbox("Symbol", radar["symbol"].tolist())
            row_match = radar.loc[radar["symbol"] == s_sym].iloc[0]
            default_p = quotes.get(s_sym, {}).get("cmp", row_match["snap_cmp"])
            p_entry = c2.number_input("Entry Price (Rs)", value=float(default_p), step=0.05)
            p_qty = c3.number_input("Quantity", value=1, min_value=1, step=1)
            p_sl = c4.number_input("Initial Invalidation / SL", value=float(row_match["invalidation"]), step=0.05)
            if st.form_submit_button("➕ Log Position", **STRETCH):
                trades.append({
                    "id": uuid.uuid4().hex[:8], "symbol": s_sym, "entry": p_entry,
                    "qty": p_qty, "sl": p_sl, "t1": row_match["t1"], "t2": row_match["t2"],
                    "t3": row_match["t3"], "status": "OPEN", "date": now.strftime("%Y-%m-%d %H:%M")
                })
                save_trades(trades)
                st.success(f"{s_sym} position added!")
                st.rerun()

        if trades:
            t_df = pd.DataFrame(trades)
            st.dataframe(t_df, hide_index=True, **STRETCH)
        else:
            st.info("No active trades logged.")

if __name__ == "__main__":
    main()
