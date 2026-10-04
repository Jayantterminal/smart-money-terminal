"""
market.py - Real index data (Yahoo Finance) for Nifty trend, 20/50/200 DMA and relative strength.
Replaces the old 'Nifty proxy' (median stock price), which was meaningless.
v10: retry on Yahoo failure; snapshot() can be cut at the bhavcopy as-of date so the
     Nifty trend and the stock data refer to the SAME session.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd


def fetch_index(symbol: str = "^NSEI", period: str = "2y", retries: int = 2) -> pd.DataFrame:
    """Daily closes -> DataFrame[Date, Close]. Empty frame if Yahoo is unreachable."""
    empty = pd.DataFrame(columns=["Date", "Close"])
    try:
        import yfinance as yf
    except Exception:
        return empty
    for attempt in range(retries):
        try:
            df = yf.download(symbol, period=period, interval="1d", auto_adjust=True,
                             progress=False, threads=False)
            if df is None or df.empty:
                time.sleep(1.5)
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            out = df[["Close"]].dropna().reset_index()
            out.columns = ["Date", "Close"]
            out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None).dt.normalize()
            return out.sort_values("Date").reset_index(drop=True)
        except Exception:
            time.sleep(1.5)
    return empty


def snapshot(df: pd.DataFrame, vix: pd.DataFrame | None = None, asof=None) -> dict:
    """Trend summary of an index. {} when data is missing.
    asof: ignore bars after this date (keeps Nifty aligned with EOD bhavcopy data)."""
    if df is not None and not df.empty and asof is not None:
        df = df[pd.to_datetime(df["Date"]) <= pd.Timestamp(asof)]
    if df is None or df.empty or len(df) < 25:
        return {}
    c = df["Close"].astype(float).values
    n = len(c)
    out = {"price": round(float(c[-1]), 2), "asof": df["Date"].iloc[-1],
           "chg_1d": round((c[-1] / c[-2] - 1) * 100, 2)}
    for k, name in ((5, "ret_1w"), (21, "ret_1m"), (63, "ret_3m")):
        out[name] = round((c[-1] / c[-1 - k] - 1) * 100, 2) if n > k else None
    for w in (20, 50, 200):
        out[f"dma{w}"] = round(float(c[-w:].mean()), 2) if n >= w else None
    p = c[-1]
    a50 = out["dma50"] is not None and p > out["dma50"]
    if out["dma200"] is not None:
        a200 = p > out["dma200"]
        out["dist_200"] = round((p / out["dma200"] - 1) * 100, 2)
        if a200 and a50:
            out["trend"] = "🟢 Bullish (above 50 & 200 DMA)"
        elif a200:
            out["trend"] = "🟡 Cautious (above 200, below 50)"
        elif a50:
            out["trend"] = "🟡 Recovering (above 50, below 200)"
        else:
            out["trend"] = "🔴 Bearish (below 50 & 200 DMA)"
    else:
        out["dist_200"] = None
        out["trend"] = "🟢 Above 50 DMA" if a50 else "🔴 Below 50 DMA"
    hi = float(c[-252:].max())
    out["from_52w_high"] = round((p / hi - 1) * 100, 2)
    if vix is not None and not vix.empty:
        out["vix"] = round(float(vix["Close"].iloc[-1]), 2)
    return out


def return_between(df: pd.DataFrame, d0, d1) -> float:
    """Index % return between two dates (ffill on holidays). NaN if unavailable."""
    if df is None or df.empty:
        return float("nan")
    s = df.set_index("Date")["Close"].astype(float)
    try:
        a = s.reindex([pd.Timestamp(d0)], method="ffill").iloc[0]
        b = s.reindex([pd.Timestamp(d1)], method="ffill").iloc[0]
        return float((b / a - 1) * 100) if pd.notna(a) and pd.notna(b) and a > 0 else float("nan")
    except Exception:
        return float("nan")
