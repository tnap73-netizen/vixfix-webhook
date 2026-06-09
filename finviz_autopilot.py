#!/usr/bin/env python3
"""
BMCMS LLC — Finviz Autopilot Scanner
Replicates TrendSpider Ultimate Market Scanner logic:
  - EMA 50 > EMA 100 > EMA 200 (fan ordered, verified via yfinance)
  - Price > SMA100 (not broken below)
  - Price < SMA20 (pulling back)
  - RSI(14) < 40 (oversold proxy for VixFix)
  - Avg volume > 500K
  - Market cap > $2B
  - US, optionable, positive EPS, analyst rec Hold or better

Finviz handles the initial filter. Python post-processes to verify
EMA50 > EMA100 (Finviz only has SMA50 > SMA200, not SMA50 > SMA100).

Run modes:
  --once       Run once and exit
  --loop       Run every N minutes continuously
  --cron       Run once, designed for cron job scheduling

Email alerts sent via SMTP when setups found.
"""

import sys
import time
import datetime
import argparse
import smtplib
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import pandas as pd
import numpy as np

try:
    import yfinance as yf
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'yfinance', '-q'])
    import yfinance as yf

# ── Config ────────────────────────────────────────────────────────────────────
FINVIZ_AUTH   = 'bd60c09b-06cb-42ab-9ef7-5b9d7259aedd'
FINVIZ_EXPORT = 'https://elite.finviz.com/export.ashx'

# Sectors to exclude (biotech/pharma handled by an_recom filter + post-process)
EXCLUDE_SECTORS   = {'Real Estate', 'Utilities'}
EXCLUDE_INDUSTRIES = {'Biotechnology', 'Drug Manufacturers - General',
                      'Drug Manufacturers - Specialty & Generic',
                      'Banks - Diversified', 'Banks - Regional',
                      'Insurance - Diversified', 'Insurance - Life',
                      'REIT - Diversified', 'REIT - Retail', 'REIT - Office',
                      'REIT - Healthcare Facilities', 'REIT - Residential',
                      'REIT - Industrial', 'REIT - Specialty',
                      'Exchange Traded Fund'}

# Finviz filter string — exact TrendSpider conditions
FINVIZ_FILTERS = ','.join([
    'ta_sma20_pb',       # Price below 20-Day SMA (pulling back)
    'ta_sma100_pa',      # Price above 100-Day SMA (not broken below)
    'ta_sma50_sa200',    # SMA50 above SMA200 (partial fan confirmation)
    'ta_rsi_os40',       # RSI(14) < 40 (oversold proxy)
    'sh_avgvol_o500',    # Avg volume > 500K
    'cap_midover',       # Market cap > $2B
    'geo_usa',           # US listed
    'sh_opt_option',     # Optionable
    'fa_eps_pos',        # Positive EPS (profitable)
    'an_recom_holdbetter', # Analyst rec Hold or better (no Sell consensus)
])

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://elite.finviz.com/',
}

# ── Email config — update with your SMTP credentials ─────────────────────────
# Uses Gmail app password by default. Set env vars or edit directly.
import os
SMTP_HOST     = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT     = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER     = os.getenv('SMTP_USER', '')        # your Gmail address
SMTP_PASS     = os.getenv('SMTP_PASS', '')        # Gmail app password
EMAIL_TO      = os.getenv('EMAIL_TO', '')         # recipient address
EMAIL_FROM    = os.getenv('EMAIL_FROM', SMTP_USER)


# ── Step 1: Finviz scan ───────────────────────────────────────────────────────
def finviz_scan() -> pd.DataFrame:
    """Fetch Finviz export with fan+oversold filters. Returns DataFrame."""
    url = f'{FINVIZ_EXPORT}?v=152&f={FINVIZ_FILTERS}&auth={FINVIZ_AUTH}'
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip().strip('"') for c in df.columns]
    # Rename for consistency
    df = df.rename(columns={
        'Ticker': 'ticker',
        'Company': 'company',
        'Sector': 'sector',
        'Industry': 'industry',
        'Market Cap': 'mktcap',
        'Price': 'price',
        'Change': 'change',
        'Volume': 'volume',
        'P/E': 'pe',
    })
    return df


# ── Step 2: Sector exclusion ─────────────────────────────────────────────────
def apply_sector_filter(df: pd.DataFrame) -> pd.DataFrame:
    if 'sector' in df.columns:
        df = df[~df['sector'].isin(EXCLUDE_SECTORS)]
    if 'industry' in df.columns:
        df = df[~df['industry'].isin(EXCLUDE_INDUSTRIES)]
    return df.reset_index(drop=True)


# ── Step 3: EMA verification via yfinance ────────────────────────────────────
def verify_ema_fan(ticker: str) -> dict | None:
    """
    Verify EMA50 > EMA100 > EMA200 with 2% spacing.
    Finviz uses SMA; we verify actual EMA fan here.
    Returns dict with EMA levels and spacing, or None if fan broken.
    """
    try:
        t = yf.Ticker(ticker)
        df = t.history(period='1y', interval='1d')
        if len(df) < 200:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)

        for p in [20, 50, 100, 200]:
            df[f'ema{p}'] = df['Close'].ewm(span=p, adjust=False).mean()

        last = df.iloc[-1]
        e20  = last['ema20']
        e50  = last['ema50']
        e100 = last['ema100']
        e200 = last['ema200']

        # Fan ordered check
        fan_ordered = e50 > e100 > e200
        if not fan_ordered:
            return None

        # Spacing check — 2% between each pair
        sp_50_100  = (e50  - e100) / e100  * 100
        sp_100_200 = (e100 - e200) / e200  * 100
        sp_20_50   = (e20  - e50)  / e50   * 100

        if sp_50_100 < 2.0 or sp_100_200 < 2.0:
            return None

        # Price position check
        price = last['Close']
        below_20 = price < e20
        above_100 = price > e100

        if not below_20 or not above_100:
            return None

        # Proximity to entry EMAs (50, 100, 200 within 3%)
        pct_from_50  = (price - e50)  / e50  * 100
        pct_from_100 = (price - e100) / e100 * 100
        pct_from_200 = (price - e200) / e200 * 100

        at_50  = -3.0 <= pct_from_50  <= 3.0 and price > e50
        at_100 = -3.0 <= pct_from_100 <= 3.0 and price > e100
        at_200 = -3.0 <= pct_from_200 <= 3.0 and price > e200

        # No man's land check
        between_50_100 = price < e50 and price > e100
        if between_50_100 and not at_50 and not at_100:
            return None  # No man's land

        if not at_50 and not at_100 and not at_200:
            return None  # Not near any valid EMA

        # Determine which EMA is being tested
        if at_200:
            ema_touch = 200
            touch_str = 'AT 200 EMA'
        elif at_100:
            ema_touch = 100
            touch_str = 'AT 100 EMA'
        else:
            ema_touch = 50
            touch_str = 'AT 50 EMA'

        # Volume
        avg_vol = df['Volume'].tail(20).mean()
        vol_ratio = last['Volume'] / avg_vol if avg_vol > 0 else 0

        return {
            'ema20': round(e20, 2),
            'ema50': round(e50, 2),
            'ema100': round(e100, 2),
            'ema200': round(e200, 2),
            'sp_20_50': round(sp_20_50, 1),
            'sp_50_100': round(sp_50_100, 1),
            'sp_100_200': round(sp_100_200, 1),
            'ema_touch': ema_touch,
            'touch_str': touch_str,
            'pct_from_touch': round(locals()[f'pct_from_{ema_touch}'], 1),
            'vol_ratio': round(vol_ratio, 2),
        }
    except Exception as e:
        return None


# ── Step 4: Build alert email ─────────────────────────────────────────────────
def build_email(setups: list) -> tuple[str, str]:
    """Returns (subject, html_body)"""
    n = len(setups)
    now = datetime.datetime.now().strftime('%a %b %d %I:%M %p ET')
    subject = f'BMCMS Scan — {n} Setup{"s" if n > 1 else ""} Found | {now}'

    rows = ''
    for s in setups:
        touch_label = {200: 'NUCLEAR', 100: 'STRONG', 50: 'GOOD'}.get(s['ema_touch'], '')
        rows += f"""
        <tr style="border-bottom:1px solid #2d2d2d">
          <td style="padding:10px 8px;font-size:16px;font-weight:bold;color:#58a6ff">{s['ticker']}</td>
          <td style="padding:10px 8px;color:#e6edf3">${s['price']:.2f} <span style="color:{'#2ea043' if s.get('chg_pct',0)>=0 else '#f85149'}">({s.get('change','')}) </span></td>
          <td style="padding:10px 8px;color:#f0c040;font-weight:bold">{s['touch_str']} ({s['pct_from_touch']:+.1f}%) <span style="color:#8b949e;font-size:11px">{touch_label}</span></td>
          <td style="padding:10px 8px;color:#8b949e;font-size:12px">
            20 EMA ${s['ema20']} | 50 EMA ${s['ema50']} | 100 EMA ${s['ema100']} | 200 EMA ${s['ema200']}<br>
            Spacing: {s['sp_20_50']}% / {s['sp_50_100']}% / {s['sp_100_200']}%<br>
            Volume: {s['vol_ratio']}x avg | {s.get('sector','')}
          </td>
        </tr>"""

    html = f"""
    <html><body style="background:#0d1117;color:#e6edf3;font-family:monospace;padding:20px">
    <h2 style="color:#58a6ff;border-bottom:1px solid #21262d;padding-bottom:10px">
      BMCMS EMA Fan Scanner — {now}
    </h2>
    <p style="color:#8b949e">
      Conditions: EMA fan (50>100>200, 2% spacing) | Price below 20 EMA | Price above 100 EMA | RSI &lt; 40<br>
      {n} setup{"s" if n > 1 else ""} found. VixFix confirmation required on TrendSpider before any entry.
    </p>
    <table style="width:100%;border-collapse:collapse;background:#161b22">
      <thead>
        <tr style="background:#21262d">
          <th style="padding:8px;text-align:left;color:#8b949e">Ticker</th>
          <th style="padding:8px;text-align:left;color:#8b949e">Price</th>
          <th style="padding:8px;text-align:left;color:#8b949e">EMA Zone</th>
          <th style="padding:8px;text-align:left;color:#8b949e">EMA Levels</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="color:#484f58;font-size:11px;margin-top:20px">
      BMCMS LLC | EMA Fan Scanner | Powered by Finviz Elite + yfinance<br>
      VixFix at or near the line required before any entry. No man's land auto-eliminated.
    </p>
    </body></html>"""

    return subject, html


# ── Step 5: Send email ────────────────────────────────────────────────────────
def send_email(subject: str, html_body: str):
    if not SMTP_USER or not SMTP_PASS or not EMAIL_TO:
        print('  Email not configured — set SMTP_USER, SMTP_PASS, EMAIL_TO env vars')
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = EMAIL_FROM
        msg['To']      = EMAIL_TO
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.ehlo()
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        print(f'  Email sent to {EMAIL_TO}')
        return True
    except Exception as e:
        print(f'  Email error: {e}')
        return False


# ── Main scan loop ────────────────────────────────────────────────────────────
def run_scan(dry_run: bool = False, verbose: bool = False) -> list:
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f'\n{"="*60}')
    print(f'  BMCMS Finviz Fan Scanner | {now_str}')
    print(f'{"="*60}')

    # Step 1 — Finviz pull
    print('  Fetching Finviz candidates...')
    try:
        df = finviz_scan()
    except Exception as e:
        print(f'  Finviz fetch error: {e}')
        return []

    print(f'  Finviz returned {len(df)} candidates')

    # Step 2 — Sector filter
    df = apply_sector_filter(df)
    print(f'  After sector exclusion: {len(df)} candidates')

    if len(df) == 0:
        print('  No candidates after filters.')
        return []

    # Step 3 — EMA verification
    print(f'  Verifying EMA fan on {len(df)} tickers...\n')
    setups = []

    for _, row in df.iterrows():
        ticker = row.get('ticker', '')
        if not ticker or not isinstance(ticker, str):
            continue

        price  = row.get('price', 0)
        change = row.get('change', '')
        sector = row.get('sector', '')
        company = row.get('company', '')

        # Skip if price > $300 (sizing rule — user can override)
        # Commented out since user wants all names surfaced regardless
        # if price > 300: continue

        ema_data = verify_ema_fan(ticker)

        if ema_data:
            setup = {
                'ticker': ticker,
                'company': company,
                'price': price,
                'change': change,
                'sector': sector,
                **ema_data
            }
            setups.append(setup)

            touch_label = {200: '[NUCLEAR]', 100: '[STRONG]', 50: '[GOOD]'}.get(ema_data['ema_touch'], '')
            print(f'  SETUP {touch_label} {ticker} | ${price:.2f} {change} | '
                  f'{ema_data["touch_str"]} ({ema_data["pct_from_touch"]:+.1f}%) | '
                  f'Spacing {ema_data["sp_50_100"]:.1f}%/{ema_data["sp_100_200"]:.1f}%')
        else:
            if verbose:
                print(f'  SKIP {ticker} — EMA fan not confirmed')

    print(f'\n  {"="*56}')
    if setups:
        print(f'  {len(setups)} valid setup(s) confirmed')
        if not dry_run:
            subject, html = build_email(setups)
            send_email(subject, html)
            print(f'  Subject: {subject}')
    else:
        print('  No valid EMA fan setups — no email sent')

    return setups


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BMCMS Finviz EMA Fan Scanner')
    parser.add_argument('--loop', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=30, help='Minutes between scans (default 30)')
    parser.add_argument('--once', action='store_true', default=True, help='Run once (default)')
    parser.add_argument('--dry-run', action='store_true', help='No email output')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show all skipped tickers')
    args = parser.parse_args()

    if args.loop:
        print(f'Running in loop mode every {args.interval} minutes. Ctrl+C to stop.')
        while True:
            run_scan(dry_run=args.dry_run, verbose=args.verbose)
            next_run = datetime.datetime.now() + datetime.timedelta(minutes=args.interval)
            print(f'\n  Next scan at {next_run.strftime("%H:%M")}. Sleeping...')
            time.sleep(args.interval * 60)
    else:
        run_scan(dry_run=args.dry_run, verbose=args.verbose)
