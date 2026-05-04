import os
import sys
import time
import signal
import logging
import logging.handlers
import threading
import traceback
from datetime import datetime, timedelta, date
from typing import Optional, Tuple, Dict, List

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Guard optional imports early — give clear messages
# ---------------------------------------------------------------------------
try:
    from lumibot.brokers import Alpaca
    from lumibot.backtesting import YahooDataBacktesting
    from lumibot.strategies.strategy import Strategy
    from lumibot.traders import Trader
except ImportError as e:
    sys.exit(f"[FATAL] lumibot not installed: {e}\n  pip install lumibot")

try:
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import StockHistoricalDataClient
except ImportError as e:
    sys.exit(f"[FATAL] alpaca-py not installed: {e}\n  pip install alpaca-py")

try:
    import yfinance as yf
except ImportError as e:
    sys.exit(f"[FATAL] yfinance not installed: {e}\n  pip install yfinance")

from strategies.sentiment_analysis import estimate_sentiment
from strategies.fundamental_analysis import data_fetcher, fundamental_analyzer

# ---------------------------------------------------------------------------
# Environment — validate all vars before doing anything else
# ---------------------------------------------------------------------------
load_dotenv()

_REQUIRED_ENV = {
    "API_KEY":    "Your Alpaca API key",
    "API_SECRET": "Your Alpaca API secret",
    "BASE_URL":   "Alpaca base URL (e.g. https://paper-api.alpaca.markets)",
}

_missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
if _missing:
    lines = "\n".join(f"  {k}: {_REQUIRED_ENV[k]}" for k in _missing)
    sys.exit(f"[FATAL] Missing environment variables:\n{lines}\nCheck your .env file.")

API_KEY    = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
BASE_URL   = os.getenv("BASE_URL")

ALPACA_CREDS = {
    "API_KEY":    API_KEY,
    "API_SECRET": API_SECRET,
    "PAPER":      True,
}

# ---------------------------------------------------------------------------
# Structured logger — rotating JSON-line log file + console
# ---------------------------------------------------------------------------
def _build_logger(name: str = "trading_bot") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Console handler — INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                      datefmt="%Y-%m-%d %H:%M:%S"))

    # Rotating file handler — DEBUG and above, 5 MB × 5 files
    os.makedirs("logs", exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(
        "logs/trading_bot.log", maxBytes=5 * 1024 * 1024, backupCount=5,
        encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}',
        datefmt="%Y-%m-%dT%H:%M:%S"
    ))

    if not logger.handlers:
        logger.addHandler(ch)
        logger.addHandler(fh)

    return logger

LOG = _build_logger()

# ---------------------------------------------------------------------------
# Retry decorator — exponential backoff for external API calls
# ---------------------------------------------------------------------------
def retry(max_attempts: int = 3, base_delay: float = 1.0, exceptions=(Exception,)):
    """Decorator: retry on specified exceptions with exponential back-off."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        LOG.error(f'"retry exhausted","fn":"{fn.__name__}","error":"{exc}"')
                        raise
                    delay = base_delay * (2 ** (attempt - 1))
                    LOG.warning(f'"retry","fn":"{fn.__name__}","attempt":{attempt},"delay":{delay},"error":"{exc}"')
                    time.sleep(delay)
        return wrapper
    return decorator

# ---------------------------------------------------------------------------
# Fallback universe
# ---------------------------------------------------------------------------
FALLBACK_STOCKS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']
FALLBACK_SCORES = [5, 5, 5, 5, 5]


# ===========================================================================
# Strategy
# ===========================================================================
class trading_strategy(Strategy):

    # ── Configurable constants ───────────────────────────────────────────
    # Sentiment thresholds
    BUY_PROB_THRESHOLD   = 0.80
    BUY_SCORE_THRESHOLD  = 7
    SELL_PROB_THRESHOLD  = 0.80
    SELL_SCORE_THRESHOLD = 5

    # Risk management
    CASH_AT_RISK          = 0.02    # base risk per trade (2 %)
    STOP_LOSS_PCT         = 0.02    # hard stop-loss below entry price (2 %)
    MAX_PORTFOLIO_EQUITY  = 0.80    # max 80 % of portfolio in positions
    MAX_DRAWDOWN_HALT     = 0.15    # halt new buys if portfolio DD > 15 %

    # Position / trade limits
    MAX_POSITIONS         = 10
    MAX_TRADES_PER_DAY    = 5
    MAX_PER_ITERATION     = 3
    MAX_PER_SECTOR        = 3

    # Sizing / quality filters
    MAX_CORRELATION       = 0.70
    TARGET_VOLATILITY     = 0.02
    SLIPPAGE_BPS          = 5
    COMMISSION_PER_SHARE  = 0.01

    # Fundamental data cache TTL (seconds) — reload once per calendar day
    FUNDAMENTAL_CACHE_TTL = 82_800   # 23 hours

    # Heartbeat interval (seconds)
    HEARTBEAT_INTERVAL    = 60
    # ─────────────────────────────────────────────────────────────────────

    def initialize(self, cash_at_risk: float = None, mode: str = "paper"):

        self.preloaded_financials= None
        self.sleeptime   = "1H"
        self.mode        = mode
        self.cash_at_risk = cash_at_risk or self.CASH_AT_RISK

        # State — all mutations go through self._lock
        self._lock             = threading.Lock()
        self.last_trade        : Dict[str, str]    = {}
        self.entry_prices      : Dict[str, float]  = {}   # symbol → fill price
        self.symbol_to_score   : Dict[str, int]    = {}
        self.symbol_to_sector  : Dict[str, str]    = {}
        self.filtered_df       : Optional[pd.DataFrame] = None

        # Daily counters
        self.trades_today      = 0
        self.last_trade_date   : Optional[date]   = None

        # Fundamental cache control
        self._fund_cache_date  : Optional[date]   = None  # date fundamentals were last loaded
        self._fund_cache_ts    : float            = 0.0

        # Portfolio high-water mark for drawdown circuit breaker
        self._hwm              : float            = 0.0

        # Alpaca REST client (with retry)
        self._build_rest_client()

        # Graceful shutdown
        self._running = True

        LOG.info(f'"init","mode":"{self.mode}","risk_per_trade":{self.cash_at_risk},'
                 f'"max_positions":{self.MAX_POSITIONS},'
                 f'"stop_loss_pct":{self.STOP_LOSS_PCT},'
                 f'"max_dd_halt":{self.MAX_DRAWDOWN_HALT}')

        if self.mode != "backtest":
            self._start_heartbeat()
            LOG.info('"loading fundamental data (this takes ~1-2 min)..."')
            self.load_filtered_data()
            n = len(self.filtered_df) if self.filtered_df is not None else 0
            LOG.info(f'"bot ready","universe_size":{n}')

    # -----------------------------------------------------------------------
    # Alpaca REST — build with retry
    # -----------------------------------------------------------------------
    @retry(max_attempts=3, base_delay=2.0, exceptions=(Exception,))
    def _build_rest_client(self):
        self.trading_client = TradingClient(
        api_key=API_KEY, 
        secret_key=API_SECRET, 
        paper=True
        )
        self.data_client = StockHistoricalDataClient(
            api_key=API_KEY, 
            secret_key=API_SECRET
        )
    




    # -----------------------------------------------------------------------
    # Graceful shutdown
    # -----------------------------------------------------------------------
    def _shutdown_handler(self, signum, frame):
        LOG.info(f'"shutdown signal received","signum":{signum}')
        self._running = False
        # Lumibot will finish the current iteration and stop cleanly
        self.stop_trading()

    # -----------------------------------------------------------------------
    # Heartbeat thread — write a timestamp every 60 s so a watchdog process
    # or systemd can confirm the bot is alive
    # -----------------------------------------------------------------------
    def _start_heartbeat(self):
        os.makedirs("logs", exist_ok=True)

        def _beat():
            while self._running:
                try:
                    with open("logs/heartbeat.txt", "w") as f:
                        f.write(datetime.utcnow().isoformat() + "\n")
                except Exception as exc:
                    LOG.warning(f'"heartbeat write failed","error":"{exc}"')
                time.sleep(self.HEARTBEAT_INTERVAL)

        t = threading.Thread(target=_beat, daemon=True, name="heartbeat")
        t.start()
        LOG.info('"heartbeat thread started"')

    # -----------------------------------------------------------------------
    # Fundamental data — cached per calendar day
    # -----------------------------------------------------------------------
    def load_filtered_data(self, as_of_date: Optional[date] = None):
        """
        Fetch and cache S&P 500 fundamental scores.

        Paper:    as_of_date=None  → live .info
        Backtest: as_of_date=<date> → point-in-time quarterly data

        FIX 4: In backtest mode we only reload when the calendar date changes,
               not on every hourly iteration (was reloading ~6× per day).
        """
        target_date = as_of_date or date.today()

        with self._lock:
            # Skip reload if we already have today's data
            if self._fund_cache_date == target_date and self.filtered_df is not None:
                return

            try:
                try:
                    fetcher = data_fetcher()
                    tickers = fetcher.fetch_sp500_ticker()[:100]
                except Exception as exc:
                    LOG.warning(f'"sp500 ticker fetch failed","error":"{exc}","action":"using fallback"')
                    self._use_fallback_stocks()
                    return
                if self.mode == 'backtest':
                    if self.preloaded_financials is None : 
                        self.preload_financials_cache(tickers)
                    
                    tickers = self._filter_survivorship(tickers ,as_of_date)
                    rows = []
                    for ticker in tickers :
                        try :
                            row = fetcher.get_point_in_time_fundamentals(
                                ticker , as_of_date , self.preloaded_financials
                            )
                            if row is not None :
                                rows.append(row)

                        except Exception : 
                            pass
                    if not rows : 
                        LOG.warning(f'"no point-in-time data","date":"{as_of_date}"')
                        return 
                    
                    sp500_df = pd.DataFrame(rows)
                    LOG.info(f'"built from cache","rows":{len(rows)},"date":"{as_of_date}"')

                else:
                    LOG.info(f'"fetching live fundamentals","ticker_count":{len(tickers)}')
                    sp500_df = fetcher.fetch_sp500_fdata(tickers, as_of_date=None)
            
            # ── Rest is identical to original ──────────────────────
                if sp500_df is None or sp500_df.empty:
                    LOG.warning('"no fundamental data returned, using fallback"')
                    self._use_fallback_stocks()
                    return

                analyzer = fundamental_analyzer(sp500_df)
                result   = analyzer.perform_fundamental_analysis()

                if result is not None and not result.empty:
                    self.filtered_df      = result
                    self.symbol_to_score  = dict(zip(result['ticker'], result['score']))
                    self.symbol_to_sector = (
                        dict(zip(result['ticker'], result['sector']))
                        if 'sector' in result.columns else {})
                    self._fund_cache_date = target_date
                    self._fund_cache_ts   = time.time()
                    LOG.info(f'"fundamentals loaded","stock_count":{len(self.symbol_to_score)},'f'"as_of":"{target_date}"')
                else:
                    LOG.warning('"fundamental analysis returned empty, using fallback"')
                    self._use_fallback_stocks()

            except Exception as exc:
                LOG.error(f'"load_filtered_data error","error":"{exc}","traceback":"{traceback.format_exc()}"')
                self._use_fallback_stocks()

                

    def _preload_financials_cache(self, tickers):
        print("=" * 60)
        print("  ONE-TIME PRE-LOAD: Caching quarterly financials ...")
        print("  This takes 2-5 minutes but makes the backtest 100× faster.")
        print("=" * 60)
   
    
    
        fetcher = data_fetcher()
        self.preloaded_financials = fetcher.fetch_all_quarters_financials(tickers)
    
        loaded = len(self.preloaded_financials) if self.preloaded_financials else 0
        print(f"  ✓ Cached {loaded} tickers. Backtest will now run fast.")
        print("=" * 60)
               
    def _filter_survivorship(self, tickers: List[str], as_of_date: date) -> List[str]:
        """
        Remove tickers that had no price history in the 30 days before as_of_date.
        This is a pragmatic proxy for 'existed and was liquid at that date'.
        A production system would use a proper historical index membership dataset.
        """
        surviving = []
        start_str = (as_of_date - timedelta(days=30)).strftime('%Y-%m-%d')
        end_str   = as_of_date.strftime('%Y-%m-%d')

        for t in tickers:
            try:
                hist = yf.Ticker(t).history(start=start_str, end=end_str)
                if not hist.empty:
                    surviving.append(t)
            except Exception:
                pass  # skip tickers that error — conservative approach

        return surviving

    def _use_fallback_stocks(self):
        self.filtered_df      = pd.DataFrame({'ticker': FALLBACK_STOCKS, 'score': FALLBACK_SCORES})
        self.symbol_to_score  = dict(zip(FALLBACK_STOCKS, FALLBACK_SCORES))
        self.symbol_to_sector = {}
        self._fund_cache_date = date.today()
        LOG.warning(f'"fallback universe active","symbols":{FALLBACK_STOCKS}')

    def get_fundamental_score(self, symbol: str) -> int:
        return self.symbol_to_score.get(symbol, 5)

    def get_sector(self, symbol: str) -> str:
        return self.symbol_to_sector.get(symbol, "Unknown")

    # -----------------------------------------------------------------------
    # Portfolio metrics
    # -----------------------------------------------------------------------
    def _get_portfolio_value(self) -> float:
        """Total portfolio value: cash + market value of all positions."""
        try:
            cash = self.get_cash()
            positions = self.get_positions()
            equity = sum(
                p.quantity * self._last_close(p.symbol)
                for p in positions
            )
            return cash + equity
        except Exception as exc:
            LOG.warning(f'"portfolio_value error","error":"{exc}"')
            return self.get_cash()

    def _last_close(self, symbol: str) -> float:
        """Safe last close price fetch, returns 0.0 on failure."""
        try:
            bars = self.get_historical_prices(symbol, 2, "day")
            if bars is None or bars.df is None or bars.df.empty:
                return 0.0
            col = "close" if "close" in bars.df.columns else "Close"
            return float(bars.df[col].iloc[-1])
        except Exception:
            return 0.0

    def _equity_exposure(self) -> float:
        """Fraction of portfolio currently in open positions (0.0 – 1.0)."""
        total = self._get_portfolio_value()
        if total <= 0:
            return 0.0
        cash = self.get_cash()
        return 1.0 - (cash / total)

    def _is_in_drawdown_halt(self) -> bool:
        """
        FIX: Halt new buys if portfolio has dropped > MAX_DRAWDOWN_HALT
        below its high-water mark.
        """
        pv = self._get_portfolio_value()
        if pv > self._hwm:
            self._hwm = pv
        if self._hwm <= 0:
            return False
        drawdown = (self._hwm - pv) / self._hwm
        if drawdown > self.MAX_DRAWDOWN_HALT:
            LOG.warning(f'"drawdown halt","current_dd":{drawdown:.4f},'
                        f'"threshold":{self.MAX_DRAWDOWN_HALT},'
                        f'"portfolio_value":{pv:.2f},"hwm":{self._hwm:.2f}')
            return True
        return False

    # -----------------------------------------------------------------------
    # Market regime filter
    # -----------------------------------------------------------------------
    def is_bull_market(self) -> bool:
        """Return False if SPY is below its 200-day MA (bear regime)."""
        try:
            bars = self.get_historical_prices("SPY", 210, "day")
            if bars is None or bars.df is None or len(bars.df) < 200:
                return True  # insufficient data — assume bull

            col   = "close" if "close" in bars.df.columns else "Close"
            close = bars.df[col]
            ma200 = close.rolling(200).mean().iloc[-1]
            current = close.iloc[-1]
            is_bull = bool(current > ma200)
            LOG.debug(f'"regime_check","spy_close":{current:.2f},"ma200":{ma200:.2f},"is_bull":{is_bull}')
            return is_bull
        except Exception as exc:
            LOG.warning(f'"regime_check error","error":"{exc}","defaulting_to":true')
            return True

    # -----------------------------------------------------------------------
    # Stop-loss check
    # -----------------------------------------------------------------------
    def _check_stop_losses(self, existing_positions) -> int:
        """
        FIX 1: Hard stop-loss check — independent of sentiment signals.
        Sells any position whose current price is more than STOP_LOSS_PCT
        below the recorded entry price.
        Returns number of stop-loss orders submitted.
        """
        stops_fired = 0
        for pos in existing_positions:
            symbol = pos.symbol
            entry  = self.entry_prices.get(symbol)
            if entry is None or entry <= 0:
                continue

            current = self._last_close(symbol)
            if current <= 0:
                continue

            loss_pct = (entry - current) / entry
            if loss_pct >= self.STOP_LOSS_PCT:
                try:
                    order = self.create_order(symbol, pos.quantity, "sell",
                                              type="market")
                    self.submit_order(order)
                    LOG.warning(
                        f'"stop_loss_fired","symbol":"{symbol}",'
                        f'"entry":{entry:.4f},"current":{current:.4f},'
                        f'"loss_pct":{loss_pct:.4f},"qty":{pos.quantity}'
                    )
                    with self._lock:
                        self.entry_prices.pop(symbol, None)
                    stops_fired += 1
                except Exception as exc:
                    LOG.error(f'"stop_loss_submit_error","symbol":"{symbol}","error":"{exc}"')

        return stops_fired

    # -----------------------------------------------------------------------
    # Correlation check
    # -----------------------------------------------------------------------
    def is_too_correlated(self, symbol: str, existing_positions) -> bool:
        if not existing_positions:
            return False

        all_symbols = [p.symbol for p in existing_positions] + [symbol]
        closes: Dict[str, pd.Series] = {}

        for s in all_symbols:
            try:
                bars = self.get_historical_prices(s, 61, "day")
                if bars is None or bars.df is None or len(bars.df) < 30:
                    return False
                col = "close" if "close" in bars.df.columns else "Close"
                closes[s] = bars.df[col]
            except Exception:
                return False  # not enough data — allow trade conservatively

        df = pd.DataFrame(closes).pct_change().dropna().corr()

        for held in existing_positions:
            if held.symbol in df.index and symbol in df.columns:
                corr_val = df.loc[held.symbol, symbol]
                if corr_val > self.MAX_CORRELATION:
                    LOG.debug(f'"correlation_skip","symbol":"{symbol}",'
                              f'"correlated_with":"{held.symbol}","corr":{corr_val:.4f}')
                    return True
        return False

    # -----------------------------------------------------------------------
    # Position sizing — volatility-adjusted, exposure-capped
    # -----------------------------------------------------------------------
    def position_sizing(self, symbol: str) -> Tuple[float, float, int]:
        """
        Returns (cash_available, fill_price, quantity).

        Improvements over original:
        - FIX 9:  Enforces MAX_PORTFOLIO_EQUITY cap before sizing
        - FIX 16: Volatility multiplier clipped more conservatively (0.5x – 1.5x)
        - Uses prior completed bar close (T-1) — no look-ahead
        """
        cash = self.get_cash()
        if cash < 1_000:
            return cash, 0.0, 0

        # Portfolio exposure cap
        if self._equity_exposure() >= self.MAX_PORTFOLIO_EQUITY:
            LOG.info(f'"exposure_cap_hit","exposure":{self._equity_exposure():.2%},'
                     f'"max":{self.MAX_PORTFOLIO_EQUITY:.2%}')
            return cash, 0.0, 0

        try:
            bars = self.get_historical_prices(symbol, 22, "day")
            if bars is None or bars.df is None or len(bars.df) < 22:
                return cash, 0.0, 0

            df  = bars.df
            col = "close" if "close" in df.columns else "Close"

            # T-1 close (second-to-last row — last row is the unfinished bar)
            last_price = float(df[col].iloc[-2])
            if last_price <= 0:
                return cash, 0.0, 0

            # Volatility adjustment (tighter cap for safety)
            returns    = df[col].pct_change().dropna()
            volatility = float(returns.std())
            risk_mult  = self.TARGET_VOLATILITY / max(volatility, 0.005)
            risk_mult  = float(np.clip(risk_mult, 0.5, 1.5))   # tighter than original

            adjusted_risk = self.cash_at_risk * risk_mult
            quantity      = max(1, int((cash * adjusted_risk) / last_price))

            # Slippage — pay slightly above mid for buys
            slippage_pct = self.SLIPPAGE_BPS / 10_000
            fill_price   = last_price * (1 + slippage_pct)

            # Commission check
            est_commission = quantity * self.COMMISSION_PER_SHARE
            available      = cash - est_commission
            if available < fill_price:
                quantity = max(1, int(available / fill_price))

            LOG.debug(
                f'"size","symbol":"{symbol}","price":{last_price:.4f},'
                f'"fill":{fill_price:.4f},"vol":{volatility:.6f},'
                f'"risk_mult":{risk_mult:.4f},"qty":{quantity}'
            )
            return cash, fill_price, quantity

        except Exception as exc:
            LOG.error(f'"position_sizing error","symbol":"{symbol}","error":"{exc}"')
            return cash, 0.0, 0

    # -----------------------------------------------------------------------
    # Sentiment — with retry
    # -----------------------------------------------------------------------
    def get_dates(self) -> Tuple[str, str]:
        today      = self.get_datetime().date()
        end_date   = today - timedelta(days=1)   # T-1 (no look-ahead)
        start_date = today - timedelta(days=4)
        return str(start_date), str(end_date)

    # @retry(max_attempts=3, base_delay=1.0, exceptions=(Exception,))
    # def _fetch_news(self, symbol: str, start: str, end: str) -> list:
    #     news = self.api.get_news(symbol=symbol, start=start, end=end)
    #     return [ev.__dict__["_raw"]["headline"] for ev in news] if news else []

    def get_sentiment(self, symbol: str) -> Tuple[float, str]:
        try:
            start, end = self.get_dates()
            headlines = self._fetch_news_v2(symbol, start, end)
        
            if headlines:
                LOG.debug(
                    f'"news","symbol":"{symbol}","window":"{start}→{end}",'
                    f'"count":{len(headlines)}'
                )
                return estimate_sentiment(headlines)

        except Exception as exc:
            LOG.warning(f'"sentiment error","symbol":"{symbol}","error":"{exc}"')

        return 0.0, "neutral"


        # -------------------------------------------------------------------
    # NEW: News fetch using alpaca-py
    # -------------------------------------------------------------------
    def _fetch_news_v2(self, symbol: str, start: str, end: str) -> list:
        """
        Fetch news headlines using alpaca-py's REST client.
        Returns list of headline strings. Falls back to empty list on error.
        """
        try:
            from alpaca.common.rest import RESTClient
            
            news_client = RESTClient(
                base_url='https://data.alpaca.markets',
                api_version='v1beta1',
                api_key=API_KEY,
                secret_key=API_SECRET,
            )
            
            response = news_client.get(
                '/news',
                {'symbols': symbol, 'start': start, 'end': end}
            )
            
            # Extract headlines from the response
            headlines = []
            if hasattr(response, 'news') and response.news:
                for article in response.news:
                    if hasattr(article, 'headline'):
                        headlines.append(article.headline)
            elif isinstance(response, dict) and 'news' in response:
                for article in response['news']:
                    if 'headline' in article:
                        headlines.append(article['headline'])
            
            return headlines
            
        except Exception as e:
            LOG.warning(f'"news fetch v2 error","symbol":"{symbol}","error":"{e}"')
            return []

    # -----------------------------------------------------------------------
    # Daily PnL summary
    # -----------------------------------------------------------------------
    def _log_daily_summary(self):
        pv    = self._get_portfolio_value()
        cash  = self.get_cash()
        pct   = self._equity_exposure()
        pos_n = len(self.get_positions())
        LOG.info(
            f'"daily_summary","portfolio_value":{pv:.2f},'
            f'"cash":{cash:.2f},"equity_exposure":{pct:.2%},'
            f'"open_positions":{pos_n},"trades_today":{self.trades_today},'
            f'"hwm":{self._hwm:.2f}'
        )

    # -----------------------------------------------------------------------
    # Main trading loop
    # -----------------------------------------------------------------------
    def on_trading_iteration(self):
        if not self._running:
            return

        today = self.get_datetime().date()

        # Reset daily trade counter
        if self.last_trade_date != today:
            if self.last_trade_date is not None:
                self._log_daily_summary()
            self.trades_today    = 0
            self.last_trade_date = today

        # FIX 4: Only reload fundamentals when the date changes (not every hour)
        if self.mode == "backtest":
            self.load_filtered_data(as_of_date=today)

        # ── Hard guards ──────────────────────────────────────────────────
        if self.trades_today >= self.MAX_TRADES_PER_DAY:
            return

        if self.filtered_df is None or self.filtered_df.empty:
            LOG.warning('"no universe — skipping iteration"')
            return

        if self.get_cash() < 1_000:
            LOG.info(f'"low cash skip","cash":{self.get_cash():.2f}')
            return

        if len(self.get_positions()) >= self.MAX_POSITIONS:
            LOG.info('"max positions held — skipping buys"')
            # Still run stop-loss check even at max positions
            existing = self.get_positions()
            self._check_stop_losses(existing)
            return

        # ── Market regime & drawdown guards ──────────────────────────────
        is_bull      = self.is_bull_market()
        in_dd_halt   = self._is_in_drawdown_halt()

        if not is_bull:
            LOG.info('"bear market — buy signals disabled"')
        if in_dd_halt:
            LOG.warning('"drawdown halt active — no new buys"')

        existing_positions = self.get_positions()

        # ── Stop-loss sweep (always runs regardless of regime) ────────────
        self._check_stop_losses(existing_positions)

        # Sector concentration for current portfolio
        sector_counts: Dict[str, int] = {}
        for pos in existing_positions:
            sec = self.get_sector(pos.symbol)
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

        trades_made = 0

        for symbol in self.filtered_df['ticker'].tolist():
            if trades_made >= self.MAX_PER_ITERATION:
                break
            if self.trades_today >= self.MAX_TRADES_PER_DAY:
                break

            try:
                cash, last_price, quantity = self.position_sizing(symbol)
                if last_price <= 0 or quantity <= 0 or cash < last_price:
                    continue

                fundamental_score      = self.get_fundamental_score(symbol)
                probability, sentiment = self.get_sentiment(symbol)
                stock_sector           = self.get_sector(symbol)

                LOG.info(
                    f'"decision","date":"{today}","symbol":"{symbol}",'
                    f'"sentiment":"{sentiment}","prob":{probability:.4f},'
                    f'"score":{fundamental_score},"sector":"{stock_sector}",'
                    f'"price":{last_price:.4f},"bull":{is_bull}'
                )

                # ── BUY ──────────────────────────────────────────────────
                if (sentiment == "positive"
                        and probability > self.BUY_PROB_THRESHOLD
                        and fundamental_score >= self.BUY_SCORE_THRESHOLD
                        and is_bull
                        and not in_dd_halt):

                    position = self.get_position(symbol)

                    if sector_counts.get(stock_sector, 0) >= self.MAX_PER_SECTOR:
                        LOG.info(f'"sector_full","symbol":"{symbol}","sector":"{stock_sector}"')
                        continue

                    if self.is_too_correlated(symbol, existing_positions):
                        LOG.info(f'"correlation_skip","symbol":"{symbol}"')
                        continue

                    if position is None or position.quantity == 0:
                        order = self.create_order(
                            symbol, quantity, "buy",
                            type="limit", limit_price=round(last_price, 2)
                        )
                        self.submit_order(order)

                        with self._lock:
                            self.last_trade[symbol]  = "buy"
                            self.entry_prices[symbol] = last_price  # record for stop-loss

                        self.trades_today  += 1
                        trades_made        += 1
                        sector_counts[stock_sector] = sector_counts.get(stock_sector, 0) + 1

                        LOG.info(
                            f'"buy","symbol":"{symbol}","qty":{quantity},'
                            f'"price":{last_price:.4f},"score":{fundamental_score},'
                            f'"sentiment_prob":{probability:.4f},"sector":"{stock_sector}"'
                        )
                        print(
                            f"  ✅ BUY  {symbol:6s} | {quantity:4d} sh "
                            f"@ ${last_price:8.2f} | score={fundamental_score} "
                            f"| {sentiment} {probability:.2%} | {stock_sector}"
                        )

                # ── SELL (signal-driven) ─────────────────────────────────
                elif (sentiment == "negative"
                        and probability > self.SELL_PROB_THRESHOLD
                        and fundamental_score <= self.SELL_SCORE_THRESHOLD):

                    position = self.get_position(symbol)
                    if position is not None and position.quantity > 0:
                        order = self.create_order(
                            symbol, position.quantity, "sell",
                            type="limit", limit_price=round(last_price, 2)
                        )
                        self.submit_order(order)

                        with self._lock:
                            self.last_trade[symbol] = "sell"
                            self.entry_prices.pop(symbol, None)

                        self.trades_today += 1
                        trades_made       += 1

                        LOG.info(
                            f'"sell_signal","symbol":"{symbol}","qty":{position.quantity},'
                            f'"price":{last_price:.4f},"score":{fundamental_score},'
                            f'"sentiment_prob":{probability:.4f}'
                        )
                        print(
                            f"  ❌ SELL {symbol:6s} | {position.quantity:4d} sh "
                            f"@ ${last_price:8.2f} | score={fundamental_score} "
                            f"| {sentiment} {probability:.2%}"
                        )

            except Exception as exc:
                LOG.error(
                    f'"iteration error","symbol":"{symbol}",'
                    f'"error":"{exc}","traceback":"{traceback.format_exc()}"'
                )
                continue

    # -----------------------------------------------------------------------
    # Crash handler
    # -----------------------------------------------------------------------
    def on_bot_crash(self, error):
        LOG.critical(f'"bot crash","error":"{error}","traceback":"{traceback.format_exc()}"')
        self._log_daily_summary()
        super().on_bot_crash(error)


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "paper"

    LOG.info(f'"startup","mode":"{mode}","api_key_present":{API_KEY is not None},'
             f'"base_url":"{BASE_URL}"')

    print("=" * 65)
    print("  SENTIMENT + FUNDAMENTALS TRADING BOT  (Professional Edition)")
    print("=" * 65)
    print(f"  Mode:    {mode.upper()}")
    print(f"  API Key: {'✓ loaded' if API_KEY else '✗ MISSING'}")
    print(f"  URL:     {BASE_URL}")
    print("=" * 65)

    if mode == "backtest":
        # ── BACKTEST ─────────────────────────────────────────────────────
        start_date = datetime(2020, 1, 1)
        end_date   = datetime(2020, 5, 31)

        print(f"  Backtest window: {start_date.date()} → {end_date.date()}")
        print(f"  Data source:     Yahoo Finance")
        print("=" * 65)

        strategy = trading_strategy(
            name='mlstrat',
            broker=Alpaca(ALPACA_CREDS),
            parameters={"cash_at_risk": 0.02, "mode": "backtest"}
        )

        result = strategy.backtest(
            YahooDataBacktesting,
            start_date,
            end_date,
            parameters={"mode": "backtest"}
        )

        # ── SPY Benchmark ────────────────────────────────────────────────
        print("\n" + "=" * 65)
        print("  BENCHMARK COMPARISON")
        print("=" * 65)

        spy = yf.download("SPY", start=start_date, end=end_date, progress=False)
        if not spy.empty:
            spy_col    = "Close" if "Close" in spy.columns else spy.columns[0]
            spy_return = float((spy[spy_col].iloc[-1] / spy[spy_col].iloc[0]) - 1)
            print(f"  SPY Return:   {spy_return:+.2%}")
        else:
            spy_return = None
            print("  SPY data unavailable")

        if result is not None:
            strat_return = getattr(result, 'total_return',   None)
            sharpe       = getattr(result, 'sharpe_ratio',   None)
            max_dd       = getattr(result, 'max_drawdown',   None)
            cagr         = getattr(result, 'cagr',           None)

            print(f"  Strategy Return: {strat_return:+.2%}" if strat_return is not None else "  Return: N/A")
            print(f"  Sharpe Ratio:    {sharpe:.4f}"         if sharpe       is not None else "  Sharpe: N/A")
            print(f"  Max Drawdown:    {max_dd:+.2%}"        if max_dd       is not None else "  Max DD: N/A")
            print(f"  CAGR:            {cagr:+.2%}"          if cagr         is not None else "  CAGR:   N/A")

            if strat_return is not None and spy_return is not None:
                alpha = strat_return - spy_return
                print(f"  Alpha vs SPY:    {alpha:+.2%}")
                if alpha > 0:
                    print("  ✅ Strategy outperformed SPY")
                else:
                    print("  ⚠️  Strategy underperformed SPY")

        print("=" * 65)

        LOG.info(
            f'"backtest_complete","spy_return":{spy_return},'
            f'"strat_return":{strat_return},'
            f'"sharpe":{sharpe},"max_dd":{max_dd}'
        )

    else:
        # ── PAPER TRADING ────────────────────────────────────────────────
        print("  Mode: PAPER TRADING  (no real money at risk)")
        print("  Logs: ./logs/trading_bot.log  (rotating, 5 MB × 5)")
        print("  Heartbeat: ./logs/heartbeat.txt  (updated every 60 s)")
        print("=" * 65)

        broker   = Alpaca(ALPACA_CREDS)
        strategy = trading_strategy(
            name='paper_trading_bot',
            broker=broker,
            parameters={"cash_at_risk": 0.02, "mode": "paper"}
        )

        trader = Trader()
        trader.add_strategy(strategy)
        trader.run_all()


"""

┌──────────────────────────────────────────────────────────────┐
│                      trading.py                              │
│                                                              │
│  python trading.py paper          python trading.py backtest │
│         │                                   │                │
│         ▼                                   ▼                │
│    Live Alpaca                          Historical test      │
│         │                                   │                │
│         └───────────────┬───────────────────┘                │
│                         ▼                                    │
│              load_filtered_data()                            │
│                         │                                    │
│         ┌───────────────┼───────────────┐                    │
│         ▼                               ▼                    │
│    Paper Mode                      Backtest Mode             │
│  (as_of_date=None)              (as_of_date=today)           │
│         │                               │                    │
│         ▼                               ▼                    │
│  fundamental_analysis.py        First day: pre-load cache    │
│  fetch_sp500_fdata()            Every day: read from cache   │
│  → live .info API               → get_point_in_time_...()   │
│                                  → ZERO additional API calls │
│                         │                                    │
│                         ▼                                    │
│              fundamental_analyzer                            │
│              → scores 0-10                                   │
│              → top 25% = filtered.csv                        │
│                         │                                    │
│                         ▼                                    │
│              on_trading_iteration()                          │
│              → every 1 hour (paper)                          │
│              → every day (backtest)                          │
│                         │                                    │
│         ┌───────────────┼───────────────┐                    │
│         ▼               ▼               ▼                    │
│   sentiment       fundamentals       risk checks             │
│   (FinBERT)       (score 0-10)     (stop-loss, DD,           │
│         │               │          correlation, etc.)        │
│         └───────┬───────┘                    │                │
│                 ▼                            │                │
│          BUY if: positive + >0.8 + score≥7  │                │
│          SELL if: negative + >0.8 + score≤5 │                │
│          (plus all risk guards passed)      │                │
└──────────────────────────────────────────────────────────────┘

"""