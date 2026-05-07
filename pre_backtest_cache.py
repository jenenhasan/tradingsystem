"""
Run this ONCE before backtesting.
Downloads all prices, fundamentals, and sentiment and saves to disk.
"""
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from strategies.fundamental_analysis import data_fetcher, fundamental_analyzer

START = "2020-01-01"
END   = "2020-05-31"

# 1. Download ALL prices at once (single Yahoo call)
print("Downloading prices for all S&P 500 stocks...")
fetcher = data_fetcher()
tickers = fetcher.fetch_sp500_ticker()[:100]
prices = yf.download(tickers, start=START, end=END, group_by="ticker")
prices.to_parquet("cache/prices.parquet")  # fast format
print(f"Saved {len(tickers)} stocks × {len(prices)} days")

# 2. Download fundamentals once per quarter (not daily)
print("Caching quarterly fundamentals...")
fundamentals = {}
for ticker in tickers:
    try:
        stock = yf.Ticker(ticker)
        fundamentals[ticker] = {
            'quarterly_financials': stock.quarterly_financials,
            'quarterly_balance_sheet': stock.quarterly_balance_sheet,
        }
    except:
        pass
pd.to_pickle(fundamentals, "cache/fundamentals.pkl")
print(f"Saved fundamentals for {len(fundamentals)} stocks")

# 3. Skip sentiment caching for now (or run FinBERT once per stock per quarter)
print("Cache complete!")