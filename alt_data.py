"""
alt_data.py - Alternative data (v3)
Bulk/Block deals, delivery value, RS vs Nifty, FII/DII, Insider trades, Telegram alerts.
"""
import numpy as np
import pandas as pd
import requests
from io import StringIO

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120 Safari/537.36"),
    "Accept": "text/csv,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

_SESSION = None


def _get_session():
    """Maintain NSE session with cookies for API access."""
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


# ============ BULK + BLOCK DEALS ============ #
def fetch_bulk_block_deals():
    frames = []
    for url, typ in [
        ("https://nsearchives.nseindia.com/content/equities/bulk.csv", "Bulk"),
        ("https://nsearchives.nseindia.com/content/equities/block.csv", "Block"),
    ]:
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
                if "date" in lc:                     cmap[c] = "Date"
                elif lc == "symbol":                 cmap[c] = "Symbol"
                elif "client" in lc:                 cmap[c] = "Client"
                elif "buy" in lc and "sell" in lc:   cmap[c] = "Buy_Sell"
                elif lc.startswith("buy"):           cmap[c] = "Buy_Sell"
                elif "quantity" in lc or "qty" in lc: cmap[c] = "Qty"
                elif "price" in lc or "rate" in lc:  cmap[c] = "Price"
            df = df.rename(columns=cmap)
            df["Deal_Type"] = typ
            frames.append(df)
        except Exception:
            continue

    cols = ["Date", "Symbol", "Client", "Buy_Sell", "Qty", "Price", "Value_Cr", "Deal_Type"]
    if not frames:
        return pd.DataFrame(columns=cols)

    d = pd.concat(frames, ignore_index=True)
    for c in ["Date", "Symbol", "Client", "Buy_Sell", "Qty", "Price"]:
        if c not in d.columns:
            d[c] = None

    d["Symbol"]   = d["Symbol"].astype(str).str.strip().str.upper()
    d["Buy_Sell"] = d["Buy_Sell"].astype(str).str.strip().str.upper()
    d["Qty"]      = pd.to_numeric(d["Qty"], errors="coerce")
    d["Price"]    = pd.to_numeric(d["Price"].astype(str).str.replace(",", ""), errors="coerce")
    d["Value_Cr"] = ((d["Qty"] * d["Price"]) / 1e7).round(3)
    return d[cols]


# ============ NIFTY PROXY ============ #
def _nifty_from_hist(hist):
    if hist is None or hist.empty or "Symbol" not in hist.columns:
        return pd.DataFrame()
    syms = hist["Symbol"].astype(str).str.upper()
    for s in ["NIFTYBEES", "NIFTYBEES-EQ", "SETFNIF50", "SETFNIFBK"]:
        d = hist[syms == s]
        if not d.empty:
            return (d[["Date", "CLOSE_PRICE"]].rename(columns={"CLOSE_PRICE": "Nifty"})
                    .sort_values("Date").reset_index(drop=True))
    return pd.DataFrame()


# ============ MAIN ENRICHMENT ============ #
def enrich_screener(scr, hist, deals):
    if scr is None or scr.empty:
        return scr
    out = scr.copy()

    # Delivery value in ₹ Cr
    try:
        if hist is not None and not hist.empty:
            need = {"Symbol", "Date", "DELIV_QTY", "CLOSE_PRICE"}
            if need.issubset(hist.columns):
                h = hist[list(need)].copy()
                h["Date"] = pd.to_datetime(h["Date"], errors="coerce")
                h["_v"] = (pd.to_numeric(h["DELIV_QTY"], errors="coerce")
                           * pd.to_numeric(h["CLOSE_PRICE"], errors="coerce")) / 1e7
                h = h.dropna(subset=["Symbol", "Date", "_v"]).sort_values(["Symbol", "Date"])

                def _agg(g):
                    v = g["_v"].values; n = len(v)
                    m1 = v[-21:].sum() if n >= 21 else v.sum()
                    m3 = v[-63:-21].sum() if n >= 63 else (v[:-21].sum() if n > 21 else 0.0)
                    return pd.Series({"Deliv_Val_1M_Cr": round(float(m1), 2),
                                      "Deliv_Val_3M_Cr": round(float(m3), 2)})
                agg = h.groupby("Symbol", dropna=False).apply(_agg).reset_index()
                out = out.merge(agg, on="Symbol", how="left")
    except Exception:
        pass

    # Relative strength vs Nifty
    try:
        nifty = _nifty_from_hist(hist)
        if not nifty.empty and hist is not None and "CLOSE_PRICE" in hist.columns:
            nc = nifty["Nifty"].astype(float).values
            n_ret = (nc[-1] / nc[-21] - 1) * 100 if len(nc) >= 21 else np.nan
            hh = hist[["Symbol", "Date", "CLOSE_PRICE"]].copy()
            hh["Date"] = pd.to_datetime(hh["Date"], errors="coerce")
            hh = hh.dropna(subset=["Symbol", "Date", "CLOSE_PRICE"]).sort_values(["Symbol", "Date"])

            def _ret(g):
                c = pd.to_numeric(g["CLOSE_PRICE"], errors="coerce").values
                if len(c) >= 21 and c[-21] > 0:
                    return (c[-1] / c[-21] - 1) * 100
                return np.nan

            rets = hh.groupby("Symbol").apply(_ret).rename("Ret_1M_px").reset_index()
            out = out.merge(rets, on="Symbol", how="left")
            out["RS_1M"] = (out["Ret_1M_px"] - n_ret).round(2)
            out = out.drop(columns=["Ret_1M_px"], errors="ignore")
            out["Nifty_1M"] = round(float(n_ret), 2) if not np.isnan(n_ret) else np.nan
    except Exception:
        pass

    # Bulk/Block summary
    try:
        if deals is not None and not deals.empty and "Symbol" in deals.columns:
            d = deals.copy()
            d["Symbol"]   = d["Symbol"].astype(str).str.strip().str.upper()
            d["Buy_Sell"] = d["Buy_Sell"].astype(str).str.strip().str.upper()
            d["Value_Cr"] = pd.to_numeric(d["Value_Cr"], errors="coerce").fillna(0)
            d["_buy"]     = d["Buy_Sell"].str.startswith("B")
            buy  = d[d["_buy"]].groupby("Symbol")["Value_Cr"].sum().rename("Bulk_Buy_Cr")
            sell = d[~d["_buy"]].groupby("Symbol")["Value_Cr"].sum().rename("Bulk_Sell_Cr")
            cnt  = d.groupby("Symbol").size().rename("Deals_Today")
            out = out.merge(buy,  on="Symbol", how="left")
            out = out.merge(sell, on="Symbol", how="left")
            out = out.merge(cnt,  on="Symbol", how="left")
            for c in ["Bulk_Buy_Cr", "Bulk_Sell_Cr", "Deals_Today"]:
                if c in out.columns:
                    out[c] = out[c].fillna(0)
            out["Bulk_Net_Cr"] = (out.get("Bulk_Buy_Cr", 0) - out.get("Bulk_Sell_Cr", 0)).round(2)
            out["Bulk_Flag"] = np.where(
                out["Bulk_Net_Cr"] >  0.01, "🟢 Buy",
                np.where(out["Bulk_Net_Cr"] < -0.01, "🔴 Sell", "-"))
        else:
            out["Bulk_Buy_Cr"]  = 0.0
            out["Bulk_Sell_Cr"] = 0.0
            out["Bulk_Net_Cr"]  = 0.0
            out["Deals_Today"]  = 0
            out["Bulk_Flag"]    = "-"
    except Exception:
        out["Bulk_Flag"] = "-"

    return out


def deals_table(deals, limit=200):
    if deals is None or deals.empty:
        return pd.DataFrame()
    d = deals.copy()
    d["Value_Cr"] = pd.to_numeric(d["Value_Cr"], errors="coerce").round(2)
    return d.sort_values("Value_Cr", ascending=False).head(limit)


# ============ FII / DII DAILY FLOW ============ #
def fetch_fiidii():
    """NSE daily FII/DII cash market flow. Returns dict or None."""
    try:
        s = _get_session()
        r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        out = {"date": None, "fii_buy": 0.0, "fii_sell": 0.0, "fii_net": 0.0,
               "dii_buy": 0.0, "dii_sell": 0.0, "dii_net": 0.0}
        for row in data:
            cat = str(row.get("category", "")).upper()
            try:
                buy = float(row.get("buyValue", 0) or 0)
                sell = float(row.get("sellValue", 0) or 0)
                net = float(row.get("netValue", 0) or 0)
            except Exception:
                continue
            out["date"] = row.get("date", out["date"])
            if "FII" in cat or "FPI" in cat:
                out["fii_buy"] = buy; out["fii_sell"] = sell; out["fii_net"] = net
            elif "DII" in cat:
                out["dii_buy"] = buy; out["dii_sell"] = sell; out["dii_net"] = net
        return out if out["date"] else None
    except Exception:
        return None


# ============ INSIDER / PROMOTER TRADES ============ #
def fetch_insider_trades(days_back=7):
    """NSE insider trading disclosures. Returns DataFrame."""
    cols = ["Date", "Symbol", "Person", "Category", "Buy_Sell", "Qty", "Value_Cr", "Mode"]
    try:
        s = _get_session()
        to_d = pd.Timestamp.today()
        from_d = to_d - pd.Timedelta(days=days_back)
        url = ("https://www.nseindia.com/api/corporates-pit?index=equities"
               f"&from_date={from_d:%d-%m-%Y}&to_date={to_d:%d-%m-%Y}")
        r = s.get(url, timeout=20)
        if r.status_code != 200:
            return pd.DataFrame(columns=cols)
        js = r.json()
        rows = js.get("data", []) or []
        if not rows:
            return pd.DataFrame(columns=cols)
        out_rows = []
        for x in rows:
            try:
                sym = str(x.get("symbol","")).strip().upper()
                person = str(x.get("personName") or x.get("acquirerName") or "")
                cat = str(x.get("personCategory") or "")
                btype = str(x.get("tdpTransactionType") or x.get("buyOrSell") or "").upper()
                qty = pd.to_numeric(x.get("secAcq") or x.get("noOfShares") or 0, errors="coerce")
                val = pd.to_numeric(x.get("secVal") or x.get("value") or 0, errors="coerce")
                dt = x.get("date") or x.get("intimDate") or ""
                mode = x.get("acqMode") or x.get("modeOfAcq") or ""
                out_rows.append([dt, sym, person, cat, btype, qty,
                                 round(float(val)/1e7, 3) if val else 0.0, mode])
            except Exception:
                continue
        return pd.DataFrame(out_rows, columns=cols)
    except Exception:
        return pd.DataFrame(columns=cols)


# ============ TELEGRAM ALERTS ============ #
def send_telegram_message(token: str, chat_id: str, text: str):
    """Send message to Telegram bot. Returns (ok, info)."""
    if not token or not chat_id:
        return False, "Token ya Chat ID missing."
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": str(chat_id), "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200 and r.json().get("ok"):
            return True, "Sent."
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"Error: {e}"


def format_telegram_alert(scr, deals, breadth, asof_date, top_n=10):
    """Format a compact alert message for Telegram."""
    lines = [f"<b>📈 Smart Money Terminal — {asof_date}</b>", ""]
    if breadth:
        lines.append(f"<b>Market:</b> {breadth.get('nifty_trend','-')}")
        lines.append(f"Breadth (above 50DMA): {breadth.get('breadth_pct_50',0)}%  |  "
                     f"A/D: {breadth.get('ad_ratio',0)}%")
        lines.append("")
    if scr is not None and not scr.empty:
        d = scr.copy()
        if "Signal" in d.columns:
            d = d[d.Signal.isin(["Strong Accumulation", "Accumulation"])]
        if "Score" in d.columns:
            d = d.sort_values("Score", ascending=False)
        d = d.head(top_n)
        if not d.empty:
            lines.append(f"<b>Top {len(d)} accumulation picks:</b>")
            for _, r in d.iterrows():
                fresh = r.get("Fresh","-")
                fresh_tag = "" if fresh in ("None", None) else f" [{fresh}]"
                lines.append(
                    f"• <b>{r.Symbol}</b> ₹{r.Price}  Score {int(r.Score)}  "
                    f"Entry ₹{r.Entry}  SL ₹{r.SL}  T1 ₹{r.T1}{fresh_tag}")
    if deals is not None and not deals.empty:
        d2 = deals.copy()
        d2["Buy_Sell"] = d2["Buy_Sell"].astype(str).str.upper()
        buys = d2[d2.Buy_Sell.str.startswith("B")].nlargest(5, "Value_Cr")
        if not buys.empty:
            lines.append("")
            lines.append("<b>Top bulk/block BUYs today:</b>")
            for _, r in buys.iterrows():
                lines.append(f"• {r.Symbol}: ₹{r.Value_Cr:.1f} Cr ({r.Deal_Type})")
    lines.append("")
    lines.append("<i>Analysis tool only. Not investment advice.</i>")
    return "\n".join(lines)
