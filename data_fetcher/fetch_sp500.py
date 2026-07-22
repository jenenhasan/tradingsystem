"""
fetch_sp500.py
========================
Ticker provider for S&P 500 stocks.

This file now only provides the ticker list. All scoring logic has been
moved to fundamental_analyzer.py, and all data fetching logic has been
moved to data_fetcher/.
"""

import os
import numpy as np
import pandas as pd
import requests
import sys
import io
import logging

# Suppress yfinance noise (if any remains)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


class SP500Fetcher:
    """
    Minimal fetcher – only provides the S&P 500 ticker list.
    """

    def fetch_sp500_ticker(self, limit: int = None):
        """
        Scrapes the S&P 500 ticker list from Wikipedia.
        Falls back to cached tickers.csv if the scrape fails.
        """
        # First check if the cache exists
        if os.path.exists('tickers.csv'):
            tickers = list(np.loadtxt('tickers.csv', dtype=str))
            print(f"Loaded {len(tickers)} tickers from cached tickers.csv")
            if limit:
                return tickers[:limit]
            return tickers

        try:
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            headers = {"User-Agent": "Mozilla/5.0 (compatible; TradingBot/1.0; jenen@example.com)"}
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")

            # Suppress pandas HTML parser warnings
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            try:
                tables = pd.read_html(response.text)
            finally:
                sys.stderr = old_stderr

            df = None
            for table in tables:
                if 'Symbol' in table.columns:
                    df = table
                    break

            if df is None:
                raise ValueError('Symbol column not found')

            tickers = df['Symbol'].tolist()
            np.savetxt('tickers.csv', tickers, fmt="%s")
            print(f"  ✓ Scraped {len(tickers)} tickers from Wikipedia")
            if limit:
                return tickers[:limit]
            return tickers

        except Exception as e:
            print(f"  Wikipedia scrape failed: {e}")
            if os.path.exists('tickers.csv'):
                print('  Falling back to cached tickers.csv')
                return list(np.loadtxt('tickers.csv', dtype=str))
            raise RuntimeError(
                'Cannot fetch S&P 500 tickers and no cached tickers.csv found.'
            )
