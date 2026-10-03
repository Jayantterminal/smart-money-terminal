"""
engine.py - Delivery-based accumulation engine (NSE bhavcopy)
Source: NSE sec_bhavdata_full_DDMMYYYY.csv (price, volume, delivery qty, delivery %)
"""
from __future__ import annotations

import datetime as dt
import io
import os
import re
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import pandas as pd
import requests

IST = ZoneInfo("Asia/Kolkata")
CACHE_DIR = os.path.join("data", "bhav")
URLS = [
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d}.csv",
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{d}.csv",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/csv,*/*",
    "Referer": "https://www.nseindia.com/",
}

# NSE symbols (no .NS). Edit freely or add more from the app sidebar.
WATCHLIST = {
    "Bank": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK"],
    "PSU Bank": ["SBIN", "BANKBARODA", "PNB", "CANBK", "UNIONBANK"],
    "Fin Services": ["BAJFINANCE", "BAJAJFINSV", "BAJAJHFL", "SBILIFE", "HDFCLIFE", "CHOLAFIN",
                     "LICHSGFIN", "PNBHOUSING", "CANFINHOME"],
    "IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM"],
    "Pharma": ["SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "LUPIN", "AUROPHARMA"],
    "Auto": ["MARUTI", "M&M", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", "TVSMOTOR"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "GODREJCP"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "NMDC"],
    "Energy": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA", "BPCL"],
    "Realty": ["DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "LODHA"],
    "Infra": ["LT", "ADANIPORTS", "SIEMENS", "ULTRACEMCO", "GRASIM"],
    "Media": ["SUNTV", "PVRINOX", "ZEEL"],
}
SECTOR_OF = {s: sec for sec, lst in WATCHLIST.items() for s in lst}

# ETFs / liquid & debt funds also trade in NSE "EQ" series - exclude them.
# Add any leftover symbol here to hide it permanently.
EXCLUDE = {"GOLDSHARE", "AXISGOLD", "SBIGOLD", "KOTAKGOLD", "TATAGOLD", "HDFCGOLD", "LICMFGOLD",
           "SILVERIETF", "CPSEETF", "GOLD1", "GOLDCASE", "SILVER1"}
_FUND_RE = re.compile(r"(BEES|ETF|LIQUID|GILT|NIFTY|SENSEX|NEXT50|MON100|MOM100|LOWVOL|QUAL30|"
                      r"MOVALUE|MOSMALL|MAFANG|MOMENTUM|MID150|SMALL250|TOP100|OVERNIGHT)")


def is_fund(sym: str) -> bool:
    return sym in EXCLUDE or bool(_FUND_RE.search(sym))


COLS = ["SYMBOL", "Date", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE",
        "TTL_TRD_QNTY", "TURNOVER_LACS", "DELIV_QTY", "DELIV_PER"]


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


# --------------------------------------------------------------------------- #
# Download (parallel, cached per day on disk)
# --------------------------------------------------------------------------- #
def _parse(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text), skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    df = df[df["SERIES"].astype(str).str.strip() == "EQ"].copy()
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
    df["Date"] = pd.to_datetime(df["DATE1"].astype(str).str.strip(), format="%d-%b-%Y")
    for c in COLS[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[COLS]


def _get_day(day: dt.date):
    """Returns (day, DataFrame|None, status)  status: ok | holiday | error"""
    path = os.path.join(CACHE_DIR, f"{day:%Y%m%d}.csv")
    miss = path + ".none"
    if os.path.exists(path):
        return day, pd.read_csv(path, parse_dates=["Date"]), "ok"
    if os.path.exists(miss):
        return day, None, "holiday"
    stamp = f"{day:%d%m%Y}"
    saw_404 = False
    for url in URLS:
        try:
            r = requests.get(url.format(d=stamp), headers=HEADERS, timeout=25)
            if r.status_code == 200 and len(r.text) > 5000:
                df = _parse(r.text)
                os.makedirs(CACHE_DIR, exist_ok=True)
                df.to_csv(path, index=False)
                return day, df, "ok"
            if r.status_code == 404:
                saw_404 = True
        except Exception:
            continue
    if saw_404:
        if day < now_ist().date():  # old 404 = market holiday, remember it
            os.makedirs(CACHE_DIR, exist_ok=True)
            open(miss, "w").close()
        return day, None, "holiday"
    return day, None, "error"


def fetch_history(sessions: int = 70):
    today = now_ist().date()
    days = [today - dt.timedelta(days=i) for i in range(0, 135)]
    days = [d for d in days if d.weekday() < 5]
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(_get_day, days))
    frames = [df for _, df, s in res if s == "ok" and df is not None]
    errors = sum(1 for _, _, s in res if s == "error")
    if not frames:
        return pd.DataFrame(), {"days": 0, "errors": errors}
    hist = pd.concat(frames, ignore_index=True)
    keep = sorted(hist.Date.unique())[-sessions:]
    hist = hist[hist.Date.isin(keep)].sort_values(["SYMBOL", "Date"]).reset_index(drop=True)
    return hist, {"days": len(keep), "errors": errors}


# --------------------------------------------------------------------------- #
# Trade plan (ATR based, mechanical)
# --------------------------------------------------------------------------- #
def trade_plan(g: pd.DataFrame) -> dict:
    c, h, l = g.CLOSE_PRICE, g.HIGH_PRICE, g.LOW_PRICE
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = float(tr.tail(14).mean())
    close = float(c.iloc[-1])
    dma20 = float(c.tail(20).mean())
    swing = float(l.tail(10).min())

    if close > dma20 * 1.06:  # extended -> wait for pullback
        lo, hi = dma20, dma20 + 0.5 * atr
        status = "Extended - wait for pullback to 20 DMA"
    else:
        lo, hi = close - 0.5 * atr, close
        status = "Buy on small dip / near CMP"
    entry = (lo + hi) / 2
    sl = min(swing, entry - 1.5 * atr)
    wide = (entry - sl) / entry > 0.08
    if wide:
        sl = entry * 0.92
    risk = entry - sl
    return {
        "Entry_Low": round(lo, 2), "Entry_High": round(hi, 2), "Entry": round(entry, 2),
        "SL": round(sl, 2), "Risk_Pct": round(risk / entry * 100, 2),
        "T1": round(entry + 1.5 * risk, 2), "T2": round(entry + 2.5 * risk, 2),
        "T3": round(entry + 4.0 * risk, 2),
        "ATR": round(atr, 2), "DMA20": round(dma20, 2), "Swing_Low10": round(swing, 2),
        "Plan_Status": status + (" | SL capped at 8%" if wide else ""),
    }


# --------------------------------------------------------------------------- #
# Accumulation screener
# --------------------------------------------------------------------------- #
def compute_screener(hist: pd.DataFrame, extra: tuple = (), min_turnover_cr: float = 2.0) -> pd.DataFrame:
    watch = set(SECTOR_OF) | set(extra)
    rows = []
    for sym, g in hist.groupby("SYMBOL", sort=False):
        if len(g) < 25 or is_fund(sym):
            continue
        # liquid/debt funds barely move (daily std < 0.4%) -> not stocks
        if g.CLOSE_PRICE.pct_change().tail(60).std() * 100 < 0.4:
            continue
        t, base = g.iloc[-1], g.iloc[-21:-1]
        if pd.isna(t.DELIV_QTY) or pd.isna(t.DELIV_PER):
            continue
        turn_cr = base.TURNOVER_LACS.mean() / 100
        if turn_cr < min_turnover_cr and sym not in watch:
            continue
        adq, adp = base.DELIV_QTY.mean(), base.DELIV_PER.mean()
        avol = base.TTL_TRD_QNTY.mean()
        if not (adq > 0 and avol > 0) or pd.isna(adp):
            continue
        dq_x = t.DELIV_QTY / adq
        vol_x = t.TTL_TRD_QNTY / avol
        dpp = t.DELIV_PER - adp
        d5_x = g.DELIV_QTY.tail(5).mean() / adq
        l10 = g.tail(10)
        strong = (l10.DELIV_QTY > adq) & (l10.DELIV_PER > adp)
        acc_days = int((strong & (l10.CLOSE_PRICE >= l10.PREV_CLOSE)).sum())
        dist_days = int((strong & (l10.CLOSE_PRICE < l10.PREV_CLOSE)).sum())
        c = g.CLOSE_PRICE
        dma20 = c.tail(20).mean()
        c60 = c.tail(60)
        lo20, lo60, hi60 = c.tail(20).min(), c60.min(), c60.max()
        run20 = (c.iloc[-1] / lo20 - 1) * 100
        from_hi = (c.iloc[-1] / hi60 - 1) * 100
        range_pos = (c.iloc[-1] - lo60) / (hi60 - lo60) * 100 if hi60 > lo60 else 50.0
        if run20 >= 18 or c.iloc[-1] > dma20 * 1.10:
            stage = "Extended (already ran)"
        elif run20 >= 10:
            stage = "Rally on"
        elif run20 >= 5:
            stage = "Early move"
        else:
            stage = "Base (not moved)"

        s = 0
        s += 25 if dq_x >= 2 else 18 if dq_x >= 1.5 else 10 if dq_x >= 1.2 else 0
        s += 20 if dpp >= 10 else 12 if dpp >= 5 else 5 if dpp > 0 else 0
        s += 15 if d5_x >= 1.3 else 8 if d5_x >= 1.1 else 0
        s += 20 if acc_days >= 5 else 12 if acc_days >= 3 else 6 if acc_days >= 2 else 0
        s += 10 if c.iloc[-1] > dma20 else 0
        s += 10 if t.CLOSE_PRICE >= t.PREV_CLOSE else 0
        signal = "Strong Accumulation" if s >= 75 else "Accumulation" if s >= 55 else "Neutral"
        if s < 55 and dist_days > acc_days:
            signal = "Distribution"
        if vol_x < 0.5 and signal != "Distribution":
            signal = "Low volume (ignore)"

        plan = trade_plan(g)
        rows.append({
            "Symbol": sym, "Sector": SECTOR_OF.get(sym, "-"), "Price": round(float(t.CLOSE_PRICE), 2),
            "Chg_Pct": round(float((t.CLOSE_PRICE / t.PREV_CLOSE - 1) * 100), 2),
            "Deliv_Per": round(float(t.DELIV_PER), 1), "Avg_Deliv_Per": round(float(adp), 1),
            "Deliv_Per_Chg": round(float(dpp), 1),
            "Deliv_Qty": int(t.DELIV_QTY), "Avg_Deliv_Qty": int(adq),
            "Deliv_Qty_X": round(float(dq_x), 2), "Deliv_5D_X": round(float(d5_x), 2),
            "Vol_X": round(float(vol_x), 2),
            "Acc_Days_10D": acc_days, "Dist_Days_10D": dist_days,
            "Avg_Turnover_Cr": round(float(turn_cr), 1),
            "Run_20D": round(float(run20), 1), "From_60D_High": round(float(from_hi), 1),
            "Range_Pos": round(float(range_pos), 0), "Stage": stage,
            "Score": int(s), "Signal": signal, **plan,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["Score", "Deliv_Qty_X"], ascending=False).reset_index(drop=True)
