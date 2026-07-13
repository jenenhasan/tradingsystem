"""
fundamental_analyzer.py
========================
Scoring engine for fundamental data.

Takes a fetcher (any BaseFetcher implementation), fetches data for a list
of tickers, and computes a composite score (0-10) for each stock.
Filters to the top 25% scorers.

This class now does ZERO fetching – it delegates all data retrieval to the
injected fetcher.
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any
from datetime import date

from data_fetcher.base_fetcher import BaseFetcher


class FundamentalAnalyzer:
    """
    Scores stocks on 5 fundamental metrics using a quantile-based system.
    """

    def __init__(self, fetcher: BaseFetcher, fill_missing: bool = True):
        """
        Parameters:
            fetcher:      An instance of a class that implements BaseFetcher.
            fill_missing: Whether to impute missing values with industry medians.
        """
        self.fetcher = fetcher
        self.fill_missing = fill_missing
        self.data = None  # Will hold the raw DataFrame after fetching

    # ----------------------------------------------------------------------
    # Public method: fetch + score
    # ----------------------------------------------------------------------
    def analyze(self, tickers: List[str], as_of_date: Optional[date] = None) -> pd.DataFrame:
        """
        Fetch fundamentals for a list of tickers and return the scored, filtered DataFrame.

        Parameters:
            tickers:      List of stock symbols.
            as_of_date:   Date for point-in-time data. If None, fetches current data.

        Returns:
            DataFrame with columns: ticker, score, sector, industry, and raw metrics.
        """
        print(f"  Fetching fundamentals for {len(tickers)} stocks...")
        rows = []

        for i, ticker in enumerate(tickers):
            row = self.fetcher.get_fundamentals(ticker, as_of_date)
            if row is not None:
                rows.append(row)

            if (i + 1) % 10 == 0:
                print(f"    ... fetched {i + 1}/{len(tickers)}")

        if not rows:
            print("  ❌ No fundamental data retrieved.")
            return pd.DataFrame()

        self.data = pd.DataFrame(rows)
        print(f"  ✓ Fetched {len(self.data)}/{len(tickers)} tickers successfully.")

        # ---- Scoring pipeline ----
        print("  Starting fundamental analysis ...")
        self._handle_data_completeness()
        self._handle_missing_data()
        self._handle_data_completeness()
        self._calculate_scores()

        # Filter to top 25% based on score
        top_quantile = self.data['score'].quantile(0.75)
        filtered_df = self.data[self.data['score'] >= top_quantile].copy()

        filtered_df.to_csv('filtered.csv', index=False)
        print(f"  Saved {len(filtered_df)} top-scoring stocks to filtered.csv")
        return filtered_df

    # ----------------------------------------------------------------------
    # Private scoring logic (exactly as before, moved from original)
    # ----------------------------------------------------------------------
    def _handle_data_completeness(self):
        required = ['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']
        for col in required:
            if col not in self.data.columns:
                print(f"  {col}: COLUMN MISSING")
                continue
            n = self.data[col].isna().sum()
            status = f"{n} missing" if n > 0 else "complete"
            print(f"  {col}: {status}")

    def _handle_missing_data(self):
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

            # Fresh dict per column to avoid cross-contamination
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

        # FSLR-specific patch
        if 'FSLR' in self.data['ticker'].values:
            med = self.data['dividend_yield'].median()
            self.data.loc[self.data['ticker'] == 'FSLR', 'dividend_yield'] = med

    def _calculate_scores(self):
        # Pre-compute quantiles once
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

            pe = row.get('pe_ratio')
            if pd.notna(pe):
                if pe <= quantiles['pe_ratio'][0.25]:
                    score += 2
                elif pe <= quantiles['pe_ratio'][0.50]:
                    score += 1

            rg = row.get('revenue_growth')
            if pd.notna(rg):
                if rg >= 0.10:
                    score += 2
                elif rg >= 0:
                    score += 1

            roe = row.get('roe')
            if pd.notna(roe):
                if roe >= quantiles['roe'][0.75]:
                    score += 2
                elif roe >= quantiles['roe'][0.50]:
                    score += 1

            de = row.get('debt_to_equity')
            if pd.notna(de):
                if de <= quantiles['debt_to_equity'][0.25]:
                    score += 2
                elif de <= quantiles['debt_to_equity'][0.50]:
                    score += 1

            dy = row.get('dividend_yield')
            if pd.notna(dy):
                if dy >= quantiles['dividend_yield'][0.75]:
                    score += 2
                elif dy >= quantiles['dividend_yield'][0.50]:
                    score += 1

            scores.append(score)

        self.data['score'] = scores