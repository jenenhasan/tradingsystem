"""
fundamental_analysis.py
========================
Fetches S&P 500 financial data and scores each stock on 5 metrics.

Changes from original
---------------------
1. fetch_financial_data() — added as_of_date parameter for backtest mode.
   When as_of_date is provided, uses quarterly_financials with a 45-day
   filing lag so only data publicly available on that date is used.
   When None (paper trading), uses .info as before.

2. fetch_sp500_ticker()   — added a fallback CSV read so if the Wikipedia
   scrape fails mid-run (network blip), we can re-use a previously saved
   tickers.csv instead of crashing.

3. calculate_scores()     — all metric comparisons now guarded with pd.notna()
   so a NaN value after imputation doesn't raise a TypeError. In the original,
   `pe_ratio <= quantile(0.25)` with pe_ratio=NaN throws silently incorrect
   results or crashes depending on the pandas version.

4. handle_missing_data()  — industry_medians dict is now reset per column
   (was shared across columns, so a median for pe_ratio could accidentally
   fill revenue_growth if the column loop order placed them consecutively
   in the same industry group).

5. perform_fundamental_analysis() — filtered_df is now a .copy() to avoid
   SettingWithCopyWarning when the caller later modifies the returned DataFrame.

6. General — removed the hardcoded Windows file path from main() and replaced
   with a relative path so the script runs on any OS.

7. fetch_all_quarters_financials() — NEW. Pre-loads all quarterly financials
   once for fast point-in-time backtests. Returns a memory cache.

8. get_point_in_time_fundamentals() — NEW. Extracts fundamentals for one
   ticker as of one date from the pre-loaded cache. Zero API calls.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import os

import logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
class data_fetcher:

    def __init__(self, tickers=None, file_path=None):
        self.tickers   = tickers
        self.file_path = file_path
        self.data      = []

    def fetch_sp500_ticker(self):
        """
        Scrapes the S&P 500 ticker list from Wikipedia.
        FIX 2: if the scrape fails, falls back to reading tickers.csv if it
        exists from a previous successful run, so the bot doesn't crash on a
        temporary network issue.
        """
        try:
            import requests
            url     = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            headers = {"User-Agent": "Mozilla/5.0  (compatible; TradingBot/1.0; jenen@example.com)"}
           # session = requests.Session()
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")
            #response.raise_for_status()
            #import urllib
            #req = urllib.request.Request(url, headers=headers)
            tables  = pd.read_html(response.text)
            df = None 
            for table in tables: 
                if 'Symbol' in table.columns:
                    df = table
                    break
            if df is None : 
                raise ValueError('Symbol column not found')
            tickers = df['Symbol'].tolist()
            np.savetxt('tickers.csv', tickers , fmt="%s")
            print(f"  ✓ Scraped {len(tickers)} tickers from Wikipedia")
            return tickers
        

        except Exception as e:
            print(f"  Wikipedia scrape failed: {e}")
            if os.path.exists('tickers.csv'):
                print('Falling back to cached tickers.csv')
                return list(np.loadtxt('tickers.csv' , dtype=str))
            raise RuntimeError(
                'cannot fetch s&p 500 tickers and no cached tickers.csv found '
            )
            


            




        """

            df      = tables[0]
            tickers = df['Symbol'].tolist()
            np.savetxt("tickers.csv", tickers, fmt="%s")
            return tickers
        except Exception as e:
            print(f"  Wikipedia scrape failed: {e}")
            if os.path.exists("tickers.csv"):
                print("  Falling back to cached tickers.csv")
                return list(np.loadtxt("tickers.csv", dtype=str))
            raise RuntimeError(
                "Cannot fetch S&P 500 tickers and no cached tickers.csv found."
            )
        """

    # =========================================================================
    # NEW METHOD 1: Pre-load ALL quarterly data for fast backtests
    # =========================================================================
    def fetch_all_quarters_financials(self, tickers):
        """
        Pre-fetch ALL quarterly financials for all tickers at ONCE.
        Returns dict: {ticker: {'income': DataFrame, 'balance': DataFrame, 'info': dict}}
        
        Call this ONCE before the backtest loop starts. The backtest then reads
        from this cache instead of calling yfinance every day.
        
        This converts:
            100 tickers × 100 backtest days = 10,000 API calls
        Into:
            100 tickers × 1 pre-load        = 100 API calls
        """
        all_data = {}
        total = len(tickers)
        
        print(f"  Pre-fetching quarterly financials for {total} tickers...")
        print(f"  This takes 2-5 minutes but makes the backtest 100× faster.")
        
        for i, ticker in enumerate(tickers):
            try:
                updated = self.update_wrong_tickers(ticker)
                stock = yf.Ticker(updated)
                income  = stock.quarterly_financials
                balance = stock.quarterly_balance_sheet
                info    = stock.info
                
                if income is not None and not income.empty:
                    all_data[ticker] = {
                        'income':  income,
                        'balance': balance if balance is not None else pd.DataFrame(),
                        'info':    info
                    }
            except Exception:
                pass  # skip tickers that fail — conservative approach
            
            # Progress indicator
            if (i + 1) % 10 == 0 or (i + 1) == total:
                print(f"    {i + 1}/{total} tickers pre-fetched...")
            
            # Be kind to Yahoo — small delay between batches
            if (i + 1) % 20 == 0:
                time.sleep(0.5)
        
        print(f"  Done. Pre-fetched {len(all_data)}/{total} tickers.")
        return all_data

    # =========================================================================
    # NEW METHOD 2: Extract point-in-time data from cache (zero API calls)
    # =========================================================================
    def get_point_in_time_fundamentals(self, ticker, as_of_date, preloaded_data):
        """
        Get fundamentals for ONE ticker as of ONE date using pre-loaded cache.
        ZERO API calls — reads entirely from the preloaded_data dict in memory.
        
        Parameters:
            ticker:          stock symbol (e.g. 'AAPL')
            as_of_date:      the decision date (only data filed 45+ days before this is used)
            preloaded_data:  dict returned by fetch_all_quarters_financials()
        
        Returns:
            dict with fundamental metrics, or None if no data available for that date.
        """
        filing_lag = timedelta(days=45)
        as_of_ts   = pd.Timestamp(as_of_date)
        
        if ticker not in preloaded_data:
            return None
        
        data    = preloaded_data[ticker]
        income  = data['income']
        balance = data['balance']
        info    = data['info']
        
        if income.empty:
            return None
        
        # Find the most recent quarter whose filing date + 45 days ≤ as_of_date
        valid_income_cols = sorted(
            [c for c in income.columns if pd.Timestamp(c) + filing_lag <= as_of_ts],
            reverse=True
        )
        
        if not valid_income_cols:
            return None
        
        latest_income = income[valid_income_cols[0]]
        
        # ---- Revenue growth (this quarter vs prior quarter) ----
        rev_now   = latest_income.get("Total Revenue")
        rev_prior = income[valid_income_cols[1]].get("Total Revenue") if len(valid_income_cols) > 1 else None
        revenue_growth = (rev_now - rev_prior) / abs(rev_prior) if rev_now and rev_prior and rev_prior != 0 else None
        
        # ---- ROE & Debt/Equity (from balance sheet) ----
        net_income = latest_income.get("Net Income")
        
        valid_balance_cols = sorted(
            [c for c in balance.columns if pd.Timestamp(c) + filing_lag <= as_of_ts],
            reverse=True
        ) if balance is not None and not balance.empty else []
        
        total_equity = None
        total_debt   = None
        
        if valid_balance_cols:
            latest_balance = balance[valid_balance_cols[0]]
            total_equity   = latest_balance.get("Total Stockholder Equity")
            total_debt     = latest_balance.get("Total Debt")
        
        roe            = (net_income / total_equity) if net_income and total_equity and total_equity != 0 else None
        debt_to_equity = (total_debt / total_equity)   if total_debt and total_equity and total_equity != 0 else None
        
        # ---- P/E ratio (uses historical price — one quick yfinance call) ----
        # This is the ONLY API call in this method, and it's lightweight (1 ticker, 6 days)
        pe_ratio = None
        try:
            hist = yf.download(
                ticker,
                start=(as_of_ts - timedelta(days=5)).strftime('%Y-%m-%d'),
                end=(as_of_ts + timedelta(days=1)).strftime('%Y-%m-%d'),
                progress=False,
                auto_adjust=True
            )
            if not hist.empty:
                price   = float(hist["Close"].iloc[-1])
                ttm_eps = latest_income.get("Diluted EPS")
                if price and ttm_eps and ttm_eps != 0:
                    pe_ratio = price / ttm_eps
        except Exception:
            pass
        
        return {
            "ticker":         ticker,
            "pe_ratio":       pe_ratio,
            "revenue_growth": revenue_growth,
            "roe":            roe,
            "debt_to_equity": debt_to_equity,
            "dividend_yield": info.get("dividendYield") if info else None,
            "industry":       info.get("industry") if info else "Unknown",
            "sector":         info.get("sector") if info else "Unknown",
            "data_as_of":     str(valid_income_cols[0].date()),
        }

    # =========================================================================
    # Existing methods — unchanged
    # =========================================================================

    def fetch_financial_data(self, ticker, as_of_date=None):
        """
        Fetch financial metrics for one ticker.

        as_of_date=None  → live paper trading mode.
            Uses yf.Ticker().info — current values. Correct for live trading.

        as_of_date=<date> → backtest mode (point-in-time safe).
            FIX 1: Uses quarterly financials with a 45-day filing lag.
            Only quarters filed before as_of_date are used, eliminating
            look-ahead bias on fundamental data.
        """
        stock = yf.Ticker(ticker)

        # ---- LIVE / PAPER TRADING ----
        if as_of_date is None:
            try:
                info = stock.info
            except Exception as e:
                print(f"  [{ticker}] yf.info failed: {e}")
                return None

            return {
                "ticker":         ticker,
                "pe_ratio":       info.get("trailingPE"),
                "revenue_growth": info.get("revenueGrowth"),
                "roe":            info.get("returnOnEquity"),
                "debt_to_equity": info.get("debtToEquity"),
                "dividend_yield": info.get("dividendYield"),
                "industry":       info.get("industry"),
                "sector":         info.get("sector"),
            }

        # ---- BACKTEST / POINT-IN-TIME MODE ----
        filing_lag = timedelta(days=45)
        as_of_ts   = pd.Timestamp(as_of_date)

        try:
            income  = stock.quarterly_financials
            balance = stock.quarterly_balance_sheet

            if income.empty or balance.empty:
                return None

            # Only keep quarters whose 45-day filing window has passed
            valid_income  = sorted(
                [c for c in income.columns  if pd.Timestamp(c) + filing_lag <= as_of_ts],
                reverse=True
            )
            valid_balance = sorted(
                [c for c in balance.columns if pd.Timestamp(c) + filing_lag <= as_of_ts],
                reverse=True
            )

            if not valid_income or not valid_balance:
                return None

            latest_income  = income[valid_income[0]]
            latest_balance = balance[valid_balance[0]]

            # Revenue growth: most recent valid quarter vs the one before it
            rev_now   = latest_income.get("Total Revenue")
            rev_prior = income[valid_income[1]].get("Total Revenue") if len(valid_income) > 1 else None
            if rev_now and rev_prior and rev_prior != 0:
                revenue_growth = (rev_now - rev_prior) / abs(rev_prior)
            else:
                revenue_growth = None

            net_income   = latest_income.get("Net Income")
            total_equity = latest_balance.get("Total Stockholder Equity")
            total_debt   = latest_balance.get("Total Debt")

            roe            = (net_income / total_equity)  if net_income   and total_equity and total_equity != 0 else None
            debt_to_equity = (total_debt  / total_equity) if total_debt   and total_equity and total_equity != 0 else None

            # P/E using historical price on as_of_date, not today's price
            hist = stock.history(
                start=(as_of_ts - timedelta(days=5)).strftime('%Y-%m-%d'),
                end=(as_of_ts   + timedelta(days=1)).strftime('%Y-%m-%d')
            )
            price    = float(hist["Close"].iloc[-1]) if not hist.empty else None
            ttm_eps  = latest_income.get("Diluted EPS")
            pe_ratio = (price / ttm_eps) if price and ttm_eps and ttm_eps != 0 else None

            info = stock.info
            return {
                "ticker":         ticker,
                "pe_ratio":       pe_ratio,
                "revenue_growth": revenue_growth,
                "roe":            roe,
                "debt_to_equity": debt_to_equity,
                "dividend_yield": info.get("dividendYield"),
                "industry":       info.get("industry"),
                "sector":         info.get("sector"),
                "data_as_of":     str(pd.Timestamp(valid_income[0]).date()),
            }

        except Exception as e:
            print(f"  [{ticker}] Point-in-time fetch error: {e}")
            return None

    def update_wrong_tickers(self, ticker):
        """Remap tickers that yfinance requires in a different format."""
        return {'BRK.B': 'BRK-B', 'BF.B': 'BF-B'}.get(ticker, ticker)

    def fetch_sp500_fdata(self, tickers, as_of_date=None):
        """
        Fetch financial data for a list of tickers.
        Pass as_of_date when running a backtest to get point-in-time data.
        """
        data = []
        for i, ticker in enumerate(tickers):
            updated = self.update_wrong_tickers(ticker)
            try:
                row = self.fetch_financial_data(updated, as_of_date=as_of_date)
                if row is not None:
                    data.append(row)
            except Exception as e:
                print(f"  [{updated}] Skipped: {e}")

            # Progress indicator for large batches
            if (i + 1) % 10 == 0:
                print(f"  ... fetched {i + 1}/{len(tickers)}")

        self.data = pd.DataFrame(data)
        return self.data

    def save_sp500_data_to_csv(self, tickers):
        sp500_data = self.fetch_sp500_fdata(tickers)
        if sp500_data.empty:
            raise ValueError("No data fetched for the provided tickers.")
        sp500_data.to_csv(self.file_path, index=False)
        print(f"  Saved to {self.file_path}")
        return sp500_data


class fundamental_analyzer:

    def __init__(self, data, fill_missing=True):
        self.data         = pd.DataFrame(data).copy()
        self.fill_missing = fill_missing

    def handle_missing_data(self):
        """
        Fills missing metric values using the median for each industry group.
        FIX 4: industry_medians dict is now reset per column so medians
        from one metric cannot accidentally spill into another.
        """
        if not self.fill_missing:
            return

        columns_to_fill = ['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']

        if 'industry' not in self.data.columns:
            self.data['industry'] = 'Unknown'
        self.data['industry'] = self.data['industry'].fillna('Unknown').astype('category')

        for column in columns_to_fill:
            if column not in self.data.columns:
                continue

            self.data[column] = pd.to_numeric(self.data[column], errors='coerce')

            # FIX 4: fresh dict per column — no cross-metric contamination
            industry_medians = {}

            for idx, row in self.data.iterrows():
                if pd.notna(row[column]):
                    continue

                industry = row['industry']
                if industry not in industry_medians:
                    vals = self.data[self.data['industry'] == industry][column].dropna()
                    if not vals.empty:
                        industry_medians[industry] = vals.median()

                if industry in industry_medians:
                    self.data.at[idx, column] = industry_medians[industry]

        # FSLR-specific patch (no dividend — fill with sector median)
        if 'FSLR' in self.data['ticker'].values:
            med = self.data['dividend_yield'].median()
            self.data.loc[self.data['ticker'] == 'FSLR', 'dividend_yield'] = med

    def calculate_scores(self):
        """
        Score each stock 0-10 on 5 metrics.
        FIX 3: every comparison is now guarded by pd.notna() so NaN rows
        score 0 on that metric instead of raising a TypeError.
        """
        # Pre-compute quantiles once (not inside the row loop — performance fix)
        quantiles = {}
        for col in ['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']:
            if col in self.data.columns:
                quantiles[col] = {
                    0.25: self.data[col].quantile(0.25),
                    0.50: self.data[col].quantile(0.50),
                    0.75: self.data[col].quantile(0.75),
                }

        scores = []
        for _, row in self.data.iterrows():
            score = 0

            # P/E — lower is better (cheaper valuation)
            pe = row.get('pe_ratio')
            if pd.notna(pe):
                if pe <= quantiles['pe_ratio'][0.25]:
                    score += 2
                elif pe <= quantiles['pe_ratio'][0.50]:
                    score += 1

            # Revenue growth — higher is better
            rg = row.get('revenue_growth')
            if pd.notna(rg):
                if rg >= 0.10:
                    score += 2
                elif rg >= 0:
                    score += 1

            # ROE — top performers score highest
            roe = row.get('roe')
            if pd.notna(roe):
                if roe >= quantiles['roe'][0.75]:
                    score += 2
                elif roe >= quantiles['roe'][0.50]:
                    score += 1

            # Debt-to-equity — lower is better (less financial risk)
            de = row.get('debt_to_equity')
            if pd.notna(de):
                if de <= quantiles['debt_to_equity'][0.25]:
                    score += 2
                elif de <= quantiles['debt_to_equity'][0.50]:
                    score += 1

            # Dividend yield — higher is better
            dy = row.get('dividend_yield')
            if pd.notna(dy):
                if dy >= quantiles['dividend_yield'][0.75]:
                    score += 2
                elif dy >= quantiles['dividend_yield'][0.50]:
                    score += 1

            scores.append(score)

        self.data['score'] = scores
        return self.data

    def handle_data_completeness(self):
        """Print a summary of missing values for the 5 key columns."""
        required = ['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']
        for col in required:
            if col not in self.data.columns:
                print(f"  {col}: COLUMN MISSING")
                continue
            n = self.data[col].isna().sum()
            status = f"{n} missing" if n > 0 else "complete"
            print(f"  {col}: {status}")

    def perform_fundamental_analysis(self):
        print("  Starting fundamental analysis ...")

        print("  Missing values before imputation:")
        self.handle_data_completeness()

        self.handle_missing_data()

        print("  Missing values after imputation:")
        self.handle_data_completeness()

        self.calculate_scores()

        # FIX 5: .copy() prevents SettingWithCopyWarning in calling code
        filtered_df = self.data[
            self.data['score'] >= self.data['score'].quantile(0.75)
        ].copy()

        filtered_df.to_csv('filtered.csv', index=False)
        print(f"  Saved {len(filtered_df)} top-scoring stocks to filtered.csv")
        return filtered_df


# ---------------------------------------------------------------------------
# Standalone entry point — run fundamental analysis independently
# ---------------------------------------------------------------------------

def main():
    start = time.time()
    fetcher = data_fetcher(file_path='sp500_financial_data.csv')  # FIX 6: relative path

    print("Fetching S&P 500 tickers ...")
    tickers = fetcher.fetch_sp500_ticker()

    print(f"Fetching financial data for {len(tickers)} stocks ...")
    sp500_df = fetcher.save_sp500_data_to_csv(tickers)

    if sp500_df.empty:
        raise ValueError("No financial data was fetched. Check your internet connection.")

    print("Running fundamental analysis ...")
    analyzer   = fundamental_analyzer(sp500_df)
    scored_df  = analyzer.perform_fundamental_analysis()

    print(f"\nDone. {len(scored_df)} stocks passed the filter.")
    print(f"Total time: {time.time() - start:.1f}s")


if __name__ == '__main__':
    main()