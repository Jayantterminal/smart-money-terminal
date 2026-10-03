"""
engine.py  -  Data + analytics layer for Smart Money Terminal
Sector rotation (RRG), stock screener, accumulation score, insights, snapshots.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")
BENCH = "^NSEI"
HIST_DIR = "data"

SECTORS = {
    "Bank": "^NSEBANK",
    "IT": "^CNXIT",
    "Pharma": "^CNXPHARMA",
    "Auto": "^CNXAUTO",
    "FMCG": "^CNXFMCG",
    "Metal": "^CNXMETAL",
    "Energy": "^CNXENERGY",
    "Realty": "^CNXREALTY",
    "Infra": "^CNXINFRA",
    "PSU Bank": "^CNXPSUBANK",
    "Fin Services": "^CNXFIN",
    "Media": "^CNXMEDIA",
}

# Stocks per sector (edit freely; use Yahoo symbols with .NS)
SECTOR_STOCKS = {
    "Bank": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK"],
    "IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM"],
    "Pharma": ["SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB", "LUPIN", "AUROPHARMA"],
    "Auto": ["MARUTI", "M&M", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", "TVSMOTOR"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "GODREJCP"],
    "Metal": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "NMDC"],
    "Energy": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA", "BPCL"],
    "Realty": ["DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "LODHA"],
    "Infra": ["LT", "ADANIPORTS", "SIEMENS", "ULTRACEMCO", "GRASIM"],
    "PSU Bank": ["SBIN", "BANKBARODA", "PNB", "CANBK", "UNIONBANK"],
    "Fin Services": ["BAJFINANCE", "BAJAJFINSV", "SBILIFE", "HDFCLIFE", "CHOLAFIN"],
    "Media": ["SUNTV", "PVRINOX", "ZEEL"],
}

STOCK_SECTOR = {f"{s}.NS": sec for sec, lst in SECTOR_STOCKS.items() for s in lst}
QUAD_CODE = {"Lagging": 0, "Improving": 1, "Weakening": 2, "Leading": 3}


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def market_status() -> str:
    n = now_ist()
    if n.weekday() >= 5:
        return "CLOSED"
    t = n.time()
    if dt.time(9, 0) <= t < dt.time(9, 15):
        return "PRE-OPEN"
    if dt.time(9, 15) <= t <= dt.time(15, 30):
        return "LIVE"
    return "CLOSED"


def all_tickers() -> list[str]:
    return [BENCH] + list(SECTORS.values()) + list(STOCK_SECTOR.keys())


# --------------------------------------------------------------------------- #
# Data download (bulk first, then per-ticker retry for anything missing)
# --------------------------------------------------------------------------- #
def _clean(df: pd.DataFrame | None, min_bars: int = 40) -> pd.DataFrame | None:
    if df is None or df.empty or "Close" not in df:
        return None
    df = df.copy()
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index).normalize()
    df = df[~df.index.duplicated(keep="last")].dropna(subset=["Close"])
    if "Volume" not in df:
        df["Volume"] = 0
    return df if len(df) >= min_bars else None


def fetch_prices(tickers: list[str], period: str = "9mo") -> dict[str, pd.DataFrame]:
    tickers = list(dict.fromkeys(tickers))
    out: dict[str, pd.DataFrame] = {}
    try:
        raw = yf.download(tickers, period=period, interval="1d", auto_adjust=True,
                          group_by="ticker", threads=True, progress=False)
    except Exception:
        raw = pd.DataFrame()

    for tk in tickers:
        try:
            part = raw[tk] if isinstance(raw.columns, pd.MultiIndex) else raw
            d = _clean(part)
            if d is not None:
                out[tk] = d
        except (KeyError, AttributeError):
            continue

    for tk in [t for t in tickers if t not in out]:  # retry one by one
        try:
            d = _clean(yf.Ticker(tk).history(period=period, interval="1d", auto_adjust=True))
            if d is not None:
                out[tk] = d
        except Exception:
            continue
    return out


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #
def pct(c: pd.Series, n: int) -> float:
    return float((c.iloc[-1] / c.iloc[-1 - n] - 1) * 100) if len(c) > n else np.nan


def rsi(c: pd.Series, n: int = 14) -> float:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    r = 100 - 100 / (1 + rs)
    return float(r.iloc[-1]) if pd.notna(r.iloc[-1]) else np.nan


def quadrant(ratio: float, mom: float) -> str:
    if ratio >= 100 and mom >= 100:
        return "Leading"
    if ratio >= 100:
        return "Weakening"
    if mom >= 100:
        return "Improving"
    return "Lagging"


def rrg_series(sec: pd.Series, bench: pd.Series, fast=5, slow=30, mom=10) -> pd.DataFrame:
    """RRG-style RS Ratio / Momentum, both centred on 100."""
    df = pd.concat([sec, bench], axis=1, join="inner").dropna()
    df.columns = ["s", "b"]
    rs = df["s"] / df["b"]
    ratio = 100 * rs.rolling(fast).mean() / rs.rolling(slow).mean()
    momentum = 100 * ratio / ratio.rolling(mom).mean()
    out = pd.DataFrame({"RS_Ratio": ratio, "RS_Mom": momentum}).dropna()
    out["Quadrant"] = np.select(
        [(out.RS_Ratio >= 100) & (out.RS_Mom >= 100),
         (out.RS_Ratio >= 100) & (out.RS_Mom < 100),
         (out.RS_Ratio < 100) & (out.RS_Mom >= 100)],
        ["Leading", "Weakening", "Improving"], default="Lagging")
    return out


def _days_in_quadrant(q: pd.Series) -> int:
    n = 0
    for v in reversed(q.tolist()):
        if v == q.iloc[-1]:
            n += 1
        else:
            break
    return n


# --------------------------------------------------------------------------- #
# Sector table
# --------------------------------------------------------------------------- #
def build_sector_table(prices: dict, tail_days: int = 63):
    if BENCH not in prices:
        return pd.DataFrame(), {}, list(SECTORS)
    bench = prices[BENCH]["Close"]
    rows, tails, missing = [], {}, []
    for name, tk in SECTORS.items():
        if tk not in prices:
            missing.append(name)
            continue
        c = prices[tk]["Close"]
        rrg = rrg_series(c, bench)
        if len(rrg) < 10:
            missing.append(name)
            continue
        tails[name] = rrg.tail(tail_days)
        last = rrg.iloc[-1]
        prev = rrg.iloc[-6] if len(rrg) > 5 else rrg.iloc[0]
        rows.append({
            "Sector": name,
            "RS_Ratio": round(last.RS_Ratio, 2),
            "RS_Mom": round(last.RS_Mom, 2),
            "Quadrant": last.Quadrant,
            "Prev_Quadrant": prev.Quadrant,
            "Days_In_Quad": _days_in_quadrant(rrg["Quadrant"]),
            "Ret_1D": pct(c, 1), "Ret_1W": pct(c, 5),
            "Ret_1M": pct(c, 21), "Ret_3M": pct(c, 63),
            "Rel_1M": pct(c, 21) - pct(bench, 21),
            "Rel_3M": pct(c, 63) - pct(bench, 63),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df, tails, missing
    df["Score"] = (df.Rel_3M.rank(pct=True) * 40 + df.Rel_1M.rank(pct=True) * 30 +
                   df.RS_Ratio.rank(pct=True) * 15 + df.RS_Mom.rank(pct=True) * 15).round(0)
    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", df.index + 1)
    num = [c for c in df.columns if c.startswith(("Ret_", "Rel_"))]
    df[num] = df[num].round(2)
    return df, tails, missing


def nifty_snapshot(prices: dict) -> dict:
    if BENCH not in prices:
        return {}
    c = prices[BENCH]["Close"]
    return {"last": float(c.iloc[-1]), "chg": pct(c, 1), "m1": pct(c, 21),
            "m3": pct(c, 63), "asof": c.index[-1]}


# --------------------------------------------------------------------------- #
# Stock screener + accumulation score
# --------------------------------------------------------------------------- #
def stock_metrics(df: pd.DataFrame, bench: pd.Series) -> dict | None:
    c, v = df["Close"], df["Volume"].fillna(0)
    if len(c) < 70:
        return None
    chg = c.diff()
    up = v.where(chg > 0, 0).tail(20).sum()
    dn = v.where(chg < 0, 0).tail(20).sum()
    ud = float(up / dn) if dn > 0 else np.nan
    obv = (np.sign(chg).fillna(0) * v).cumsum()
    obv_up = bool(obv.iloc[-1] > obv.iloc[-21])
    d20, d50 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1]
    hi = c.tail(252).max()
    from_hi = float((c.iloc[-1] / hi - 1) * 100)
    r = rsi(c)
    rel3 = pct(c, 63) - pct(bench, 63)
    vol_ratio = float(v.tail(5).mean() / v.tail(20).mean()) if v.tail(20).mean() > 0 else np.nan

    score = 0
    if pd.notna(ud):
        score += 25 if ud >= 1.3 else 12 if ud >= 1.0 else 0
    score += 20 if obv_up else 0
    score += 15 if c.iloc[-1] > d50 else 0
    score += 10 if d20 > d50 else 0
    score += 15 if rel3 > 0 else 0
    score += 10 if from_hi >= -10 else 0
    score += 5 if pd.notna(r) and 45 <= r <= 70 else 0
    signal = ("Strong Accumulation" if score >= 75 else "Accumulation" if score >= 55
              else "Neutral" if score >= 35 else "Weak / Distribution")
    return {
        "Price": round(float(c.iloc[-1]), 2),
        "Ret_1D": round(pct(c, 1), 2), "Ret_1W": round(pct(c, 5), 2),
        "Ret_1M": round(pct(c, 21), 2), "Ret_3M": round(pct(c, 63), 2),
        "Rel_3M": round(rel3, 2), "RSI": round(r, 1) if pd.notna(r) else np.nan,
        "From_52W_High": round(from_hi, 2),
        "Vol_Ratio": round(vol_ratio, 2) if pd.notna(vol_ratio) else np.nan,
        "UpDown_Vol": round(ud, 2) if pd.notna(ud) else np.nan,
        "Above_50DMA": bool(c.iloc[-1] > d50),
        "Acc_Score": int(score), "Signal": signal,
    }


def build_screener(prices: dict, sector_df: pd.DataFrame) -> pd.DataFrame:
    if BENCH not in prices:
        return pd.DataFrame()
    bench = prices[BENCH]["Close"]
    quad = dict(zip(sector_df.Sector, sector_df.Quadrant)) if not sector_df.empty else {}
    rows = []
    for tk, sec in STOCK_SECTOR.items():
        if tk not in prices:
            continue
        m = stock_metrics(prices[tk], bench)
        if m:
            rows.append({"Symbol": tk.replace(".NS", ""), "Ticker": tk, "Sector": sec,
                         "Sector_Quad": quad.get(sec, "-"), **m})
    df = pd.DataFrame(rows)
    return df.sort_values("Acc_Score", ascending=False).reset_index(drop=True) if not df.empty else df


# --------------------------------------------------------------------------- #
# Insights
# --------------------------------------------------------------------------- #
def build_insights(sec: pd.DataFrame, scr: pd.DataFrame) -> list[str]:
    if sec.empty:
        return ["Sector data unavailable right now. Try Refresh."]
    msgs = []
    lead = sec[sec.Quadrant == "Leading"].Sector.tolist()
    impr = sec[sec.Quadrant == "Improving"].Sector.tolist()
    lag = sec[sec.Quadrant == "Lagging"].Sector.tolist()
    if lead:
        msgs.append(f"Leading: {', '.join(lead)} are outperforming Nifty with rising momentum.")
    if impr:
        msgs.append(f"Improving (watch for breakout into Leading): {', '.join(impr)}.")
    if lag:
        msgs.append(f"Lagging (avoid / underweight): {', '.join(lag)}.")
    moved = sec[sec.Quadrant != sec.Prev_Quadrant]
    for _, r in moved.iterrows():
        msgs.append(f"Rotation: {r.Sector} moved {r.Prev_Quadrant} -> {r.Quadrant} in the last 5 sessions.")
    top = sec.iloc[0]
    msgs.append(f"Strongest sector by composite score: {top.Sector} "
                f"(3M relative {top.Rel_3M:+.1f}% vs Nifty).")
    if not scr.empty:
        pick = scr[scr.Sector_Quad.isin(["Leading", "Improving"]) & (scr.Acc_Score >= 55)].head(5)
        if not pick.empty:
            msgs.append("Accumulation candidates in Leading/Improving sectors: "
                        + ", ".join(f"{r.Symbol} ({r.Acc_Score})" for r in pick.itertuples()) + ".")
    return msgs


# --------------------------------------------------------------------------- #
# Records: one verified snapshot per trading day
# --------------------------------------------------------------------------- #
def save_snapshot(sec: pd.DataFrame, asof: pd.Timestamp) -> str | None:
    if sec.empty or sec[["RS_Ratio", "RS_Mom"]].isna().any().any():
        return None  # never store incomplete records
    os.makedirs(HIST_DIR, exist_ok=True)
    d = sec.copy()
    d.insert(0, "Date", asof.strftime("%Y-%m-%d"))
    d["Saved_At_IST"] = now_ist().strftime("%Y-%m-%d %H:%M:%S")
    path = os.path.join(HIST_DIR, f"sector_{asof.strftime('%Y-%m-%d')}.csv")
    d.to_csv(path, index=False)
    return path


def load_snapshots() -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(HIST_DIR, "sector_*.csv")))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
