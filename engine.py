"""
engine.py - Delivery-based accumulation engine (NSE bhavcopy)
Source: NSE sec_bhavdata_full_DDMMYYYY.csv (price, volume, delivery qty, delivery %)
"""
from __future__ import annotations
import numpy as np
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
SECTOR_URLS = [
    "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
]
SECTOR_FILE = os.path.join("data", "sector_map.csv")


def fetch_sector_map() -> dict:
    """Symbol -> NSE Industry (Nifty 500 + Microcap 250 = ~750 stocks). Cached 7 days on disk."""
    try:
        if os.path.exists(SECTOR_FILE) and (dt.datetime.now().timestamp() - os.path.getmtime(SECTOR_FILE)) < 7 * 86400:
            m = pd.read_csv(SECTOR_FILE)
            return dict(zip(m.Symbol, m.Industry))
    except Exception:
        pass
    frames = []
    for url in SECTOR_URLS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                df = pd.read_csv(io.StringIO(r.text))
                df.columns = [c.strip() for c in df.columns]
                frames.append(df[["Symbol", "Industry"]])
        except Exception:
            continue
    if frames:
        m = pd.concat(frames).drop_duplicates("Symbol")
        m["Symbol"] = m.Symbol.astype(str).str.strip()
        os.makedirs("data", exist_ok=True)
        m.to_csv(SECTOR_FILE, index=False)
        return dict(zip(m.Symbol, m.Industry))
    try:  # stale cache is better than nothing
        m = pd.read_csv(SECTOR_FILE)
        return dict(zip(m.Symbol, m.Industry))
    except Exception:
        return {}


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


def _ret(c: pd.Series, n: int) -> float:
    return round(float((c.iloc[-1] / c.iloc[-1 - n] - 1) * 100), 1) if len(c) > n else float("nan")


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
def compute_screener(hist: pd.DataFrame, extra: tuple = (), min_turnover_cr: float = 0.0,
                     sector_map: dict | None = None) -> pd.DataFrame:
    sectors = sector_map or {}
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

        # --- fresh activity: catches a sudden accumulation day immediately (1M avg is slow) ---
        last5 = g.iloc[-5:]
        x5 = (last5.DELIV_QTY / dq_3m).values
        up5 = (last5.CLOSE_PRICE >= last5.PREV_CLOSE).values
        last5_x = float(last5.DELIV_QTY.mean() / dq_3m)
        pattern = "".join("🟢" if (x >= 1.2 and u) else "🔴" if x >= 1.2 else "⚪" for x, u in zip(x5, up5))
        if today_x >= 2 and up5[-1] and t.DELIV_PER >= dp_3m + 5:
            fresh = "Spike today"
        elif any(x5[i] >= 2 and up5[i] for i in (-4, -3, -2)):
            fresh = "Spike (last 3D)"
        elif last5_x >= 1.5 and _flow(last5) > 0:
            fresh = "Building (5D)"
        else:
            fresh = "None"

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
            "Symbol": sym, "Sector": sectors.get(sym) or SECTOR_OF.get(sym) or "Other", "Price": round(close, 2),
            "Chg_Pct": round(float((close / t.PREV_CLOSE - 1) * 100), 2),
            "Ret_1W": _ret(c, 5), "Ret_1M": _ret(c, 21), "Ret_3M": _ret(c, 62),
            "Deliv_Per": round(float(t.DELIV_PER), 1), "Deliv_Per_1M": round(float(dp_1m), 1),
            "Deliv_Per_3M": round(float(dp_3m), 1), "Deliv_Per_Chg": round(float(pp), 1),
            "Deliv_Qty": int(t.DELIV_QTY), "Deliv_Qty_1M": int(dq_1m), "Deliv_Qty_3M": int(dq_3m),
            "Deliv_Qty_X": round(float(qty_x), 2), "Today_X": round(float(today_x), 2),
            "Last5_X": round(last5_x, 2), "Fresh": fresh, "Last5": pattern,
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


# --------------------------------------------------------------------------- #
# Sector rotation (delivery-flow based): where is money coming in / shifting?
# --------------------------------------------------------------------------- #
FRESH_SET = ("Spike today", "Spike (last 3D)", "Building (5D)")


def sector_rotation(pool: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-stock accumulation metrics to sector level.
    pool must have: Symbol, Sector, Signal, Net_Flow_1M, Net_Flow_3M.
    Optional: Buying_Status, Fresh, Deliv_Qty_X, Ret_1W, Ret_1M, Ret_3M.
    """
    if pool is None or pool.empty:
        return pd.DataFrame()

    for c in ["Sector", "Signal", "Net_Flow_1M", "Net_Flow_3M"]:
        if c not in pool.columns:
            return pd.DataFrame()

    d = pool.copy()
    d["Sector"] = d["Sector"].fillna("Unknown").astype(str).str.strip()
    d.loc[d.Sector.isin(["", "nan", "None", "NaN"]), "Sector"] = "Unknown"

    for c in ["Net_Flow_1M", "Net_Flow_3M", "Deliv_Qty_X", "Ret_1W", "Ret_1M", "Ret_3M"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")

    acc_signals = {"Accumulation", "Strong Accumulation"}
    d["_is_acc"]  = d.Signal.isin(acc_signals)
    d["_is_str"]  = d.Signal.eq("Strong Accumulation")
    d["_is_cont"] = (d["Buying_Status"].eq("Continuing")
                     if "Buying_Status" in d.columns
                     else pd.Series(False, index=d.index))
    d["_is_fresh"] = (d["Fresh"].isin(FRESH_SET)
                      if "Fresh" in d.columns
                      else pd.Series(False, index=d.index))

    agg = {
        "Stocks":       ("Symbol", "count"),
        "Accumulating": ("_is_acc", "sum"),
        "Strong":       ("_is_str", "sum"),
        "Continuing":   ("_is_cont", "sum"),
        "Fresh":        ("_is_fresh", "sum"),
        "Flow_1M":      ("Net_Flow_1M", "mean"),
        "Flow_Prev":    ("Net_Flow_3M", "mean"),
    }
    if "Deliv_Qty_X" in d.columns:
        agg["Deliv_Qty_X"] = ("Deliv_Qty_X", "mean")
    for c in ["Ret_1W", "Ret_1M", "Ret_3M"]:
        if c in d.columns:
            agg[c] = (c, "median")

    g = d.groupby("Sector", dropna=False).agg(**agg).reset_index()

    g["Acc_Pct"]   = (100 * g.Accumulating / g.Stocks.replace(0, np.nan)).round(0).fillna(0).astype(int)
    g["Flow_1M"]   = g.Flow_1M.round(2)
    g["Flow_Prev"] = g.Flow_Prev.round(2)
    g["Flow_Chg"]  = (g.Flow_1M - g.Flow_Prev).round(2)

    def _q(row):
        f, ch = row.Flow_1M, row.Flow_Chg
        if pd.isna(f) or pd.isna(ch): return "Lagging"
        if f >= 0 and ch >= 0: return "Leading"
        if f <  0 and ch >= 0: return "Improving"
        if f >= 0 and ch <  0: return "Weakening"
        return "Lagging"

    g["Quadrant"] = g.apply(_q, axis=1)

    cols = ["Sector", "Quadrant", "Stocks", "Accumulating", "Strong", "Continuing", "Fresh",
            "Acc_Pct", "Flow_1M", "Flow_Prev", "Flow_Chg", "Deliv_Qty_X",
            "Ret_1W", "Ret_1M", "Ret_3M"]
    cols = [c for c in cols if c in g.columns]
    return g[cols].sort_values(["Flow_Chg", "Flow_1M"], ascending=False).reset_index(drop=True)
