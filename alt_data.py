"""
alt_data.py - Alternative data (v10)
Bulk/Block deals, delivery value, RS vs REAL Nifty, FII/DII, insider, Telegram.
Fixes over v9:
  - RS vs Nifty used a 1-session-longer window than the stock's own Ret_1M/Ret_3M -> aligned
  - Delivered value NaN'd for stocks with a split/bonus in window (qty x price distorted)
  - FII/DII parsing handles comma-formatted numbers
  - Telegram: lines longer than the limit are hard-split (HTTP 400 otherwise), 429 retry
  - Telegram alert marks wide-range stocks
"""
from __future__ import annotations

import html
import os
import time
from io import StringIO

import numpy as np
import pandas as pd
import requests

import market as M

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120 Safari/537.36"),
    "Accept": "text/csv,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
_SESSION = None
_TG_LIMIT = 3900


def _get_session():
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    s = requests.Session()
    s.headers.update(_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10)
        s.get("https://www.nseindia.com/market-data/securities-lending-and-borrowing", timeout=10)
    except Exception:
        pass
    _SESSION = s
    return s


def _num(x, default=0.0):
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return default


def fetch_bulk_block_deals() -> pd.DataFrame:
    cols = ["Date", "Symbol", "Client", "Buy_Sell", "Qty", "Price", "Value_Cr", "Deal_Type"]
    frames = []
    for url, typ in (("https://nsearchives.nseindia.com/content/equities/bulk.csv", "Bulk"),
                     ("https://nsearchives.nseindia.com/content/equities/block.csv", "Block")):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=20)
            if r.status_code != 200 or len(r.text) < 50:
                continue
            df = pd.read_csv(StringIO(r.text))
            if df.empty:
                continue
            df.columns = [str(c).strip() for c in df.columns]
            cmap = {}
            for c in df.columns:
                lc = c.lower().replace(" ", "").replace(".", "")
                if "date" in lc and "Date" not in cmap.values():
                    cmap[c] = "Date"
                elif lc == "symbol":
                    cmap[c] = "Symbol"
                elif "client" in lc:
                    cmap[c] = "Client"
                elif "buy" in lc:
                    cmap[c] = "Buy_Sell"
                elif "quantity" in lc or "qty" in lc:
                    cmap[c] = "Qty"
                elif "price" in lc or "rate" in lc:
                    cmap[c] = "Price"
            df = df.rename(columns=cmap)
            df["Deal_Type"] = typ
            frames.append(df)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame(columns=cols)
    d = pd.concat(frames, ignore_index=True)
    for c in ("Date", "Symbol", "Client", "Buy_Sell", "Qty", "Price"):
        if c not in d.columns:
            d[c] = None
    d["Symbol"] = d["Symbol"].astype(str).str.strip().str.upper()
    d["Buy_Sell"] = d["Buy_Sell"].astype(str).str.strip().str.upper()
    d["Qty"] = pd.to_numeric(d["Qty"].astype(str).str.replace(",", ""), errors="coerce")
    d["Price"] = pd.to_numeric(d["Price"].astype(str).str.replace(",", ""), errors="coerce")
    d["Value_Cr"] = ((d["Qty"] * d["Price"]) / 1e7).round(3)
    return d[cols]


def deals_date(deals: pd.DataFrame):
    if deals is None or deals.empty:
        return None
    ds = pd.to_datetime(deals["Date"].astype(str).str.strip(), format="%d-%b-%Y", errors="coerce")
    if ds.isna().all():
        ds = pd.to_datetime(deals["Date"], errors="coerce")
    return ds.max() if ds.notna().any() else None


def deals_table(deals, limit=200):
    if deals is None or deals.empty:
        return pd.DataFrame()
    d = deals.copy()
    d["Value_Cr"] = pd.to_numeric(d["Value_Cr"], errors="coerce").round(2)
    return d.sort_values("Value_Cr", ascending=False).head(limit)


def enrich_screener(scr, hist, deals, nifty=None):
    if scr is None or scr.empty:
        return scr
    out = scr.copy()
    stats = dict(getattr(scr, "attrs", {}).get("stats", {}))
    sessions = sorted(hist.Date.unique()) if hist is not None and not hist.empty else []

    # delivered value (qty x close, so skip stocks whose qty/price were split-adjusted)
    try:
        if len(sessions) >= 30:
            last21, prev42 = sessions[-21:], sessions[-63:-21]
            h = hist[["Symbol", "Date", "DELIV_QTY", "CLOSE_PRICE"]].copy()
            h["_v"] = h.DELIV_QTY * h.CLOSE_PRICE / 1e7
            v1 = h[h.Date.isin(last21)].groupby("Symbol")["_v"].sum().rename("Deliv_Val_1M_Cr")
            v3 = h[h.Date.isin(prev42)].groupby("Symbol")["_v"].sum().rename("Deliv_Val_3M_Cr")
            out = out.merge(v1, on="Symbol", how="left").merge(v3, on="Symbol", how="left")
            out["Deliv_Val_X"] = ((out.Deliv_Val_1M_Cr / len(last21))
                                  / (out.Deliv_Val_3M_Cr / max(1, len(prev42)))).replace([np.inf, -np.inf], np.nan)
            if "Has_Split_Adjust" in out.columns:
                bad = out.Has_Split_Adjust.fillna(False).astype(bool)
                for c in ("Deliv_Val_1M_Cr", "Deliv_Val_3M_Cr", "Deliv_Val_X"):
                    out.loc[bad, c] = np.nan
            for c in ("Deliv_Val_1M_Cr", "Deliv_Val_3M_Cr", "Deliv_Val_X"):
                out[c] = out[c].round(2)
    except Exception:
        pass

    # RS vs real Nifty - SAME windows as engine's Ret_1M (c[-21]) and Ret_3M (c[-63])
    try:
        if nifty is not None and not nifty.empty and len(sessions) >= 63:
            n1 = M.return_between(nifty, sessions[-21], sessions[-1])
            n3 = M.return_between(nifty, sessions[-63], sessions[-1])
            out["Nifty_1M"] = round(n1, 2) if np.isfinite(n1) else np.nan
            out["Nifty_3M"] = round(n3, 2) if np.isfinite(n3) else np.nan
            out["RS_1M"] = (out.Ret_1M - n1).round(2) if np.isfinite(n1) else np.nan
            out["RS_3M"] = (out.Ret_3M - n3).round(2) if np.isfinite(n3) else np.nan
    except Exception:
        pass

    # bulk / block deals
    out["Bulk_Buy_Cr"], out["Bulk_Sell_Cr"], out["Bulk_Net_Cr"] = 0.0, 0.0, 0.0
    out["Deals_Today"], out["Bulk_Flag"] = 0, "-"
    try:
        dd = deals_date(deals)
        asof = pd.Timestamp(sessions[-1]) if sessions else None
        stale = bool(dd is not None and asof is not None and dd.normalize() != asof.normalize())
        stats["deals_stale"] = stale
        stats["deals_date"] = str(dd.date()) if dd is not None else None
        if deals is not None and not deals.empty and not stale:
            d = deals.copy()
            d["Value_Cr"] = pd.to_numeric(d["Value_Cr"], errors="coerce").fillna(0)
            d["_buy"] = d["Buy_Sell"].astype(str).str.startswith("B")
            buy = d[d["_buy"]].groupby("Symbol")["Value_Cr"].sum()
            sell = d[~d["_buy"]].groupby("Symbol")["Value_Cr"].sum()
            cnt = d.groupby("Symbol").size()
            out["Bulk_Buy_Cr"] = out.Symbol.map(buy).fillna(0.0)
            out["Bulk_Sell_Cr"] = out.Symbol.map(sell).fillna(0.0)
            out["Deals_Today"] = out.Symbol.map(cnt).fillna(0).astype(int)
            out["Bulk_Net_Cr"] = (out.Bulk_Buy_Cr - out.Bulk_Sell_Cr).round(2)
            out["Bulk_Flag"] = np.where(out.Bulk_Net_Cr > 0.01, "🟢 Buy",
                                        np.where(out.Bulk_Net_Cr < -0.01, "🔴 Sell", "-"))
    except Exception:
        pass
    out.attrs["stats"] = stats
    return out


def fetch_fiidii():
    try:
        r = _get_session().get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=15)
        if r.status_code != 200:
            return None
        out = {"date": None, "fii_buy": 0.0, "fii_sell": 0.0, "fii_net": 0.0,
               "dii_buy": 0.0, "dii_sell": 0.0, "dii_net": 0.0}
        for row in r.json():
            cat = str(row.get("category", "")).upper()
            buy, sell, net = _num(row.get("buyValue")), _num(row.get("sellValue")), _num(row.get("netValue"))
            out["date"] = row.get("date", out["date"])
            if "FII" in cat or "FPI" in cat:
                out.update(fii_buy=buy, fii_sell=sell, fii_net=net)
            elif "DII" in cat:
                out.update(dii_buy=buy, dii_sell=sell, dii_net=net)
        return out if out["date"] else None
    except Exception:
        return None


def fetch_insider_trades(days_back: int = 7) -> pd.DataFrame:
    cols = ["Date", "Symbol", "Person", "Category", "Buy_Sell", "Qty", "Value_Cr", "Mode"]
    try:
        to_d = pd.Timestamp.today()
        url = ("https://www.nseindia.com/api/corporates-pit?index=equities"
               f"&from_date={(to_d - pd.Timedelta(days=days_back)):%d-%m-%Y}&to_date={to_d:%d-%m-%Y}")
        r = _get_session().get(url, timeout=20)
        if r.status_code != 200:
            return pd.DataFrame(columns=cols)
        rows = []
        for x in (r.json().get("data") or []):
            try:
                val = pd.to_numeric(x.get("secVal") or x.get("value") or 0, errors="coerce")
                rows.append([x.get("date") or x.get("intimDt") or "",
                             str(x.get("symbol", "")).strip().upper(),
                             str(x.get("acqName") or x.get("personName") or ""),
                             str(x.get("personCategory") or ""),
                             str(x.get("tdpTransactionType") or x.get("buyOrSell") or "").upper(),
                             pd.to_numeric(x.get("secAcq") or x.get("noOfShares") or 0, errors="coerce"),
                             round(float(val) / 1e7, 3) if pd.notna(val) else 0.0,
                             x.get("acqMode") or x.get("modeOfAcq") or ""])
            except Exception:
                continue
        return pd.DataFrame(rows, columns=cols)
    except Exception:
        return pd.DataFrame(columns=cols)


def telegram_creds_from_env():
    return os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")


def _split_for_telegram(text, limit=_TG_LIMIT):
    """Split at newlines; a single over-long line is hard-split too."""
    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:                 # pathological long line
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = (current + "\n" + line) if current else line
    if current:
        chunks.append(current)
    return chunks


def send_telegram_message(token, chat_id, text):
    """HTML-safe chunking (splits at newlines) + one retry on HTTP 429."""
    if not token or not chat_id:
        return False, "Token ya Chat ID missing."
    try:
        for chunk in _split_for_telegram(text):
            for attempt in range(2):
                r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                  data={"chat_id": str(chat_id), "text": chunk,
                                        "parse_mode": "HTML", "disable_web_page_preview": True},
                                  timeout=15)
                if r.status_code == 429 and attempt == 0:
                    try:
                        wait = int(r.json().get("parameters", {}).get("retry_after", 2))
                    except Exception:
                        wait = 2
                    time.sleep(min(wait, 10))
                    continue
                break
            if not (r.status_code == 200 and r.json().get("ok")):
                return False, f"HTTP {r.status_code}: {r.text[:200]}"
        return True, "Sent."
    except Exception as e:
        return False, f"Error: {e}"


def format_telegram_alert(scr, deals, breadth, asof_date, top_n=10, nifty=None, stale_deals=False):
    e = html.escape
    lines = [f"<b>📈 Smart Money Terminal — {e(str(asof_date))}</b>", ""]
    if breadth:
        lines.append(f"<b>Market:</b> {e(str(breadth.get('nifty_trend', '-')))}")
        lines.append(f"Breadth (>50DMA): {breadth.get('breadth_pct_50', 0)}%  |  "
                     f"Advances: {breadth.get('ad_ratio', 0)}%")
        if breadth.get("nifty_source"):
            lines.append(f"Nifty source: {e(str(breadth['nifty_source']))}")
        lines.append("")
    if scr is not None and not scr.empty:
        d = scr[scr.Signal.isin(["Strong Accumulation", "Accumulation"])].sort_values("Score", ascending=False)
        d = d[d.Stage != "Extended (already ran)"].head(top_n)
        if not d.empty:
            lines.append(f"<b>Top {len(d)} accumulation picks (not extended):</b>")
            for r in d.itertuples():
                tag = "" if r.Fresh in ("None", None) else f" [{e(str(r.Fresh))}]"
                wide = " ⚠️wide" if getattr(r, "Wide_Range", False) else ""
                lines.append(f"• <b>{e(r.Symbol)}</b> ₹{r.Price:,.2f}  Score {int(r.Score)}  "
                             f"Entry ₹{r.Entry:,.2f}  SL ₹{r.SL:,.2f}  T1 ₹{r.T1:,.2f}{tag}{wide}")
        fr = scr[scr.Fresh == "Spike today"].head(5)
        if not fr.empty:
            lines += ["", "<b>🔥 Spike today:</b> " + ", ".join(e(s) for s in fr.Symbol)]
    if deals is not None and not deals.empty and not stale_deals:
        buys = deals[deals.Buy_Sell.astype(str).str.startswith("B")].nlargest(5, "Value_Cr")
        if not buys.empty:
            lines += ["", "<b>Top bulk/block BUYs:</b>"]
            for r in buys.itertuples():
                lines.append(f"• {e(r.Symbol)}: ₹{r.Value_Cr:.1f} Cr ({r.Deal_Type})")
    elif stale_deals:
        lines += ["", "<i>Bulk/block data is stale (NSE not updated yet).</i>"]
    lines += ["", "<i>Analysis tool only. Not investment advice.</i>"]
    return "\n".join(lines)
