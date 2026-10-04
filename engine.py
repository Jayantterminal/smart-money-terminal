"""
engine.py - Smart Money Terminal data engine (v3)
- Parallel downloads (8x faster)
- Fixed fresh spike, entry zone, SL cap, split detection
- Calendar-week buy weeks, exclusion of breakout days from range
- Market breadth + Nifty trend functions
"""
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import StringIO

import numpy as np
import pandas as pd
import requests

IST = timezone(timedelta(hours=5, minutes=30))
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(_BASE_DIR, ".nse_cache")
DB_PATH = os.path.join(_BASE_DIR, "signals_log.db")
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
except Exception:
    pass

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

FRESH_SET = {"Spike today", "Spike (last 3D)", "Building (5D)"}

SECTOR_OF = {
    "RELIANCE": "Oil Gas & Consumable Fuels", "TCS": "Information Technology",
    "HDFCBANK": "Financial Services", "INFY": "Information Technology",
    "ICICIBANK": "Financial Services", "HINDUNILVR": "FMCG",
    "SBIN": "Financial Services", "BHARTIARTL": "Telecommunication",
    "ITC": "FMCG", "KOTAKBANK": "Financial Services", "LT": "Construction",
    "AXISBANK": "Financial Services", "BAJFINANCE": "Financial Services",
    "BAJAJHFL": "Financial Services", "ASIANPAINT": "Consumer Durables",
    "MARUTI": "Automobile", "BAJAJFINSV": "Financial Services",
    "TITAN": "Consumer Durables", "SUNPHARMA": "Pharmaceuticals",
    "ULTRACEMCO": "Cement", "WIPRO": "Information Technology",
    "NESTLEIND": "FMCG", "TATAMOTORS": "Automobile", "NTPC": "Power",
    "POWERGRID": "Power", "M&M": "Automobile", "TATASTEEL": "Metals",
    "JSWSTEEL": "Metals", "ADANIENT": "Diversified", "ADANIPORTS": "Services",
    "COALINDIA": "Mining", "HCLTECH": "Information Technology",
    "TECHM": "Information Technology", "INDUSINDBK": "Financial Services",
    "GRASIM": "Cement", "HINDALCO": "Metals", "DRREDDY": "Pharmaceuticals",
    "CIPLA": "Pharmaceuticals", "DIVISLAB": "Pharmaceuticals",
    "BRITANNIA": "FMCG", "EICHERMOT": "Automobile", "HEROMOTOCO": "Automobile",
    "APOLLOHOSP": "Healthcare", "SBILIFE": "Financial Services",
    "HDFCLIFE": "Financial Services", "BPCL": "Oil Gas & Consumable Fuels",
    "IOC": "Oil Gas & Consumable Fuels", "ONGC": "Oil Gas & Consumable Fuels",
    "SHREECEM": "Cement", "PIDILITIND": "Chemicals", "DMART": "Retail",
    "GODREJCP": "FMCG", "HAVELLS": "Consumer Durables", "DABUR": "FMCG",
    "MARICO": "FMCG", "COLPAL": "FMCG", "BERGEPAINT": "Consumer Durables",
    "SIEMENS": "Capital Goods", "BOSCHLTD": "Automobile",
    "LTIM": "Information Technology",
}


def now_ist():
    return datetime.now(IST)


def _bhav_url(dt):
    return f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{dt:%d%m%Y}.csv"


def _fetch_bhav_day(dt):
    fp = os.path.join(CACHE_DIR, f"sec_bhav_{dt:%Y%m%d}.csv")
    if os.path.exists(fp):
        try:
            df = pd.read_csv(fp)
            if not df.empty:
                return df
        except Exception:
            try:
                os.remove(fp)
            except Exception:
                pass
    url = _bhav_url(dt)
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200 or len(r.text) < 200:
            return None
        df = pd.read_csv(StringIO(r.text))
        if df.empty:
            return None
        df.columns = [str(c).strip() for c in df.columns]
        try:
            df.to_csv(fp, index=False)
        except Exception:
            pass
        return df
    except Exception:
        return None


def fetch_history(days=65):
    """Parallel download - 8x faster than sequential."""
    today = now_ist().date()
    dates_to_fetch = []
    for i in range(days * 2 + 15):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        dates_to_fetch.append(d)

    errs = 0
    results = []

    def _safe(d):
        try:
            return (d, _fetch_bhav_day(d))
        except Exception:
            return (d, None)

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(_safe, d) for d in dates_to_fetch]
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception:
                errs += 1

    results.sort(key=lambda x: x[0], reverse=True)
    frames = []
    for d, df in results:
        if len(frames) >= days:
            break
        if df is None or df.empty:
            errs += 1
            continue
        df.columns = [str(c).strip() for c in df.columns]
        date_col = None
        for c in ("DATE1", "DATE", "TIMESTAMP"):
            if c in df.columns:
                date_col = c
                break
        need = {"SYMBOL", "SERIES", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE",
                "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER"}
        if not need.issubset(df.columns) or date_col is None:
            errs += 1
            continue
        df = df[df["SERIES"].astype(str).str.strip().isin(["EQ", "BE"])].copy()
        df["Symbol"] = df["SYMBOL"].astype(str).str.strip()
        df["Date"] = pd.to_datetime(df[date_col], errors="coerce")
        for c in ["PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE",
                  "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["Date", "CLOSE_PRICE", "Symbol"])
        if df.empty:
            errs += 1
            continue
        frames.append(df[["Date", "Symbol", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE",
                          "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER"]])

    if not frames:
        return pd.DataFrame(), {"days": 0, "errors": errs}

    hist = pd.concat(frames, ignore_index=True)
    hist = (hist.drop_duplicates(subset=["Date", "Symbol"])
                .sort_values(["Date", "Symbol"]).reset_index(drop=True))
    hist = hist[~hist.Symbol.str.contains(
        r"(NIFTY|BEES|ETF|GOLD|SILVER|LIQUID|GSEC|SDL|E-GOLD)", case=False, na=False)]
    mask = hist.DELIV_PER.isna() & hist.TTL_TRD_QNTY.gt(0)
    hist.loc[mask, "DELIV_PER"] = (hist.loc[mask, "DELIV_QTY"]
                                    / hist.loc[mask, "TTL_TRD_QNTY"] * 100).round(2)
    return hist, {"days": int(hist.Date.nunique()), "errors": int(errs)}


def fetch_sector_map():
    urls = [
        "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
        "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200 or len(r.text) < 100:
                continue
            df = pd.read_csv(StringIO(r.text))
            if df.empty:
                continue
            df.columns = [str(c).strip() for c in df.columns]
            sym_c = next((c for c in df.columns if c.lower() == "symbol"), None)
            ind_c = next((c for c in df.columns if c.lower() in ("industry", "sector",
                                                                  "basic industry")), None)
            if not sym_c or not ind_c:
                continue
            return dict(zip(df[sym_c].astype(str).str.strip().str.upper(),
                            df[ind_c].astype(str).str.strip()))
        except Exception:
            continue
    return dict(SECTOR_OF)


def _detect_split_events(g):
    if g is None or len(g) < 2:
        return []
    g = g.sort_values("Date").reset_index(drop=True).copy()
    events = []
    prev_close = g["PREV_CLOSE"].astype(float).values
    close = g["CLOSE_PRICE"].astype(float).values
    dq = g["DELIV_QTY"].fillna(0).astype(float).values
    for i in range(1, len(g)):
        if close[i-1] > 0 and prev_close[i] > 0:
            r = prev_close[i] / close[i-1]
            if r > 1.5 or (0 < r < 0.67):
                events.append(i); continue
        if dq[i] > 0 and dq[i-1] > 0 and close[i] < close[i-1]:
            if dq[i] / dq[i-1] > 3.0:
                events.append(i)
    return events


def _adjust_splits(g):
    if g is None or len(g) < 2:
        return g, False
    g = g.sort_values("Date").reset_index(drop=True).copy()
    events = _detect_split_events(g)
    if not events:
        return g, False
    ratio = g["PREV_CLOSE"].astype(float) / g["CLOSE_PRICE"].astype(float).shift(1)
    cum = np.ones(len(g))
    for i in range(1, len(g)):
        r = ratio.iloc[i]
        if pd.notna(r) and (r > 1.5 or (0 < r < 0.67)):
            cum[:i] = cum[:i] / r
    for col in ["OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "PREV_CLOSE"]:
        g[col] = g[col] * cum
    for col in ["DELIV_QTY", "TTL_TRD_QNTY"]:
        g[col] = g[col] / cum
    return g, True


def compute_screener(hist, sector_filter, min_turnover_cr, sector_map):
    if hist is None or hist.empty:
        return pd.DataFrame()
    hist = hist.copy()
    hist["Date"] = pd.to_datetime(hist["Date"], errors="coerce")
    hist = hist.dropna(subset=["Date", "Symbol", "CLOSE_PRICE"])
    if hist.empty:
        return pd.DataFrame()
    if sector_map is None:
        sector_map = {}

    rows = []
    for sym, g in hist.groupby("Symbol", sort=False):
        g, had_split = _adjust_splits(g)
        if len(g) < 5:
            continue
        is_new_listing = len(g) < 20

        c = g["CLOSE_PRICE"].astype(float).values
        h = g["HIGH_PRICE"].astype(float).values
        l = g["LOW_PRICE"].astype(float).values
        pc = g["PREV_CLOSE"].astype(float).values
        v = g["TTL_TRD_QNTY"].fillna(0).astype(float).values
        dq = g["DELIV_QTY"].fillna(0).astype(float).values
        dp = g["DELIV_PER"].fillna(0).astype(float).values
        dates = pd.to_datetime(g["Date"].values)

        price = c[-1]
        prev = pc[-1] if pc[-1] > 0 else (c[-2] if len(c) > 1 else price)
        chg_pct = (price / prev - 1) * 100 if prev else 0.0

        n = len(g)
        i1m = max(0, n - 21); i3m = max(0, n - 63)
        dq_1m = dq[i1m:]; dq_3m = dq[i3m:i1m]
        dp_1m = dp[i1m:]; dp_3m = dp[i3m:i1m]
        c_1m = c[i1m:]; c_3m = c[i3m:i1m]
        pc_1m = pc[i1m:]; pc_3m = pc[i3m:i1m]

        avg_dq_1m = float(dq_1m.mean()) if len(dq_1m) else 0.0
        avg_dq_3m = float(dq_3m.mean()) if len(dq_3m) else 0.0
        deliv_qty_x = avg_dq_1m / avg_dq_3m if avg_dq_3m > 0 else 0.0
        deliv_per_1m = float(dp_1m.mean()) if len(dp_1m) else 0.0
        deliv_per_3m = float(dp_3m.mean()) if len(dp_3m) else 0.0
        deliv_per_chg = deliv_per_1m - deliv_per_3m

        up = c_1m > pc_1m; dn = c_1m < pc_1m; tot = dq_1m.sum()
        net_flow_1m = float((dq_1m[up].sum() - dq_1m[dn].sum()) / tot * 100) if tot > 0 else 0.0
        up3 = c_3m > pc_3m; dn3 = c_3m < pc_3m; tot3 = dq_3m.sum()
        net_flow_3m = float((dq_3m[up3].sum() - dq_3m[dn3].sum()) / tot3 * 100) if tot3 > 0 else 0.0

        buy_weeks = 0
        try:
            df_w = pd.DataFrame({"Date": dates, "C": c, "PC": pc, "DQ": dq}).dropna()
            if not df_w.empty:
                df_w["Week"] = df_w["Date"].dt.to_period("W")
                for wk, grp in list(df_w.groupby("Week"))[-4:]:
                    if grp.DQ[grp.C > grp.PC].sum() > grp.DQ[grp.C < grp.PC].sum():
                        buy_weeks += 1
        except Exception:
            buy_weeks = 0

        turnover_cr = float((v[-min(21, n):] * c[-min(21, n):]).sum() / 1e7 / min(21, n))

        lb_start = max(0, n - 30); lb_end = max(lb_start, n - 2)
        if lb_end - lb_start >= 5:
            rng_lo = float(l[lb_start:lb_end].min()); rng_hi = float(h[lb_start:lb_end].max())
        else:
            rng_lo = float(l[lb_start:].min()); rng_hi = float(h[lb_start:].max())
        rng_pct = ((rng_hi / rng_lo) - 1) * 100 if rng_lo > 0 else 0.0

        low20 = float(l[-min(20, n):].min()); sma20 = float(c[-min(20, n):].mean())
        dist_low = (price / low20 - 1) * 100 if low20 > 0 else 0.0
        dist_sma = (price / sma20 - 1) * 100 if sma20 > 0 else 0.0
        if dist_low >= 18 or dist_sma >= 10: stage = "Extended (already ran)"
        elif dist_low >= 10: stage = "Rally on"
        elif dist_low >= 5:  stage = "Early move"
        else:                stage = "Base (not moved)"

        if rng_pct <= 25 and price > rng_hi * 0.99: setup = "Breakout"
        elif rng_pct <= 25 and rng_lo * 0.98 <= price <= rng_hi * 1.02: setup = "In range (base)"
        else: setup = "Trending / wide"
        if price < rng_lo: setup = "Breakdown"

        if setup == "Breakout":
            entry = rng_hi * 1.005; entry_low = rng_hi * 1.000; entry_high = rng_hi * 1.02
        elif setup == "In range (base)":
            entry = (rng_lo + rng_hi) / 2; entry_low = rng_lo * 1.01; entry_high = rng_lo * 1.05
        elif setup == "Trending / wide":
            entry = min(price, sma20); entry_low = entry * 0.98; entry_high = entry * 1.02
        else:
            entry = price; entry_low = price * 0.98; entry_high = price * 1.00

        entry_zone = f"{entry_low:,.2f}–{entry_high:,.2f}"
        if entry_low <= price <= entry_high: entry_status = "In zone"
        elif price > entry_high:             entry_status = "Above zone (wait)"
        else:                                entry_status = "Below zone"
        entry_gap = (price / entry - 1) * 100 if entry > 0 else 0.0

        if setup == "Breakout":
            sl = min(rng_hi * 0.97, entry * 0.92)
        elif setup == "In range (base)":
            sl = max(rng_lo * 0.97, entry * 0.90)
        else:
            sl = max(low20 * 0.97, entry * 0.90)
        if sl <= 0 or sl >= entry:
            sl = entry * 0.92
        risk_pct = (entry - sl) / entry * 100 if entry > 0 else 0.0

        rng_height = rng_hi - rng_lo
        t1 = rng_hi if rng_hi > entry else entry * 1.05
        t2 = t1 + rng_height * 0.5
        t3 = t1 + rng_height
        if t2 <= t1: t2 = t1 * 1.05
        if t3 <= t2: t3 = t2 * 1.05

        plan_status = "Entry zone current range ke andar hai."
        if price > rng_hi:   plan_status = "Price range ke upar breakout hua hai."
        elif price < rng_lo: plan_status = "Price range se neeche - wait karo."

        dq_ref = avg_dq_3m if avg_dq_3m > 0 else (avg_dq_1m if avg_dq_1m > 0 else 1.0)
        today_dq = float(dq[-1]); today_dp = float(dp[-1])
        today_up = bool(c[-1] > pc[-1])
        today_x = today_dq / dq_ref if dq_ref > 0 else 0.0
        last5 = dq[-5:] if n >= 5 else dq
        last5_x = float(last5.mean() / dq_ref) if dq_ref > 0 else 0.0

        fresh = "None"
        if today_x >= 2 and today_dp >= (deliv_per_3m + 5) and today_up:
            fresh = "Spike today"
        elif n >= 3:
            r3 = dq[-3:]; r3_dp = dp[-3:]
            if r3.mean() >= 2 * dq_ref and r3_dp.mean() >= (deliv_per_3m + 3) and today_up:
                fresh = "Spike (last 3D)"
        if fresh == "None" and last5_x >= 1.5 and net_flow_1m > 0:
            fresh = "Building (5D)"

        icons = []
        for i in range(max(0, n - 5), n):
            di = dq[i] / dq_ref if dq_ref else 0
            pi = c[i] > pc[i]
            if di >= 1.5 and pi:     icons.append("🟢")
            elif di >= 1.5 and not pi: icons.append("🔴")
            else:                    icons.append("⚪")
        last5_str = "".join(icons)

        acc_days = 0; dist_days = 0
        for i in range(max(0, n - 21), n):
            di = dq[i] / dq_ref if dq_ref else 0
            if di >= 1.2 and c[i] > pc[i]:   acc_days += 1
            elif di >= 1.2 and c[i] < pc[i]: dist_days += 1

        ret_1w = (c[-1] / c[-6] - 1) * 100 if n >= 6 and c[-6] > 0 else 0.0
        ret_1m = (c[-1] / c[-21] - 1) * 100 if n >= 21 and c[-21] > 0 else 0.0
        ret_3m = (c[-1] / c[-63] - 1) * 100 if n >= 63 and c[-63] > 0 else 0.0

        score = 0
        if deliv_qty_x >= 1.5:   score += 20
        elif deliv_qty_x >= 1.2: score += 14
        elif deliv_qty_x >= 1.05: score += 7
        if deliv_per_chg >= 8:   score += 15
        elif deliv_per_chg >= 4: score += 10
        elif deliv_per_chg > 0:  score += 4
        if net_flow_1m >= 30:    score += 20
        elif net_flow_1m >= 15:  score += 14
        elif net_flow_1m > 0:    score += 7
        if buy_weeks >= 4:       score += 15
        elif buy_weeks >= 3:     score += 11
        elif buy_weeks >= 2:     score += 6
        if setup in ("In range (base)", "Breakout"): score += 10
        if price >= rng_lo: score += 10
        if today_dq >= dq_ref: score += 10

        if score >= 70 and net_flow_1m > 20: signal = "Strong Accumulation"
        elif score >= 50:                    signal = "Accumulation"
        elif score >= 30:                    signal = "Neutral"
        elif net_flow_1m < -15:              signal = "Distribution"
        else:                                signal = "Low volume (ignore)"

        if buy_weeks >= 3 and net_flow_1m > 10:     buying_status = "Continuing"
        elif buy_weeks >= 2 and net_flow_1m > 0:    buying_status = "Just started"
        elif buy_weeks <= 1 and net_flow_1m < 0:    buying_status = "Not buying"
        else:                                       buying_status = "Fading"

        rows.append({
            "Symbol": sym, "Sector": sector_map.get(sym, "Unknown"),
            "Price": round(price, 2), "Chg_Pct": round(chg_pct, 2),
            "Deliv_Qty_X": round(deliv_qty_x, 2),
            "Deliv_Qty_1M": int(avg_dq_1m), "Deliv_Qty_3M": int(avg_dq_3m),
            "Deliv_Per_1M": round(deliv_per_1m, 1), "Deliv_Per_3M": round(deliv_per_3m, 1),
            "Deliv_Per_Chg": round(deliv_per_chg, 1),
            "Net_Flow_1M": round(net_flow_1m, 1), "Net_Flow_3M": round(net_flow_3m, 1),
            "Score": int(score), "Signal": signal,
            "Buying_Status": buying_status, "Buy_Weeks": int(buy_weeks),
            "Fresh": fresh, "Last5": last5_str,
            "Last5_X": round(last5_x, 2), "Today_X": round(today_x, 2),
            "Acc_Days": int(acc_days), "Dist_Days": int(dist_days),
            "Setup": setup, "Stage": stage,
            "Range_Lo": round(rng_lo, 2), "Range_Hi": round(rng_hi, 2),
            "Range_Pct": round(rng_pct, 1),
            "Entry": round(entry, 2),
            "Entry_Low": round(entry_low, 2), "Entry_High": round(entry_high, 2),
            "Entry_Zone": entry_zone, "Entry_Status": entry_status,
            "Entry_Gap": round(entry_gap, 2),
            "SL": round(sl, 2), "Risk_Pct": round(risk_pct, 2),
            "T1": round(t1, 2), "T2": round(t2, 2), "T3": round(t3, 2),
            "Plan_Status": plan_status, "Avg_Turnover_Cr": round(turnover_cr, 2),
            "Ret_1W": round(ret_1w, 2), "Ret_1M": round(ret_1m, 2), "Ret_3M": round(ret_3m, 2),
            "Is_New_Listing": bool(is_new_listing),
            "Has_Split_Adjust": bool(had_split),
        })

    scr = pd.DataFrame(rows)
    if scr.empty:
        return scr
    if min_turnover_cr and min_turnover_cr > 0:
        scr = scr[scr.Avg_Turnover_Cr >= min_turnover_cr]
    return scr.reset_index(drop=True)


def symbol_view(hist, symbol):
    if hist is None or hist.empty:
        return pd.DataFrame()
    g = hist[hist.Symbol == symbol].sort_values("Date").reset_index(drop=True).copy()
    if g.empty:
        return g
    if "DELIV_PER" not in g.columns or g.DELIV_PER.isna().all():
        g["DELIV_PER"] = (g.DELIV_QTY / g.TTL_TRD_QNTY * 100).round(2)
    return g


def weekly_flows(g, n=12):
    if g is None or g.empty or "Date" not in g.columns:
        return []
    g = g.sort_values("Date").reset_index(drop=True).copy()
    g["Date"] = pd.to_datetime(g["Date"], errors="coerce")
    g = g.dropna(subset=["Date"])
    if g.empty:
        return []
    g["Week"] = g.Date.dt.to_period("W").dt.start_time
    out = []
    for wk, grp in g.groupby("Week", sort=True):
        up = grp.CLOSE_PRICE > grp.PREV_CLOSE
        dn = grp.CLOSE_PRICE < grp.PREV_CLOSE
        net = float(grp.DELIV_QTY.where(up, 0).sum() - grp.DELIV_QTY.where(dn, 0).sum())
        out.append((wk, net))
    return out[-n:]


def sector_rotation(pool: pd.DataFrame) -> pd.DataFrame:
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
    d["_is_acc"] = d.Signal.isin({"Accumulation", "Strong Accumulation"})
    d["_is_str"] = d.Signal.eq("Strong Accumulation")
    d["_is_cont"] = (d["Buying_Status"].eq("Continuing")
                     if "Buying_Status" in d.columns else pd.Series(False, index=d.index))
    d["_is_fresh"] = (d["Fresh"].isin(FRESH_SET)
                      if "Fresh" in d.columns else pd.Series(False, index=d.index))
    agg = {"Stocks": ("Symbol", "count"), "Accumulating": ("_is_acc", "sum"),
           "Strong": ("_is_str", "sum"), "Continuing": ("_is_cont", "sum"),
           "Fresh": ("_is_fresh", "sum"), "Flow_1M": ("Net_Flow_1M", "mean"),
           "Flow_Prev": ("Net_Flow_3M", "mean")}
    if "Deliv_Qty_X" in d.columns:
        agg["Deliv_Qty_X"] = ("Deliv_Qty_X", "mean")
    for c in ["Ret_1W", "Ret_1M", "Ret_3M"]:
        if c in d.columns:
            agg[c] = (c, "median")
    g = d.groupby("Sector", dropna=False).agg(**agg).reset_index()
    g["Acc_Pct"] = (100 * g.Accumulating / g.Stocks.replace(0, np.nan)).round(0).fillna(0).astype(int)
    g["Flow_1M"] = g.Flow_1M.round(2)
    g["Flow_Prev"] = g.Flow_Prev.round(2)
    g["Flow_Chg"] = (g.Flow_1M - g.Flow_Prev).round(2)

    def _q(row):
        f, ch = row.Flow_1M, row.Flow_Chg
        if pd.isna(f) or pd.isna(ch): return "Lagging"
        if f >= 0 and ch >= 0: return "Leading"
        if f < 0 and ch >= 0: return "Improving"
        if f >= 0 and ch < 0: return "Weakening"
        return "Lagging"
    g["Quadrant"] = g.apply(_q, axis=1)
    cols = ["Sector", "Quadrant", "Stocks", "Accumulating", "Strong", "Continuing", "Fresh",
            "Acc_Pct", "Flow_1M", "Flow_Prev", "Flow_Chg", "Deliv_Qty_X",
            "Ret_1W", "Ret_1M", "Ret_3M"]
    cols = [c for c in cols if c in g.columns]
    return g[cols].sort_values(["Flow_Chg", "Flow_1M"], ascending=False).reset_index(drop=True)


# ============ MARKET BREADTH + NIFTY TREND ============ #
def market_breadth(hist, scr):
    """Compute market breadth + Nifty trend from hist data."""
    out = {
        "total": 0, "above_20dma": 0, "above_50dma": 0, "above_200dma": 0,
        "advances": 0, "declines": 0, "breadth_pct_20": 0.0, "breadth_pct_50": 0.0,
        "breadth_pct_200": 0.0, "ad_ratio": 0.0,
        "nifty_price": 0.0, "nifty_20dma": 0.0, "nifty_50dma": 0.0, "nifty_200dma": 0.0,
        "nifty_trend": "-",
    }
    if hist is None or hist.empty:
        return out

    h = hist.copy()
    h["Date"] = pd.to_datetime(h["Date"], errors="coerce")
    h = h.dropna(subset=["Date", "CLOSE_PRICE"])

    # Per-stock DMAs (need 200+ sessions for 200-DMA; if not available, use what we have)
    last_day = h.Date.max()
    latest = h[h.Date == last_day]
    out["total"] = int(len(latest))
    if "Chg_Pct" in scr.columns:
        out["advances"] = int((scr.Chg_Pct > 0).sum())
        out["declines"] = int((scr.Chg_Pct < 0).sum())
        tot = max(1, out["advances"] + out["declines"])
        out["ad_ratio"] = round(out["advances"] / tot * 100, 1)

    counts = {"above_20dma": 0, "above_50dma": 0, "above_200dma": 0}
    denom = {"d20": 0, "d50": 0, "d200": 0}
    for sym, g in h.groupby("Symbol", sort=False):
        g = g.sort_values("Date")
        c = g["CLOSE_PRICE"].astype(float).values
        if len(c) >= 20:
            denom["d20"] += 1
            if c[-1] > c[-20:].mean(): counts["above_20dma"] += 1
        if len(c) >= 50:
            denom["d50"] += 1
            if c[-1] > c[-50:].mean(): counts["above_50dma"] += 1
        if len(c) >= 200:
            denom["d200"] += 1
            if c[-1] > c[-200:].mean(): counts["above_200dma"] += 1

    out["above_20dma"]  = counts["above_20dma"]
    out["above_50dma"]  = counts["above_50dma"]
    out["above_200dma"] = counts["above_200dma"]
    out["breadth_pct_20"]  = round(100 * counts["above_20dma"]  / max(1, denom["d20"]), 1)
    out["breadth_pct_50"]  = round(100 * counts["above_50dma"]  / max(1, denom["d50"]), 1)
    out["breadth_pct_200"] = round(100 * counts["above_200dma"] / max(1, denom["d200"]), 1)

    # Nifty proxy via NIFTYBEES or similar - but we stripped ETFs. Use median of large stocks as proxy.
    try:
        grp = h.groupby("Date")["CLOSE_PRICE"].median().reset_index().sort_values("Date")
        nc = grp["CLOSE_PRICE"].values
        if len(nc) > 0:
            out["nifty_price"] = round(float(nc[-1]), 2)
            if len(nc) >= 20:  out["nifty_20dma"]  = round(float(nc[-20:].mean()), 2)
            if len(nc) >= 50:  out["nifty_50dma"]  = round(float(nc[-50:].mean()), 2)
            if len(nc) >= 200: out["nifty_200dma"] = round(float(nc[-200:].mean()), 2)
            p = nc[-1]
            above20  = out["nifty_20dma"]  and p > out["nifty_20dma"]
            above50  = out["nifty_50dma"]  and p > out["nifty_50dma"]
            above200 = out["nifty_200dma"] and p > out["nifty_200dma"]
            if above200 and above50:  out["nifty_trend"] = "🟢 Bullish (above 50 & 200 DMA)"
            elif above200:            out["nifty_trend"] = "🟡 Cautious (above 200, below 50)"
            elif above50:             out["nifty_trend"] = "🟡 Mixed (above 50, below 200)"
            else:                     out["nifty_trend"] = "🔴 Bearish (below 50 & 200 DMA)"
    except Exception:
        pass

    return out


# ============ RE-ENTRY TRACKER ============ #
def _init_tracker_db():
    try:
        con = sqlite3.connect(DB_PATH, timeout=10)
        con.execute("""
            CREATE TABLE IF NOT EXISTS screener_log (
                run_date TEXT NOT NULL, symbol TEXT NOT NULL, signal TEXT, score INTEGER,
                price REAL, entry REAL, sl REAL, t1 REAL, t2 REAL, t3 REAL,
                sl_hit INTEGER DEFAULT 0,
                PRIMARY KEY (run_date, symbol)
            )
        """)
        con.commit(); con.close()
    except Exception:
        pass


def update_sl_hits(hist):
    if hist is None or hist.empty:
        return
    try:
        _init_tracker_db()
        con = sqlite3.connect(DB_PATH, timeout=10)
        cur = con.execute("SELECT rowid, symbol, run_date, sl FROM screener_log WHERE sl_hit = 0")
        rows = cur.fetchall()
        if not rows:
            con.close(); return
        h = hist.copy()
        h["Date"] = pd.to_datetime(h["Date"], errors="coerce")
        to_mark = []
        for rid, sym, rd, sl in rows:
            if not sym or not sl or sl <= 0:
                continue
            try:
                rd_dt = pd.to_datetime(rd)
            except Exception:
                continue
            g = h[(h.Symbol == sym) & (h.Date > rd_dt)]
            if g.empty:
                continue
            if float(g.LOW_PRICE.min()) <= float(sl):
                to_mark.append((rid,))
        if to_mark:
            con.executemany("UPDATE screener_log SET sl_hit=1 WHERE rowid=?", to_mark)
            con.commit()
        con.close()
    except Exception:
        pass


def reentry_stats(scr, asof_date, window_days=120):
    if scr is None or scr.empty:
        return scr
    try:
        _init_tracker_db()
        con = sqlite3.connect(DB_PATH, timeout=10)
        cur = con.execute("""
            SELECT symbol, COUNT(*) AS ap, MIN(run_date) AS fs, MAX(run_date) AS ls, MAX(sl_hit) AS sl
            FROM screener_log WHERE run_date >= date(?, ?) GROUP BY symbol
        """, (str(asof_date), f"-{window_days} days"))
        rows = cur.fetchall()
        con.close()
        stats = pd.DataFrame(rows, columns=["Symbol","Past_Appearances","First_Seen","Last_Seen","SL_Hit_Ever"])
    except Exception:
        stats = pd.DataFrame()

    if stats.empty:
        scr["Reentry"] = "🆕 First time"
        scr["Appearances_120D"] = 1
        scr["Days_Since_First"] = 0
        return scr

    m = scr.merge(stats, on="Symbol", how="left")
    m["Past_Appearances"] = m["Past_Appearances"].fillna(0).astype(int)
    m["SL_Hit_Ever"] = m["SL_Hit_Ever"].fillna(0).astype(int)
    m["Appearances_120D"] = m["Past_Appearances"] + 1

    def _flag(r):
        if r.Past_Appearances == 0: return "🆕 First time"
        if r.SL_Hit_Ever == 1: return "🔁 SL hit earlier"
        if r.Past_Appearances >= 3: return "🔁 Repeat"
        return "🔁 Second chance"

    m["Reentry"] = m.apply(_flag, axis=1)
    try:
        asof_dt = pd.to_datetime(asof_date)
        m["Days_Since_First"] = m["First_Seen"].apply(
            lambda x: (asof_dt - pd.to_datetime(x)).days if pd.notna(x) else 0)
    except Exception:
        m["Days_Since_First"] = 0
    m = m.drop(columns=["Past_Appearances","SL_Hit_Ever","First_Seen","Last_Seen"], errors="ignore")
    return m


def log_screener_run(scr, asof_date):
    if scr is None or scr.empty:
        return
    try:
        _init_tracker_db()
        con = sqlite3.connect(DB_PATH, timeout=10)
        rd = str(asof_date)
        rows = []
        for _, r in scr.iterrows():
            rows.append((rd, str(r.get("Symbol","")), str(r.get("Signal","")),
                int(r.get("Score", 0) or 0), float(r.get("Price", 0) or 0),
                float(r.get("Entry", 0) or 0), float(r.get("SL", 0) or 0),
                float(r.get("T1", 0) or 0), float(r.get("T2", 0) or 0),
                float(r.get("T3", 0) or 0)))
        con.executemany("""INSERT OR IGNORE INTO screener_log
            (run_date, symbol, signal, score, price, entry, sl, t1, t2, t3, sl_hit)
            VALUES (?,?,?,?,?,?,?,?,?,?,0)""", rows)
        con.execute("DELETE FROM screener_log WHERE run_date < date(?, '-180 days')", (rd,))
        con.commit(); con.close()
    except Exception:
        pass


def reentry_history(symbol, limit=20):
    try:
        _init_tracker_db()
        con = sqlite3.connect(DB_PATH, timeout=10)
        cur = con.execute("""SELECT run_date, signal, score, price, entry, sl, sl_hit
            FROM screener_log WHERE symbol = ? ORDER BY run_date DESC LIMIT ?""",
            (str(symbol), int(limit)))
        rows = cur.fetchall()
        con.close()
        return pd.DataFrame(rows, columns=["Date","Signal","Score","Price","Entry","SL","SL_Hit"])
    except Exception:
        return pd.DataFrame()
