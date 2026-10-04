"""
alt_data.py - Alternative data for Smart Money Terminal
Bulk/Block deals, delivery value ₹ Cr, relative strength vs Nifty. All automatic.
"""
import numpy as np
import pandas as pd
import requests
from io import StringIO

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120 Safari/537.36"),
    "Accept": "text/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


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


def _nifty_from_hist(hist):
    if hist is None or hist.empty or "Symbol" not in hist.columns:
        return pd.DataFrame()
    syms = hist["Symbol"].astype(str).str.upper()
    for s in ["NIFTYBEES", "NIFTYBEES-EQ", "SETFNIF50", "SETFNIFBK"]:
        d = hist[syms == s]
        if not d.empty:
            return (d[["Date", "CLOSE_PRICE"]]
                    .rename(columns={"CLOSE_PRICE": "Nifty"})
                    .sort_values("Date").reset_index(drop=True))
    return pd.DataFrame()


def enrich_screener(scr: pd.DataFrame, hist: pd.DataFrame, deals: pd.DataFrame):
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

    # Bulk / Block summary
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


def deals_table(deals: pd.DataFrame, limit: int = 200):
    if deals is None or deals.empty:
        return pd.DataFrame()
    d = deals.copy()
    d["Value_Cr"] = pd.to_numeric(d["Value_Cr"], errors="coerce").round(2)
    d = d.sort_values("Value_Cr", ascending=False).head(limit)
    return d
