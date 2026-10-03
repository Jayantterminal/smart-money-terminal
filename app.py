"""
Institutional Smart Money Terminal (v4.0 - Professional Edition)
------------------------------------------------------------------
Framework (Three-Pillar Institutional SMC):
  Pillar 1: Full 22 NSE Sector Capital Rotation Matrix (Inflow vs Outflow)
  Pillar 2: Cash Delivery Spurt Filter (Deliv >= 45%, Spurt >= 2.0x)
  Pillar 3: Micro Execution Engine (15m CHoCH / BOS, Accumulation / Distribution Zones)

v4.0 changes
  * FIX  Bearish zone check never fired (zone_low > zone_high in data) -> zones normalised
  * FIX  Sector status/signal now derived from share shift (single source of truth)
  * FIX  Zero-shift sector is NEUTRAL (was wrongly Outflow); sector tab no longer breaks on it
  * FIX  Trade form defaults now follow the selected symbol (selectbox moved out of form)
  * FIX  st.secrets crash when secrets.toml is missing; weak default key now warns
  * NEW  Serial numbering (No.) on every table, tab and section
  * NEW  Bordered HTML report tables (sticky header, tone badges) + interactive grid toggle
  * NEW  Bearish "extended - no chase" rule, distance-to-trigger %, radar-aged flag
  * NEW  Actionable-now strip, sector flow chart, methodology tab
  * NEW  Trade book: LONG/SHORT side, live P&L, close / delete, SL validation, summary metrics
  * NEW  Excel export: numbering, borders, number formats, sector sheet
"""
from __future__ import annotations

import datetime as dt
import hmac
import html
import io
import json
import os
import uuid

import numpy as np
import openpyxl
import pandas as pd
import streamlit as st
import yfinance as yf
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
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
RADAR_MAX_AGE_DAYS = 3
HEAVY_SHIFT = 0.50
MAX_LOGIN_ATTEMPTS = 5
LEGACY_PASSWORD = "2000"  # dev fallback only - set TERMINAL_PASSWORD in secrets / env
TRADE_BOOK_PATH = "data/active_trades.json"

# Pillar 1 - (recent 12D share %, base share %). Shift / status / signal are DERIVED.
SECTOR_SHARES = {
    "Financial Services": (29.01, 26.50),
    "Healthcare": (8.13, 7.45),
    "Construction Materials": (1.23, 1.14),
    "Power": (3.03, 2.97),
    "Consumer Services": (5.86, 5.81),
    "Oil Gas & Consumable Fuels": (4.74, 4.69),
    "Construction": (1.62, 1.59),
    "Forest Materials": (0.02, 0.02),
    "Diversified": (0.01, 0.02),
    "Textiles": (0.38, 0.39),
    "Media Entertainment & Publication": (0.42, 0.45),
    "Chemicals": (2.50, 2.56),
    "Utilities": (0.12, 0.21),
    "Telecommunication": (2.88, 2.99),
    "Metals & Mining": (3.45, 3.60),
    "Services": (1.10, 1.30),
    "Consumer Durables": (2.15, 2.45),
    "Fast Moving Consumer Goods": (7.80, 8.25),
    "Capital Goods": (6.10, 6.85),
    "Automobile and Auto Components": (5.40, 6.30),
    "Information Technology": (11.20, 12.45),
    "Realty": (0.85, 0.95),
}

RADAR_COLUMNS = [
    "symbol", "company", "sector", "bias", "snap_cmp",
    "zone_low", "zone_high", "choch", "bos", "invalidation",
    "t1", "t2", "t3", "remark", "spurt", "deliv", "age_days",
]

RADAR_ROWS = [
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
    "ACTIVE": 0, "BOS": 1, "EXTENDED": 2, "ZONE": 3, "PRE": 4,
    "BELOW": 5, "BEAR_ACTIVE": 6, "BEAR_BOS": 7, "NODATA": 8, "STALE": 9, "INVALID": 10, "BLOCKED": 11,
}
TONE = {
    "ACTIVE": "g", "BOS": "g", "EXTENDED": "o", "ZONE": "b", "PRE": "y", "BELOW": "n",
    "BEAR_ACTIVE": "r", "BEAR_BOS": "r", "NODATA": "n", "STALE": "o", "INVALID": "r", "BLOCKED": "n",
}
ACTIONABLE_KEYS = ["ACTIVE", "BOS", "BEAR_ACTIVE", "BEAR_BOS"]


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
    # NOTE: NSE trading holidays are not modelled here.
    if now.weekday() >= 5:
        return "CLOSED (weekend)"
    if dt.time(9, 15) <= now.time() <= dt.time(15, 30):
        return "OPEN"
    return "CLOSED"


def fmt_pct(x: float | None) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:+.2f}%"


def _master_key() -> tuple[str, bool]:
    """Return (key, is_custom). Never crashes if secrets.toml is absent."""
    val = None
    try:
        val = st.secrets.get("TERMINAL_PASSWORD")
    except Exception:
        val = None
    val = val or os.environ.get("TERMINAL_PASSWORD")
    return (str(val), True) if val else (LEGACY_PASSWORD, False)


def auth_gate() -> bool:
    st.session_state.setdefault("authenticated", False)
    st.session_state.setdefault("failed_attempts", 0)
    if st.session_state["authenticated"]:
        return True

    master, custom = _master_key()
    st.markdown(
        "<div class='gate'><div class='gate-ico'>🔒</div><h2>Terminal Access Gate</h2>"
        "<p>Enter the terminal master security key to continue.</p></div>",
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("auth_form"):
            pwd_in = st.text_input("Password", type="password", placeholder="Enter key...")
            submitted = st.form_submit_button("Unlock Terminal", **STRETCH)
        if not custom:
            st.warning("Default key in use. Set `TERMINAL_PASSWORD` in secrets / environment.")
        if submitted:
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
# PILLAR 1 - SECTOR FLOW (derived)
# ==========================================================
def sector_info(name: str) -> dict:
    sh = SECTOR_SHARES.get(name)
    if sh is None:
        return {"recent": np.nan, "base": np.nan, "shift": 0.0, "status": None, "signal": "Unmapped"}
    recent, base = sh
    shift = round(recent - base, 2)
    status = True if shift > 0 else False if shift < 0 else None
    if status is None:
        signal = "Neutral"
    else:
        signal = ("Heavy " if abs(shift) >= HEAVY_SHIFT else "") + ("Inflow" if status else "Outflow")
    return {"recent": recent, "base": base, "shift": shift, "status": status, "signal": signal}


def build_sector_df() -> pd.DataFrame:
    rows = []
    for name in SECTOR_SHARES:
        i = sector_info(name)
        icon = "🟢" if i["status"] is True else "🔴" if i["status"] is False else "⚪"
        rows.append({
            "Sector": name,
            "Recent 12D Share (%)": i["recent"], "Base Share (%)": i["base"],
            "Flow Shift (%)": i["shift"], "Flow Signal": f"{icon} {i['signal']}",
            "_status": i["status"],
            "_tone": "g" if i["status"] is True else "r" if i["status"] is False else "n",
        })
    return pd.DataFrame(rows).sort_values("Flow Shift (%)", ascending=False).reset_index(drop=True)


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
        sym, bias = r["symbol"], r["bias"]
        q = quotes.get(sym)
        cmp_ = q["cmp"] if q else None
        last_close = q["last_close"] if q else None

        # FIX: bearish rows store zone_low > zone_high -> normalise
        zl, zh = min(r["zone_low"], r["zone_high"]), max(r["zone_low"], r["zone_high"])

        info = sector_info(r["sector"])
        flow_status = info["status"]
        if flow_status is True:
            flow_label = f"🟢 Inflow ({info['shift']:+.2f}%)"
        elif flow_status is False:
            flow_label = f"🔴 Outflow ({info['shift']:+.2f}%)"
        else:
            flow_label = f"⚪ {info['signal']}"

        p2_pass = r["deliv"] >= MIN_DELIVERY_PCT and r["spurt"] >= MIN_SPURT
        long_ = bias == "BULLISH"
        p1_pass = (flow_status is True) if long_ else (flow_status is False)
        tradable = p1_pass and p2_pass

        entry_ref = r["choch"]
        risk = abs(entry_ref - r["invalidation"])
        t_pct = [abs((r[t] / entry_ref - 1) * 100) for t in ("t1", "t2", "t3")]
        rr_t1 = abs(r["t1"] - entry_ref) / risk if risk > 0 else np.nan

        dev_pct = abs(cmp_ / r["snap_cmp"] - 1) * 100 if cmp_ is not None else None
        day_pct = (cmp_ / q["prev_close"] - 1) * 100 if q and q.get("prev_close") else None
        to_trigger = (entry_ref / cmp_ - 1) * 100 if cmp_ else None

        side_word = "LONGS" if long_ else "SHORTS"
        if not p1_pass:
            why = "Sector Outflow" if long_ else "Sector Inflow"
            if flow_status is None:
                why = "Sector Neutral"
            blocked = ("BLOCKED", f"⛔ BLOCKED – {why}", f"AVOID {side_word} (Pillar 1)")
        elif not p2_pass:
            blocked = ("BLOCKED", "⛔ BLOCKED – Delivery Spurt" if long_ else "⛔ BLOCKED – Distribution Spurt",
                       f"AVOID {side_word} (Pillar 2)")
        else:
            blocked = None

        if blocked:
            key, status, action = blocked
        elif cmp_ is None or last_close is None:
            key, status, action = "NODATA", "📴 NO LIVE DATA", "WAIT – FEED UNAVAILABLE"
        elif dev_pct > stale_pct:
            key, status, action = "STALE", "⚠️ LEVELS STALE", "REFRESH RADAR SNAPSHOT"
        elif long_:
            if last_close < r["invalidation"]:
                key, status, action = "INVALID", "❌ INVALIDATED", "AVOID – SUPPORT BROKEN"
            elif last_close >= r["bos"]:
                key, status, action = "BOS", "🚀 MOMENTUM (BULLISH BOS)", f"TREND EXPANSION > {r['bos']:.2f}"
            elif last_close >= r["choch"]:
                ext = (last_close / r["choch"] - 1) * 100
                if ext > max_chase_pct:
                    key, status, action = "EXTENDED", "🟠 EXTENDED – NO CHASE", f"PULLBACK WAIT (+{ext:.1f}%)"
                else:
                    key, status, action = "ACTIVE", "⚡ ACTIVE (BULLISH CHoCH)", "BUY ENTRY (15m CHoCH CONFIRMED)"
            elif zl <= cmp_ <= zh:
                key, status, action = "ZONE", "🟢 IN BUY ZONE", "ACCUMULATING – WAIT CHoCH"
            elif cmp_ > zh:
                key, status = "PRE", "🟡 PRE-TRIGGER"
                action = "CHoCH TOUCHED – WAIT 15m CLOSE" if cmp_ >= r["choch"] else "WATCHING NEAR TRIGGER"
            else:
                key, status, action = "BELOW", "⚪ BELOW BUY ZONE", "TRACKING"
        else:  # BEARISH
            if last_close > r["invalidation"]:
                key, status, action = "INVALID", "❌ INVALIDATED", "AVOID – RESISTANCE SWEPT"
            elif last_close <= r["bos"]:
                key, status, action = "BEAR_BOS", "🔻 SHORT/EXIT (BEARISH BOS)", f"MARKDOWN EXPANSION < {r['bos']:.2f}"
            elif last_close <= r["choch"]:
                ext = (r["choch"] / last_close - 1) * 100
                if ext > max_chase_pct:
                    key, status, action = "EXTENDED", "🟠 EXTENDED – NO CHASE", f"BOUNCE WAIT (-{ext:.1f}%)"
                else:
                    key, status, action = "BEAR_ACTIVE", "🔻 ACTIVE (BEARISH CHoCH)", "EXIT / SHORT (15m BREAKDOWN)"
            elif zl <= cmp_ <= zh:  # FIX: previously never true
                key, status, action = "ZONE", "🔴 IN DISTRIBUTION ZONE", "DISTRIBUTING – WAIT BREAKDOWN"
            else:
                key, status, action = "PRE", "⚪ TRACKING SUPPLY", "SUPPLY RESISTANCE INTACT"

        if r["age_days"] >= RADAR_MAX_AGE_DAYS:
            action += f" | ⏳ RADAR {r['age_days']}D OLD"

        out.append({
            "Symbol": sym, "Company": r["company"], "Sector": r["sector"], "Bias": bias,
            "Sector Flow": flow_label, "Tradable (3-Pillar)": "✅" if tradable else "—",
            "Status": status, "Action": action,
            "CMP (Rs)": cmp_, "Day %": day_pct,
            "Smart Money Zone (Rs)": f"₹{zl:.2f} – ₹{zh:.2f}",
            "CHoCH Trigger (Rs)": r["choch"], "Dist. to CHoCH %": to_trigger,
            "BOS Level (Rs)": r["bos"],
            "Last 15m Close (Rs)": last_close, "Invalidation / SL (Rs)": r["invalidation"],
            "Target 1": r["t1"], "Target 2": r["t2"], "Target 3": r["t3"],
            "T1 %": t_pct[0], "T2 %": t_pct[1], "T3 %": t_pct[2], "R:R (T1)": rr_t1,
            "Volume Spurt (x)": r["spurt"], "Delivery %": r["deliv"], "Radar Age (Days)": r["age_days"],
            "Catalyst Remark": r["remark"], "Radar Snapshot CMP (Rs)": r["snap_cmp"],
            "_key": key, "_rank": RANK.get(key, 99), "_tone": TONE.get(key, "n"), "_tradable": tradable,
        })
    df = pd.DataFrame(out)
    return df.sort_values(["_rank", "Volume Spurt (x)"], ascending=[True, False]).reset_index(drop=True)


# ==========================================================
# TABLE RENDERING (numbered + bordered)
# ==========================================================
EXPORT_COLUMNS = [
    "Symbol", "Company", "Sector", "Bias", "Sector Flow", "Tradable (3-Pillar)", "Status", "Action",
    "CMP (Rs)", "Day %", "Smart Money Zone (Rs)", "CHoCH Trigger (Rs)", "Dist. to CHoCH %", "BOS Level (Rs)",
    "Last 15m Close (Rs)", "Invalidation / SL (Rs)", "Target 1", "Target 2", "Target 3",
    "T1 %", "T2 %", "T3 %", "R:R (T1)", "Volume Spurt (x)", "Delivery %", "Radar Age (Days)", "Catalyst Remark",
]
COMPACT_COLUMNS = [
    "Symbol", "Bias", "Status", "CMP (Rs)", "CHoCH Trigger (Rs)", "Invalidation / SL (Rs)",
    "Target 1", "R:R (T1)", "Volume Spurt (x)", "Delivery %",
]

# column -> (formatter, colour-by-sign)
FORMATS = {
    "Day %": (lambda v: f"{v:+.2f}%", True),
    "Dist. to CHoCH %": (lambda v: f"{v:+.2f}%", False),
    "T1 %": (lambda v: f"{v:.1f}%", False), "T2 %": (lambda v: f"{v:.1f}%", False),
    "T3 %": (lambda v: f"{v:.1f}%", False),
    "Delivery %": (lambda v: f"{v:.1f}%", False),
    "Volume Spurt (x)": (lambda v: f"{v:.2f}x", False),
    "R:R (T1)": (lambda v: f"1 : {v:.2f}", False),
    "Recent 12D Share (%)": (lambda v: f"{v:.2f}%", False),
    "Base Share (%)": (lambda v: f"{v:.2f}%", False),
    "Flow Shift (%)": (lambda v: f"{v:+.2f}%", True),
    "P&L (Rs)": (lambda v: f"{v:+,.2f}", True),
    "P&L %": (lambda v: f"{v:+.2f}%", True),
    "Radar Age (Days)": (lambda v: f"{int(v)}", False),
    "Qty": (lambda v: f"{int(v):,}", False),
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
        return "<div class='empty'>No records match the current filters.</div>"
    head = "<th class='c-no'>No.</th>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        tone = row.get("_tone", "n")
        cells = [f"<td class='c-no t-{tone}'>{i}</td>"]
        for c in cols:
            txt, cls = fmt_cell(c, row[c])
            if c in badge_cols:
                cells.append(f"<td><span class='bdg b-{tone}'>{txt}</span></td>")
            else:
                cells.append(f"<td class='{cls}'>{txt}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f"<div class='tbl-wrap' style='max-height:{height}px'><table class='smc'>"
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")


def numbered(df: pd.DataFrame) -> pd.DataFrame:
    d = df.reset_index(drop=True).copy()
    d.insert(0, "No.", np.arange(1, len(d) + 1))
    return d


def section(num: str, title: str, sub: str = "") -> None:
    sub_html = f"<span class='sec-sub'>{html.escape(sub)}</span>" if sub else ""
    st.markdown(f"<div class='sec'><span class='sec-no'>{num}</span>{html.escape(title)}{sub_html}</div>",
                unsafe_allow_html=True)


# ==========================================================
# EXCEL GENERATOR (numbered + bordered)
# ==========================================================
XL_FMT = {
    "CMP (Rs)": "#,##0.00", "CHoCH Trigger (Rs)": "#,##0.00", "BOS Level (Rs)": "#,##0.00",
    "Last 15m Close (Rs)": "#,##0.00", "Invalidation / SL (Rs)": "#,##0.00",
    "Target 1": "#,##0.00", "Target 2": "#,##0.00", "Target 3": "#,##0.00",
    "Day %": '+0.00"%";-0.00"%"', "Dist. to CHoCH %": '+0.00"%";-0.00"%"', "Flow Shift (%)": '+0.00"%";-0.00"%"',
    "T1 %": '0.0"%"', "T2 %": '0.0"%"', "T3 %": '0.0"%"', "Delivery %": '0.0"%"',
    "R:R (T1)": "0.00", "Volume Spurt (x)": '0.00"x"',
    "Recent 12D Share (%)": '0.00"%"', "Base Share (%)": '0.00"%"',
}


def _write_sheet(ws, df: pd.DataFrame, cols: list[str], freeze: str) -> None:
    head_fill = PatternFill("solid", start_color="161B22", end_color="161B22")
    alt_fill = PatternFill("solid", start_color="F3F6FA", end_color="F3F6FA")
    side = Side(style="thin", color="B8C0CC")
    border = Border(left=side, right=side, top=side, bottom=side)
    headers = ["No."] + cols
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.border = head_fill, border
        cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30

    clean = df[cols].astype(object).where(pd.notna(df[cols]), None)
    for i, rec in enumerate(clean.to_dict("records"), start=2):
        ws.append([i - 1] + [rec[c] for c in cols])
        for j, h in enumerate(headers, start=1):
            cell = ws.cell(row=i, column=j)
            cell.border = border
            cell.alignment = Alignment(vertical="center", horizontal="center" if j == 1 else None)
            if i % 2 == 1:
                cell.fill = alt_fill
            if h in XL_FMT:
                cell.number_format = XL_FMT[h]
            if h == "Bias" and cell.value:
                cell.font = Font(bold=True, color="1A7F37" if cell.value == "BULLISH" else "CF222E")

    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        longest = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[letter].width = min(max(longest + 3, 8 if letter == "A" else 12), 50)
    ws.freeze_panes = freeze
    ws.auto_filter.ref = ws.dimensions


def generate_excel_export(df: pd.DataFrame, sec_df: pd.DataFrame) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Audited_SMC_Radar"
    _write_sheet(ws, df, EXPORT_COLUMNS, "C2")
    ws2 = wb.create_sheet("Sector_Rotation")
    _write_sheet(ws2, sec_df, ["Sector", "Recent 12D Share (%)", "Base Share (%)", "Flow Shift (%)", "Flow Signal"], "C2")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ==========================================================
# TRADE BOOK ENGINE
# ==========================================================
def load_trades() -> list:
    if os.path.exists(TRADE_BOOK_PATH):
        try:
            with open(TRADE_BOOK_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_trades(trades: list) -> None:
    os.makedirs(os.path.dirname(TRADE_BOOK_PATH), exist_ok=True)
    with open(TRADE_BOOK_PATH, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)


def trade_row(t: dict, quotes: dict) -> dict:
    side = t.get("side", "LONG")
    mult = 1 if side == "LONG" else -1
    closed = t.get("status") == "CLOSED"
    px = t.get("exit") if closed else (quotes.get(t["symbol"]) or {}).get("cmp")
    pnl = (px - t["entry"]) * mult * t["qty"] if px is not None else np.nan
    pnl_pct = (px / t["entry"] - 1) * 100 * mult if px is not None else np.nan
    return {
        "ID": t["id"], "Symbol": t["symbol"], "Side": side, "Qty": t["qty"],
        "Entry (Rs)": t["entry"], "SL (Rs)": t["sl"],
        "CMP / Exit (Rs)": px, "P&L (Rs)": pnl, "P&L %": pnl_pct,
        "Risk (Rs)": abs(t["entry"] - t["sl"]) * t["qty"],
        "Status": t.get("status", "OPEN"), "Opened": t.get("date", ""),
        "_tone": "n" if np.isnan(pnl) else "g" if pnl > 0 else "r" if pnl < 0 else "n",
    }


# ==========================================================
# UI STYLING
# ==========================================================
CSS = """
<style>
  .block-container{padding-top:1.4rem;max-width:1600px;}
  div[data-testid="stMetric"]{background:linear-gradient(180deg,#161B22,#10151C);border:1px solid #30363D;
      border-left:3px solid #58A6FF;padding:12px 16px;border-radius:8px;}
  div[data-testid="stMetricLabel"]{color:#8B949E;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;}
  div[data-testid="stMetricValue"]{color:#F0F6FC;font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700;}
  div[data-testid="stDataFrame"]{border:1px solid #30363D;border-radius:8px;padding:2px;}
  div[data-testid="stForm"]{border:1px solid #30363D;border-radius:8px;background:#0F141B;}
  .stTabs [data-baseweb="tab-list"]{gap:6px;border-bottom:1px solid #30363D;}
  .stTabs [data-baseweb="tab"]{background-color:#161B22;border:1px solid #30363D;border-bottom:none;
      border-radius:6px 6px 0 0;color:#C9D1D9;padding:8px 18px;}
  .stTabs [aria-selected="true"]{background-color:#21262D !important;color:#58A6FF !important;
      border-bottom:2px solid #58A6FF !important;}
  /* header */
  .hdr{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;
      background:linear-gradient(90deg,#0D1117,#161B22);border:1px solid #30363D;border-radius:10px;
      padding:16px 22px;margin-bottom:14px;}
  .hdr h1{margin:0;font-size:24px;color:#F0F6FC;letter-spacing:.01em;}
  .hdr .sub{color:#8B949E;font-size:12.5px;margin-top:2px;}
  .chips{display:flex;gap:8px;flex-wrap:wrap;}
  .chip{border:1px solid #30363D;background:#0D1117;color:#C9D1D9;border-radius:999px;padding:5px 12px;
      font-size:12px;font-family:'JetBrains Mono',monospace;}
  .chip b{color:#8B949E;font-weight:600;margin-right:6px;font-family:inherit;}
  /* section titles */
  .sec{display:flex;align-items:center;gap:10px;margin:18px 0 10px;font-size:17px;font-weight:700;color:#F0F6FC;
      border-bottom:1px solid #30363D;padding-bottom:8px;}
  .sec-no{background:#1F6FEB;color:#fff;border-radius:5px;padding:1px 9px;font-size:13px;
      font-family:'JetBrains Mono',monospace;}
  .sec-sub{margin-left:auto;font-size:12px;font-weight:400;color:#8B949E;}
  /* bordered tables */
  .tbl-wrap{overflow:auto;border:1px solid #30363D;border-radius:8px;background:#0D1117;}
  table.smc{border-collapse:collapse;width:100%;font-size:12.5px;}
  table.smc th{position:sticky;top:0;z-index:2;background:#161B22;color:#8B949E;border:1px solid #30363D;
      padding:9px 11px;text-transform:uppercase;font-size:10.5px;letter-spacing:.05em;white-space:nowrap;text-align:left;}
  table.smc td{border:1px solid #21262D;padding:7px 11px;white-space:nowrap;color:#C9D1D9;}
  table.smc tbody tr:nth-child(even) td{background:#0F141B;}
  table.smc tbody tr:hover td{background:#1B2230;}
  table.smc td.num{text-align:right;font-family:'JetBrains Mono',monospace;}
  table.smc td.pos{color:#3FB950;} table.smc td.neg{color:#F85149;}
  table.smc th.c-no,table.smc td.c-no{text-align:center;width:44px;color:#8B949E;
      font-family:'JetBrains Mono',monospace;background:#12171F !important;}
  td.c-no.t-g{border-left:3px solid #3FB950;} td.c-no.t-r{border-left:3px solid #F85149;}
  td.c-no.t-o{border-left:3px solid #F0883E;} td.c-no.t-y{border-left:3px solid #D29922;}
  td.c-no.t-b{border-left:3px solid #58A6FF;} td.c-no.t-n{border-left:3px solid #484F58;}
  .bdg{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid;}
  .b-g{color:#3FB950;background:#12261A;border-color:#238636;} .b-r{color:#F85149;background:#2D1214;border-color:#DA3633;}
  .b-o{color:#F0883E;background:#2B1B0E;border-color:#BD561D;} .b-y{color:#D29922;background:#272010;border-color:#9E6A03;}
  .b-b{color:#58A6FF;background:#0F2036;border-color:#1F6FEB;} .b-n{color:#8B949E;background:#161B22;border-color:#30363D;}
  .empty{border:1px dashed #30363D;border-radius:8px;padding:22px;text-align:center;color:#8B949E;}
  .legend{color:#8B949E;font-size:12px;margin:4px 0 8px;}
  .foot{margin-top:26px;padding-top:12px;border-top:1px solid #30363D;color:#6E7681;font-size:11.5px;text-align:center;}
  .gate{text-align:center;margin-top:60px;} .gate h2{margin:6px 0 2px;color:#F0F6FC;} .gate p{color:#8B949E;}
  .gate-ico{font-size:42px;}
</style>
"""

COLUMN_CONFIG = {
    "No.": st.column_config.NumberColumn("No.", format="%d", width="small"),
    "CMP (Rs)": st.column_config.NumberColumn(format="%.2f"),
    "Day %": st.column_config.NumberColumn(format="%.2f"),
    "Dist. to CHoCH %": st.column_config.NumberColumn(format="%.2f"),
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
    "Recent 12D Share (%)": st.column_config.NumberColumn(format="%.2f%%"),
    "Base Share (%)": st.column_config.NumberColumn(format="%.2f%%"),
    "Flow Shift (%)": st.column_config.NumberColumn(format="%+.2f%%"),
}


def show_table(df: pd.DataFrame, cols: list[str], mode: str, badge: tuple = ("Status",), height: int = 560) -> None:
    if mode == "Bordered Report":
        st.markdown(html_table(df, cols, badge_cols=badge, height=height), unsafe_allow_html=True)
    else:
        st.dataframe(numbered(df[cols]), hide_index=True, height=height,
                     column_config=COLUMN_CONFIG, **STRETCH)


# ==========================================================
# MAIN
# ==========================================================
def main():
    st.set_page_config(page_title="Institutional Smart Money Terminal", page_icon="⚡", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    if not auth_gate():
        st.stop()

    radar = build_radar()
    live = fetch_live_quotes(tuple(radar["symbol"]))
    quotes, fetched_at = live["quotes"], live["fetched_at"]

    with st.sidebar:
        st.markdown("### ⚙️ 1. Controls")
        if st.button("🔄 Refresh Live Data", **STRETCH):
            st.cache_data.clear()
            st.rerun()
        view_mode = st.radio("2. View Mode", ["Bordered Report", "Interactive Grid"], horizontal=True)
        bias_filter = st.selectbox("3. Trading Bias", ["All Setups", "BULLISH Setups Only", "BEARISH Setups Only"])
        tradable_only = st.toggle("4. Tradable Only (P1 + P2)", value=False)
        max_chase = st.slider("5. Max Extension vs Trigger (%)", 0.5, 5.0, 2.0, 0.5)
        text_filter = st.text_input("6. Search Symbol / Sector").strip().lower()
        st.markdown("---")
        if st.button("🔒 Lock Terminal", **STRETCH):
            st.session_state["authenticated"] = False
            st.rerun()

    df = evaluate_setups(radar, quotes, max_chase)
    sec_df = build_sector_df()
    regime = get_market_regime()
    now = now_ist()
    mkt = market_state(now)
    regime_txt = (f"{regime['regime']} · Nifty {regime['nifty']:,.0f} ({fmt_pct(regime['nifty_chg'])})"
                  if regime["ok"] else "Index feed offline")

    st.markdown(
        "<div class='hdr'><div><h1>⚡ Institutional Smart Money Terminal</h1>"
        "<div class='sub'>Three-Pillar SMC · 22 NSE Sector Rotation · Delivery Spurt · 15m CHoCH / BOS</div></div>"
        "<div class='chips'>"
        f"<span class='chip'><b>SYNC</b>{fetched_at.strftime('%d-%b-%Y %I:%M:%S %p IST')}</span>"
        f"<span class='chip'><b>MARKET</b>{html.escape(mkt)}</span>"
        f"<span class='chip'><b>REGIME</b>{html.escape(regime_txt)}</span>"
        "</div></div>", unsafe_allow_html=True)

    if not quotes:
        st.warning("Live quote feed returned no data. Statuses show NO LIVE DATA until the feed recovers.")

    m = st.columns(6)
    m[0].metric("1 · Tracked", len(df))
    m[1].metric("2 · Tradable (P1+P2)", int(df["_tradable"].sum()))
    m[2].metric("3 · ⚡ Active Triggers", int(df["_key"].isin(["ACTIVE", "BEAR_ACTIVE"]).sum()))
    m[3].metric("4 · 🚀 BOS Momentum", int(df["_key"].isin(["BOS", "BEAR_BOS"]).sum()))
    m[4].metric("5 · Inflow Aligned", int(df["Sector Flow"].str.contains("Inflow").sum()))
    m[5].metric("6 · Blocked", int((df["_key"] == "BLOCKED").sum()))

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

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "1 ▸ Live Radar", "2 ▸ Sector Rotation (P1)", "3 ▸ Audit & Export", "4 ▸ Trade Book", "5 ▸ Methodology",
    ])

    # ---------------- TAB 1 ----------------
    with tab1:
        section("1.1", "Actionable Now", "Tradable + confirmed 15m CHoCH / BOS")
        act = df[df["_key"].isin(ACTIONABLE_KEYS) & df["_tradable"]]
        if act.empty:
            st.markdown("<div class='empty'>No confirmed actionable setups right now.</div>", unsafe_allow_html=True)
        else:
            show_table(act, COMPACT_COLUMNS, view_mode, height=300)

        section("1.2", "Full Accumulation / Distribution Radar", f"{len(view)} of {len(df)} setups shown")
        st.markdown("<div class='legend'>Bullish: valid on a completed 15m close above CHoCH; BOS marks expansion. "
                    "Bearish: breakdown below CHoCH / BOS. Left bar colour = status tone.</div>", unsafe_allow_html=True)
        show_table(view, [c for c in EXPORT_COLUMNS if c in view.columns], view_mode, height=560)

    # ---------------- TAB 2 ----------------
    with tab2:
        section("2.1", "NSE Institutional Capital Flow (22 Sectors)", "Rule: Longs only in Inflow, Shorts only in Outflow")
        s_cols = ["Sector", "Recent 12D Share (%)", "Base Share (%)", "Flow Shift (%)", "Flow Signal"]
        n_in = int((sec_df["_status"] == True).sum())  # noqa: E712
        n_out = int((sec_df["_status"] == False).sum())  # noqa: E712
        c1, c2, c3 = st.columns(3)
        c1.metric("Inflow Sectors", n_in)
        c2.metric("Outflow Sectors", n_out)
        c3.metric("Neutral", len(sec_df) - n_in - n_out)

        section("2.2", "🟢 Inflow Sectors")
        show_table(sec_df[sec_df["_status"] == True], s_cols, view_mode, badge=("Flow Signal",), height=330)  # noqa: E712
        section("2.3", "🔴 Outflow Sectors")
        show_table(sec_df[sec_df["_status"] == False], s_cols, view_mode, badge=("Flow Signal",), height=480)  # noqa: E712
        neutral = sec_df[sec_df["_status"].isna()]
        if not neutral.empty:
            section("2.4", "⚪ Neutral Sectors")
            show_table(neutral, s_cols, view_mode, badge=("Flow Signal",), height=200)
        section("2.5", "Flow Shift Chart", "Share change vs base (pp)")
        st.bar_chart(sec_df.set_index("Sector")["Flow Shift (%)"], height=320)

    # ---------------- TAB 3 ----------------
    with tab3:
        section("3.1", "Audited Radar Data", "Live on-screen audit - no need to open Excel")
        show_table(df, EXPORT_COLUMNS, view_mode, height=450)
        section("3.2", "Offline Export")
        xlsx = generate_excel_export(df, sec_df)
        st.download_button(
            "📥 Download Audited Excel (.xlsx)", data=xlsx,
            file_name=f"SMC_Institutional_Radar_{now.strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", **STRETCH,
        )

    # ---------------- TAB 4 ----------------
    with tab4:
        if "trades" not in st.session_state:
            st.session_state.trades = load_trades()
        trades = st.session_state.trades

        rows = [trade_row(t, quotes) for t in trades]
        t_df = pd.DataFrame(rows)
        open_df = t_df[t_df["Status"] == "OPEN"] if not t_df.empty else t_df
        closed_df = t_df[t_df["Status"] == "CLOSED"] if not t_df.empty else t_df
        open_pnl = float(open_df["P&L (Rs)"].sum()) if not open_df.empty else 0.0
        real_pnl = float(closed_df["P&L (Rs)"].sum()) if not closed_df.empty else 0.0
        win = (f"{(closed_df['P&L (Rs)'] > 0).mean() * 100:.0f}%" if not closed_df.empty else "n/a")

        section("4.1", "Position Summary")
        k = st.columns(4)
        k[0].metric("Open Positions", len(open_df))
        k[1].metric("Open P&L (Rs)", f"{open_pnl:+,.2f}")
        k[2].metric("Realised P&L (Rs)", f"{real_pnl:+,.2f}")
        k[3].metric("Win Rate (Closed)", win)

        section("4.2", "Log New Position")
        s_sym = st.selectbox("Symbol", radar["symbol"].tolist())  # outside form -> defaults follow symbol
        row_match = radar.loc[radar["symbol"] == s_sym].iloc[0]
        is_long = row_match["bias"] == "BULLISH"
        default_p = (quotes.get(s_sym) or {}).get("cmp", row_match["snap_cmp"])
        with st.form("tb_add"):
            c1, c2, c3, c4, c5 = st.columns(5)
            p_side = c1.selectbox("Side", ["LONG", "SHORT"], index=0 if is_long else 1)
            p_entry = c2.number_input("Entry Price (Rs)", value=float(default_p), step=0.05)
            p_qty = c3.number_input("Quantity", value=1, min_value=1, step=1)
            p_sl = c4.number_input("Initial SL (Rs)", value=float(row_match["invalidation"]), step=0.05)
            c5.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            add = c5.form_submit_button("➕ Log Position", **STRETCH)
        if add:
            if (p_side == "LONG" and p_sl >= p_entry) or (p_side == "SHORT" and p_sl <= p_entry):
                st.error("Invalid SL: LONG needs SL below entry, SHORT needs SL above entry.")
            else:
                trades.append({
                    "id": uuid.uuid4().hex[:8], "symbol": s_sym, "side": p_side, "entry": p_entry,
                    "qty": int(p_qty), "sl": p_sl, "t1": float(row_match["t1"]), "t2": float(row_match["t2"]),
                    "t3": float(row_match["t3"]), "status": "OPEN", "date": now.strftime("%Y-%m-%d %H:%M"),
                })
                save_trades(trades)
                st.success(f"{p_side} {s_sym} logged.")
                st.rerun()

        section("4.3", "Trade Book", f"{len(t_df)} records")
        if t_df.empty:
            st.markdown("<div class='empty'>No trades logged yet.</div>", unsafe_allow_html=True)
        else:
            t_cols = ["ID", "Symbol", "Side", "Qty", "Entry (Rs)", "SL (Rs)", "CMP / Exit (Rs)",
                      "P&L (Rs)", "P&L %", "Risk (Rs)", "Status", "Opened"]
            show_table(t_df, t_cols, view_mode, badge=("Status",), height=380)

            section("4.4", "Manage Positions")
            mc1, mc2 = st.columns(2)
            open_ids = [t["id"] for t in trades if t.get("status") == "OPEN"]
            with mc1:
                with st.form("tb_close"):
                    cid = st.selectbox("Close position", open_ids) if open_ids else None
                    ex_px = st.number_input("Exit Price (Rs)", value=0.0, step=0.05)
                    if st.form_submit_button("✅ Close Position", **STRETCH) and cid:
                        for t in trades:
                            if t["id"] == cid:
                                t["status"] = "CLOSED"
                                t["exit"] = float(ex_px) if ex_px > 0 else float(
                                    (quotes.get(t["symbol"]) or {}).get("cmp", t["entry"]))
                                t["closed_at"] = now.strftime("%Y-%m-%d %H:%M")
                        save_trades(trades)
                        st.rerun()
                    st.caption("Exit price 0 = use current CMP.")
            with mc2:
                with st.form("tb_del"):
                    did = st.selectbox("Delete record", [t["id"] for t in trades])
                    if st.form_submit_button("🗑️ Delete Record", **STRETCH):
                        st.session_state.trades = [t for t in trades if t["id"] != did]
                        save_trades(st.session_state.trades)
                        st.rerun()

    # ---------------- TAB 5 ----------------
    with tab5:
        section("5.1", "Three-Pillar Framework")
        st.markdown(
            f"1. **Pillar 1 – Sector Rotation:** longs only in sectors with positive share shift, shorts only in negative. "
            f"A shift of ±{HEAVY_SHIFT:.2f}pp or more is *Heavy*.\n"
            f"2. **Pillar 2 – Delivery Spurt:** delivery ≥ {MIN_DELIVERY_PCT:.0f}% and volume spurt ≥ {MIN_SPURT:.1f}x.\n"
            f"3. **Pillar 3 – Execution:** completed {CANDLE_MIN}m close beyond CHoCH confirms entry; BOS marks expansion; "
            f"close beyond invalidation cancels the setup.")
        section("5.2", "Status Legend")
        legend = pd.DataFrame([
            ("ACTIVE / BEAR_ACTIVE", "15m CHoCH confirmed, within chase limit", "g"),
            ("BOS / BEAR_BOS", "Structure break - trend expansion", "g"),
            ("EXTENDED", "Too far from trigger - wait for pullback / bounce", "o"),
            ("ZONE", "Inside accumulation / distribution zone", "b"),
            ("PRE", "Watching near trigger", "y"),
            ("BLOCKED", "Failed Pillar 1 or Pillar 2", "n"),
            ("INVALID", "Close beyond invalidation", "r"),
            ("STALE / NODATA", f"CMP deviates >{STALE_DEVIATION_PCT:.0f}% from snapshot / feed missing", "o"),
        ], columns=["Status", "Meaning", "_tone"])
        st.markdown(html_table(legend, ["Status", "Meaning"], badge_cols=("Status",), height=360), unsafe_allow_html=True)

    st.markdown("<div class='foot'>For educational and research use only. Not investment advice. "
                "Data via Yahoo Finance may be delayed or incomplete; verify before trading. "
                "Radar levels are static snapshots - refresh them regularly.</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
