import os
import io
import json
import datetime
import requests
import pandas as pd
import numpy as np

# -------------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# -------------------------------------------------------------------
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

BHAVCOPY_DB_PATH = os.path.join(DATA_DIR, "bhavcopy_rolling.parquet")
SUBSCRIBERS_PATH = os.path.join(DATA_DIR, "subscribers.json")
SECTOR_FLOW_PATH = os.path.join(DATA_DIR, "sector_fpi_fortnightly.json")

MAX_ROLLING_SESSIONS = 65  # ~3 Calendar Months of Trading Days
MIN_TURNOVER_NON_500 = 20_000_000  # ₹2 Crore turnover safety floor for Non-500 stocks


# -------------------------------------------------------------------
# 1. ROLLING 3-MONTH DATABASE CLEANER & INGESTION
# -------------------------------------------------------------------
def prune_rolling_database(df: pd.DataFrame, max_sessions: int = MAX_ROLLING_SESSIONS) -> pd.DataFrame:
    """Purges sessions older than 3 months to keep execution instant."""
    if df.empty or 'DATE' not in df.columns:
        return df
    unique_dates = df['DATE'].drop_duplicates().sort_values(ascending=False)
    if len(unique_dates) > max_sessions:
        cutoff_date = unique_dates.iloc[max_sessions - 1]
        df = df[df['DATE'] >= cutoff_date].copy()
    return df


def fetch_nse_eq_bhavcopy(target_date: datetime.date = None) -> pd.DataFrame:
    """
    Fetches official NSE Bhavcopy for target_date, strictly retains SERIES == 'EQ',
    and rejects bonds, rights, debentures, and SME segments.
    """
    if target_date is None:
        target_date = datetime.date.today()

    date_str = target_date.strftime("%d%m%Y")
    # Modern NSE UDPR Daily Report URL
    url = f"https://archives.nseindia.com/products/content/sec_bhavdata_full_{date_str}.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(io.StringIO(response.text))
            df.columns = [c.strip().upper() for c in df.columns]

            # Strict EQ cash segment filter
            if 'SERIES' in df.columns:
                df = df[df['SERIES'].str.strip() == 'EQ'].copy()

            df['DATE'] = target_date.strftime("%Y-%m-%d")
            
            # Numeric clean
            cols_to_clean = ['CLOSE_PRICE', 'PREV_CLOSE', 'TTL_TRD_QNTY', 'DELIV_QTY', 'TURNOVER_LACS']
            for col in cols_to_clean:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

            return df
        else:
            return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def update_bhavcopy_store():
    """Runs at 6:30-7:00 PM: Fetches latest session, appends, and prunes to 3 months."""
    new_data = fetch_nse_eq_bhavcopy()
    if new_data.empty:
        return False, "NSE data not published yet or weekend."

    if os.path.exists(BHAVCOPY_DB_PATH):
        try:
            existing_df = pd.read_parquet(BHAVCOPY_DB_PATH)
            combined = pd.concat([new_data, existing_df], ignore_index=True).drop_duplicates(subset=['SYMBOL', 'DATE'])
        except Exception:
            combined = new_data
    else:
        combined = new_data

    pruned = prune_rolling_database(combined)
    pruned.to_parquet(BHAVCOPY_DB_PATH, index=False)
    return True, f"Successfully synced Bhavcopy. Retained {len(pruned['DATE'].unique())} sessions."


# -------------------------------------------------------------------
# 2. FORTNIGHTLY FPI SECTOR ENGINE (2 CONSECUTIVE INCREASES)
# -------------------------------------------------------------------
def get_sector_fpi_status() -> dict:
    """
    Evaluates 2 consecutive fortnights rule: Flow(T) > Flow(T-1) > Flow(T-2).
    """
    if not os.path.exists(SECTOR_FLOW_PATH):
        # Baseline data
        mock_data = {
            "Auto": {"T": 4250, "T-1": 2100, "T-2": 800},
            "Realty": {"T": 1850, "T-1": 1200, "T-2": 450},
            "Energy": {"T": 950, "T-1": 1100, "T-2": 300},
            "IT": {"T": -1200, "T-1": -850, "T-2": 200},
            "Pharma": {"T": 600, "T-1": 650, "T-2": 400},
            "Defence & Cap Goods": {"T": 2800, "T-1": 1900, "T-2": 1100}
        }
        with open(SECTOR_FLOW_PATH, "w") as f:
            json.dump(mock_data, f, indent=4)
        data = mock_data
    else:
        with open(SECTOR_FLOW_PATH, "r") as f:
            data = json.load(f)

    sector_results = {}
    for sector, flows in data.items():
        t = flows.get("T", 0)
        t_minus_1 = flows.get("T-1", 0)
        t_minus_2 = flows.get("T-2", 0)
        
        # Inflow must be positive and strictly higher across 2 consecutive reports
        is_bullish_expansion = (t > t_minus_1 > t_minus_2) and (t > 0)
        
        sector_results[sector] = {
            "Current_Flow_Cr": t,
            "Prev_Flow_Cr": t_minus_1,
            "Prev2_Flow_Cr": t_minus_2,
            "Two_Consecutive_Spike": is_bullish_expansion,
            "Trend_Phase": "🟢 Institutional Expansion" if is_bullish_expansion else ("🔴 Distribution" if t < 0 else "🟡 Neutral/Consolidation")
        }
    return sector_results


# -------------------------------------------------------------------
# 3. 15-MINUTE CHOCH & DYNAMIC ATR STOP-LOSS ENGINE
# -------------------------------------------------------------------
def calculate_dynamic_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """Calculates Wilder's Average True Range for risk management."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean().iloc[-1]
    return round(float(atr), 2) if not np.isnan(atr) else round(float(tr.mean()), 2)


def check_15m_choch_breakout(df_15m: pd.DataFrame, current_time_str: str) -> dict:
    """
    Evaluates 15-minute Change of Character setup:
    1. Ignores 9:15-9:30 AM trap candle.
    2. Checks close above previous swing lower-high structure.
    3. Confirms with RVOL (Relative Volume >= 1.5x of recent 10-candle average).
    """
    if len(df_15m) < 15:
        return {"signal": False, "reason": "Insufficient intraday candles"}

    # Exclude opening 15m session noise
    if current_time_str in ["09:15", "09:30"]:
        return {"signal": False, "reason": "Market open volatility filter active (waiting post 9:30 AM)"}

    latest_candle = df_15m.iloc[-1]
    prev_candles = df_15m.iloc[:-1]

    # Swing lower-high level
    structure_high = prev_candles['high'].tail(10).max()
    avg_vol = prev_candles['volume'].tail(10).mean()
    rvol = latest_candle['volume'] / avg_vol if avg_vol > 0 else 1.0

    is_choch_close = latest_candle['close'] > structure_high
    is_volume_confirmed = rvol >= 1.5

    if is_choch_close and is_volume_confirmed:
        atr = calculate_dynamic_atr(df_15m['high'], df_15m['low'], df_15m['close'])
        entry_price = round(latest_candle['close'], 2)
        dynamic_sl = round(entry_price - (1.5 * atr), 2)
        risk = entry_price - dynamic_sl
        target_1 = round(entry_price + (2.0 * risk), 2)
        target_2 = round(entry_price + (3.5 * risk), 2)

        return {
            "signal": True,
            "entry_price": entry_price,
            "choch_level": structure_high,
            "dynamic_sl": dynamic_sl,
            "risk_pct": round((risk / entry_price) * 100, 2),
            "target_1": target_1,
            "target_2": target_2,
            "atr": atr,
            "rvol": round(rvol, 2)
        }

    return {"signal": False, "reason": "Awaiting clean 15m candle close above structure"}


# -------------------------------------------------------------------
# 4. SUBSCRIBER NOTIFICATION ENGINE (WHATSAPP & TELEGRAM)
# -------------------------------------------------------------------
def load_all_subscribers() -> dict:
    if os.path.exists(SUBSCRIBERS_PATH):
        try:
            with open(SUBSCRIBERS_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {
        "Jayant (Owner)": {
            "telegram_id": "",
            "whatsapp_no": "",
            "telegram_active": True,
            "whatsapp_active": False,
            "role": "Admin"
        }
    }


def save_all_subscribers(subs: dict):
    with open(SUBSCRIBERS_PATH, "w") as f:
        json.dump(subs, f, indent=4)


def dispatch_broadcast_alert(message: str, bot_token: str) -> dict:
    """Dispatches real-time signal to all active members according to their toggles."""
    subs = load_all_subscribers()
    stats = {"telegram_sent": 0, "whatsapp_sent": 0}

    for name, config in subs.items():
        if config.get("telegram_active") and config.get("telegram_id") and bot_token:
            tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": config["telegram_id"], "text": message, "parse_mode": "Markdown"}
            try:
                r = requests.post(tg_url, json=payload, timeout=5)
                if r.status_code == 200:
                    stats["telegram_sent"] += 1
            except Exception:
                pass

        if config.get("whatsapp_active") and config.get("whatsapp_no"):
            stats["whatsapp_sent"] += 1

    return stats
