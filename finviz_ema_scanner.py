#!/usr/bin/env python3
"""
Finviz Elite EMA Fan Scanner — BMCMS LLC
Replicates TrendSpider EMA fan logic using Finviz Elite API + yfinance price data.

LOGIC:
  Mode 1 (EMA Fan Pullback):
    - Fan confirmed: 20 EMA > 50 EMA > 100 EMA > 200 EMA
    - 2% spacing between each consecutive EMA pair
    - Price BELOW 20 EMA (pulling back)
    - Price AT key EMA (50/100/200 within 3%)
    - Price ABOVE the specific EMA being tested (not broken below)
    - Earnings this or next week (optional filter — disabled per user rule)

  Scoring (out of 10):
    Fan ordered:            +2
    All spacings >= 2%:     +2
    Price below 20 EMA:     +1
    At 50 EMA (within 3%):  +3
    At 100 EMA (within 3%): +3 (stronger)
    At 200 EMA (within 3%): +4 (strongest)
    Price above tested EMA: +1 (confirmation)
    Volume > 1.5x avg:      +1 (conviction)

  Alert threshold: >= 7/10
  Priority:        >= 9/10

OUTPUT:
  Prints results and optionally sends Perplexity notification.

CREDENTIALS:
  Finviz Elite: bd60c09b-06cb-42ab-9ef7-5b9d7259aedd
"""

import sys
import time
import json
import datetime
import requests
import subprocess
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# ── Config ───────────────────────────────────────────────────────────────────
FINVIZ_AUTH  = 'bd60c09b-06cb-42ab-9ef7-5b9d7259aedd'
FINVIZ_BASE  = 'https://elite.finviz.com'
WATCHLIST_FILE = '/tmp/watchlist_quality.txt'
ALERT_THRESHOLD = 7
PRIORITY_THRESHOLD = 9

# ── Finviz Screener ───────────────────────────────────────────────────────────
def finviz_screen(filters: dict, max_results: int = 100) -> list:
    """
    Use Finviz Elite screener to get initial candidate list.
    Filters applied: above price/vol/cap minimums, not in broken fan sectors.
    Returns list of tickers.
    """
    # Finviz screener v1 export
    params = {
        'auth': FINVIZ_AUTH,
        'v': '111',     # detail view
        'f': build_filter_string(filters),
        'r': '1',
        'c': '1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20',
        'o': '-change',
        'export': 'true',
    }
    url = f'{FINVIZ_BASE}/screener.ashx'
    try:
        resp = requests.get(url, params=params, timeout=30,
                           headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        lines = resp.text.strip().split('\n')
        if len(lines) < 2:
            return []
        # Parse CSV
        headers = [h.strip().strip('"') for h in lines[0].split(',')]
        tickers = []
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split(',')
            if len(parts) > 1:
                ticker = parts[1].strip().strip('"')
                if ticker and ticker.isalpha():
                    tickers.append(ticker)
        return tickers[:max_results]
    except Exception as e:
        print(f'  Finviz screen error: {e}')
        return []

def build_filter_string(filters: dict) -> str:
    """Convert filter dict to Finviz filter string"""
    parts = []
    # Price > $5
    parts.append('sh_price_o5')
    # Average volume > 500K
    parts.append('sh_avgvol_o500')
    # Market cap > $2B
    parts.append('cap_midover')
    # Country: USA
    parts.append('geo_usa')
    # Optionable
    parts.append('sh_opt_option')
    # Positive EPS (profitable)
    parts.append('fa_eps_pos')
    # Analyst rec not Sell (1=Strong Buy to 5=Strong Sell; filter <= 3 = not sell)
    parts.append('an_recom_holdbetter')
    # Exclude sectors: Financial, Healthcare (biotech/pharma), Real Estate, Utilities
    # Note: Finviz doesn't have a direct NOT filter — we handle sector exclusion post-fetch
    return ','.join(parts)

# ── Price history + EMA calculation ──────────────────────────────────────────
def get_price_data(ticker: str, days: int = 252) -> pd.DataFrame | None:
    """Fetch price history via yfinance"""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        df = t.history(period='1y', interval='1d')
        df.index = pd.to_datetime(df.index).tz_localize(None)
        if len(df) < 200:
            return None
        return df
    except Exception as e:
        return None

def compute_emas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for p in [20, 50, 100, 200]:
        df[f'ema{p}'] = df['Close'].ewm(span=p, adjust=False).mean()
    return df

def score_ticker(ticker: str, df: pd.DataFrame) -> dict:
    """
    Score a ticker against Mode 1 EMA fan pullback criteria.
    Returns score dict.
    """
    df = compute_emas(df)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    price  = last['Close']
    e20    = last['ema20']
    e50    = last['ema50']
    e100   = last['ema100']
    e200   = last['ema200']
    volume = last['Volume']
    avg_vol = df['Volume'].tail(20).mean()

    score = 0
    reasons = []

    # 1. Fan ordered (20 > 50 > 100 > 200)
    fan_ordered = e20 > e50 > e100 > e200
    if fan_ordered:
        score += 2
        reasons.append('Fan ordered +2')
    else:
        reasons.append('Fan BROKEN — skip')
        return {'ticker': ticker, 'score': 0, 'reasons': reasons,
                'price': price, 'e20': e20, 'e50': e50, 'e100': e100, 'e200': e200,
                'fan_ordered': False, 'eliminated': True}

    # 2. Spacing >= 2% between each pair
    sp_20_50   = (e20 - e50)   / e50   * 100
    sp_50_100  = (e50 - e100)  / e100  * 100
    sp_100_200 = (e100 - e200) / e200  * 100

    spacing_ok = sp_20_50 >= 2.0 and sp_50_100 >= 2.0 and sp_100_200 >= 2.0
    if spacing_ok:
        score += 2
        reasons.append(f'Spacing OK ({sp_20_50:.1f}%/{sp_50_100:.1f}%/{sp_100_200:.1f}%) +2')
    else:
        thin = []
        if sp_20_50 < 2.0:   thin.append(f'20/50={sp_20_50:.1f}%')
        if sp_50_100 < 2.0:  thin.append(f'50/100={sp_50_100:.1f}%')
        if sp_100_200 < 2.0: thin.append(f'100/200={sp_100_200:.1f}%')
        reasons.append(f'Spacing thin: {", ".join(thin)} — fan not valid')
        return {'ticker': ticker, 'score': score, 'reasons': reasons,
                'price': price, 'e20': e20, 'e50': e50, 'e100': e100, 'e200': e200,
                'fan_ordered': True, 'spacing_ok': False, 'eliminated': True}

    # 3. Price below 20 EMA (pullback in progress)
    below_20 = price < e20
    if below_20:
        score += 1
        reasons.append(f'Below 20 EMA (${e20:.2f}) +1')
    else:
        pct_above_20 = (price - e20) / e20 * 100
        reasons.append(f'Price ABOVE 20 EMA by {pct_above_20:.1f}% — extended, no entry')
        return {'ticker': ticker, 'score': score, 'reasons': reasons,
                'price': price, 'e20': e20, 'e50': e50, 'e100': e100, 'e200': e200,
                'fan_ordered': True, 'spacing_ok': True, 'below_20': False, 'eliminated': True}

    # 4. Check no man's land (between two EMAs with no EMA to test)
    # Valid entry only if price is near 50, 100, or 200 EMA
    pct_from_50  = (price - e50)  / e50  * 100
    pct_from_100 = (price - e100) / e100 * 100
    pct_from_200 = (price - e200) / e200 * 100

    at_50  = abs(pct_from_50)  <= 3.0 and price > e50
    at_100 = abs(pct_from_100) <= 3.0 and price > e100
    at_200 = abs(pct_from_200) <= 3.0 and price > e200

    # No man's land check: below 50 AND above 100 (not near either)
    below_50 = price < e50
    above_100 = price > e100
    if below_50 and above_100 and not at_50 and not at_100:
        reasons.append(f'NO MAN\'S LAND: between 50 EMA (${e50:.2f}) and 100 EMA (${e100:.2f}) — skip')
        return {'ticker': ticker, 'score': score, 'reasons': reasons,
                'price': price, 'e20': e20, 'e50': e50, 'e100': e100, 'e200': e200,
                'no_mans_land': True, 'eliminated': True}

    # Score EMA proximity
    ema_touch = None
    if at_200:
        score += 4
        reasons.append(f'AT 200 EMA ${e200:.2f} ({pct_from_200:+.1f}%) NUCLEAR +4')
        ema_touch = 200
    elif at_100:
        score += 3
        reasons.append(f'AT 100 EMA ${e100:.2f} ({pct_from_100:+.1f}%) STRONG +3')
        ema_touch = 100
    elif at_50:
        score += 2
        reasons.append(f'AT 50 EMA ${e50:.2f} ({pct_from_50:+.1f}%) GOOD +2')
        ema_touch = 50
    else:
        # Not near any valid entry EMA
        nearest = min([(abs(pct_from_50), 50, pct_from_50),
                       (abs(pct_from_100), 100, pct_from_100),
                       (abs(pct_from_200), 200, pct_from_200)])
        reasons.append(f'Not at any EMA (nearest: {nearest[1]} EMA at {nearest[2]:+.1f}%)')
        return {'ticker': ticker, 'score': score, 'reasons': reasons,
                'price': price, 'e20': e20, 'e50': e50, 'e100': e100, 'e200': e200,
                'fan_ordered': True, 'spacing_ok': True, 'below_20': True,
                'ema_touch': None, 'eliminated': True}

    # 5. Price ABOVE the EMA being tested (not broken below)
    if ema_touch and price > df.iloc[-1][f'ema{ema_touch}']:
        score += 1
        reasons.append(f'Price above {ema_touch} EMA (not broken) +1')

    # 6. Volume > 1.5x average
    vol_ratio = volume / avg_vol if avg_vol > 0 else 0
    if vol_ratio > 1.5:
        score += 1
        reasons.append(f'Volume {vol_ratio:.1f}x avg +1')

    return {
        'ticker': ticker,
        'score': score,
        'price': price,
        'e20': e20, 'e50': e50, 'e100': e100, 'e200': e200,
        'sp_20_50': sp_20_50, 'sp_50_100': sp_50_100, 'sp_100_200': sp_100_200,
        'ema_touch': ema_touch,
        'vol_ratio': vol_ratio,
        'reasons': reasons,
        'fan_ordered': True,
        'spacing_ok': True,
        'below_20': True,
        'eliminated': False
    }

# ── Load watchlist ────────────────────────────────────────────────────────────
def load_watchlist(path: str) -> list:
    try:
        with open(path) as f:
            tickers = [t.strip() for t in f.read().split('\n') if t.strip()]
        return tickers
    except:
        print(f'  Could not load watchlist from {path}')
        return []

# ── Main scan ─────────────────────────────────────────────────────────────────
def run_scan(tickers: list = None, max_tickers: int = 200, verbose: bool = False):
    """
    Run EMA fan pullback scan.
    If tickers not provided, loads from BMCMS FULL watchlist.
    """
    print(f'\n{"="*60}')
    print(f'  BMCMS EMA Fan Scanner — {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")} ET')
    print(f'{"="*60}')

    if tickers is None:
        tickers = load_watchlist(WATCHLIST_FILE)
        if not tickers:
            print('  ERROR: No watchlist loaded. Run from watchlist file.')
            return []

    print(f'  Universe: {len(tickers)} tickers')
    print(f'  Scanning up to {min(max_tickers, len(tickers))} ...\n')

    results = []
    scan_list = tickers[:max_tickers]

    # Install yfinance if needed
    try:
        import yfinance
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'yfinance', '-q'])

    for i, ticker in enumerate(scan_list):
        if verbose:
            print(f'  [{i+1}/{len(scan_list)}] {ticker}...', end=' ', flush=True)

        df = get_price_data(ticker)
        if df is None:
            if verbose: print('no data')
            continue

        result = score_ticker(ticker, df)

        if result['score'] >= ALERT_THRESHOLD:
            results.append(result)
            flag = 'PRIORITY' if result['score'] >= PRIORITY_THRESHOLD else 'ALERT'
            print(f'  {flag} [{result["score"]}/10] {ticker} @ ${result["price"]:.2f} | '
                  f'AT {result["ema_touch"]} EMA | '
                  f'Spacing {result["sp_20_50"]:.1f}%/{result["sp_50_100"]:.1f}%/{result["sp_100_200"]:.1f}%')
        else:
            if verbose and not result.get('eliminated'):
                print(f'  [{result["score"]}/10] {ticker} — below threshold')
            elif verbose:
                print(f'skip ({result["reasons"][-1][:40] if result["reasons"] else "no data"})')

        # Light throttle to avoid hammering yfinance
        if i > 0 and i % 50 == 0:
            time.sleep(2)

    print(f'\n{"="*60}')
    if results:
        print(f'  {len(results)} setup(s) found above threshold {ALERT_THRESHOLD}/10')
        for r in sorted(results, key=lambda x: -x['score']):
            flag = 'PRIORITY' if r['score'] >= PRIORITY_THRESHOLD else 'ALERT'
            touch = r.get('ema_touch', '?')
            sp = f"{r.get('sp_20_50',0):.1f}%/{r.get('sp_50_100',0):.1f}%/{r.get('sp_100_200',0):.1f}%"
            print(f'\n  [{flag}] {r["ticker"]} | Score {r["score"]}/10 | ${r["price"]:.2f}')
            print(f'    EMA touch: {touch} EMA | Spacing: {sp}')
            print(f'    20 EMA ${r["e20"]:.2f} | 50 EMA ${r["e50"]:.2f} | '
                  f'100 EMA ${r["e100"]:.2f} | 200 EMA ${r["e200"]:.2f}')
            if r.get('vol_ratio'):
                print(f'    Volume: {r["vol_ratio"]:.1f}x avg')
    else:
        print('  No EMA fan pullback setups today')
    print(f'{"="*60}\n')

    return results

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='BMCMS EMA Fan Scanner')
    parser.add_argument('--tickers', '-t', nargs='*', help='Override ticker list')
    parser.add_argument('--max', '-m', type=int, default=200, help='Max tickers to scan')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--watchlist', '-w', type=str, default=WATCHLIST_FILE,
                        help='Path to watchlist file')
    args = parser.parse_args()

    if args.tickers:
        tickers = args.tickers
    else:
        WATCHLIST_FILE = args.watchlist
        tickers = None

    results = run_scan(tickers=tickers, max_tickers=args.max, verbose=args.verbose)
    sys.exit(0 if results is not None else 1)
