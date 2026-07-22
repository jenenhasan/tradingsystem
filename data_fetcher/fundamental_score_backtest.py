"""
fundamental_score_backtest.py
==============================
ISOLATED TEST: does the fundamental score, by itself, predict forward
returns? No momentum, no RS, no ATR stops, no position sizing — those
all get evaluated separately. This script answers one question only:

    "If I rank stocks by fundamental score on date D and buy the top
     quintile, holding until the next rebalance, do they actually
     outperform the bottom quintile?"

Method
------
1. Build a quarterly rebalance calendar over the test window.
2. On each rebalance date, pull POINT-IN-TIME fundamentals for the
   universe from SEC EDGAR (sec_edgar_fetcher.py) — same source as the
   live pipeline, so this test isn't cheating with look-ahead data.
3. Score each stock (0-10, same 5-metric heuristic as the rest of the
   project: P/E, revenue growth, ROE, D/E, dividend yield).
4. Bucket cross-sectionally into quintiles BY THAT DATE's scores only
   (never bucketed against future information).
5. Measure each stock's forward return from this rebalance date to the
   NEXT rebalance date, using actual historical prices.
6. Aggregate: mean forward return per quintile (Q1=worst score,
   Q5=best), the Q5-Q1 spread, and the Information Coefficient (Spearman
   rank correlation between score and forward return) per date, averaged
   across all dates ("mean IC").

If the score has real predictive power: Q5 should beat Q1 consistently,
the spread should be positive on average, and mean IC should be
positive and preferably > ~0.02-0.05 (typical for a usable, if noisy,
equity factor — real factors are rarely much higher than this).

If Q5/Q1 are noisy/flat or mean IC is ~0 or negative: the score has no
demonstrated edge, and no amount of tuning ATR_MULTIPLIER or
MAX_POSITIONS in trading.py will fix that — the problem is upstream.

Usage
-----
    python fundamental_score_backtest.py
    python fundamental_score_backtest.py 2018-01-01 2025-07-31
"""

import os
import sys
import time
import warnings
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

warnings.filterwarnings("ignore")

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# FIX: sec_edgar_fetcher.py was refactored into a class-based fetcher
# (SECEdgarFetcher.get_fundamentals(ticker, as_of_date=...)) instead of a
# standalone get_point_in_time_fundamentals(ticker, as_of_date) function.
# Import the class and instantiate once, reused across all calls below.
from sec_edgar_fetcher import SECEdgarFetcher  # noqa: E402

_fetcher = SECEdgarFetcher()


def get_point_in_time_fundamentals(ticker: str, as_of_date):
    """Thin wrapper so the rest of this script's call sites don't change."""
    return _fetcher.get_fundamentals(ticker, as_of_date=as_of_date)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_START = "2018-01-01"
DEFAULT_END = "2025-07-31"
N_QUINTILES = 5
MIN_UNIVERSE_PER_DATE = 30   # skip a rebalance date if too few valid stocks
CACHE_DIR = "cache/fund_score_backtest"
os.makedirs(CACHE_DIR, exist_ok=True)

FALLBACK_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "JPM", "V", "WMT",
    "JNJ", "PG", "UNH", "HD", "DIS", "MA", "BAC", "NFLX", "ADBE", "CRM",
    "KO", "PEP", "TMO", "CSCO", "ACN", "ABT", "LIN", "VZ", "WFC", "TMUS",
    "XOM", "CVX", "MRK", "PFE", "COST", "AVGO", "TXN", "QCOM", "HON",
    "UPS", "LOW", "SBUX", "MDT", "INTC", "AMD", "CAT", "GS", "MS", "BLK",
    "SPGI", "DE",
]


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def get_universe() -> List[str]:
    """S&P 500 ticker list, Wikipedia scrape with cache/fallback."""
    cache_path = os.path.join(CACHE_DIR, "tickers.csv")
    if os.path.exists(cache_path):
        return list(pd.read_csv(cache_path, header=None)[0])
    try:
        import requests
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; FundScoreTest/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        tables = pd.read_html(resp.text)
        df = next(t for t in tables if "Symbol" in t.columns)
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        pd.Series(tickers).to_csv(cache_path, index=False, header=False)
        print(f"  Scraped {len(tickers)} tickers from Wikipedia")
        return tickers
    except Exception as e:
        print(f"  Wikipedia scrape failed ({e}); using {len(FALLBACK_TICKERS)}-ticker fallback list")
        return FALLBACK_TICKERS


# ---------------------------------------------------------------------------
# Scoring — mirrors the 5-metric heuristic used elsewhere in the project
# ---------------------------------------------------------------------------

def score_row(pe, rev_growth, roe, debt_equity, div_yield) -> int:
    score = 0
    if pd.notna(pe) and pe is not None and pe > 0:
        if pe <= 15:
            score += 2
        elif pe <= 20:
            score += 1
    if pd.notna(rev_growth) and rev_growth is not None:
        if rev_growth >= 0.10:
            score += 2
        elif rev_growth >= 0:
            score += 1
    if pd.notna(roe) and roe is not None:
        if roe >= 0.20:
            score += 2
        elif roe >= 0.10:
            score += 1
    if pd.notna(debt_equity) and debt_equity is not None:
        if debt_equity <= 0.5:
            score += 2
        elif debt_equity <= 1.0:
            score += 1
    if pd.notna(div_yield) and div_yield is not None:
        if div_yield >= 0.03:
            score += 2
        elif div_yield >= 0.015:
            score += 1
    return score


# ---------------------------------------------------------------------------
# Price data (cached per-ticker, used only for forward-return measurement —
# never for scoring, so this can't introduce look-ahead bias into the score)
# ---------------------------------------------------------------------------

_price_cache: Dict[str, pd.Series] = {}


def get_price_series(ticker: str, start: str, end: str) -> Optional[pd.Series]:
    cache_path = os.path.join(CACHE_DIR, f"px_{ticker}.pkl")
    if ticker in _price_cache:
        return _price_cache[ticker]
    if os.path.exists(cache_path):
        try:
            s = pd.read_pickle(cache_path)
            _price_cache[ticker] = s
            return s
        except Exception:
            pass
    try:
        hist = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if hist.empty:
            return None
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        s = hist["Close"]
        s.to_pickle(cache_path)
        _price_cache[ticker] = s
        return s
    except Exception:
        return None


def price_on_or_after(series: pd.Series, target: pd.Timestamp, max_lookahead_days: int = 7) -> Optional[float]:
    window = series[(series.index >= target) & (series.index <= target + timedelta(days=max_lookahead_days))]
    if window.empty:
        return None
    return float(window.iloc[0])


# ---------------------------------------------------------------------------
# Rebalance calendar
# ---------------------------------------------------------------------------

def quarterly_dates(start: str, end: str) -> List[pd.Timestamp]:
    return list(pd.date_range(start=start, end=end, freq="QS"))


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

def run_fundamental_score_test(start: str = DEFAULT_START, end: str = DEFAULT_END):
    print("=" * 70)
    print("  ISOLATED FUNDAMENTAL SCORE TEST")
    print(f"  Window: {start} -> {end}")
    print("=" * 70)

    tickers = get_universe()
    print(f"  Universe: {len(tickers)} tickers")

    rebal_dates = quarterly_dates(start, end)
    print(f"  Rebalance dates: {len(rebal_dates)} (quarterly)\n")

    per_date_records = []   # for IC calc
    quintile_returns: Dict[int, List[float]] = {q: [] for q in range(1, N_QUINTILES + 1)}

    for i, rebal_date in enumerate(rebal_dates[:-1]):
        next_date = rebal_dates[i + 1]
        as_of = rebal_date.date()
        print(f"  [{i+1}/{len(rebal_dates)-1}] Scoring as of {as_of} "
              f"-> forward return to {next_date.date()}")

        rows = []
        for ticker in tickers:
            try:
                fund = get_point_in_time_fundamentals(ticker, as_of)
                if fund is None:
                    continue
                score = score_row(
                    fund.get("pe_ratio"),
                    fund.get("revenue_growth"),
                    fund.get("roe"),
                    fund.get("debt_to_equity"),
                    fund.get("dividend_yield"),
                )
                rows.append({"ticker": ticker, "score": score})
            except Exception:
                continue

        if len(rows) < MIN_UNIVERSE_PER_DATE:
            print(f"      skipped — only {len(rows)} valid tickers "
                  f"(need {MIN_UNIVERSE_PER_DATE})")
            continue

        df = pd.DataFrame(rows)

        # Cross-sectional quintile bucketing using ONLY this date's scores
        try:
            df["quintile"] = pd.qcut(df["score"], N_QUINTILES, labels=False, duplicates="drop") + 1
        except ValueError:
            # too few distinct score values to form 5 buckets this quarter
            print(f"      skipped — score distribution too narrow to bucket")
            continue

        # Forward returns
        fwd_returns = []
        for _, row in df.iterrows():
            series = get_price_series(row["ticker"], rebal_date.strftime("%Y-%m-%d"),
                                       (next_date + timedelta(days=10)).strftime("%Y-%m-%d"))
            if series is None or series.empty:
                fwd_returns.append(np.nan)
                continue
            p0 = price_on_or_after(series, rebal_date)
            p1 = price_on_or_after(series, next_date)
            if p0 is None or p1 is None or p0 <= 0:
                fwd_returns.append(np.nan)
                continue
            fwd_returns.append((p1 - p0) / p0)
        df["fwd_return"] = fwd_returns
        df = df.dropna(subset=["fwd_return"])

        if len(df) < MIN_UNIVERSE_PER_DATE:
            print(f"      skipped — only {len(df)} tickers had valid price data")
            continue

        # Per-quintile mean return for this date
        for q in range(1, N_QUINTILES + 1):
            q_rets = df.loc[df["quintile"] == q, "fwd_return"]
            if not q_rets.empty:
                quintile_returns[q].extend(q_rets.tolist())

        # Information Coefficient for this date (Spearman rank corr)
        if df["score"].nunique() > 1:
            ic, _ = stats.spearmanr(df["score"], df["fwd_return"])
            per_date_records.append({"date": as_of, "ic": ic, "n": len(df)})

        q5_mean = df.loc[df["quintile"] == N_QUINTILES, "fwd_return"].mean()
        q1_mean = df.loc[df["quintile"] == 1, "fwd_return"].mean()
        print(f"      n={len(df):3d}  Q1={q1_mean:+.2%}  Q5={q5_mean:+.2%}  "
              f"spread={q5_mean - q1_mean:+.2%}")

    # -----------------------------------------------------------------
    # Aggregate results
    # -----------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)

    print(f"\n  {'Quintile':>10} {'N obs':>8} {'Mean fwd ret':>14} {'Std':>10}")
    q_means = {}
    for q in range(1, N_QUINTILES + 1):
        rets = quintile_returns[q]
        if rets:
            mean_r = np.mean(rets)
            std_r = np.std(rets)
            q_means[q] = mean_r
            label = f"Q{q}" + (" (worst)" if q == 1 else " (best)" if q == N_QUINTILES else "")
            print(f"  {label:>10} {len(rets):>8} {mean_r:>13.2%} {std_r:>10.2%}")
        else:
            print(f"  Q{q:>9} {'0':>8} {'N/A':>14} {'N/A':>10}")

    if N_QUINTILES in q_means and 1 in q_means:
        spread = q_means[N_QUINTILES] - q_means[1]
        print(f"\n  Q5 - Q1 spread (per-period):  {spread:+.2%}")

    if per_date_records:
        ic_df = pd.DataFrame(per_date_records)
        mean_ic = ic_df["ic"].mean()
        ic_std = ic_df["ic"].std()
        ic_ir = mean_ic / ic_std if ic_std and ic_std > 0 else float("nan")
        pct_positive = (ic_df["ic"] > 0).mean()
        print(f"\n  Mean IC (rank correlation, score vs fwd return): {mean_ic:+.4f}")
        print(f"  IC std dev across periods:                        {ic_std:.4f}")
        print(f"  IC information ratio (mean/std):                  {ic_ir:+.3f}")
        print(f"  % of periods with positive IC:                    {pct_positive:.1%}")
        print(f"  Periods evaluated:                                {len(ic_df)}")
    else:
        print("\n  No valid periods produced an IC — cannot assess predictive power.")

    print("\n" + "-" * 70)
    print("  HOW TO READ THIS")
    print("-" * 70)
    print("  - Q5 (best score) should show a HIGHER mean forward return than")
    print("    Q1 (worst score) if the fundamental score has real signal.")
    print("  - Mean IC near 0 (roughly -0.02 to +0.02) = no meaningful edge.")
    print("  - Mean IC consistently > ~0.03-0.05 with IR > ~0.3-0.5 suggests")
    print("    a usable, if modest, signal (real single factors are rarely")
    print("    much stronger than this — don't expect IC > 0.15).")
    print("  - If % positive periods is close to 50%, the sign of IC is")
    print("    essentially a coin flip even if the average looks positive.")
    print("=" * 70)

    return {
        "quintile_returns": quintile_returns,
        "quintile_means": q_means,
        "ic_records": per_date_records,
    }


if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_START
    end = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_END
    run_fundamental_score_test(start, end)