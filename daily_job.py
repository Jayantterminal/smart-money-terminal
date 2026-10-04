"""
daily_job.py - headless daily run (GitHub Actions / cron / manual)

    python daily_job.py              # fetch NSE data, log picks, send Telegram (once per session date)
    python daily_job.py --force      # send Telegram even if already sent for this date
    python daily_job.py --no-telegram

Env vars (GitHub Secrets):  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

Writes:  data/signals_log.csv   (every pick, one set per session date - used for re-entry + hit-rate)
         data/last_run.json     (status of the last run)
         data/last_alert.txt    (session date for which Telegram was already sent)
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="send Telegram even if already sent for this date")
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
          f"dropped {info['dropped']}")

    nifty_df = M.fetch_index("^NSEI", "2y")
    nifty = M.snapshot(nifty_df)
    scr = E.compute_screener(hist, (), 0.0, E.fetch_sector_map())
    if scr.empty:
        print("Screener empty")
        return 1
    deals = A.fetch_bulk_block_deals()
    scr = A.enrich_screener(scr, hist, deals, nifty_df)

    E.log_signals(scr, asof)
    outcomes = E.signal_outcomes(hist)
    scr = E.reentry_stats(scr, asof, outcomes)
    breadth = E.market_breadth(scr, nifty)

    n_acc = int(scr.Signal.isin(E.ACC_SIGNALS).sum())
    n_fresh = int(scr.Fresh.isin(E.FRESH_SET).sum())
    status = {"asof": asof_s, "run_at_ist": E.now_ist().strftime("%Y-%m-%d %H:%M"), "stocks": int(len(scr)),
              "accumulation": n_acc, "fresh": n_fresh, "info": {k: (v if not isinstance(v, pd.Timestamp) else str(v))
                                                                  for k, v in info.items()},
              "telegram": "skipped"}

    token, chat = A.telegram_creds_from_env()
    last_alert_fp = os.path.join(DATA, "last_alert.txt")
    last = open(last_alert_fp).read().strip() if os.path.exists(last_alert_fp) else ""
    if args.no_telegram or not token or not chat:
        status["telegram"] = "no creds / disabled"
    elif last == asof_s and not args.force:
        status["telegram"] = "already sent for this date"
    else:
        msg = A.format_telegram_alert(scr, deals, breadth, f"{asof:%d %b %Y}", top_n=10)
        ok, why = A.send_telegram_message(token, chat, msg)
        status["telegram"] = "sent" if ok else f"failed: {why}"
        if ok:
            open(last_alert_fp, "w").write(asof_s)

    json.dump(status, open(os.path.join(DATA, "last_run.json"), "w"), indent=2, default=str)
    print(json.dumps(status, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
