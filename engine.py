"""
engine.py - Smart Money Terminal data engine (v11)
Fixes over v10:
  - Split/bonus adjustment direction was INVERTED (prices x2 instead of /2) -> fixed
  - Split detection no longer depends on delivery-qty (more robust)
  - Re-entry logic: only accumulation signals are logged, same-day not counted,
    consecutive days = one episode (not a "repeat"), SL-hit tracked properly
  - Market breadth: liquid universe only, consistent denominators, split-adjusted
  - Fund/ETF filter no longer drops real stocks (GOLDIAM, SILVERTUC ...)
  - Fetch window trimmed, error counter no longer counts holidays/today
  - Sector rotation ignores "Unknown" bucket
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import StringIO

import numpy as np
import pandas as pd
import requests

IST = timezone(timedelta(hours=5, minutes=30))
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(_BASE_DIR, ".nse_cache")
DATA_DIR = os.path.join(_BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "signals_log.db")
SIGNALS_CSV = os.path.join(DATA_DIR, "signals_log.csv")
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    pass

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

FRESH_SET = {"Spike today", "Spike (last 3D)", "Building (5D)"}
ACC_SIGNALS = {"Accumulation", "Strong Accumulation"}

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


_FUND_RE = (r"(NIFTY|BEES$|ETF$|IETF$|^LIQUID|^GSEC|^SDL|^E-GOLD|"
            r"^(GOLD|SILVER)(BEES|ETF|IETF|CASE|ADD|SHARE|\d|$))")


def _prune_cache(keep_days=220):
    try:
        cutoff = now_ist().date() - timedelta(days=keep_days)
        for fn in os.listdir(CACHE_DIR):
            m = re.match(r"sec_bhav_(\d{8})\.csv$", fn)
            if m and datetime.strptime(m.group(1), "%Y%m%d").date() < cutoff:
                os.remove(os.path.join(CACHE_DIR, fn))
    except Exception:
        pass


def fetch_history(days=65):
    today = now_ist().date()
    dates_to_fetch = []
    for i in range(int(days * 1.6) + 10):          # calendar days (~81 weekdays for 65 sessions)
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
    dropped = 0
    missing = 0          # holidays / not-yet-published days (informational only)
    seen_ok = False
    for d, df in results:
        if len(frames) >= days:
            break
        if df is None or df.empty:
            if seen_ok:
                missing += 1       # today's file not out yet is NOT counted
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
        opt_cols = [c for c in ["TURNOVER_LACS", "NO_OF_TRADES", "AVG_PRICE", "LAST_PRICE"]
                    if c in df.columns]
        df = df[df["SERIES"].astype(str).str.strip().isin(["EQ", "BE"])].copy()
        df["Symbol"] = df["SYMBOL"].astype(str).str.strip()
        df["Date"] = pd.to_datetime(df[date_col].astype(str).str.strip(), errors="coerce")
        for c in ["PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE",
                  "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER"] + opt_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        before = len(df)
        df = df.dropna(subset=["Date", "CLOSE_PRICE", "Symbol"])
        dropped += max(0, before - len(df))
        if df.empty:
            errs += 1
            continue
        seen_ok = True
        base_cols = ["Date", "Symbol", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE",
                     "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER"]
        frames.append(df[base_cols + opt_cols])

    if not frames:
        return pd.DataFrame(), {"days": 0, "errors": errs, "missing": missing,
                                "delivery_cov": 0.0, "dropped": dropped}

    hist = pd.concat(frames, ignore_index=True)
    hist = (hist.drop_duplicates(subset=["Date", "Symbol"])
                .sort_values(["Date", "Symbol"]).reset_index(drop=True))
    hist = hist[~hist.Symbol.str.contains(_FUND_RE, case=False, regex=True, na=False)]
    mask = hist.DELIV_PER.isna() & hist.TTL_TRD_QNTY.gt(0)
    hist.loc[mask, "DELIV_PER"] = (hist.loc[mask, "DELIV_QTY"]
                                    / hist.loc[mask, "TTL_TRD_QNTY"] * 100).round(2)
    for c in ["TURNOVER_LACS", "NO_OF_TRADES", "AVG_PRICE", "LAST_PRICE"]:
        if c not in hist.columns:
            hist[c] = np.nan
    delivery_cov = float(hist.DELIV_PER.notna().mean() * 100) if len(hist) else 0.0
    info = {"days": int(hist.Date.nunique()), "errors": int(errs), "missing": int(missing),
            "delivery_cov": round(delivery_cov, 1), "dropped": int(dropped)}
    _prune_cache()
    return hist, info


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


def _split_ratio(g):
    """NSE's PREV_CLOSE on ex-date is already adjusted. If it differs a lot from the
    actual previous close, a split/bonus happened. ratio = adjusted_prev / actual_prev."""
    prev_close = g["PREV_CLOSE"].astype(float).values
    close = g["CLOSE_PRICE"].astype(float).values
    r = np.ones(len(g))
    for i in range(1, len(g)):
        if close[i - 1] > 0 and prev_close[i] > 0:
            x = prev_close[i] / close[i - 1]
            if (1.5 <= x <= 5.0) or (0.2 <= x <= 0.67):
                r[i] = x
    return r


def _detect_split_events(g):
    if g is None or len(g) < 2:
        return []
    g = g.sort_values("Date").reset_index(drop=True)
    r = _split_ratio(g)
    return [i for i in range(1, len(g)) if r[i] != 1.0]


def _adjust_splits(g):
    """Back-adjust prices (x ratio) and quantities (/ ratio) before each split date.
    Split 1:2 -> ratio 0.5 -> old prices halved, old quantities doubled."""
    if g is None or len(g) < 2:
        return g, False
    g = g.sort_values("Date").reset_index(drop=True).copy()
    r = _split_ratio(g)
    if not (r != 1.0).any():
        return g, False
    cum = np.ones(len(g))
    for i in range(1, len(g)):
        if r[i] != 1.0:
            cum[:i] = cum[:i] * r[i]
    for col in ["OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "PREV_CLOSE"]:
        g[col] = g[col].astype(float) * cum
    for col in ["DELIV_QTY", "TTL_TRD_QNTY"]:
        g[col] = g[col].astype(float) / cum
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

        if n >= 2 and dq[-2] > 0:
            dq_dod_pct = (dq[-1] / dq[-2] - 1) * 100
        else:
            dq_dod_pct = 0.0
        if n >= 2:
            dp_dod_pp = float(dp[-1] - dp[-2])
        else:
            dp_dod_pp = 0.0
        if n >= 6 and dq[-6:-3].mean() > 0:
            dq_3d_ratio = float(dq[-3:].mean() / dq[-6:-3].mean())
        else:
            dq_3d_ratio = 1.0

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

        # ============ FIX: Range cap on wide-range stocks ============
        wide_range = rng_pct > 40
        if wide_range:
            # Use fixed % targets - wide ranges give absurd projections
            t1 = entry * 1.10
            t2 = entry * 1.20
            t3 = entry * 1.35
        else:
            rng_height = rng_hi - rng_lo
            t1 = rng_hi if rng_hi > entry else entry * 1.05
            t2 = t1 + rng_height * 0.5
            t3 = t1 + rng_height
            if t2 <= t1: t2 = t1 * 1.05
            if t3 <= t2: t3 = t2 * 1.05
            # Sanity cap - targets never exceed reasonable %
            t1 = min(t1, entry * 1.30)
            t2 = min(t2, entry * 1.45)
            t3 = min(t3, entry * 1.60)

        plan_status = "Entry zone current range ke andar hai."
        if price > rng_hi:   plan_status = "Price range ke upar breakout hua hai."
        elif price < rng_lo: plan_status = "Price range se neeche - wait karo."
        if wide_range:
            plan_status = "Range bahut wide hai - targets % based (10/20/35%) rakhe gaye hain."

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

        to_1m = 0.0; to_3m = 0.0; tr_1m = 0.0; to_x = 0.0
        trades_per_cr = 0.0; close_vs_avg = 0.0
        try:
            if "TURNOVER_LACS" in g.columns:
                to_arr = pd.to_numeric(g["TURNOVER_LACS"], errors="coerce").fillna(0).values / 100.0
                to_1m = float(to_arr[i1m:].sum()) if len(to_arr[i1m:]) else 0.0
                to_3m = float(to_arr[i3m:i1m].sum()) if len(to_arr[i3m:i1m]) else 0.0
                to_1m_avg = to_1m / max(1, len(to_arr[i1m:]))
                to_3m_avg = to_3m / max(1, len(to_arr[i3m:i1m])) if len(to_arr[i3m:i1m]) else 0.0
                to_x = to_1m_avg / to_3m_avg if to_3m_avg > 0 else 0.0
            if "NO_OF_TRADES" in g.columns:
                tr_arr = pd.to_numeric(g["NO_OF_TRADES"], errors="coerce").fillna(0).values
                tr_1m = float(tr_arr[i1m:].mean()) if len(tr_arr[i1m:]) else 0.0
                to_1m_avg_for_ratio = to_1m / max(1, len(to_arr[i1m:])) if to_1m > 0 else 0.0
                trades_per_cr = tr_1m / to_1m_avg_for_ratio if to_1m_avg_for_ratio > 0 else 0.0
            if "AVG_PRICE" in g.columns:
                ap_arr = pd.to_numeric(g["AVG_PRICE"], errors="coerce").values
                gaps = []
                for i in range(i1m, n):
                    if pd.notna(ap_arr[i]) and ap_arr[i] > 0:
                        gaps.append((c[i] - ap_arr[i]) / ap_arr[i] * 100)
                close_vs_avg = float(np.mean(gaps)) if gaps else 0.0
        except Exception:
            pass

        delivery_score = 20 if deliv_qty_x >= 1.5 else 14 if deliv_qty_x >= 1.2 else 7 if deliv_qty_x >= 1.05 else 0
        delivery_pct_score = 15 if deliv_per_chg >= 8 else 10 if deliv_per_chg >= 4 else 4 if deliv_per_chg > 0 else 0
        flow_score = 20 if net_flow_1m >= 30 else 14 if net_flow_1m >= 15 else 7 if net_flow_1m > 0 else 0
        trend_score = 15 if buy_weeks >= 4 else 11 if buy_weeks >= 3 else 6 if buy_weeks >= 2 else 0
        setup_score = 10 if setup in ("In range (base)", "Breakout") else 0
        structure_score = 10 if price >= rng_lo else 0
        activity_score = 10 if today_dq >= dq_ref else 0
        score = delivery_score + delivery_pct_score + flow_score + trend_score + setup_score + structure_score + activity_score

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
            "Deliv_Qty_DoD": round(dq_dod_pct, 1),
            "Deliv_Per_DoD": round(dp_dod_pp, 2),
            "Deliv_3D_Ratio": round(dq_3d_ratio, 2),
            "Net_Flow_1M": round(net_flow_1m, 1), "Net_Flow_3M": round(net_flow_3m, 1),
            "Score": int(score), "Score_Delivery": int(delivery_score), "Score_DeliveryPct": int(delivery_pct_score),
            "Score_Flow": int(flow_score), "Score_Trend": int(trend_score), "Score_Setup": int(setup_score),
            "Score_Structure": int(structure_score), "Score_Activity": int(activity_score), "Signal": signal,
            "Buying_Status": buying_status, "Buy_Weeks": int(buy_weeks),
            "Fresh": fresh, "Last5": last5_str,
            "Last5_X": round(last5_x, 2), "Today_X": round(today_x, 2),
            "Acc_Days": int(acc_days), "Dist_Days": int(dist_days),
            "Setup": setup, "Stage": stage,
            "Range_Lo": round(rng_lo, 2), "Range_Hi": round(rng_hi, 2),
            "Range_Pct": round(rng_pct, 1),
            "Wide_Range": bool(wide_range),
            "Entry": round(entry, 2),
            "Entry_Low": round(entry_low, 2), "Entry_High": round(entry_high, 2),
            "Entry_Zone": entry_zone, "Entry_Status": entry_status,
            "Entry_Gap": round(entry_gap, 2),
            "SL": round(sl, 2), "Risk_Pct": round(risk_pct, 2),
            "T1": round(t1, 2), "T2": round(t2, 2), "T3": round(t3, 2),
            "Plan_Status": plan_status, "Avg_Turnover_Cr": round(turnover_cr, 2),
            "Ret_1W": round(ret_1w, 2), "Ret_1M": round(ret_1m, 2), "Ret_3M": round(ret_3m, 2),
            "Turnover_1M_Cr": round(to_1m, 2),
            "Turnover_3M_Cr": round(to_3m, 2),
            "Turnover_X": round(to_x, 2),
            "Trades_1M_Avg": int(tr_1m),
            "Trades_per_Cr": round(trades_per_cr, 1),
            "Close_vs_Avg": round(close_vs_avg, 2),
            "Is_New_Listing": bool(is_new_listing),
            "Has_Split_Adjust": bool(had_split),
        })

    scr = pd.DataFrame(rows)
    if scr.empty:
        return scr
    if min_turnover_cr and min_turnover_cr > 0:
        scr = scr[scr.Avg_Turnover_Cr >= min_turnover_cr]
    return scr.reset_index(drop=True)


def symbol_view(hist, symbol, adjust=True):
    if hist is None or hist.empty:
        return pd.DataFrame()
    g = hist[hist.Symbol == symbol].sort_values("Date").reset_index(drop=True).copy()
    if g.empty:
        return g
    if adjust:
        g, _ = _adjust_splits(g)
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


def sector_rotation(pool):
    if pool is None or pool.empty:
        return pd.DataFrame()
    for c in ["Sector", "Signal", "Net_Flow_1M", "Net_Flow_3M"]:
        if c not in pool.columns:
            return pd.DataFrame()
    d = pool.copy()
    d["Sector"] = d["Sector"].fillna("Unknown").astype(str).str.strip()
    d.loc[d.Sector.isin(["", "nan", "None", "NaN"]), "Sector"] = "Unknown"
    _known = d[d.Sector != "Unknown"]
    if not _known.empty:          # "Unknown" is not a real sector - keep it out of rotation
        d = _known
    for c in ["Net_Flow_1M", "Net_Flow_3M", "Deliv_Qty_X", "Ret_1W", "Ret_1M", "Ret_3M"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d["_is_acc"] = d.Signal.isin(ACC_SIGNALS)
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


def _trend_label(p, d50, d200, short=False):
    a50 = bool(d50) and p > d50
    a200 = bool(d200) and p > d200
    if a200 and a50:
        return "🟢 Bullish (above 50 & 200 DMA)"
    if a200:
        return "🟡 Cautious (above 200, below 50)" if not short else "🟡 Cautious"
    if a50:
        return "🟡 Recovering (above 50, below 200)" if not short else "🟡 Recovering"
    return "🔴 Bearish (below 50 & 200 DMA)" if not short else "🔴 Bearish"


def market_breadth(hist, scr, nifty=None):
    out = {
        "total": 0, "total_20": 0, "total_50": 0, "total_200": 0,
        "above_20dma": 0, "above_50dma": 0, "above_200dma": 0,
        "advances": 0, "declines": 0,
        "breadth_pct_20": 0.0, "breadth_pct_50": 0.0,
        "breadth_pct_200": None,
        "ad_ratio": 0.0,
        "nifty_price": 0.0, "nifty_20dma": 0.0, "nifty_50dma": 0.0, "nifty_200dma": 0.0,
        "nifty_trend": "-",
        "nifty_source": "-",
    }
    if hist is None or hist.empty:
        return out
    h = hist.copy()
    h["Date"] = pd.to_datetime(h["Date"], errors="coerce")
    h = h.dropna(subset=["Date", "CLOSE_PRICE"])
    if h.empty:
        return out
    last_day = h.Date.max()

    univ = None     # breadth only on the liquid screener universe (not every illiquid BE stock)
    if scr is not None and not scr.empty and "Symbol" in scr.columns:
        univ = set(scr.Symbol)
    if scr is not None and not scr.empty and "Chg_Pct" in scr.columns:
        out["advances"] = int((scr.Chg_Pct > 0).sum())
        out["declines"] = int((scr.Chg_Pct < 0).sum())
        tot = max(1, out["advances"] + out["declines"])
        out["ad_ratio"] = round(out["advances"] / tot * 100, 1)

    counts = {20: 0, 50: 0, 200: 0}
    denom = {20: 0, 50: 0, 200: 0}
    for sym, g in h.groupby("Symbol", sort=False):
        if univ is not None and sym not in univ:
            continue
        g = g.sort_values("Date")
        if g.Date.iloc[-1] != last_day:        # not traded on last session -> stale
            continue
        g, _ = _adjust_splits(g)
        c = g["CLOSE_PRICE"].astype(float).values
        for w in (20, 50, 200):
            if len(c) >= w:
                denom[w] += 1
                if c[-1] > c[-w:].mean():
                    counts[w] += 1

    out["above_20dma"], out["above_50dma"], out["above_200dma"] = counts[20], counts[50], counts[200]
    out["total_20"], out["total_50"], out["total_200"] = denom[20], denom[50], denom[200]
    out["total"] = denom[20]
    out["breadth_pct_20"] = round(100 * counts[20] / max(1, denom[20]), 1)
    out["breadth_pct_50"] = round(100 * counts[50] / max(1, denom[50]), 1)
    if denom[200] > 0:
        out["breadth_pct_200"] = round(100 * counts[200] / denom[200], 1)

    # Real Nifty (Yahoo), trimmed to the same as-of date as the bhavcopy data
    try:
        if nifty is not None and not nifty.empty and "Close" in nifty.columns:
            nf = nifty[pd.to_datetime(nifty["Date"]) <= last_day] if "Date" in nifty.columns else nifty
            nc = nf["Close"].astype(float).values
            if len(nc) >= 20:
                out["nifty_price"] = round(float(nc[-1]), 2)
                out["nifty_20dma"] = round(float(nc[-20:].mean()), 2)
                d50 = float(nc[-50:].mean()) if len(nc) >= 50 else None
                d200 = float(nc[-200:].mean()) if len(nc) >= 200 else None
                out["nifty_50dma"] = round(d50, 2) if d50 else 0.0
                out["nifty_200dma"] = round(d200, 2) if d200 else 0.0
                out["nifty_trend"] = _trend_label(nc[-1], d50, d200)
                out["nifty_source"] = "Yahoo"
                return out
    except Exception:
        pass

    try:     # fallback: median stock price (weak proxy, clearly labelled)
        grp = h.groupby("Date")["CLOSE_PRICE"].median().reset_index().sort_values("Date")
        nc = grp["CLOSE_PRICE"].values
        if len(nc):
            out["nifty_price"] = round(float(nc[-1]), 2)
            d50 = float(nc[-50:].mean()) if len(nc) >= 50 else None
            d200 = float(nc[-200:].mean()) if len(nc) >= 200 else None
            if len(nc) >= 20:
                out["nifty_20dma"] = round(float(nc[-20:].mean()), 2)
            out["nifty_50dma"] = round(d50, 2) if d50 else 0.0
            out["nifty_200dma"] = round(d200, 2) if d200 else 0.0
            out["nifty_trend"] = _trend_label(nc[-1], d50, d200, short=True)
            out["nifty_source"] = "median (fallback)"
    except Exception:
        pass
    return out


# ============ SIGNAL LOG ============ #
def load_signal_log():
    if not os.path.exists(SIGNALS_CSV):
        return pd.DataFrame()
    try:
        df = pd.read_csv(SIGNALS_CSV)
        if "run_date" in df.columns:
            df["run_date"] = pd.to_datetime(df["run_date"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


def log_signals(scr, asof):
    """Log ONLY accumulation signals. (Logging every stock made every stock look like a repeat.)"""
    if scr is None or scr.empty:
        return 0
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        rd = str(pd.Timestamp(asof).date())
        rows = []
        for _, r in scr[scr["Signal"].isin(ACC_SIGNALS)].iterrows():
            rows.append({
                "run_date": rd,
                "symbol": str(r.get("Symbol", "")),
                "signal": str(r.get("Signal", "")),
                "score": int(r.get("Score", 0) or 0),
                "price": float(r.get("Price", 0) or 0),
                "entry": float(r.get("Entry", 0) or 0),
                "sl": float(r.get("SL", 0) or 0),
                "t1": float(r.get("T1", 0) or 0),
                "t2": float(r.get("T2", 0) or 0),
                "t3": float(r.get("T3", 0) or 0),
            })
        new_df = pd.DataFrame(rows, columns=["run_date", "symbol", "signal", "score", "price",
                                             "entry", "sl", "t1", "t2", "t3"])
        if os.path.exists(SIGNALS_CSV):
            old = pd.read_csv(SIGNALS_CSV)
            old = old[old["run_date"].astype(str) != rd]
            combined = pd.concat([old, new_df], ignore_index=True)
        else:
            combined = new_df
        try:
            combined["_d"] = pd.to_datetime(combined["run_date"], errors="coerce")
            cutoff = pd.Timestamp(asof) - pd.Timedelta(days=180)
            combined = combined[combined["_d"] >= cutoff].drop(columns=["_d"])
        except Exception:
            pass
        combined.to_csv(SIGNALS_CSV, index=False)
        return len(rows)
    except Exception:
        return 0


def signal_outcomes(hist):
    log = load_signal_log()
    if log.empty or hist is None or hist.empty:
        return pd.DataFrame()
    h = hist.copy()
    h["Date"] = pd.to_datetime(h["Date"], errors="coerce")
    h = h.dropna(subset=["Date", "Symbol", "LOW_PRICE", "HIGH_PRICE"])
    grouped = {sym: g.sort_values("Date") for sym, g in h.groupby("Symbol")}
    out_rows = []
    for _, r in log.iterrows():
        try:
            sym = str(r["symbol"])
            rd = pd.to_datetime(r["run_date"])
            sl = float(r.get("sl", 0) or 0)
            t1 = float(r.get("t1", 0) or 0)
            t2 = float(r.get("t2", 0) or 0)
            t3 = float(r.get("t3", 0) or 0)
            g = grouped.get(sym)
            if g is None or rd is None or pd.isna(rd):
                continue
            after = g[g.Date > rd]
            if after.empty:
                out_rows.append({"run_date": rd, "symbol": sym,
                                 "hit_sl": 0, "hit_t1": 0, "hit_t2": 0, "hit_t3": 0,
                                 "days_tracked": 0})
                continue
            out_rows.append({
                "run_date": rd, "symbol": sym,
                "hit_sl": int((after.LOW_PRICE <= sl).any()) if sl > 0 else 0,
                "hit_t1": int((after.HIGH_PRICE >= t1).any()) if t1 > 0 else 0,
                "hit_t2": int((after.HIGH_PRICE >= t2).any()) if t2 > 0 else 0,
                "hit_t3": int((after.HIGH_PRICE >= t3).any()) if t3 > 0 else 0,
                "days_tracked": len(after),
            })
        except Exception:
            continue
    return pd.DataFrame(out_rows)


def _episodes(dates, gap_days):
    """Group dates into episodes: dates <= gap_days apart belong to the same episode."""
    eps = []
    for x in sorted(set(pd.Timestamp(d) for d in dates)):
        if eps and (x - eps[-1][-1]).days <= gap_days:
            eps[-1].append(x)
        else:
            eps.append([x])
    return eps


def reentry_stats(scr, asof, outcomes=None, window_days=120, gap_days=7):
    """Re-entry = stock showed an accumulation signal, went quiet for > gap_days, and is back.
    Consecutive days of the same signal are ONE episode, not a repeat.
    Today's own row (if already logged) is ignored, so call order doesn't matter."""
    if scr is None or scr.empty:
        return scr
    attrs = dict(getattr(scr, "attrs", {}))
    out = scr.copy()
    out["Reentry"] = "🆕 First time"
    out["Appearances_120D"] = 1
    out["Days_Since_First"] = 0
    log = load_signal_log()
    if log.empty or "run_date" not in log.columns:
        out.attrs = attrs
        return out
    log["run_date"] = pd.to_datetime(log["run_date"], errors="coerce")
    asof_ts = pd.Timestamp(asof).normalize()
    recent = log[(log.run_date >= asof_ts - pd.Timedelta(days=window_days))
                 & (log.run_date < asof_ts)].dropna(subset=["run_date"])
    if recent.empty:
        out.attrs = attrs
        return out

    sl_hits = {}
    if outcomes is not None and not outcomes.empty and "hit_sl" in outcomes.columns:
        oc = outcomes[outcomes.hit_sl == 1]
        for sym, g in oc.groupby("symbol"):
            sl_hits[sym] = set(pd.to_datetime(g.run_date))

    info = {}
    for sym, g in recent.groupby("symbol"):
        eps = _episodes(g.run_date, gap_days)
        continuing = (asof_ts - eps[-1][-1]).days <= gap_days
        prior = eps[:-1] if continuing else eps
        first_seen = eps[0][0]
        flag, n_app = "🆕 First time", 1
        if prior:
            prior_dates = {d for ep in prior for d in ep}
            if prior_dates & sl_hits.get(sym, set()):
                flag = "🔁 SL hit earlier"
            elif len(prior) >= 2:
                flag = "🔁 Repeat"
            else:
                flag = "🔁 Second chance"
            n_app = len(prior) + 1
        info[sym] = (flag, n_app, int((asof_ts - first_seen).days))

    out["Reentry"] = out.Symbol.map(lambda s_: info[s_][0] if s_ in info else "🆕 First time")
    out["Appearances_120D"] = out.Symbol.map(lambda s_: info[s_][1] if s_ in info else 1).astype(int)
    out["Days_Since_First"] = out.Symbol.map(lambda s_: info[s_][2] if s_ in info else 0).astype(int)
    out.attrs = attrs
    return out


def reentry_history(symbol, limit=20, outcomes=None):
    log = load_signal_log()
    if log.empty:
        return pd.DataFrame()
    d = log[log.symbol == symbol].sort_values("run_date", ascending=False).head(limit).copy()
    if d.empty:
        return pd.DataFrame()
    d["run_date"] = pd.to_datetime(d["run_date"], errors="coerce")
    hit = set()
    if outcomes is not None and not outcomes.empty and "hit_sl" in outcomes.columns:
        m = outcomes[(outcomes.symbol == symbol) & (outcomes.hit_sl == 1)]
        hit = set(pd.to_datetime(m.run_date))
    d["SL_Hit"] = d["run_date"].isin(hit)
    try:
        d["Date"] = d["run_date"].dt.strftime("%d %b %Y")
        d = d.rename(columns={"signal": "Signal", "score": "Score",
                              "price": "Price", "entry": "Entry", "sl": "SL"})
        return d[["Date", "Signal", "Score", "Price", "Entry", "SL", "SL_Hit"]]
    except Exception:
        return d


def compute_10d_bhavcopy(hist, sector_map=None):
    """Build a security-wise 10-session activity view from NSE bhavcopy data."""
    if hist is None or hist.empty:
        return pd.DataFrame()
    h = hist.copy()
    h["Date"] = pd.to_datetime(h["Date"], errors="coerce")
    h = h.dropna(subset=["Date", "Symbol", "CLOSE_PRICE"]).sort_values(["Symbol", "Date"])
    dates = sorted(h.Date.unique())[-10:]
    h = h[h.Date.isin(dates)].copy()
    if h.empty:
        return pd.DataFrame()
    rows = []
    sector_map = sector_map or {}
    for sym, g in h.groupby("Symbol", sort=False):
        g = g.sort_values("Date").copy()
        if len(g) < 5:
            continue
        close = pd.to_numeric(g.CLOSE_PRICE, errors="coerce")
        qty = pd.to_numeric(g.TTL_TRD_QNTY, errors="coerce").fillna(0)
        dq = pd.to_numeric(g.DELIV_QTY, errors="coerce").fillna(0)
        dp = pd.to_numeric(g.DELIV_PER, errors="coerce")
        turn = qty * close / 1e7
        price = float(close.iloc[-1])
        p1 = float(close.iloc[0])
        def ret(n):
            return float((close.iloc[-1] / close.iloc[-min(n, len(close))] - 1) * 100) if p1 > 0 else 0.0
        avg_vol = float(qty.mean())
        latest_vol = float(qty.iloc[-1])
        avg_turn = float(turn.mean())
        deliv_trend = float(dp.iloc[-1] - dp.mean()) if dp.notna().any() else 0.0
        positive = int((close.diff() > 0).sum())
        active = int((qty > qty.mean()).sum())
        # Delivery-weighted activity score, capped 0..100.
        dscore = float(dp.fillna(0).mean()) / 100 * 25
        volscore = min(25.0, max(0.0, (latest_vol / avg_vol if avg_vol else 0) * 12.5))
        ret_score = min(30.0, max(0.0, (ret(10) + 10) * 1.5))
        cons_score = min(20.0, active * 2.0)
        score = round(min(100.0, dscore + volscore + ret_score + cons_score), 1)
        rows.append({"Symbol": sym, "Sector": sector_map.get(str(sym).upper(), "Other"),
                     "Price": price, "Ret_1D": ret(2), "Ret_3D": ret(3), "Ret_5D": ret(5),
                     "Ret_10D": ret(10), "Avg_Vol_10D": avg_vol, "Latest_Vol": latest_vol,
                     "Vol_vs_Avg": latest_vol / avg_vol if avg_vol else 0.0,
                     "Delivery_Pct": float(dp.iloc[-1]) if pd.notna(dp.iloc[-1]) else 0.0,
                     "Delivery_Trend": deliv_trend, "Turnover_10D_Cr": avg_turn,
                     "Activity_Score": score, "Positive_Days": positive, "Active_Days": active,
                     "Liquidity": "Liquid" if avg_turn >= 10 else "Thin"})
    return pd.DataFrame(rows).sort_values(["Activity_Score", "Ret_10D"], ascending=False).reset_index(drop=True)


def outcome_dashboard(hist, log=None):
    """Research backtest: valid logged entry signals only. Same-day SL wins if both SL/T1 touch."""
    if log is None: log = load_signal_log()
    if hist is None or hist.empty or log is None or log.empty: return pd.DataFrame()
    h=hist.copy(); h["Date"]=pd.to_datetime(h["Date"],errors="coerce")
    h=h.dropna(subset=["Date","Symbol","LOW_PRICE","HIGH_PRICE","CLOSE_PRICE"])
    grouped={s:g.sort_values("Date") for s,g in h.groupby("Symbol")}
    rows=[]
    for _,r in log.iterrows():
        try:
            sym=str(r.symbol); entry=float(r.entry); sl=float(r.sl); t1=float(r.t1); rd=pd.Timestamp(r.run_date)
            if entry<=0 or sl<=0 or t1<=entry: continue
            g=grouped.get(sym); after=g[g.Date>rd] if g is not None else pd.DataFrame()
            status="Open"; ret=0.0; days=0
            for _,bar in after.iterrows():
                days+=1; low=float(bar.LOW_PRICE); high=float(bar.HIGH_PRICE); close=float(bar.CLOSE_PRICE)
                if low<=sl:
                    status="SL"; ret=(sl/entry-1)*100; break
                if high>=t1:
                    status="T1"; ret=(t1/entry-1)*100; break
                ret=(close/entry-1)*100
            rows.append({"run_date":rd,"symbol":sym,"status":status,"return_pct":ret,"days":days})
        except Exception: continue
    return pd.DataFrame(rows)
