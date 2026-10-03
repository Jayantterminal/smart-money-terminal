"""
ENGINE - data + scoring + 15m signal logic.
Apna purana engine yahan merge karna ho to sirf signal_15m() aur accumulation_scan() badlo.
Daily auto-update:  python engine.py   (Task Scheduler / cron se roz 7 PM chalao)
"""
import io, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd, requests, yfinance as yf

DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)
HDR = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}

SECTORS = {
    "IT": "^CNXIT", "Bank": "^NSEBANK", "Auto": "^CNXAUTO", "Pharma": "^CNXPHARMA",
    "FMCG": "^CNXFMCG", "Metal": "^CNXMETAL", "Energy": "^CNXENERGY",
    "Realty": "^CNXREALTY", "Infra": "^CNXINFRA", "PSU Bank": "^CNXPSUBANK", "Media": "^CNXMEDIA",
}

# ---------------- BHAVCOPY (delivery data) ----------------
def _bhav_url(d):
    return f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"

def update_bhavcopy(days=45):
    """Last `days` calendar days ki bhavcopy download (jo already hai skip)."""
    got = 0
    for i in range(days):
        d = dt.date.today() - dt.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        f = DATA / f"bhav_{d:%Y%m%d}.csv"
        if f.exists():
            continue
        try:
            r = requests.get(_bhav_url(d), headers=HDR, timeout=20)
            if r.status_code == 200 and len(r.content) > 5000:
                f.write_bytes(r.content); got += 1
        except Exception:
            pass
    return got

def load_bhav(n_days=30):
    files = sorted(DATA.glob("bhav_*.csv"))[-n_days:]
    frames = []
    for f in files:
        df = pd.read_csv(f, skipinitialspace=True)
        df.columns = [c.strip() for c in df.columns]
        df = df[df["SERIES"].str.strip() == "EQ"].copy()
        df["DATE"] = pd.to_datetime(f.stem.split("_")[1])
        for c in ["CLOSE_PRICE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "AVG_PRICE",
                  "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER", "TURNOVER_LACS"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        frames.append(df)
    return pd.concat(frames) if frames else pd.DataFrame()

# ---------------- SMART MONEY / ACCUMULATION ----------------
def accumulation_scan(top_n=250):
    """Delivery-based footprint: zyada delivery + price absorb + close > avg price."""
    b = load_bhav()
    if b.empty:
        return pd.DataFrame()
    last = b["DATE"].max()
    liquid = b[b.DATE == last].nlargest(top_n, "TURNOVER_LACS")["SYMBOL"]
    rows = []
    for sym, g in b[b.SYMBOL.isin(liquid)].groupby("SYMBOL"):
        g = g.sort_values("DATE")
        if len(g) < 12:
            continue
        rec, base = g.tail(3), g.iloc[:-3]
        deliv_x = rec.DELIV_PER.mean() / max(base.DELIV_PER.mean(), 1)
        dq_x = rec.DELIV_QTY.mean() / max(base.DELIV_QTY.mean(), 1)
        chg5 = g.CLOSE_PRICE.iloc[-1] / g.CLOSE_PRICE.iloc[-6] * 100 - 100
        above_avg = (rec.CLOSE_PRICE > rec.AVG_PRICE).mean()          # buyers ka control
        up_days = (g.tail(10).CLOSE_PRICE.diff() > 0).mean()
        score = (min(deliv_x, 1.6) / 1.6 * 30 + min(dq_x, 2) / 2 * 25 +
                 above_avg * 20 + up_days * 10 +
                 (15 if -2 <= chg5 <= 6 else 5 if chg5 > 6 else 0))   # absorb zone bonus
        rows.append(dict(Symbol=sym, Close=g.CLOSE_PRICE.iloc[-1], Chg5d=round(chg5, 2),
                         DelivPct=round(rec.DELIV_PER.mean(), 1), DelivX=round(deliv_x, 2),
                         DelivQtyX=round(dq_x, 2), Score=round(score, 1)))
    df = pd.DataFrame(rows).sort_values("Score", ascending=False)
    df["Footprint"] = np.where(df.Score >= 70, "🟢 ACCUMULATION",
                       np.where(df.Score >= 55, "🟡 BUILDING", "⚪ NEUTRAL"))
    return df.reset_index(drop=True)

# ---------------- SECTOR ROTATION (RRG style) ----------------
def sector_rotation():
    tick = list(SECTORS.values()) + ["^NSEI"]
    px = yf.download(tick, period="9mo", interval="1d", progress=False, auto_adjust=True)["Close"].ffill()
    rows = []
    for name, t in SECTORS.items():
        if t not in px or px[t].dropna().empty:
            continue
        rs = px[t] / px["^NSEI"]
        ratio = rs / rs.rolling(50).mean() * 100
        mom = ratio / ratio.shift(10) * 100
        r, m = ratio.iloc[-1], mom.iloc[-1]
        q = ("Leading" if r >= 100 and m >= 100 else "Weakening" if r >= 100 else
             "Improving" if m >= 100 else "Lagging")
        rows.append(dict(Sector=name, RS_Ratio=round(r, 2), RS_Mom=round(m, 2), Quadrant=q,
                         Ret1M=round((px[t].iloc[-1] / px[t].iloc[-22] - 1) * 100, 2)))
    return pd.DataFrame(rows).sort_values("RS_Ratio", ascending=False)

# ---------------- FII / DII ----------------
def fii_dii():
    try:
        s = requests.Session(); s.headers.update(HDR)
        s.get("https://www.nseindia.com", timeout=15)
        r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=15)
        return pd.DataFrame(r.json())
    except Exception:
        return pd.DataFrame()

# ---------------- 15m LIVE SIGNAL ENGINE ----------------
def get_15m(sym, period="5d"):
    df = yf.Ticker(f"{sym}.NS").history(period=period, interval="15m", auto_adjust=True)
    return df[["Open", "High", "Low", "Close", "Volume"]] if not df.empty else df

def signal_15m(df):
    """BUY = EMA9 cross EMA21 upar + price > VWAP + volume spike. SL/Target ATR based."""
    d = df.copy()
    d["ema9"] = d.Close.ewm(span=9, adjust=False).mean()
    d["ema21"] = d.Close.ewm(span=21, adjust=False).mean()
    tp = (d.High + d.Low + d.Close) / 3
    day = d.index.date
    d["vwap"] = (tp * d.Volume).groupby(day).cumsum() / d.Volume.groupby(day).cumsum()
    d["volavg"] = d.Volume.rolling(20).mean()
    d["atr"] = (d.High - d.Low).rolling(14).mean()
    cross = (d.ema9 > d.ema21) & (d.ema9.shift() <= d.ema21.shift())
    d["buy"] = cross & (d.Close > d.vwap) & (d.Volume > 1.2 * d.volavg)
    d["sl"] = d.Close - 1.5 * d.atr
    d["target"] = d.Close + 3 * d.atr
    return d

# ---------------- TRADE TRACKER (SL hit / running / target) ----------------
def track_trades(trades):
    out = []
    for _, t in trades.iterrows():
        try:
            h = yf.Ticker(f"{t.symbol}.NS").history(start=str(t.date), interval="15m", auto_adjust=True)
            if h.empty:
                h = yf.Ticker(f"{t.symbol}.NS").history(start=str(t.date), interval="1d")
            sl_hit = h[h.Low <= t.sl]; tg_hit = h[h.High >= t.target]
            ltp = h.Close.iloc[-1]
            slt = sl_hit.index[0] if len(sl_hit) else None
            tgt = tg_hit.index[0] if len(tg_hit) else None
            if slt is not None and (tgt is None or slt <= tgt):
                status, px = "❌ SL HIT", t.sl
            elif tgt is not None:
                status, px = "✅ TARGET", t.target
            else:
                status, px = "🔵 RUNNING", ltp
            out.append(dict(Symbol=t.symbol, Entry=t.entry, SL=t.sl, Target=t.target, LTP=round(ltp, 2),
                            Status=status, PnL_pct=round((px / t.entry - 1) * 100, 2)))
        except Exception:
            out.append(dict(Symbol=t.symbol, Status="⚠️ data error"))
    return pd.DataFrame(out)

if __name__ == "__main__":
    print("Bhavcopy new files:", update_bhavcopy())
