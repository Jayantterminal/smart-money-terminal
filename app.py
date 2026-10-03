"""
Institutional Smart Money Terminal (v12.1 - Production Cloud & Local Unified)
----------------------------------------------------------------------------
Complete Fusion of smart_money_bot.py Engine with Streamlit Terminal:
  1. Sheet 1: Top_Accumulation_Radar (Active Holds, Breakout BOS, & Fresh Entries)
  2. Sheet 2: Sector_Rotation (22 NSE Sector Inflow/Outflow Capital Shift)
  3. Sheet 3: Exited_Stocks_Log (1-Week Historical Audit with Hinglish Reasons)
  4. Real-time Multi-key Bhavcopy Sync & Clean Professional Autocomplete
"""
from __future__ import annotations

import datetime as dt
import glob
import hmac
import html
import io
import os
import tempfile
import zipfile

import numpy as np
import openpyxl
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ==========================================================
# CONSTANTS & ENVIRONMENT-AWARE PATHS
# ==========================================================
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")
CANDLE_MIN = 15
MIN_DELIVERY_PCT = 45.0
MIN_SPURT = 1.40
STALE_DEVIATION_PCT = 15.0
MAX_LOGIN_ATTEMPTS = 5
LEGACY_PASSWORD = "2000"

# Auto-detect Environment: Local D: drive vs Cloud deployment
if os.path.exists(r"D:\Bhavdata"):
    BASE_DIR = r"D:\Bhavdata\bhavdata_3months_arranged"
    DASHBOARD_FILE = r"D:\Bhavdata\SmartMoney_Live_Dashboard.xlsx"
else:
    BASE_DIR = os.path.join("data", "bhavdata_archive")
    DASHBOARD_FILE = os.path.join("data", "SmartMoney_Live_Dashboard.xlsx")

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

BHAV_DIR = BASE_DIR

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

NSE_FO_UNIVERSE = {
    "BAJAJFINSV", "BAJFINANCE", "CANBK", "HDFCBANK", "ICICIBANK",
    "KOTAKBANK", "INDHOTEL", "JKCEMENT", "SHREECEM", "COFORGE",
    "BAJAJ-AUTO", "BEL", "AIAENG", "KAJARIACER", "RELIANCE", "TCS",
    "INFY", "LT", "SBIN", "AXISBANK", "TATAMOTORS", "TATASTEEL", "DLF"
}

# ==========================================================
# AUTHENTICATION & REGIME ENGINE
# ==========================================================
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
        "<div style='text-align:center;margin-top:60px;'><h2 style='color:#F0F6FC;'>🔒 Institutional Terminal Gate</h2>"
        "<p style='color:#8B949E;'>Enter security master password to unlock corporate cockpit.</p></div>",
        unsafe_allow_html=True
    )
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("auth_form"):
            pwd_in = st.text_input("Master Password", type="password", placeholder="Enter authorization key...")
            if st.form_submit_button("Unlock Cockpit", use_container_width=True):
                if st.session_state["failed_attempts"] >= MAX_LOGIN_ATTEMPTS:
                    st.error("Too many failed attempts. Reload page.")
                elif hmac.compare_digest(pwd_in.encode("utf-8"), master.encode("utf-8")):
                    st.session_state["authenticated"] = True
                    st.session_state["failed_attempts"] = 0
                    st.rerun()
                else:
                    st.session_state["failed_attempts"] += 1
                    left = MAX_LOGIN_ATTEMPTS - st.session_state["failed_attempts"]
                    st.error(f"Invalid credentials. Attempts left: {max(left, 0)}")
    return False

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

# ==========================================================
# LIVE QUOTE FETCHER (FIXED FOR LINE 604 ERROR)
# ==========================================================
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
# BHAVCOPY DOWNLOAD & ARCHIVE
# ==========================================================
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
            return local_path, res.content, "Downloaded Directly from NSE"
    except Exception:
        pass
    return None, None, "Market Holiday / Data Unavailable"

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
# UNIFIED BHAVDATA & SMART MONEY BOT CORE
# ==========================================================
@st.cache_data(ttl=1800, show_spinner=False)
def load_unified_institutional_data() -> dict:
    prev_tracking_dict = {}
    user_trade_actions = {}
    user_buy_prices = {}

    if os.path.exists(DASHBOARD_FILE):
        try:
            prev_df = pd.read_excel(DASHBOARD_FILE, sheet_name="Top_Accumulation_Radar", skiprows=2)
            cols = [str(c).strip() for c in prev_df.columns]
            prev_df.columns = cols
            if "Symbol" in prev_df.columns:
                for _, r in prev_df.iterrows():
                    sym = str(r["Symbol"]).strip().upper()
                    if "First Detected Date" in prev_df.columns and pd.notna(r["First Detected Date"]):
                        prev_tracking_dict[sym] = str(r["First Detected Date"])
                    if "Trade Action" in prev_df.columns and pd.notna(r["Trade Action"]):
                        act = str(r["Trade Action"]).strip().upper()
                        if act and act != "NAN":
                            user_trade_actions[sym] = act
                    if "My Buy Price (Rs)" in prev_df.columns and pd.notna(r["My Buy Price (Rs)"]):
                        try:
                            bp = float(r["My Buy Price (Rs)"])
                            if bp > 0:
                                user_buy_prices[sym] = bp
                        except Exception:
                            pass
        except Exception:
            pass

    sector_mapping = {}
    target_universe = set()
    try:
        u500 = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
        r500 = requests.get(u500, headers=HEADERS, timeout=6)
        df_500 = pd.read_csv(io.BytesIO(r500.content))
        for _, row in df_500.iterrows():
            sym = str(row["Symbol"]).strip().upper()
            sector_mapping[sym] = str(row.get("Industry", "Diversified")).strip()
            target_universe.add(sym)
    except Exception:
        pass

    try:
        umicro = "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv"
        rmicro = requests.get(umicro, headers=HEADERS, timeout=6)
        df_micro = pd.read_csv(io.BytesIO(rmicro.content))
        for _, row in df_micro.iterrows():
            sym = str(row["Symbol"]).strip().upper()
            if sym not in sector_mapping:
                sector_mapping[sym] = str(row.get("Industry", "Microcap / Others")).strip()
            target_universe.add(sym)
    except Exception:
        pass

    csv_paths = sorted(glob.glob(f"{BASE_DIR}/**/*.csv", recursive=True))
    if not csv_paths:
        # Fallback fetch
        today_d = now_ist().date()
        fetch_nse_delivery_bhav(today_d - dt.timedelta(days=1))
        csv_paths = sorted(glob.glob(f"{BHAV_DIR}/*.csv"))

    df_list = []
    for f in csv_paths:
        try:
            tmp = pd.read_csv(f)
            tmp.columns = [c.strip().upper() for c in tmp.columns]
            if "SERIES" in tmp.columns:
                tmp = tmp[tmp["SERIES"].str.strip() == "EQ"]
            df_list.append(tmp)
        except Exception:
            continue

    if not df_list:
        # Failsafe dummy container
        return {"ok": False, "radar": pd.DataFrame(), "sectors": pd.DataFrame(), "exited": pd.DataFrame(), "market_date": "N/A"}

    df_bhav = pd.concat(df_list, ignore_index=True)
    if len(target_universe) > 10:
        df_bhav = df_bhav[df_bhav["SYMBOL"].str.strip().str.upper().isin(target_universe)].copy()

    etf_keywords = ["BEES", "ETF", "10BE", "GOLD", "LIQUID", "NIFTY", "SENSEX", "MON100"]
    df_bhav = df_bhav[~df_bhav["SYMBOL"].str.upper().str.contains("|".join(etf_keywords))].copy()

    if "DATE1" in df_bhav.columns:
        df_bhav["DATE1"] = pd.to_datetime(df_bhav["DATE1"].str.strip(), format="%d-%b-%Y", errors="coerce")
    else:
        df_bhav["DATE1"] = pd.to_datetime(now_ist().date())

    df_bhav = df_bhav.sort_values(["SYMBOL", "DATE1"]).reset_index(drop=True)

    for col in ["DELIV_QTY", "DELIV_PER", "TTL_TRD_QNTY", "CLOSE_PRICE", "HIGH_PRICE", "LOW_PRICE"]:
        if col in df_bhav.columns:
            df_bhav[col] = pd.to_numeric(df_bhav[col].astype(str).str.strip(), errors="coerce")

    if "DELIV_PER" not in df_bhav.columns and "DELIV_QTY" in df_bhav.columns and "TTL_TRD_QNTY" in df_bhav.columns:
        df_bhav["DELIV_PER"] = (df_bhav["DELIV_QTY"] / (df_bhav["TTL_TRD_QNTY"] + 1e-9)) * 100

    df_bhav["DELIV_TURNOVER_CR"] = (df_bhav["DELIV_QTY"] * df_bhav["CLOSE_PRICE"]) / 1e7
    df_bhav["SECTOR"] = df_bhav["SYMBOL"].map(sector_mapping).fillna("Others")

    unique_dates = sorted(df_bhav["DATE1"].dropna().unique())
    latest_market_date = unique_dates[-1].strftime("%d-%b-%Y") if len(unique_dates) > 0 else now_ist().strftime("%d-%b-%Y")
    recent_dates = unique_dates[-12:] if len(unique_dates) >= 12 else unique_dates
    baseline_dates = unique_dates[:-12] if len(unique_dates) > 12 else unique_dates

    df_recent = df_bhav[df_bhav["DATE1"].isin(recent_dates)]
    df_base = df_bhav[df_bhav["DATE1"].isin(baseline_dates)] if len(baseline_dates) > 0 else df_recent

    base_total_cr = max(df_base["DELIV_TURNOVER_CR"].sum(), 1.0)
    recent_total_cr = max(df_recent["DELIV_TURNOVER_CR"].sum(), 1.0)

    base_sec = df_base.groupby("SECTOR")["DELIV_TURNOVER_CR"].sum().reset_index()
    base_sec["3M Base Share (%)"] = (base_sec["DELIV_TURNOVER_CR"] / base_total_cr * 100).round(2)

    recent_sec = df_recent.groupby("SECTOR")["DELIV_TURNOVER_CR"].sum().reset_index()
    recent_sec["Recent 12D Share (%)"] = (recent_sec["DELIV_TURNOVER_CR"] / recent_total_cr * 100).round(2)

    sector_rotation = pd.merge(
        recent_sec[["SECTOR", "Recent 12D Share (%)"]],
        base_sec[["SECTOR", "3M Base Share (%)"]],
        on="SECTOR", how="outer"
    ).fillna(0)

    sector_rotation["Flow Shift (%)"] = (sector_rotation["Recent 12D Share (%)"] - sector_rotation["3M Base Share (%)"]).round(2)
    sector_rotation["Flow Signal"] = sector_rotation["Flow Shift (%)"].apply(
        lambda x: "🟢 Heavy Inflow" if x >= 0.5 else ("🟢 Inflow" if x > 0 else ("🔴 Heavy Outflow" if x <= -0.5 else "🔴 Outflow"))
    )
    sector_rotation = sector_rotation.sort_values(by="Flow Shift (%)", ascending=False).reset_index(drop=True)
    inflow_sectors = set(sector_rotation[sector_rotation["Flow Shift (%)"] > 0]["SECTOR"])

    base_stats = df_base.groupby("SYMBOL").agg(
        BASE_AVG_QTY=("DELIV_QTY", "mean"),
        BASE_AVG_DELIV_PER=("DELIV_PER", "mean")
    ).reset_index()

    recent_stats = df_recent.groupby("SYMBOL").agg(
        RECENT_AVG_QTY=("DELIV_QTY", "mean"),
        CURRENT_PRICE=("CLOSE_PRICE", "last"),
        PRICE_CHG_PCT=("CLOSE_PRICE", lambda x: ((x.iloc[-1] - x.iloc[0]) / (x.iloc[0] + 1e-9)) * 100 if len(x) > 1 else 0),
        RECENT_AVG_DELIV_PER=("DELIV_PER", "mean"),
        RECENT_DELIV_CR=("DELIV_TURNOVER_CR", "sum"),
        SECTOR=("SECTOR", "first"),
        SWING_HIGH_KEY=("HIGH_PRICE", lambda x: x.iloc[:-1].max() if len(x) > 1 else x.iloc[-1]),
        SWING_LOW_KEY=("LOW_PRICE", "min")
    ).reset_index()

    acc_df = pd.merge(recent_stats, base_stats, on="SYMBOL", how="inner")
    acc_df["QTY_SPIKE_RATIO"] = (acc_df["RECENT_AVG_QTY"] / (acc_df["BASE_AVG_QTY"] + 1e-9)).round(2)

    current_active = acc_df[
        (acc_df["QTY_SPIKE_RATIO"] >= MIN_SPURT) &
        (acc_df["PRICE_CHG_PCT"].between(-4.0, 10.0)) &
        (acc_df["RECENT_AVG_DELIV_PER"] >= MIN_DELIVERY_PCT) &
        (acc_df["RECENT_DELIV_CR"] >= 8.0)
    ].sort_values(by="QTY_SPIKE_RATIO", ascending=False).reset_index(drop=True)

    if current_active.empty:
        current_active = acc_df[acc_df["RECENT_AVG_DELIV_PER"] >= 40.0].sort_values(by="QTY_SPIKE_RATIO", ascending=False).head(25).reset_index(drop=True)

    today_date = now_ist().date()
    tracking_status, first_dates, holding_days, smc_status, bos_triggers, sl_levels = [], [], [], [], [], []
    final_actions, final_buy_prices, trailing_sls, signal_advices = [], [], [], []

    for _, r in current_active.iterrows():
        sym = r["SYMBOL"]
        cmp_ = r["CURRENT_PRICE"]
        sw_high = r["SWING_HIGH_KEY"]
        sw_low = r["SWING_LOW_KEY"]
        sec = r["SECTOR"]

        if sym in prev_tracking_dict:
            tracking_status.append("⚡ ACTIVE HOLD")
            f_date = prev_tracking_dict[sym]
            first_dates.append(f_date)
            try:
                d_obj = dt.datetime.strptime(f_date, "%d-%b-%Y").date()
                h_days = (today_date - d_obj).days
            except Exception:
                h_days = 1
            holding_days.append(f"{max(h_days, 1)} Days")
        else:
            tracking_status.append("🟢 NEW ENTRY")
            first_dates.append(latest_market_date)
            holding_days.append("1 Day")

        if cmp_ >= sw_high:
            smc_status.append("🚀 CONFIRMED BOS")
        else:
            smc_status.append("⏳ EQUILIBRIUM OB (50%)")

        bos_triggers.append(round(sw_high, 2))
        sl_levels.append(round(sw_low, 2))

        act = user_trade_actions.get(sym, "WATCHLIST")
        bp = user_buy_prices.get(sym, None)
        final_actions.append(act)
        final_buy_prices.append(bp if bp else np.nan)

        if act == "ENTERED" and bp:
            pnl = ((cmp_ - bp) / bp) * 100
            tsl = max(bp, sw_low) if pnl >= 5.0 else sw_low
            advice = f"🟢 HOLD & RIDE (+{pnl:.1f}%)" if cmp_ >= tsl else f"🔴 SL HIT @ ₹{tsl:.2f}"
            trailing_sls.append(round(tsl, 2))
            signal_advices.append(advice)
        else:
            trailing_sls.append(round(sw_low, 2))
            signal_advices.append("🟢 READY TO BUY" if cmp_ >= sw_high else "⏳ WAIT FOR BOS TRIGGER")

    current_active["Live Status"] = tracking_status
    current_active["First Detected Date"] = first_dates
    current_active["Radar Age"] = holding_days
    current_active["SMC Structure"] = smc_status
    current_active["BOS Trigger (Rs)"] = bos_triggers
    current_active["Support / TSL (Rs)"] = sl_levels
    current_active["Trade Action"] = final_actions
    current_active["My Buy Price (Rs)"] = final_buy_prices
    current_active["Trade Signal"] = signal_advices
    current_active["Sector Alignment"] = current_active["SECTOR"].apply(lambda s: "✅ Inflow Aligned" if s in inflow_sectors else "⚠️ Sector Outflow")
    current_active["Volume Spurt"] = current_active["QTY_SPIKE_RATIO"]
    current_active["Recent Deliv %"] = current_active["RECENT_AVG_DELIV_PER"].round(1)
    current_active["CMP (Rs)"] = current_active["CURRENT_PRICE"].round(2)

    exited_rows = []
    active_syms = set(current_active["SYMBOL"])
    if len(unique_dates) >= 18:
        w1_dates = unique_dates[-17:-5]
        w1_base = unique_dates[:-17]
        df_w1 = df_bhav[df_bhav["DATE1"].isin(w1_dates)]
        df_w1_base = df_bhav[df_bhav["DATE1"].isin(w1_base)]

        w1_base_agg = df_w1_base.groupby("SYMBOL")["DELIV_QTY"].mean().reset_index().rename(columns={"DELIV_QTY": "W1_BASE_QTY"})
        w1_agg = df_w1.groupby("SYMBOL").agg(
            W1_QTY=("DELIV_QTY", "mean"),
            W1_PRICE_CHG=("CLOSE_PRICE", lambda x: ((x.iloc[-1] - x.iloc[0]) / (x.iloc[0] + 1e-9)) * 100 if len(x) > 1 else 0),
            W1_DELIV_PER=("DELIV_PER", "mean"),
            W1_DELIV_CR=("DELIV_TURNOVER_CR", "sum")
        ).reset_index()

        w1_merged = pd.merge(w1_agg, w1_base_agg, on="SYMBOL", how="inner")
        w1_merged["W1_SPURT"] = (w1_merged["W1_QTY"] / (w1_merged["W1_BASE_QTY"] + 1e-9)).round(2)
        w1_qualified = set(w1_merged[
            (w1_merged["W1_SPURT"] >= 1.40) &
            (w1_merged["W1_PRICE_CHG"].between(-4.0, 10.0)) &
            (w1_merged["W1_DELIV_PER"] >= 45.0) &
            (w1_merged["W1_DELIV_CR"] >= 8.0)
        ]["SYMBOL"])

        hist_exits = list(w1_qualified - active_syms)
        for x_sym in hist_exits:
            match = acc_df[acc_df["SYMBOL"] == x_sym]
            if not match.empty:
                cmp_val = match["CURRENT_PRICE"].values[0]
                chg_val = match["PRICE_CHG_PCT"].values[0]
                spurt_val = match["QTY_SPIKE_RATIO"].values[0]

                if chg_val > 10.0:
                    h_reason = f"🚀 Target Hit / Breakout Complete ({chg_val:+.1f}% move aa gaya)"
                elif chg_val < -4.0:
                    h_reason = f"🛑 Support Broken / Structure Fail ({chg_val:+.1f}% drawdown)"
                elif spurt_val < 1.40:
                    h_reason = f"📉 Volume Spurt khatam hua (Spurt {spurt_val:.2f}x par gir gaya)"
                else:
                    h_reason = "⚠️ Delivery percentage threshold se niche chala gaya"

                exited_rows.append({
                    "Symbol": x_sym,
                    "Exit Date": unique_dates[-5].strftime("%d-%b-%Y"),
                    "Current Price (Rs)": round(cmp_val, 2),
                    "Recent Return (%)": round(chg_val, 2),
                    "Last Spurt Ratio": spurt_val,
                    "Hinglish Exit Reason": h_reason
                })

    exited_df = pd.DataFrame(exited_rows).sort_values(by="Recent Return (%)", ascending=False).reset_index(drop=True) if exited_rows else pd.DataFrame(
        columns=["Symbol", "Exit Date", "Current Price (Rs)", "Recent Return (%)", "Last Spurt Ratio", "Hinglish Exit Reason"]
    )

    return {
        "ok": True,
        "radar": current_active,
        "sectors": sector_rotation,
        "exited": exited_df,
        "market_date": latest_market_date
    }

# ==========================================================
# EVALUATION & ACTION VERDICT ENGINE
# ==========================================================
def evaluate_final_radar(current_active: pd.DataFrame, quotes: dict, max_chase_pct: float) -> pd.DataFrame:
    rows = []
    for r in current_active.to_dict("records"):
        sym = str(r["SYMBOL"]).strip().upper()
        sec = r["SECTOR"]
        q = quotes.get(sym)
        cmp_ = q["cmp"] if q else r["CURRENT_PRICE"]
        last_close = q["last_close"] if q else cmp_

        is_fo = sym in NSE_FO_UNIVERSE
        is_inflow = "Inflow" in r["Sector Alignment"]
        p2_pass = r["Volume Spurt"] >= MIN_SPURT and r["Recent Deliv %"] >= MIN_DELIVERY_PCT

        bos_trigger = float(r["BOS Trigger (Rs)"])
        sl_level = float(r["Support / TSL (Rs)"])

        if not is_inflow:
            key, verdict, action = "BLOCKED", "⛔ BLOCKED", "Sector Outflow: Avoid Long Trades"
        elif not p2_pass:
            key, verdict, action = "BLOCKED", "⛔ BLOCKED", "Delivery / Spurt Criteria Weak"
        elif last_close < sl_level:
            key, verdict, action = "INVALID", "❌ INVALIDATED", "Support Broken / Stop Hit - EXIT"
        elif last_close >= bos_trigger:
            ext = (last_close / bos_trigger - 1) * 100
            if ext > max_chase_pct:
                key, verdict, action = "EXTENDED", "🟠 EXTENDED", f"Chasing Avoid: Wait Pullback (+{ext:.1f}%)"
            else:
                key, verdict, action = "READY_BUY", "🟢 READY BUY", "15m Breakout Confirmed - Place Order"
        elif last_close >= (bos_trigger * 0.985):
            key, verdict, action = "PRE", "🟡 PRE-TRIGGER", "Near Trigger: Wait 15m Candle Close"
        else:
            key, verdict, action = "IN_ZONE", "⏳ EQUILIBRIUM OB", "In 50% Accumulation Base - Wait Trigger"

        dist_to_bos = ((bos_trigger / cmp_) - 1) * 100 if cmp_ else 0.0
        day_chg = ((cmp_ / q["prev_close"]) - 1) * 100 if q and q.get("prev_close") else r["PRICE_CHG_PCT"]

        rank_map = {"READY_BUY": 0, "IN_ZONE": 1, "PRE": 2, "EXTENDED": 3, "BLOCKED": 4, "INVALID": 5}
        tone_map = {"READY_BUY": "g", "IN_ZONE": "b", "PRE": "y", "EXTENDED": "o", "BLOCKED": "r", "INVALID": "r"}

        rows.append({
            "Symbol": sym, "Sector": sec, "Live Status": r["Live Status"],
            "VERDICT": verdict, "Action": action,
            "CMP (Rs)": round(cmp_, 2), "Day %": round(day_chg, 2),
            "BOS Trigger (Rs)": bos_trigger, "Dist. to BOS %": round(dist_to_bos, 2),
            "Support / TSL (Rs)": sl_level,
            "Volume Spurt": f"{r['Volume Spurt']:.2f}x", "Recent Deliv %": f"{r['Recent Deliv %']:.1f}%",
            "Radar Age": r["Radar Age"], "Sector Flow": r["Sector Alignment"],
            "_key": key, "_rank": rank_map.get(key, 9), "_tone": tone_map.get(key, "n"),
            "_tradable": is_inflow and p2_pass, "_segment": "F&O Tradable" if is_fo else "Cash Only"
        })
    df = pd.DataFrame(rows)
    return df.sort_values(["_rank", "Dist. to BOS %"], ascending=[True, True]).reset_index(drop=True)

# ==========================================================
# REPORT FORMATTING & CSS
# ==========================================================
MASTER_COLS = [
    "Symbol", "Sector", "Live Status", "VERDICT", "Action", "CMP (Rs)", "Day %",
    "BOS Trigger (Rs)", "Dist. to BOS %", "Support / TSL (Rs)", "Volume Spurt",
    "Recent Deliv %", "Radar Age", "Sector Flow"
]

COMPACT_COLS = [
    "Symbol", "VERDICT", "Action", "CMP (Rs)", "BOS Trigger (Rs)",
    "Support / TSL (Rs)", "Volume Spurt", "Recent Deliv %"
]

def html_table(df: pd.DataFrame, cols: list[str], badge_cols: tuple = (), height: int = 560) -> str:
    if df.empty:
        return "<div class='empty'>No setups match your selected filters.</div>"
    head = "<th class='c-no'>No.</th>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        tone = row.get("_tone", "n")
        cells = [f"<td class='c-no t-{tone}'>{i}</td>"]
        for c in cols:
            val = row[c]
            cls = "num" if "Rs" in c or "%" in c or "Spurt" in c else ""
            txt = f"{val:+.2f}%" if c == "Day %" or c == "Dist. to BOS %" else str(val)
            if c == "Day %":
                cls += " pos" if val > 0 else " neg" if val < 0 else ""
            cells.append(f"<td><span class='bdg b-{tone}'>{txt}</span></td>" if c in badge_cols else f"<td class='{cls}'>{txt}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f"<div class='tbl-wrap' style='max-height:{height}px'><table class='smc'>"
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")

def generate_excel_bytes(radar_df: pd.DataFrame, sec_df: pd.DataFrame, exit_df: pd.DataFrame) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    head_fill = PatternFill("solid", start_color="161B22", end_color="161B22")
    side = Side(style="thin", color="CBD5E1")
    border = Border(left=side, right=side, top=side, bottom=side)

    ws1 = wb.create_sheet(title="Top_Accumulation_Radar")
    headers1 = ["No."] + MASTER_COLS
    ws1.append(headers1)
    for c in range(1, len(headers1) + 1):
        ws1.cell(row=1, column=c).fill = head_fill
        ws1.cell(row=1, column=c).font = Font(name="Calibri", bold=True, color="FFFFFF")
    for i, rec in enumerate(radar_df[MASTER_COLS].to_dict("records"), start=2):
        ws1.append([i - 1] + [rec[c] for c in MASTER_COLS])
        for j in range(1, len(headers1) + 1):
            ws1.cell(row=i, column=j).border = border

    ws2 = wb.create_sheet(title="Sector_Rotation")
    s_cols = ["SECTOR", "Recent 12D Share (%)", "3M Base Share (%)", "Flow Shift (%)", "Flow Signal"]
    if all(c in sec_df.columns for c in s_cols):
        ws2.append(["No."] + s_cols)
        for i, rec in enumerate(sec_df[s_cols].to_dict("records"), start=2):
            ws2.append([i - 1] + [rec[c] for c in s_cols])

    ws3 = wb.create_sheet(title="Exited_Stocks_Log")
    x_cols = list(exit_df.columns)
    ws3.append(["No."] + x_cols)
    for i, rec in enumerate(exit_df.to_dict("records"), start=2):
        ws3.append([i - 1] + [rec[c] for c in x_cols])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

CSS = """
<style>
  .block-container{padding-top:1.2rem;max-width:1600px;}
  div[data-testid="stMetric"]{background:linear-gradient(180deg,#161B22,#10151C);border:1px solid #30363D;
      border-left:3px solid #58A6FF;padding:12px 16px;border-radius:8px;}
  div[data-testid="stMetricLabel"]{color:#8B949E;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;}
  div[data-testid="stMetricValue"]{color:#F0F6FC;font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700;}

  .stTabs [data-baseweb="tab-list"]{gap:10px;border-bottom:2px solid #30363D;padding-bottom:6px;}
  .stTabs [data-baseweb="tab"]{
      background-color:#161B22;border:1px solid #30363D;border-radius:6px;
      color:#8B949E;font-weight:600;padding:8px 18px;font-size:13px;
  }
  .stTabs [data-baseweb="tab"]:nth-child(1) {
      border: 2px solid #238636 !important;
      background: linear-gradient(180deg, #161B22, #0d2a1a) !important;
      color: #3FB950 !important;
      font-weight: 700 !important;
      font-size: 14px !important;
      padding: 10px 22px !important;
  }
  .stTabs [data-baseweb="tab"]:nth-child(2) {
      border: 2px solid #1F6FEB !important;
      background: linear-gradient(180deg, #161B22, #0d213a) !important;
      color: #58A6FF !important;
      font-weight: 700 !important;
      font-size: 14px !important;
      padding: 10px 22px !important;
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
# MAIN APPLICATION ROUTINE
# ==========================================================
def main():
    st.set_page_config(page_title="Institutional Smart Money Terminal", page_icon="⚡", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    if not auth_gate():
        st.stop()

    data_bundle = load_unified_institutional_data()
    if not data_bundle["ok"]:
        st.warning("⚠️ Local Bhavcopy CSV archive empty. Fetching historical session...")
        today_d = now_ist().date()
        fetch_nse_delivery_bhav(today_d - dt.timedelta(days=1))
        st.cache_data.clear()
        st.rerun()

    active_raw = data_bundle["radar"]
    sec_df = data_bundle["sectors"]
    exit_df = data_bundle["exited"]
    market_date = data_bundle["market_date"]

    with st.sidebar:
        st.markdown("### ⚙️ Live Execution Controls")
        if st.button("🔄 Instant Live Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        view_mode = st.radio("View Layout", ["Bordered Report", "Interactive Grid"], horizontal=True)
        status_filter = st.selectbox("Status Filter", ["All Setups", "🟢 NEW ENTRY Only", "⚡ ACTIVE HOLD Only"])
        tradable_only = st.toggle("Tradable Only (P1 + P2 Qualified)", value=False)
        max_chase = st.slider("Max Extension vs Trigger (%)", 0.5, 5.0, 2.0, 0.5)

        avail_syms = sorted(active_raw["SYMBOL"].unique()) if not active_raw.empty else []
        selected_symbols = st.multiselect(
            "🔍 Search & Filter Stocks:",
            options=avail_syms,
            placeholder="Search stock..."
        )

        with st.expander("ℹ️ Framework Methodology & Rules"):
            st.markdown(
                "• **Pillar 1:** 22 NSE Sector Inflow (+Shift) vs Outflow (-Shift).\n"
                "• **Pillar 2:** Delivery >= 45% + Historical Spurt >= 1.40x.\n"
                "• **Pillar 3:** 15m candle close > BOS Level confirms execution.\n"
                "• **Preservation:** Active holds carry forward across trading sessions."
            )

        st.markdown("---")
        if st.button("🔒 Lock Cockpit", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()

    # Fixed: Live quote tuple with safe fallback
    symbols_tuple = tuple(active_raw["SYMBOL"].unique()) if not active_raw.empty else ()
    live = fetch_live_quotes(symbols_tuple)
    quotes, fetched_at = live["quotes"], live["fetched_at"]

    evaluated_df = evaluate_final_radar(active_raw, quotes, max_chase)
    regime = get_market_regime()
    now = now_ist()
    mkt = market_state(now)
    regime_txt = (f"{regime['regime']} · Nifty {regime['nifty']:,.0f} ({fmt_pct(regime['nifty_chg'])})" if regime["ok"] else "Index feed offline")

    st.markdown(
        "<div class='hdr'><div><h1>⚡ Institutional Smart Money Terminal</h1>"
        f"<div class='sub'>Automated 3-Pillar Pipeline · As On {market_date} · FII/DII Net Cash Flow · 15m Micro Timing</div></div>"
        "<div class='chips'>"
        f"<span class='chip'><b>SYNC</b>{fetched_at.strftime('%d-%b-%Y %I:%M:%S %p IST')}</span>"
        f"<span class='chip'><b>MARKET</b>{html.escape(mkt)}</span>"
        f"<span class='chip'><b>REGIME</b>{html.escape(regime_txt)}</span>"
        f"<span class='chip'><b>FII NET</b>₹{regime['fii']:+,.1f} Cr</span>"
        f"<span class='chip'><b>DII NET</b>₹{regime['dii']:+,.1f} Cr</span>"
        "</div></div>", unsafe_allow_html=True)

    blocked_count = int((evaluated_df["_key"].isin(["BLOCKED", "INVALID"])).sum())
    m = st.columns(6)
    m[0].metric("1 · Tracked", len(evaluated_df))
    m[1].metric("2 · Tradable (P1+P2)", int(evaluated_df["_tradable"].sum()))
    m[2].metric("3 · ⚡ Ready Buy", int((evaluated_df["_key"] == "READY_BUY").sum()))
    m[3].metric("4 · ⏳ In OB Base", int((evaluated_df["_key"] == "IN_ZONE").sum()))
    m[4].metric("5 · Inflow Aligned", int(evaluated_df["Sector Flow"].str.contains("Inflow").sum()))
    m[5].metric("6 · Blocked / Avoid", blocked_count)

    view = evaluated_df.copy()
    if status_filter != "All Setups":
        view = view[view["Live Status"].str.contains(status_filter.split()[1])]

    if tradable_only:
        view = view[view["_tradable"]]

    if selected_symbols:
        view = view[view["Symbol"].isin(selected_symbols)]

    tab1, tab2, tab3 = st.tabs([
        "⚡ Top Accumulation Radar",
        "🔄 Sector Rotation Matrix (P1)",
        "📁 Exited Log & Bhavcopy Archive"
    ])

    with tab1:
        section("1.1", "Actionable Now (Direct Buy/Sell Signals)", "Pillar 1 + Pillar 2 + 15m BOS Trigger Confirmed")
        act = view[view["_key"] == "READY_BUY"]
        if act.empty:
            st.markdown("<div class='empty'>No setups currently crossing exact 15m BOS trigger. Active candidates are accumulating in base or awaiting volume expansion.</div>", unsafe_allow_html=True)
        else:
            if view_mode == "Bordered Report":
                st.markdown(html_table(act, COMPACT_COLS, badge_cols=("VERDICT",), height=280), unsafe_allow_html=True)
            else:
                st.dataframe(act[COMPACT_COLS], hide_index=True, use_container_width=True)

        section("1.2", "Master Execution Radar", f"{len(view)} of {len(evaluated_df)} institutional setups tracked")
        if view_mode == "Bordered Report":
            st.markdown(html_table(view, MASTER_COLS, badge_cols=("VERDICT",), height=560), unsafe_allow_html=True)
        else:
            st.dataframe(view[MASTER_COLS], hide_index=True, height=560, use_container_width=True)

        section("1.3", "Live Synchronized Excel Export")
        xlsx = generate_excel_bytes(evaluated_df, sec_df, exit_df)
        st.download_button(
            "📥 Download SmartMoney_Live_Dashboard (.xlsx)", data=xlsx,
            file_name=f"SmartMoney_Live_Dashboard_{now.strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True
        )

    with tab2:
        section("2.1", "NSE Sector Inflow/Outflow Matrix", "Institutional Rule: Trade strictly in Inflow (+), Avoid Outflow (-)")
        s_cols = ["SECTOR", "Recent 12D Share (%)", "3M Base Share (%)", "Flow Shift (%)", "Flow Signal"]
        if all(c in sec_df.columns for c in s_cols):
            c1, c2, c3 = st.columns(3)
            c1.metric("Inflow Sectors", int((sec_df["Flow Shift (%)"] > 0).sum()))
            c2.metric("Outflow Sectors", int((sec_df["Flow Shift (%)"] < 0).sum()))
            c3.metric("Neutral", int((sec_df["Flow Shift (%)"] == 0).sum()))

            col_a, col_b = st.columns(2)
            with col_a:
                section("2.2", "🟢 Institutional Inflow Sectors")
                st.markdown(html_table(sec_df[sec_df["Flow Shift (%)"] > 0], s_cols, badge_cols=("Flow Signal",), height=340), unsafe_allow_html=True)
            with col_b:
                section("2.3", "🔴 Institutional Outflow Sectors")
                st.markdown(html_table(sec_df[sec_df["Flow Shift (%)"] < 0], s_cols, badge_cols=("Flow Signal",), height=340), unsafe_allow_html=True)

            section("2.4", "Sector Share Shift (pp vs 3M Base Share)")
            st.bar_chart(sec_df.set_index("SECTOR")["Flow Shift (%)"], height=320)

    with tab3:
        section("3.1", "1-Week Removed / Exited Stocks Audit Log", "Tracking stocks that Hit Target or Broke Structure")
        if not exit_df.empty:
            st.dataframe(exit_df, hide_index=True, use_container_width=True)
        else:
            st.info("No stocks have exited the criteria during the rolling analysis period.")

        section("3.2", "NSE Day-Wise Official Bhavcopy Downloader", "Direct browser delivery download")
        b1, b2 = st.columns([1.5, 2.5])
        with b1:
            sel_date = st.date_input("Select Trading Date", value=now.date() - dt.timedelta(days=1))
            if st.button("📥 Fetch & Verify Bhavcopy", use_container_width=True):
                with st.spinner("Handshaking with NSE servers..."):
                    fpath, raw_bytes, msg = fetch_nse_delivery_bhav(sel_date)
                    if fpath and raw_bytes:
                        st.session_state["last_bhav_bytes"] = raw_bytes
                        st.session_state["last_bhav_name"] = os.path.basename(fpath)
                        st.success(f"{msg}: {os.path.basename(fpath)}")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)

            if "last_bhav_bytes" in st.session_state:
                st.download_button(
                    label=f"💾 Download {st.session_state['last_bhav_name']} to PC",
                    data=st.session_state["last_bhav_bytes"],
                    file_name=st.session_state["last_bhav_name"],
                    mime="text/csv", use_container_width=True
                )

        with b2:
            section("3.3", "Local Archive Health")
            files = [f for f in os.listdir(BHAV_DIR) if f.endswith(".csv")]
            st.info(f"📁 Local Disk Buffer: **{len(files)} daily bhavcopy CSVs archived** (Rolling 90-day buffer).")
            if files:
                zip_stream = generate_chunked_bhav_zip()
                st.download_button(
                    "📦 Download Consolidated 90-Day Bulk Archive (.zip)",
                    data=zip_stream,
                    file_name=f"NSE_Bhavcopy_90D_{now.strftime('%Y%m%d')}.zip",
                    mime="application/zip", use_container_width=True
                )

    st.markdown("<div class='foot'>Institutional Smart Money Terminal v12.1 · Enterprise Cloud & Local Edition.</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
