"""
yfinance_fetcher.py
====================
yfinance implementation of BaseFetcher.
Used for live/paper trading (current data) and as a fallback.
"""

from datetime import timedelta, date
from typing import Optional, Dict, Any

import pandas as pd
import yfinance as yf

from .base_fetcher import BaseFetcher


class YFinanceFetcher(BaseFetcher):
    """yfinance implementation for live/paper trading and fallback."""

    def _fix_ticker(self, ticker: str) -> str:
        """Remap tickers that yfinance requires in a different format."""
        return {'BRK.B': 'BRK-B', 'BF.B': 'BF-B'}.get(ticker, ticker)

    def get_fundamentals(self, ticker: str, as_of_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch fundamentals from yfinance.
        - If as_of_date is None: uses .info (current data). Perfect for live/paper.
        - If as_of_date is provided: uses quarterly financials with 45-day lag (for backtest fallback).
        """
        stock = yf.Ticker(self._fix_ticker(ticker))

        # ---- LIVE / PAPER (no historical date) ----
        if as_of_date is None:
            try:
                info = stock.info
            except Exception:
                return None

            return {
                "ticker": ticker,
                "pe_ratio": info.get("trailingPE"),
                "revenue_growth": info.get("revenueGrowth"),
                "roe": info.get("returnOnEquity"),
                "debt_to_equity": info.get("debtToEquity"),
                "dividend_yield": info.get("dividendYield"),
                "industry": info.get("industry"),
                "sector": info.get("sector"),
            }

        # ---- BACKTEST / HISTORICAL (fallback, uses quarterly data) ----
        filing_lag = timedelta(days=45)
        as_of_ts = pd.Timestamp(as_of_date)

        try:
            income = stock.quarterly_financials
            balance = stock.quarterly_balance_sheet

            if income.empty or balance.empty:
                return None

            valid_income = sorted(
                [c for c in income.columns if pd.Timestamp(c) + filing_lag <= as_of_ts],
                reverse=True
            )
            valid_balance = sorted(
                [c for c in balance.columns if pd.Timestamp(c) + filing_lag <= as_of_ts],
                reverse=True
            )

            if not valid_income or not valid_balance:
                return None

            latest_income = income[valid_income[0]]
            latest_balance = balance[valid_balance[0]]

            rev_now = latest_income.get("Total Revenue")
            rev_prior = income[valid_income[1]].get("Total Revenue") if len(valid_income) > 1 else None
            revenue_growth = (rev_now - rev_prior) / abs(rev_prior) if rev_now and rev_prior and rev_prior != 0 else None

            net_income = latest_income.get("Net Income")
            total_equity = latest_balance.get("Total Stockholder Equity")
            total_debt = latest_balance.get("Total Debt")

            roe = (net_income / total_equity) if net_income and total_equity and total_equity != 0 else None
            debt_to_equity = (total_debt / total_equity) if total_debt and total_equity and total_equity != 0 else None

            hist = stock.history(
                start=(as_of_ts - timedelta(days=5)).strftime('%Y-%m-%d'),
                end=(as_of_ts + timedelta(days=1)).strftime('%Y-%m-%d')
            )
            price = float(hist["Close"].iloc[-1]) if not hist.empty else None
            ttm_eps = latest_income.get("Diluted EPS")
            pe_ratio = (price / ttm_eps) if price and ttm_eps and ttm_eps != 0 else None

            info = stock.info
            return {
                "ticker": ticker,
                "pe_ratio": pe_ratio,
                "revenue_growth": revenue_growth,
                "roe": roe,
                "debt_to_equity": debt_to_equity,
                "dividend_yield": info.get("dividendYield"),
                "industry": info.get("industry"),
                "sector": info.get("sector"),
            }

        except Exception:
            return None
