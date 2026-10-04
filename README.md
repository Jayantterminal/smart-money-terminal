# Smart Money Terminal

Personal Streamlit research dashboard for NSE end-of-day delivery/volume analysis.

## Data
- NSE full bhavcopy + security deliverable data
- NSE bulk/block deals
- NSE FII/DII and insider disclosures where available
- Yahoo Finance Nifty 50 EOD data

## Important
This is a research/analytics tool. The accumulation score, entry/SL/target levels,
and outcome journal are heuristic and should not be treated as guaranteed results.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## GitHub Actions
The daily workflow runs `daily_job.py` without `--force`, so a retry on the same
trading date does not intentionally send a duplicate Telegram alert. Use the
workflow's manual dispatch with `--force` only when you explicitly want to resend.

Set these GitHub Actions secrets:
- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

Do not commit `.env`, Streamlit secrets, API tokens, or the local NSE cache.
