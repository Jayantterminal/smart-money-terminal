"""
Institutional Smart Money Terminal  (v2)
----------------------------------------
Framework (3 pillars):
  P1  Sector capital rotation  -> trade only sectors with institutional INFLOW
  P2  Cash delivery spurt      -> delivery % >= 45  AND  spurt >= 2.0x
  P3  Buy range + 15m CHoCH    -> entry only on a CLOSED 15m candle above the CHoCH trigger

Run:      streamlit run app.py
Needs:    streamlit>=1.40, pandas, numpy, yfinance, openpyxl, requests(optional)
Password: set TERMINAL_PASSWORD in .streamlit/secrets.toml (or env var).
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
# CONSTANTS
# ==========================================================
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")
CANDLE_MIN = 15                 # CHoCH timeframe (minutes)
MIN_DELIVERY_PCT = 45.0         # Pillar 2
MIN_SPURT = 2.0                 # Pillar 2
STALE_DEVIATION_PCT = 15.0      # live price vs radar snapshot -> levels considered stale
MAX_LOGIN_ATTEMPTS = 5
LEGACY_PASSWORD = "2000"        # fallback ONLY if no secret/env var is configured
TRADE_BOOK_PATH = "data/active_trades.json"

# Pillar 1 - single source of truth. True = institutional INFLOW, False = OUTFLOW.
# Update this once per fortnight from your 6-fortnight rotation study.
SECTOR_FLOW: dict[str, bool] = {
    "Oil Gas & Consumable Fuels": True,
    "Financial Services": True,
    "Consumer Services": True,
    "Construction Materials": True,
    "Construction": True,
    "Healthcare": True,
    "Capital Goods": False,
    "Chemicals": False,
    "Automobile and Auto Components": False,
    "Consumer Durables": False,
    "Information Technology": False,
    "Fast Moving Consumer Goods": False,
}

# Accumulation universe (snapshot from Bhavcopy study).
RADAR_COLUMNS = [
    "symbol", "company", "sector", "snap_cmp", "buy_low", "buy_high", "choch", "support",
    "t1", "t2", "t3", "remark", "spurt", "deliv", "age_days",
]
RADAR_ROWS = [
    ("CASTROLIND", "Castrol India Ltd.", "Oil Gas & Consumable Fuels", 199.04, 196.00, 201.00, 204.50, 191.00, 215.00, 226.00, 240.00, "Strong cash delivery, deserve a spot on watchlist", 2.12, 57.4, 1),
    ("AIAENG", "AIA Engineering Ltd.", "Capital Goods", 3824.40, 3790.00, 3845.00, 3950.00, 3710.00, 4180.00, 4350.00, 4580.00, "Mining consumables order expansion, heavy block deals", 2.25, 52.4, 1),
    ("ANURAS", "Anuras Chemicals Ltd.", "Chemicals", 1163.70, 1150.00, 1175.00, 1195.00, 1135.00, 1280.00, 1340.00, 1410.00, "Specialty chemical demand & base level institutional support", 3.12, 58.1, 1),
    ("ATHERENERG", "Ather Energy Ltd.", "Automobile and Auto Components", 1406.10, 1385.00, 1420.00, 1455.00, 1350.00, 1560.00, 1640.00, 1740.00, "EV 2W delivery volume spike at baseline support", 2.05, 49.5, 1),
    ("BAJAJ-AUTO", "Bajaj Auto Ltd.", "Automobile and Auto Components", 10045.00, 9950.00, 10120.00, 10350.00, 9750.00, 11200.00, 11800.00, 12500.00, "Premium 2W exports rise, institutional base building", 2.25, 53.0, 1),
    ("BAJAJFINSV", "Bajaj Finserv Ltd.", "Financial Services", 1732.60, 1715.00, 1745.00, 1785.00, 1680.00, 1920.00, 2040.00, 2180.00, "Lending & insurance premium growth momentum", 2.35, 62.0, 1),
    ("BAJAJHFL", "Bajaj Housing Finance Ltd.", "Financial Services", 82.91, 81.80, 83.60, 86.40, 79.50, 95.00, 102.00, 110.00, "Institutional absorption post-listing consolidation", 2.90, 61.2, 1),
    ("BAJFINANCE", "Bajaj Finance Ltd.", "Financial Services", 7250.00, 7180.00, 7290.00, 7450.00, 7020.00, 7900.00, 8250.00, 8650.00, "AUM expansion & consumer finance delivery spurt", 2.70, 65.0, 1),
    ("BEL", "Bharat Electronics Ltd.", "Capital Goods", 383.10, 380.00, 386.00, 392.50, 375.00, 416.00, 435.00, 465.00, "Defence order book surge, awaiting 15m breakout above 392.5", 2.80, 55.4, 4),
    ("CANBK", "Canara Bank", "Financial Services", 118.36, 116.50, 119.50, 123.50, 113.00, 132.00, 142.00, 154.00, "PSU Bank credit expansion & low credit cost accumulation", 2.45, 57.0, 1),
    ("COFORGE", "Coforge Ltd.", "Information Technology", 7850.00, 7780.00, 7920.00, 8080.00, 7580.00, 8500.00, 8900.00, 9300.00, "Midcap IT client deal signing & delivery expansion", 2.30, 50.5, 1),
    ("CUPID", "Cupid Ltd.", "Consumer Durables", 92.40, 91.00, 93.50, 96.50, 88.50, 105.00, 112.00, 120.00, "Capacity expansion & retail distribution ramp-up", 2.20, 52.8, 1),
    ("EIHOTEL", "EIH Associated Hotels", "Consumer Services", 880.00, 868.00, 890.00, 908.00, 850.00, 965.00, 1020.00, 1090.00, "Hospitality sector inflow shift, delivery build-up", 2.35, 55.0, 1),
    ("ELECTCAST", "Electrosteel Castings Ltd.", "Capital Goods", 74.54, 73.00, 75.50, 77.80, 71.50, 84.00, 89.00, 96.00, "Brokerage houses se target upgrade & buy call", 2.46, 47.4, 1),
    ("EMAMILTD", "Emami Ltd.", "Fast Moving Consumer Goods", 372.65, 368.00, 375.00, 386.00, 361.00, 425.00, 445.00, 470.00, "Price rise, lower level valuation support", 2.32, 52.9, 1),
    ("ENTERO", "Entero Healthcare Solutions", "Consumer Services", 1145.00, 1130.00, 1155.00, 1175.00, 1105.00, 1240.00, 1300.00, 1380.00, "Healthcare logistics expansion & institutional absorption", 2.65, 58.2, 1),
    ("HDFCBANK", "HDFC Bank Ltd.", "Financial Services", 1680.00, 1665.00, 1692.00, 1718.00, 1635.00, 1790.00, 1850.00, 1920.00, "Deposit growth uptick, heavy FPI absorption", 3.40, 72.1, 1),
    ("ICICIBANK", "ICICI Bank Ltd.", "Financial Services", 1285.00, 1272.00, 1294.00, 1315.00, 1250.00, 1380.00, 1430.00, 1490.00, "Strong NIMs stability & sustained institutional delivery", 2.95, 69.0, 1),
    ("IIFLCAPS", "IIFL Capital Services Ltd.", "Financial Services", 345.60, 340.00, 348.00, 354.00, 332.00, 375.00, 395.00, 420.00, "Institutional block deal / heavy stake accumulation", 2.40, 66.4, 1),
    ("IKS", "IKS Health", "Information Technology", 1420.00, 1400.00, 1435.00, 1465.00, 1370.00, 1560.00, 1640.00, 1720.00, "IT healthcare services steady institutional base", 2.20, 48.1, 1),
    ("INDHOTEL", "Indian Hotels Co Ltd.", "Consumer Services", 718.00, 710.00, 724.00, 738.00, 698.00, 785.00, 820.00, 855.00, "Share price rise 2.2%: valuation and sector rotation positive", 2.40, 61.3, 1),
    ("JKCEMENT", "JK Cement Ltd.", "Construction Materials", 4350.00, 4310.00, 4390.00, 4465.00, 4220.00, 4700.00, 4900.00, 5150.00, "Capacity commissioning and strong regional pricing", 2.40, 63.5, 1),
    ("KAJARIACER", "Kajaria Ceramics Ltd.", "Consumer Durables", 1225.10, 1210.00, 1235.00, 1255.00, 1180.00, 1315.00, 1380.00, 1450.00, "Fundamentals & sector valuation expansion", 3.10, 68.5, 1),
    ("KOTAKBANK", "Kotak Mahindra Bank", "Financial Services", 1820.00, 1805.00, 1835.00, 1858.00, 1775.00, 1940.00, 2010.00, 2100.00, "Tech embargo resolution benefits & loan growth pickup", 2.75, 62.1, 1),
    ("LENSKART", "Lenskart Solutions", "Consumer Durables", 385.00, 380.00, 389.00, 398.00, 368.00, 430.00, 455.00, 485.00, "Retail expansion footprint & strong offline same-store sales", 2.85, 64.0, 1),
    ("NATCOPHARM", "Natco Pharma Ltd.", "Healthcare", 1410.00, 1395.00, 1425.00, 1450.00, 1365.00, 1540.00, 1620.00, 1700.00, "US generic approvals and steady formulation cash flows", 2.85, 61.0, 1),
    ("PNCINFRA", "PNC Infratech Ltd.", "Construction", 138.16, 136.00, 139.50, 143.90, 128.40, 152.00, 162.00, 175.00, "Brokerage houses se target upgrade & heavy buying pressure", 3.77, 45.4, 1),
    ("SANSERA", "Sansera Engineering Ltd.", "Automobile and Auto Components", 1320.00, 1305.00, 1335.00, 1358.00, 1275.00, 1430.00, 1500.00, 1580.00, "EV aerospace components order book expansion", 2.45, 46.7, 1),
    ("SHREECEM", "Shree Cement Ltd.", "Construction Materials", 21900.00, 21700.00, 22100.00, 22650.00, 21350.00, 23800.00, 24900.00, 26200.00, "Share Price Near Low With Mixed Valuation, institutional accumulation", 3.47, 51.9, 1),
    ("SHRIPISTON", "Shriram Pistons & Rings", "Automobile and Auto Components", 2040.00, 2015.00, 2060.00, 2110.00, 1965.00, 2240.00, 2350.00, 2480.00, "Strong cash delivery absorption at support band", 2.15, 54.2, 1),
    ("STARHEALTH", "Star Health and Allied Insurance", "Financial Services", 537.70, 530.00, 542.00, 558.00, 513.00, 595.00, 625.00, 660.00, "Pullback support level hold kar raha hai, delivery 59.6%", 4.77, 59.6, 1),
    ("VESUVIUS", "Vesuvius India Ltd.", "Capital Goods", 404.10, 398.00, 408.00, 422.00, 388.00, 465.00, 495.00, 530.00, "REG - American Century Inv Vesuvius plc Form 8.3 heavy stake filing", 2.55, 48.9, 1),
    ("WESTLIFE", "Westlife Foodworld Ltd.", "Consumer Services", 588.05, 580.00, 594.00, 605.00, 568.00, 645.00, 680.00, 720.00, "Institutional block deal / heavy stake accumulation", 2.18, 49.9, 1),
]

# status -> sort rank (lower = more actionable)
RANK = {
    "ACTIVE": 0, "EXTENDED": 1, "ZONE": 2, "PRE": 3, "BELOW": 4,
    "NODATA": 5, "STALE": 6, "INVALID": 7, "BLOCKED": 8,
}

# ==========================================================
# SMALL HELPERS
# ==========================================================
def _stretch_kwargs() -> dict:
    """Streamlit >=1.50 prefers width='stretch'; older versions need use_container_width."""
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
    """Weekday + 09:15-15:30 IST check. NSE holiday calendar is NOT checked."""
    if now.weekday() >= 5:
        return "CLOSED (weekend)"
    if dt.time(9, 15) <= now.time() <= dt.time(15, 30):
        return "OPEN"
    return "CLOSED"


def fmt_pct(x: float | None) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:+.2f}%"


# ==========================================================
# AUTH
# ==========================================================
def _master_password() -> tuple[str, bool]:
    """Returns (password, is_default). Secret > env var > legacy fallback."""
    pwd = None
    try:
        pwd = st.secrets.get("TERMINAL_PASSWORD")
    except Exception:  # no secrets.toml present
        pwd = None
    pwd = pwd or os.environ.get("TERMINAL_PASSWORD")
    if pwd:
        return str(pwd), False
    return LEGACY_PASSWORD, True


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
            master, _ = _master_password()
            if st.session_state["failed_attempts"] >= MAX_LOGIN_ATTEMPTS:
                st.error("Too many failed attempts in this session. Reload the page to retry.")
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
# LIVE DATA
# ==========================================================
@st.cache_data(ttl=600, show_spinner=False)
def get_market_regime() -> dict:
    """Nifty vs 20/50 EMA (daily). Never fabricates data: returns ok=False on failure."""
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
    """
    One batched 15m download for the whole universe.
      cmp         -> latest traded price (may belong to a still-forming candle)
      last_close  -> close of the LAST COMPLETED 15m candle  (used for CHoCH confirmation)
    A candle stamped T covers [T, T+15m); it is 'closed' only when T+15m <= now.
    """
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
    if not multi and len(symbols) > 1:  # ambiguous shape -> refuse rather than mis-assign prices
        return empty

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
                continue  # dead / stale feed

            closed = close[(close.index + pd.Timedelta(minutes=CANDLE_MIN)) <= now_ts]
            last_date = close.index[-1].date()
            prev_mask = np.array([d < last_date for d in close.index.date], dtype=bool)
            prev = close[prev_mask]

            quotes[sym] = {
                "cmp": float(close.iloc[-1]),
                "last_close": float(closed.iloc[-1]) if not closed.empty else None,
                "candle_time": closed.index[-1] if not closed.empty else None,
                "data_time": close.index[-1],
                "prev_close": float(prev.iloc[-1]) if not prev.empty else None,
            }
        except Exception:
            continue
    return {"quotes": quotes, "fetched_at": fetched_at}


# ==========================================================
# RADAR LOGIC
# ==========================================================
def build_radar() -> pd.DataFrame:
    return pd.DataFrame(RADAR_ROWS, columns=RADAR_COLUMNS)


def validate_radar(df: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    dups = df.loc[df["symbol"].duplicated(), "symbol"].tolist()
    if dups:
        issues.append(f"Duplicate symbols: {', '.join(dups)}")
    for r in df.to_dict("records"):
        s = r["symbol"]
        if not (0 < r["support"] < r["buy_low"] <= r["buy_high"] < r["choch"]):
            issues.append(f"{s}: levels must satisfy Support < Buy Low <= Buy High < CHoCH")
        if not (r["choch"] < r["t1"] < r["t2"] < r["t3"]):
            issues.append(f"{s}: targets must satisfy CHoCH < T1 < T2 < T3")
        if r["sector"] not in SECTOR_FLOW:
            issues.append(f"{s}: sector '{r['sector']}' missing in SECTOR_FLOW (treated as NOT tradable)")
    return issues


def evaluate_setups(radar: pd.DataFrame, quotes: dict, max_chase_pct: float,
                    stale_pct: float = STALE_DEVIATION_PCT) -> pd.DataFrame:
    out = []
    for r in radar.to_dict("records"):
        sym = r["symbol"]
        q = quotes.get(sym)
        cmp_ = q["cmp"] if q else None
        last_close = q["last_close"] if q else None

        flow = SECTOR_FLOW.get(r["sector"])
        flow_label = "☑️ Inflow" if flow is True else ("⚠️ Outflow" if flow is False else "❓ Unmapped")
        p2_pass = r["deliv"] >= MIN_DELIVERY_PCT and r["spurt"] >= MIN_SPURT
        tradable = (flow is True) and p2_pass

        entry_ref = r["choch"]
        risk = entry_ref - r["support"]
        t1_pct = (r["t1"] / entry_ref - 1) * 100
        t2_pct = (r["t2"] / entry_ref - 1) * 100
        t3_pct = (r["t3"] / entry_ref - 1) * 100
        rr_t1 = (r["t1"] - entry_ref) / risk if risk > 0 else np.nan

        dev_pct = (cmp_ / r["snap_cmp"] - 1) * 100 if cmp_ is not None else None
        day_pct = None
        if q and q.get("prev_close"):
            day_pct = (cmp_ / q["prev_close"] - 1) * 100

        # ---- status ladder (order matters) ----
        if flow is not True:
            key, status, action = "BLOCKED", "⛔ BLOCKED – Sector Outflow" if flow is False else "⛔ BLOCKED – Unmapped Sector", "NO TRADE (Pillar 1)"
        elif not p2_pass:
            key, status, action = "BLOCKED", "⛔ BLOCKED – Delivery/Spurt", "NO TRADE (Pillar 2)"
        elif cmp_ is None or last_close is None:
            key, status, action = "NODATA", "📴 NO LIVE DATA", "WAIT – FEED UNAVAILABLE"
        elif abs(cmp_ / r["snap_cmp"] - 1) * 100 > stale_pct:
            key, status, action = "STALE", "⚠️ LEVELS STALE", "REFRESH RADAR LEVELS / CHECK TICKER"
        elif last_close < r["support"]:
            key, status, action = "INVALID", "❌ INVALIDATED", "AVOID – STRUCTURE BROKEN"
        elif last_close >= r["choch"]:
            ext = (last_close / r["choch"] - 1) * 100
            if ext > max_chase_pct:
                key, status, action = "EXTENDED", "🟠 EXTENDED – NO CHASE", f"WAIT PULLBACK ({ext:.1f}% above trigger)"
            else:
                key, status, action = "ACTIVE", "⚡ ACTIVE – BUY TRIGGER", "ENTER (15m CHoCH CONFIRMED)"
        elif r["buy_low"] <= cmp_ <= r["buy_high"]:
            key, status, action = "ZONE", "🟢 IN BUY ZONE", "WATCH – WAIT 15m CLOSE > CHoCH"
        elif cmp_ > r["buy_high"]:
            key, status = "PRE", "🟡 PRE-TRIGGER"
            action = "CHoCH TOUCHED – WAIT 15m CLOSE" if cmp_ >= r["choch"] else "WATCH – NEAR TRIGGER"
        else:
            key, status, action = "BELOW", "⚪ BELOW BUY ZONE", "TRACKING"

        if last_close is None:
            choch_state = "—"
        else:
            choch_state = "✅ Confirmed" if last_close >= r["choch"] else "⏳ Pending"

        out.append({
            "Symbol": sym, "Company": r["company"], "Sector": r["sector"],
            "Sector Flow": flow_label, "Tradable (3-Pillar)": "✅" if tradable else "—",
            "Status": status, "Action": action,
            "CMP (Rs)": cmp_, "Day %": day_pct,
            "Smart Money Buy Range (Rs)": f"₹{r['buy_low']:.2f} – ₹{r['buy_high']:.2f}",
            "CHoCH Trigger (Rs)": r["choch"], "Last 15m Close (Rs)": last_close, "15m CHoCH": choch_state,
            "Support / TSL (Rs)": r["support"],
            "Target 1": r["t1"], "Target 2": r["t2"], "Target 3": r["t3"],
            "T1 %": t1_pct, "T2 %": t2_pct, "T3 %": t3_pct, "R:R (T1)": rr_t1,
            "Volume Spurt (x)": r["spurt"], "Delivery %": r["deliv"], "Radar Age (Days)": r["age_days"],
            "Catalyst Remark": r["remark"],
            "Radar Snapshot CMP (Rs)": r["snap_cmp"], "Live vs Snapshot %": dev_pct,
            "_key": key, "_rank": RANK[key], "_tradable": tradable,
        })
    df = pd.DataFrame(out)
    return df.sort_values(["_rank", "Volume Spurt (x)"], ascending=[True, False]).reset_index(drop=True)


# ==========================================================
# EXCEL EXPORT
# ==========================================================
EXPORT_COLUMNS = [
    "Symbol", "Company", "Sector", "Sector Flow", "Tradable (3-Pillar)", "Status", "Action",
    "CMP (Rs)", "Day %", "Smart Money Buy Range (Rs)", "CHoCH Trigger (Rs)", "Last 15m Close (Rs)",
    "15m CHoCH", "Support / TSL (Rs)", "Target 1", "Target 2", "Target 3",
    "T1 %", "T2 %", "T3 %", "R:R (T1)", "Volume Spurt (x)", "Delivery %", "Radar Age (Days)", "Catalyst Remark",
]
_PRICE_COLS = {"CMP (Rs)", "CHoCH Trigger (Rs)", "Last 15m Close (Rs)", "Support / TSL (Rs)", "Target 1", "Target 2", "Target 3"}
_NUM2_COLS = {"Day %", "T1 %", "T2 %", "T3 %", "R:R (T1)", "Volume Spurt (x)"}
_ROW_FILL = {
    "ACTIVE": "C6EFCE", "EXTENDED": "FCE4D6", "ZONE": "E2EFDA",
    "INVALID": "F8CBAD", "BLOCKED": "EDEDED", "STALE": "FFF2CC",
}


def generate_excel_export(df: pd.DataFrame, meta: dict) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SMC_Accumulation_Radar"
    ws.append(EXPORT_COLUMNS)

    head_fill = PatternFill(start_color="161B22", end_color="161B22", fill_type="solid")
    head_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    for c in range(1, len(EXPORT_COLUMNS) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = head_fill, head_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    clean = df.astype(object).where(pd.notna(df), None)
    for i, rec in enumerate(clean.to_dict("records"), start=2):
        ws.append([rec[c] for c in EXPORT_COLUMNS])
        hex_fill = _ROW_FILL.get(rec["_key"])
        fill = PatternFill(start_color=hex_fill, end_color=hex_fill, fill_type="solid") if hex_fill else None
        for j, name in enumerate(EXPORT_COLUMNS, start=1):
            cell = ws.cell(row=i, column=j)
            cell.alignment = Alignment(vertical="center")
            if fill:
                cell.fill = fill
            if name in _PRICE_COLS or name in _NUM2_COLS:
                cell.number_format = "#,##0.00"
            elif name == "Delivery %":
                cell.number_format = "0.0"

    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[letter].width = min(max(longest + 3, 11), 60)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions

    meta_ws = wb.create_sheet("Framework_Meta")
    for line in [
        ("Generated (IST)", meta["generated"]),
        ("Price source", meta["source"]),
        ("Market regime", meta["regime"]),
        ("Pillar 1", "Trade only sectors with institutional capital INFLOW"),
        ("Pillar 2", f"Delivery >= {MIN_DELIVERY_PCT:.0f}% and Spurt >= {MIN_SPURT:.1f}x"),
        ("Pillar 3", "Entry only on a CLOSED 15m candle above the CHoCH trigger (no breakout chase)"),
        ("T1 / T2 / T3", "+8-12% (SL to cost) / +18-25% (1.272 fib, partial) / +30-45% (1.618 fib, exit)"),
        ("Note", "R:R and target % are measured from the CHoCH trigger. Educational tool, not investment advice."),
    ]:
        meta_ws.append(list(line))
    meta_ws.column_dimensions["A"].width = 18
    meta_ws.column_dimensions["B"].width = 100
    for r in meta_ws.iter_rows(min_row=1, max_col=1):
        r[0].font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ==========================================================
# TRADE BOOK (persistence + exit rules)
# ==========================================================
def _num(raw: dict, *keys: str) -> float | None:
    for k in keys:
        v = raw.get(k)
        try:
            if v is not None and v != "":
                return float(v)
        except (TypeError, ValueError):
            continue
    return None


def normalize_trade(raw, levels: dict) -> tuple[dict | None, str | None]:
    """
    Converts any stored trade (old/new schema) into the current schema.
    Returns (trade, note). trade=None means it could not be repaired safely.
    """
    if not isinstance(raw, dict):
        return None, "entry is not an object"
    sym = str(raw.get("symbol") or raw.get("Symbol") or "").strip().upper()
    lv = levels.get(sym, {})
    entry = _num(raw, "entry_price", "entry", "Entry", "price", "buy_price")
    if not sym or entry is None or entry <= 0:
        return None, f"{sym or '?'}: symbol/entry price missing"

    note = None
    qty = _num(raw, "qty", "quantity", "Qty")
    if qty is None or qty < 1:
        qty, note = 1, f"{sym}: quantity missing, set to 1 (log it again with the right qty)"

    sl = _num(raw, "initial_sl", "stop_loss", "sl", "stoploss")
    if sl is None:
        sl = lv.get("support")
    t1 = _num(raw, "t1", "target1", "Target 1") or lv.get("t1")
    t2 = _num(raw, "t2", "target2", "Target 2") or lv.get("t2")
    t3 = _num(raw, "t3", "target3", "Target 3") or lv.get("t3")
    if sl is None or sl >= entry or not (t1 and t2 and t3):
        return None, f"{sym}: stop-loss/targets missing or invalid"

    status = str(raw.get("status", "OPEN")).upper()
    exit_px = _num(raw, "exit_price")
    if status != "CLOSED" or exit_px is None:
        status, exit_px = "OPEN", None

    return {
        "id": str(raw.get("id") or uuid.uuid4().hex[:8]), "symbol": sym,
        "entry_price": entry, "qty": int(qty), "initial_sl": float(sl),
        "t1": float(t1), "t2": float(t2), "t3": float(t3),
        "t1_hit": bool(raw.get("t1_hit", False)), "t2_hit": bool(raw.get("t2_hit", False)),
        "entry_date": str(raw.get("entry_date") or "n/a"),
        "status": status, "exit_price": exit_px, "exit_date": raw.get("exit_date"),
    }, note


def load_trades(levels: dict) -> tuple[list[dict], list[str]]:
    """Loads + repairs the trade book. Unrepairable rows are skipped, original file is backed up."""
    if not os.path.exists(TRADE_BOOK_PATH):
        return [], []
    try:
        with open(TRADE_BOOK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], ["Trade file unreadable (corrupt JSON) - starting empty."]
    if not isinstance(data, list):
        return [], ["Trade file has unexpected format - starting empty."]

    trades, problems, seen = [], [], set()
    for raw in data:
        t, note = normalize_trade(raw, levels)
        if note:
            problems.append(note)
        if t is None:
            continue
        while t["id"] in seen:
            t["id"] = uuid.uuid4().hex[:8]
        seen.add(t["id"])
        trades.append(t)
    if problems:
        try:
            bak = TRADE_BOOK_PATH + ".legacy.bak"
            if not os.path.exists(bak):
                with open(bak, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
        except OSError:
            pass
    return trades, problems


def save_trades(trades: list[dict]) -> bool:
    try:
        os.makedirs(os.path.dirname(TRADE_BOOK_PATH), exist_ok=True)
        tmp = TRADE_BOOK_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(trades, f, indent=2)
        os.replace(tmp, TRADE_BOOK_PATH)  # atomic: no half-written file
        return True
    except OSError:
        return False


def position_action(t: dict, cmp_: float | None) -> tuple[str, float]:
    """Returns (action text, active stop-loss). After T1 the SL is trailed to cost."""
    active_sl = t["entry_price"] if t["t1_hit"] else t["initial_sl"]
    if cmp_ is None:
        return "📴 NO LIVE DATA", active_sl
    if cmp_ <= active_sl:
        return ("🔴 EXIT – SL AT COST HIT" if t["t1_hit"] else "🔴 EXIT – INITIAL SL HIT"), active_sl
    if cmp_ >= t["t3"]:
        return "🏁 T3 – PEAK EXIT", active_sl
    if t["t2_hit"]:
        return "🟡 T2 REACHED – PARTIAL PROFIT LOCKED", active_sl
    if t["t1_hit"]:
        return "🟢 T1 REACHED – SL AT COST (ZERO RISK)", active_sl
    return "⏳ HOLD", active_sl


def render_trade_book(radar: pd.DataFrame, quotes: dict) -> None:
    st.subheader("Position Tracker – exit rules from framework")
    st.caption("T1 hit → stop-loss trails to cost. T2 → partial profit. T3 → peak exit. "
               "Hits are latched when this page loads with live data; the file lives on the server disk, so keep a backup.")

    trades: list[dict] = st.session_state.trades
    symbols = radar["symbol"].tolist()
    sym = st.selectbox("Symbol", symbols, key="tb_symbol")
    row = radar.loc[radar["symbol"] == sym].iloc[0]
    q = quotes.get(sym)
    default_entry = float(q["cmp"]) if q else float(row["snap_cmp"])

    with st.form("tb_add_form"):
        c1, c2, c3 = st.columns(3)
        entry = c1.number_input("Entry price (Rs)", min_value=0.01, value=round(default_entry, 2), step=0.05, key=f"tb_entry_{sym}")
        qty = c2.number_input("Quantity", min_value=1, value=1, step=1, key=f"tb_qty_{sym}")
        sl = c3.number_input("Initial stop-loss (Rs)", min_value=0.01, value=float(row["support"]), step=0.05, key=f"tb_sl_{sym}")
        add = st.form_submit_button("➕ Log trade", **STRETCH)
    if add:
        if sl >= entry:
            st.error("Stop-loss must be below the entry price.")
        else:
            trades.append({
                "id": uuid.uuid4().hex[:8], "symbol": sym,
                "entry_price": float(entry), "qty": int(qty), "initial_sl": float(sl),
                "t1": float(row["t1"]), "t2": float(row["t2"]), "t3": float(row["t3"]),
                "t1_hit": False, "t2_hit": False,
                "entry_date": now_ist().strftime("%Y-%m-%d %H:%M"),
                "status": "OPEN", "exit_price": None, "exit_date": None,
            })
            if not save_trades(trades):
                st.warning("Trade logged for this session, but saving to disk failed.")
            st.success(f"{sym} logged.")

    open_trades = [t for t in trades if t["status"] == "OPEN"]
    changed = False
    rows = []
    for t in open_trades:
        qd = quotes.get(t["symbol"])
        cmp_ = qd["cmp"] if qd else None
        if cmp_ is not None:
            if not t["t1_hit"] and cmp_ >= t["t1"]:
                t["t1_hit"], changed = True, True
            if not t["t2_hit"] and cmp_ >= t["t2"]:
                t["t1_hit"] = t["t2_hit"] = changed = True
        action, active_sl = position_action(t, cmp_)
        pnl = (cmp_ - t["entry_price"]) * t["qty"] if cmp_ is not None else None
        pnl_pct = (cmp_ / t["entry_price"] - 1) * 100 if cmp_ is not None else None
        rows.append({
            "ID": t["id"], "Symbol": t["symbol"], "Entry Date": t["entry_date"],
            "Entry (Rs)": t["entry_price"], "Qty": t["qty"], "CMP (Rs)": cmp_,
            "P&L (Rs)": pnl, "P&L %": pnl_pct, "Active SL (Rs)": active_sl,
            "T1": t["t1"], "T2": t["t2"], "T3": t["t3"], "Action": action,
        })
    if changed:
        save_trades(trades)

    st.markdown("**Open positions**")
    if rows:
        pos_df = pd.DataFrame(rows)
        st.dataframe(pos_df, hide_index=True, **STRETCH)
        total = pos_df["P&L (Rs)"].dropna().sum()
        st.metric("Open P&L (Rs)", f"{total:,.2f}")

        with st.form("tb_close_form"):
            labels = {f"{t['symbol']} | {t['qty']} @ {t['entry_price']:.2f} | {t['id']}": t["id"] for t in open_trades}
            pick = st.selectbox("Close position", list(labels.keys()))
            exit_px = st.number_input("Exit price (Rs)", min_value=0.01, value=None, step=0.05, placeholder="Enter exit price")
            close = st.form_submit_button("Close position", **STRETCH)
        if close and exit_px is None:
            st.error("Enter the exit price first.")
        elif close:
            tid = labels[pick]
            for t in trades:
                if t["id"] == tid:
                    t["status"], t["exit_price"] = "CLOSED", float(exit_px)
                    t["exit_date"] = now_ist().strftime("%Y-%m-%d %H:%M")
            save_trades(trades)
            st.rerun()
    else:
        st.info("No open positions.")

    closed = [t for t in trades if t["status"] == "CLOSED"]
    if closed:
        st.markdown("**Closed trades**")
        cdf = pd.DataFrame([{
            "Symbol": t["symbol"], "Entry (Rs)": t["entry_price"], "Exit (Rs)": t["exit_price"], "Qty": t["qty"],
            "Realised P&L (Rs)": (t["exit_price"] - t["entry_price"]) * t["qty"],
            "Return %": (t["exit_price"] / t["entry_price"] - 1) * 100,
            "Entry Date": t["entry_date"], "Exit Date": t["exit_date"],
        } for t in closed])
        st.dataframe(cdf, hide_index=True, **STRETCH)
        st.metric("Realised P&L (Rs)", f"{cdf['Realised P&L (Rs)'].sum():,.2f}")

    st.download_button(
        "💾 Download trade book backup (JSON)",
        data=json.dumps(trades, indent=2),
        file_name="active_trades_backup.json", mime="application/json", **STRETCH,
    )


# ==========================================================
# UI
# ==========================================================
CSS = """
<style>
  div[data-testid="stMetric"]{background:#161B22;border:1px solid #30363D;padding:14px 18px;border-radius:6px;}
  div[data-testid="stMetricLabel"]{color:#8B949E;font-size:13px;font-weight:600;text-transform:uppercase;}
  div[data-testid="stMetricValue"]{color:#F0F6FC;font-family:'JetBrains Mono',Consolas,monospace;font-size:20px;font-weight:700;}
  .stTabs [data-baseweb="tab-list"]{gap:8px;}
  .stTabs [data-baseweb="tab"]{background-color:#161B22;border-radius:4px;color:#C9D1D9;padding:8px 16px;}
  .stTabs [aria-selected="true"]{background-color:#21262D !important;color:#58A6FF !important;border-bottom:2px solid #58A6FF !important;}
</style>
"""

COLUMN_CONFIG = {
    "CMP (Rs)": st.column_config.NumberColumn(format="%.2f"),
    "Day %": st.column_config.NumberColumn(format="%.2f"),
    "CHoCH Trigger (Rs)": st.column_config.NumberColumn(format="%.2f"),
    "Last 15m Close (Rs)": st.column_config.NumberColumn(format="%.2f"),
    "Support / TSL (Rs)": st.column_config.NumberColumn(format="%.2f"),
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


def main() -> None:
    st.set_page_config(page_title="Institutional Smart Money Terminal", page_icon="⚡",
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)
    if not auth_gate():
        st.stop()

    radar = build_radar()
    levels = {r["symbol"]: {"support": r["support"], "t1": r["t1"], "t2": r["t2"], "t3": r["t3"]}
              for r in radar.to_dict("records")}
    if st.session_state.get("trades_schema") != 2:  # reload/repair once per session (and after code upgrades)
        st.session_state.trades, st.session_state.trade_problems = load_trades(levels)
        st.session_state.trades_schema = 2

    # ---------------- sidebar ----------------
    with st.sidebar:
        st.header("⚙️ Controls")
        if st.button("🔄 Refresh live data", **STRETCH):
            st.cache_data.clear()
            st.rerun()
        max_chase = st.slider("Max extension above CHoCH (no-chase %)", 0.5, 5.0, 2.0, 0.5,
                              help="If the last closed 15m candle is further above the trigger than this, it is treated as a chase, not an entry.")
        stale_pct = st.slider("Stale-level threshold (% vs radar snapshot)", 5.0, 50.0, STALE_DEVIATION_PCT, 1.0,
                              help="If live price is further than this from the radar snapshot CMP, the levels are treated as outdated.")
        tradable_only = st.toggle("Tradable only (Pillar 1 + 2 pass)", value=False)
        status_filter = st.multiselect("Status filter", [
            "⚡ ACTIVE", "🟠 EXTENDED", "🟢 IN BUY ZONE", "🟡 PRE-TRIGGER", "⚪ BELOW BUY ZONE",
            "📴 NO LIVE DATA", "⚠️ LEVELS STALE", "❌ INVALIDATED", "⛔ BLOCKED",
        ])
        text_filter = st.text_input("Search symbol / company / sector").strip().lower()
        if _master_password()[1]:
            st.warning("Default password in use. Set TERMINAL_PASSWORD in secrets or env.")
        if st.button("🔒 Lock terminal", **STRETCH):
            st.session_state["authenticated"] = False
            st.rerun()

    # ---------------- data ----------------
    issues = validate_radar(radar)
    live = fetch_live_quotes(tuple(radar["symbol"]))
    quotes, fetched_at = live["quotes"], live["fetched_at"]
    df = evaluate_setups(radar, quotes, max_chase, stale_pct)
    regime = get_market_regime()
    now = now_ist()
    mkt = market_state(now)

    live_ok = len(quotes)
    source = (f"Live yfinance 15m ({live_ok}/{len(radar)} symbols)" if live_ok
              else "Snapshot only – live feed unavailable")
    if regime["ok"]:
        regime_txt = (f"{regime['regime']} | Nifty {regime['nifty']:,.0f} ({fmt_pct(regime['nifty_chg'])}) "
                      f"| Sensex {regime['sensex']:,.0f} ({fmt_pct(regime['sensex_chg'])})")
    else:
        regime_txt = "Unavailable (index feed failed)"

    st.title("⚡ Institutional Smart Money Terminal")
    st.markdown(f"**Last Sync:** `{fetched_at.strftime('%d-%b-%Y | %I:%M:%S %p IST')}` &nbsp;|&nbsp; "
                f"**Market:** `{mkt}` &nbsp;|&nbsp; **Regime:** `{regime_txt}`")
    if live_ok == 0:
        st.error("Live prices unavailable – NO trigger can be confirmed. Showing radar snapshot only.")
    elif live_ok < len(radar):
        st.warning(f"Live data missing for {len(radar) - live_ok} symbol(s); they show 'NO LIVE DATA'.")
    if mkt != "OPEN" and live_ok:
        st.info("Market closed – CHoCH status reflects the last completed 15m candle. NSE holidays are not auto-detected. "
                "Yahoo intraday data can lag the exchange; confirm on your broker before placing orders.")

    # ---------------- metrics ----------------
    m = st.columns(6)
    m[0].metric("Tracked", len(df))
    m[1].metric("Tradable (P1+P2)", int(df["_tradable"].sum()))
    m[2].metric("⚡ Active Triggers", int((df["_key"] == "ACTIVE").sum()))
    m[3].metric("In Buy Zone", int((df["_key"] == "ZONE").sum()))
    m[4].metric("Inflow Aligned", int(df["Sector Flow"].str.contains("Inflow").sum()))
    m[5].metric("Blocked", int((df["_key"] == "BLOCKED").sum()))
    st.markdown("---")

    # ---------------- filtered view ----------------
    view = df.copy()
    if tradable_only:
        view = view[view["_tradable"]]
    if status_filter:
        pats = [s.split(" ", 1)[0] for s in status_filter]  # leading emoji
        view = view[view["Status"].apply(lambda s: any(s.startswith(p) for p in pats))]
    if text_filter:
        blob = (view["Symbol"] + " " + view["Company"] + " " + view["Sector"]).str.lower()
        view = view[blob.str.contains(text_filter, regex=False)]

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Live Accumulation Radar", "📒 Trade Book", "🧪 Data Quality", "📥 Export & Reports"])

    with tab1:
        st.subheader("Smart Money Delivery Spurt & 15m CHoCH Radar")
        show_cols = [c for c in EXPORT_COLUMNS if c in view.columns]
        st.dataframe(view[show_cols], hide_index=True, height=560, column_config=COLUMN_CONFIG, **STRETCH)
        st.caption("Entry is valid only when the last COMPLETED 15m candle closes at/above the CHoCH trigger "
                   "inside a Pillar 1 + 2 qualified name. Target % and R:R are measured from the CHoCH trigger.")

    with tab2:
        for msg in st.session_state.get("trade_problems", []):
            st.warning("Trade book repair: " + msg)
        try:
            render_trade_book(radar, quotes)
        except Exception as exc:  # keep the other tabs alive
            st.error(f"Trade book error: {type(exc).__name__}: {exc}")

    with tab3:
        st.subheader("Data integrity & framework fit")
        if issues:
            for i in issues:
                st.warning(i)
        else:
            st.success("Radar levels are internally consistent (Support < Buy Low ≤ Buy High < CHoCH < T1 < T2 < T3).")
        low_t1 = df[df["T1 %"] < 8.0]
        low_rr = df[df["R:R (T1)"] < 1.5]
        st.markdown(f"- **T1 below framework band (< +8% from trigger):** {len(low_t1)} of {len(df)}")
        st.markdown(f"- **R:R to T1 below 1.5:** {len(low_rr)} of {len(df)}")
        st.caption("These are not bugs in the app – they are the radar's own target/support levels. "
                   "Re-derive T1/T2/T3 from swing high and 1.272 / 1.618 extensions, or skip the weak-R:R names.")
        stale = df[df["_key"] == "STALE"]
        if not stale.empty:
            st.error(f"Live price is >{stale_pct:.0f}% away from the radar snapshot for {len(stale)} stock(s). "
                     "If almost ALL stocks are off, the radar levels are old - refresh them from fresh Bhavcopy. "
                     "If only a few are off, check the ticker mapping.")
        st.markdown("**Live vs radar snapshot**")
        diag = df.loc[df["CMP (Rs)"].notna(), ["Symbol", "Radar Snapshot CMP (Rs)", "CMP (Rs)", "Live vs Snapshot %", "Status"]]
        diag = diag.reindex(diag["Live vs Snapshot %"].abs().sort_values(ascending=False).index)
        st.dataframe(diag, hide_index=True, column_config={
            "Radar Snapshot CMP (Rs)": st.column_config.NumberColumn(format="%.2f"),
            "CMP (Rs)": st.column_config.NumberColumn(format="%.2f"),
            "Live vs Snapshot %": st.column_config.NumberColumn(format="%.1f")}, **STRETCH)
        st.dataframe(
            df[["Symbol", "T1 %", "T2 %", "T3 %", "R:R (T1)", "Delivery %", "Volume Spurt (x)", "Tradable (3-Pillar)"]],
            hide_index=True, column_config=COLUMN_CONFIG, **STRETCH,
        )

    with tab4:
        st.subheader("Download Audited Radar Data")
        meta = {"generated": now.strftime("%d-%b-%Y %I:%M:%S %p IST"), "source": source, "regime": regime_txt}
        xlsx = generate_excel_export(df, meta)
        st.download_button(
            "📥 Download Excel (.xlsx)", data=xlsx,
            file_name=f"SMC_Institutional_Radar_{now.strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", **STRETCH,
        )
        st.caption("Export contains the full (unfiltered) radar, row-coloured by status.")


if __name__ == "__main__":
    main()
