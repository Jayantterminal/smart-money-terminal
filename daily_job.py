"""
daily_job.py - headless daily run (GitHub Actions / cron / manual)
v11 fixes:
  - re-entry stats computed BEFORE logging today's signals (and engine ignores same-day rows anyway)
  - Nifty snapshot cut at bhavcopy as-of date
  - deals-stale flag read before the screener frame is rebuilt
  - network helpers wrapped so one failing source can't kill the job
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import pandas as pd

import alt_data as A
import engine as E
import market as M

DATA = E.DATA_DIR
MIN_TURNOVER_CR = 5.0  # illiquid stocks filter


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    args = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)

    hist, info = E.fetch_history(65)
    if hist.empty:
        print("NSE data nahi mila:", info)
        return 1
    asof = pd.Timestamp(hist.Date.max())
    asof_s = f"{asof:%Y-%m-%d}"
    print(f"As-of {asof_s} | sessions {info['days']} | delivery coverage {info['delivery_cov']}% | "
          f"dropped {info['dropped']} | errors {info['errors']} | missing days {info.get('missing', 0)}")

    nifty_df = M.fetch_index("^NSEI", "2y")
    nifty_snap = M.snapshot(nifty_df, asof=asof)
    if not nifty_snap:
        print("Warning: Nifty data unavailable, using fallback")

    scr = E.compute_screener(hist, (), MIN_TURNOVER_CR, E.fetch_sector_map())
    if scr.empty:
        print("Screener empty")
        return 1
    print(f"Screener: {len(scr)} stocks after min turnover ₹{MIN_TURNOVER_CR} Cr filter")

    try:
        deals = A.fetch_bulk_block_deals()
    except Exception as ex:
        print("Deals fetch failed:", ex)
        deals = pd.DataFrame()
    try:
        scr = A.enrich_screener(scr, hist, deals, nifty_df)
    except Exception as ex:
        print("Enrich failed:", ex)
    stale_deals = bool(scr.attrs.get("stats", {}).get("deals_stale", False))

    outcomes = E.signal_outcomes(hist)
    scr = E.reentry_stats(scr, asof, outcomes)     # first: uses PREVIOUS days' log only
    n_logged = E.log_signals(scr, asof)            # then: log today's accumulation signals

    breadth = E.market_breadth(hist, scr, nifty_df)

    n_acc = int(scr.Signal.isin(E.ACC_SIGNALS).sum())
    n_fresh = int(scr.Fresh.isin(E.FRESH_SET).sum())

    status = {
        "asof": asof_s,
        "run_at_ist": E.now_ist().strftime("%Y-%m-%d %H:%M"),
        "stocks": int(len(scr)),
        "accumulation": n_acc,
        "fresh": n_fresh,
        "logged": n_logged,
        "min_turnover_cr": MIN_TURNOVER_CR,
        "info": info,
        "deals_stale": stale_deals,
        "telegram": "skipped",
    }

    token, chat = A.telegram_creds_from_env()
    last_alert_fp = os.path.join(DATA, "last_alert.txt")
    last = open(last_alert_fp).read().strip() if os.path.exists(last_alert_fp) else ""
    if args.no_telegram or not token or not chat:
        status["telegram"] = "no creds / disabled"
    elif last == asof_s and not args.force:
        status["telegram"] = "already sent for this date"
    else:
        msg = A.format_telegram_alert(scr, deals, breadth, f"{asof:%d %b %Y}",
                                      top_n=10, nifty=nifty_df, stale_deals=stale_deals)
        ok, why = A.send_telegram_message(token, chat, msg)
        status["telegram"] = "sent" if ok else f"failed: {why}"
        if ok:
            with open(last_alert_fp, "w") as f:
                f.write(asof_s)

    with open(os.path.join(DATA, "last_run.json"), "w") as f:
        json.dump(status, f, indent=2, default=str)
    print(json.dumps(status, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
