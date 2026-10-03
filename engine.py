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


def fetch_history(sessions: int = 80):
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
# Corporate action adjustment (splits / bonus) - otherwise delivery qty jumps
# --------------------------------------------------------------------------- #
PRICE_COLS = ["PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE"]
QTY_COLS = ["TTL_TRD_QNTY", "DELIV_QTY"]


def session_pos(hist: pd.DataFrame) -> pd.Series:
    idx = pd.DatetimeIndex(sorted(hist.Date.unique()))
    return pd.Series(range(len(idx)), index=idx)


def adjust_splits(g: pd.DataFrame, pos: pd.Series) -> pd.DataFrame:
    """NSE's PREV_CLOSE is already adjusted on ex-date. A big gap between PREV_CLOSE and the
    previous row's CLOSE (on consecutive sessions) = split/bonus -> back-adjust history."""
    g = g.copy()
    f = g.PREV_CLOSE / g.CLOSE_PRICE.shift(1)
    consec = g.Date.map(pos).diff() == 1
    ev = consec & ((f < 0.9) | (f > 1.1))
    if not ev.any():
        return g
    factor = pd.Series(1.0, index=g.index)
    factor[ev] = f[ev]
    rev = factor.shift(-1).fillna(1.0)[::-1].cumprod()[::-1]
    for c in PRICE_COLS:
        g[c] = g[c] * rev
    for c in QTY_COLS:
        g[c] = g[c] / rev
    return g


def symbol_view(hist: pd.DataFrame, sym: str) -> pd.DataFrame:
    g = hist[hist.SYMBOL == sym].sort_values("Date")
    return adjust_splits(g, session_pos(hist))


# --------------------------------------------------------------------------- #
# Delivery flow helpers
# --------------------------------------------------------------------------- #
RECENT, BASE = 21, 42      # last 1 month vs the 2 months before it (3 months total)


def _flow(df: pd.DataFrame) -> float:
    """Net delivered qty: delivery on up-days minus delivery on down-days."""
    up, dn = df.CLOSE_PRICE > df.PREV_CLOSE, df.CLOSE_PRICE < df.PREV_CLOSE
    return float(df.DELIV_QTY[up].sum() - df.DELIV_QTY[dn].sum())


def weekly_flows(g: pd.DataFrame, weeks: int = 12) -> list[tuple]:
    out, n = [], len(g)
    for k in range(weeks - 1, -1, -1):
        seg = g.iloc[max(0, n - 5 * (k + 1)): n - 5 * k]
        if len(seg):
            out.append((seg.Date.iloc[-1], _flow(seg)))
    return out


# --------------------------------------------------------------------------- #
# Trade plan: range / base based (smart-money style), ATR fallback
# --------------------------------------------------------------------------- #
def _atr(g: pd.DataFrame) -> float:
    c, h, l = g.CLOSE_PRICE, g.HIGH_PRICE, g.LOW_PRICE
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return float(tr.tail(14).mean())


def _finish(lo, hi, sl, t1, t2, t3, status, extra=None):
    entry = (lo + hi) / 2
    risk = entry - sl
    if risk / entry > 0.10:                      # cap very wide stops at 10%
        sl, risk = entry * 0.90, entry * 0.10
        status += " | SL capped at 10%"
    t1 = max(t1, entry + 1.0 * risk)
    t2 = max(t2, entry + 2.0 * risk, t1 * 1.005)
    t3 = max(t3, entry + 3.5 * risk, t2 * 1.005)
    out = {"Entry_Low": round(lo, 2), "Entry_High": round(hi, 2), "Entry": round(entry, 2),
           "SL": round(sl, 2), "Risk_Pct": round(risk / entry * 100, 2),
           "T1": round(t1, 2), "T2": round(t2, 2), "T3": round(t3, 2), "Plan_Status": status}
    out.update(extra or {})
    return out


def make_plan(g, setup, hi_c, lo_c, lo_low) -> dict:
    atr = _atr(g)
    close = float(g.CLOSE_PRICE.iloc[-1])
    dma20 = float(g.CLOSE_PRICE.tail(20).mean())
    h = hi_c - lo_c
    extra = {"ATR": round(atr, 2)}

    if setup == "In range (base)" and h > 0:
        p = (close - lo_c) / h
        if p <= 0.6:
            lo, hi = max(lo_c, close - 0.5 * atr), close
            status = "Buy within range (near support)"
        else:
            lo, hi = lo_c + 0.3 * h, lo_c + 0.5 * h
            status = f"Near range top - buy dip, or breakout above Rs {hi_c * 1.005:.2f}"
        sl = lo_low - 0.25 * atr
        return _finish(lo, hi, sl, hi_c, hi_c + 0.5 * h, hi_c + 1.0 * h, status, extra)

    if setup == "Breakout" and h > 0:
        if close > hi_c * 1.05:
            lo, hi = hi_c, hi_c + 0.5 * atr
            status = f"Extended after breakout - wait for retest of Rs {hi_c:.2f}"
        else:
            lo, hi = hi_c, max(close, hi_c + 0.1 * atr)
            status = f"Fresh breakout - buy near/after retest of Rs {hi_c:.2f}"
        sl = max(hi_c - 1.2 * atr, lo_low)
        return _finish(lo, hi, sl, hi_c + 0.5 * h, hi_c + 1.0 * h, hi_c + 1.5 * h, status, extra)

    # fallback: plain ATR plan
    swing = float(g.LOW_PRICE.tail(10).min())
    if close > dma20 * 1.06:
        lo, hi, status = dma20, dma20 + 0.5 * atr, "No clear range, extended - wait for pullback to 20 DMA"
    else:
        lo, hi, status = close - 0.5 * atr, close, "No clear range - ATR plan"
    entry = (lo + hi) / 2
    sl = min(swing, entry - 1.5 * atr)
    risk = entry - sl
    return _finish(lo, hi, sl, entry + 1.5 * risk, entry + 2.5 * risk, entry + 4.0 * risk, status, extra)


# --------------------------------------------------------------------------- #
# Screener: last 1 month vs previous 2 months
# --------------------------------------------------------------------------- #
def compute_screener(hist: pd.DataFrame, extra: tuple = (), min_turnover_cr: float = 0.0) -> pd.DataFrame:
    pos = session_pos(hist)
    watch = set(SECTOR_OF) | set(extra)
    rows = []
    for sym, g in hist.groupby("SYMBOL", sort=False):
        if len(g) < RECENT + BASE or is_fund(sym):
            continue
        g = adjust_splits(g.sort_values("Date"), pos)
        c = g.CLOSE_PRICE
        r = c.pct_change()
        if r.tail(63).abs().max() > 0.30:        # unadjusted corporate action / bad data
            continue
        if r.tail(60).std() * 100 < 0.4:         # liquid / debt funds
            continue
        t = g.iloc[-1]
        if pd.isna(t.DELIV_QTY) or pd.isna(t.DELIV_PER):
            continue
        rec, base = g.iloc[-RECENT:], g.iloc[-(RECENT + BASE):-RECENT]
        turn_cr = g.TURNOVER_LACS.tail(63).mean() / 100
        if turn_cr < min_turnover_cr and sym not in watch:
            continue
        dq_1m, dq_3m = rec.DELIV_QTY.mean(), base.DELIV_QTY.mean()
        dp_1m, dp_3m = rec.DELIV_PER.mean(), base.DELIV_PER.mean()
        vol_b = base.TTL_TRD_QNTY.mean()
        if not (dq_3m > 0 and vol_b > 0) or pd.isna(dp_1m) or pd.isna(dp_3m):
            continue
        qty_x, pp = dq_1m / dq_3m, dp_1m - dp_3m
        today_x = t.DELIV_QTY / dq_3m
        vol_x = rec.TTL_TRD_QNTY.mean() / vol_b

        flow_1m = _flow(rec) / max(rec.DELIV_QTY.sum(), 1)
        flow_3m = _flow(base) / max(base.DELIV_QTY.sum(), 1)
        flows = [f for _, f in weekly_flows(g, 4)]
        buy_weeks = int(sum(f > 0 for f in flows))
        last_wk = bool(flows and flows[-1] > 0)
        if buy_weeks >= 3 and last_wk:
            bstat = "Continuing"
        elif last_wk:
            bstat = "Just started"
        elif buy_weeks >= 2:
            bstat = "Fading"
        else:
            bstat = "Not buying"

        strong = (rec.DELIV_QTY > dq_3m) & (rec.DELIV_PER > dp_3m)
        acc_days = int((strong & (rec.CLOSE_PRICE >= rec.PREV_CLOSE)).sum())
        dist_days = int((strong & (rec.CLOSE_PRICE < rec.PREV_CLOSE)).sum())

        # range / base (last 30 sessions before today)
        rng = g.iloc[-31:-1]
        hi_c, lo_c, lo_low = rng.CLOSE_PRICE.max(), rng.CLOSE_PRICE.min(), rng.LOW_PRICE.min()
        range_pct = (hi_c / lo_c - 1) * 100
        close = float(t.CLOSE_PRICE)
        if close > hi_c:
            setup = "Breakout"
        elif close < lo_c * 0.99:
            setup = "Breakdown"
        elif range_pct <= 25:
            setup = "In range (base)"
        else:
            setup = "Trending / wide"

        dma20 = c.tail(20).mean()
        run20 = (close / c.tail(20).min() - 1) * 100
        from_hi = (close / c.tail(60).max() - 1) * 100
        if run20 >= 18 or close > dma20 * 1.10:
            stage = "Extended (already ran)"
        elif run20 >= 10:
            stage = "Rally on"
        elif run20 >= 5:
            stage = "Early move"
        else:
            stage = "Base (not moved)"

        s = 0
        s += 20 if qty_x >= 1.5 else 14 if qty_x >= 1.2 else 7 if qty_x >= 1.05 else 0
        s += 15 if pp >= 8 else 10 if pp >= 4 else 4 if pp > 0 else 0
        s += 20 if flow_1m >= 0.3 else 14 if flow_1m >= 0.15 else 7 if flow_1m > 0 else 0
        s += 15 if buy_weeks == 4 else 11 if buy_weeks == 3 else 6 if buy_weeks == 2 else 0
        s += 10 if setup in ("In range (base)", "Breakout") else 0
        s += 10 if close >= lo_c * 0.99 else 0
        s += 10 if today_x >= 1 else 0
        signal = "Strong Accumulation" if s >= 75 else "Accumulation" if s >= 55 else "Neutral"
        if s < 55 and (dist_days > acc_days or flow_1m < -0.1):
            signal = "Distribution"
        if vol_x < 0.5 and signal != "Distribution":
            signal = "Low volume (ignore)"

        plan = make_plan(g, setup, hi_c, lo_c, lo_low)
        if close > plan["Entry_High"] * 1.003:
            est = "Above zone (wait)"
        elif close < plan["Entry_Low"] * 0.997:
            est = "Below zone"
        else:
            est = "In zone"
        rows.append({
            "Symbol": sym, "Sector": SECTOR_OF.get(sym, "-"), "Price": round(close, 2),
            "Chg_Pct": round(float((close / t.PREV_CLOSE - 1) * 100), 2),
            "Deliv_Per": round(float(t.DELIV_PER), 1), "Deliv_Per_1M": round(float(dp_1m), 1),
            "Deliv_Per_3M": round(float(dp_3m), 1), "Deliv_Per_Chg": round(float(pp), 1),
            "Deliv_Qty": int(t.DELIV_QTY), "Deliv_Qty_1M": int(dq_1m), "Deliv_Qty_3M": int(dq_3m),
            "Deliv_Qty_X": round(float(qty_x), 2), "Today_X": round(float(today_x), 2),
            "Vol_X": round(float(vol_x), 2),
            "Net_Flow_1M": round(float(flow_1m) * 100, 0), "Net_Flow_3M": round(float(flow_3m) * 100, 0),
            "Buy_Weeks": buy_weeks, "Buying_Status": bstat,
            "Acc_Days": acc_days, "Dist_Days": dist_days,
            "Setup": setup, "Range_Pct": round(float(range_pct), 1),
            "Range_Hi": round(float(hi_c), 2), "Range_Lo": round(float(lo_c), 2),
            "Run_20D": round(float(run20), 1), "From_60D_High": round(float(from_hi), 1), "Stage": stage,
            "Avg_Turnover_Cr": round(float(turn_cr), 1), "Score": int(s), "Signal": signal,
            "Entry_Status": est, "Entry_Gap": round((close / plan["Entry"] - 1) * 100, 2),
            "Entry_Zone": f"{plan['Entry_Low']:.2f} - {plan['Entry_High']:.2f}", **plan,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["Score", "Deliv_Qty_X"], ascending=False).reset_index(drop=True)
