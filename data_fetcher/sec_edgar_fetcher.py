"""
sec_edgar_fetcher.py
=====================
SEC EDGAR implementation of BaseFetcher.
Fetches point-in-time fundamental data from the SEC's XBRL API.

This is identical to your original sec_edgar_fetcher.py, but now wrapped in a class.
"""

import os
import json
import time
import pickle
import random
from datetime import timedelta, date
from typing import Optional, Dict, List, Any

import requests
import pandas as pd
import yfinance as yf

from .base_fetcher import BaseFetcher


# ---------------------------------------------------------------------------
# Config & Helpers (kept exactly as they were)
# ---------------------------------------------------------------------------

SEC_HEADERS = {"User-Agent": "TradingBotResearch jenenhasan77@gmail.com"}
CACHE_DIR = "cache/sec_edgar"
os.makedirs(CACHE_DIR, exist_ok=True)

_TICKER_TO_CIK: Optional[Dict[str, str]] = None


def _load_ticker_map() -> Dict[str, str]:
    global _TICKER_TO_CIK
    if _TICKER_TO_CIK is not None:
        return _TICKER_TO_CIK

    cache_path = os.path.join(CACHE_DIR, "ticker_cik_map.json")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            raw = json.load(f)
    else:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=SEC_HEADERS, timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()
        with open(cache_path, "w") as f:
            json.dump(raw, f)

    _TICKER_TO_CIK = {
        row["ticker"].upper(): str(row["cik_str"]).zfill(10)
        for row in raw.values()
    }
    return _TICKER_TO_CIK


def ticker_to_cik(ticker: str) -> Optional[str]:
    mapping = _load_ticker_map()
    t = ticker.upper()
    return mapping.get(t) or mapping.get(t.replace("-", "").replace(".", ""))


def fetch_company_facts(ticker: str) -> Optional[dict]:
    cik = ticker_to_cik(ticker)
    if cik is None:
        return None

    cache_path = os.path.join(CACHE_DIR, f"{cik}.pkl")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass

    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        time.sleep(0.15 + random.random() * 0.1)
        if resp.status_code != 200:
            return None
        facts = resp.json()
    except Exception:
        return None

    try:
        with open(cache_path, "wb") as f:
            pickle.dump(facts, f)
    except Exception:
        pass

    return facts


def _extract_tag_series(facts: dict, tag: str, unit: str = "USD") -> List[dict]:
    try:
        units = facts["facts"]["us-gaap"][tag]["units"][unit]
    except KeyError:
        return []

    out = []
    for item in units:
        if item.get("form") not in ("10-Q", "10-K"):
            continue
        if item.get("val") is None or item.get("filed") is None:
            continue
        out.append({
            "end": item.get("end"),
            "val": item.get("val"),
            "filed": item.get("filed"),
            "fp": item.get("fp"),
        })
    out.sort(key=lambda x: x["filed"], reverse=True)
    return out


def _most_recent_as_of(series: List[dict], as_of_date, lag_days: int) -> Optional[dict]:
    cutoff = pd.Timestamp(as_of_date) - timedelta(days=lag_days)
    for item in series:
        if pd.Timestamp(item["filed"]) <= cutoff:
            return item
    return None


_SECTOR_CACHE: Dict[str, dict] = {}


def _get_sector_industry(ticker: str) -> dict:
    if ticker in _SECTOR_CACHE:
        return _SECTOR_CACHE[ticker]
    try:
        info = yf.Ticker(ticker).info
        result = {"sector": info.get("sector", "Unknown"), "industry": info.get("industry", "Unknown")}
    except Exception:
        result = {"sector": "Unknown", "industry": "Unknown"}
    _SECTOR_CACHE[ticker] = result
    return result


# ---------------------------------------------------------------------------
# SEC EDGAR Fetcher Class
# ---------------------------------------------------------------------------

class SECEdgarFetcher(BaseFetcher):
    """SEC EDGAR implementation for point-in-time historical fundamentals."""

    def get_fundamentals(self, ticker: str, as_of_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch point-in-time fundamentals from SEC EDGAR.
        If as_of_date is None, returns the most recent filing (for live/paper).
        """
        # If no date is provided, use today's date (live/paper mode)
        if as_of_date is None:
            as_of_date = date.today()

        facts = fetch_company_facts(ticker)
        if facts is None:
            return None

        filing_lag_days = 2

        revenue_series = (
            _extract_tag_series(facts, "Revenues")
            or _extract_tag_series(facts, "RevenueFromContractWithCustomerExcludingAssessedTax")
            or _extract_tag_series(facts, "SalesRevenueNet")
        )
        net_income_series = _extract_tag_series(facts, "NetIncomeLoss")
        equity_series = _extract_tag_series(facts, "StockholdersEquity")
        liabilities_series = _extract_tag_series(facts, "Liabilities")
        eps_series = _extract_tag_series(facts, "EarningsPerShareDiluted", unit="USD/shares")

        latest_rev = _most_recent_as_of(revenue_series, as_of_date, filing_lag_days)
        if latest_rev is None:
            return None

        # Revenue growth
        prior_rev = None
        for item in revenue_series:
            if pd.Timestamp(item["filed"]) < pd.Timestamp(latest_rev["filed"]):
                prior_rev = item
                break
        revenue_growth = (
            (latest_rev["val"] - prior_rev["val"]) / abs(prior_rev["val"])
            if prior_rev and prior_rev["val"] not in (0, None) else None
        )

        latest_ni = _most_recent_as_of(net_income_series, as_of_date, filing_lag_days)
        latest_equity = _most_recent_as_of(equity_series, as_of_date, filing_lag_days)
        latest_debt = _most_recent_as_of(liabilities_series, as_of_date, filing_lag_days)
        latest_eps = _most_recent_as_of(eps_series, as_of_date, filing_lag_days)

        net_income = latest_ni["val"] if latest_ni else None
        total_equity = latest_equity["val"] if latest_equity else None
        total_debt = latest_debt["val"] if latest_debt else None

        roe = (net_income / total_equity) if net_income and total_equity else None
        debt_to_equity = (total_debt / total_equity) if total_debt and total_equity else None

        # P/E
        pe_ratio = None
        try:
            as_of_ts = pd.Timestamp(as_of_date)
            hist = yf.download(
                ticker,
                start=(as_of_ts - timedelta(days=5)).strftime("%Y-%m-%d"),
                end=(as_of_ts + timedelta(days=1)).strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
            if not hist.empty and latest_eps and latest_eps["val"]:
                price = float(hist["Close"].iat[0])
                pe_ratio = price / latest_eps["val"]
        except Exception:
            pass

        sector_info = _get_sector_industry(ticker)

        return {
            "ticker": ticker,
            "pe_ratio": pe_ratio,
            "revenue_growth": revenue_growth,
            "roe": roe,
            "debt_to_equity": debt_to_equity,
            "dividend_yield": None,  # SEC XBRL doesn't provide this reliably
            "industry": sector_info["industry"],
            "sector": sector_info["sector"],
        }