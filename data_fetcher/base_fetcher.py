"""
base_fetcher.py
================
Abstract base class for all fundamental data fetchers.

Defines the contract that any data source (SEC EDGAR, yfinance, etc.)
must follow to be used by the fundamental_analyzer.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import date


class BaseFetcher(ABC):
    """Abstract interface for fetching point-in-time fundamental data."""

    @abstractmethod
    def get_fundamentals(self, ticker: str, as_of_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch fundamental metrics for a single ticker.

        Parameters:
            ticker:      Stock symbol (e.g., 'AAPL').
            as_of_date:  The date for point-in-time data.
                         If None, return the most current available data (live/paper mode).

        Returns:
            Dictionary with keys:
                'ticker', 'pe_ratio', 'revenue_growth', 'roe',
                'debt_to_equity', 'dividend_yield', 'industry', 'sector'
            Returns None if no data is available.
        """
        pass
