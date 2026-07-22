"""
persistence/repository.py
============================
Replaces db_logger.py's free-function style with a `Repository` class.
Behavior is unchanged from db_logger.py — every method here does the
same INSERT/UPDATE/SELECT as before — but connection open/commit/close/
error-logging is now written ONCE (`_run`) instead of being repeated at
the top and bottom of every function. That was the actual duplication
in the old file: every function had its own
`conn = get_connection(); cur = conn.cursor(); ...; conn.commit(); cur.close(); conn.close()`
try/except block copy-pasted seven times.

Usage
-----
    from persistence.repository import Repository
    repo = Repository()
    repo.log_trade("AAPL", "BUY", 10, 150.0)
    positions = repo.get_all_positions()
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from persistence.db import get_connection
from infra.logger import LOG


class Repository:
    """Single point of contact for all trade/position/bot-state persistence."""

    # ── shared connection-management helper ─────────────────────────
    def _run(self, label: str, fn, default=None):
        """
        Open a connection, hand a live cursor to `fn(cur)`, commit, close,
        and return whatever `fn` returned. On any exception: log it the
        same way db_logger.py did and return `default` instead of raising
        — callers (the trading loop) should never crash because a DB
        write failed.
        """
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            result = fn(cur)
            conn.commit()
            cur.close()
            return result
        except Exception as e:
            LOG.error(f'"DB {label} error","error":"{e}"')
            return default
        finally:
            if conn is not None:
                conn.close()

    # ── Trades ────────────────────────────────────────────────────────
    def log_trade(self, symbol, action, quantity, price, sentiment=None,
                  sentiment_prob=None, fundamental_score=None, sector=None):
        def _fn(cur):
            cur.execute("""
                INSERT INTO trades
                (symbol, action, quantity, price, sentiment, sentiment_prob, fundamental_score, sector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (symbol, action, quantity, price, sentiment, sentiment_prob, fundamental_score, sector))
        self._run("log_trade", _fn)

    # ── Portfolio snapshots ──────────────────────────────────────────
    def log_portfolio_snapshot(self, portfolio_value, cash, equity_exposure,
                                open_positions, trades_today):
        def _fn(cur):
            cur.execute("""
                INSERT INTO portfolio_snapshots
                (portfolio_value, cash, equity_exposure, open_positions, trades_today)
                VALUES (%s, %s, %s, %s, %s)
            """, (portfolio_value, cash, equity_exposure, open_positions, trades_today))
        self._run("log_portfolio_snapshot", _fn)

    # ── Positions ─────────────────────────────────────────────────────
    def upsert_position(self, symbol, quantity, entry_price, current_price=None,
                         sector=None, fundamental_score=None, entry_date=None,
                         peak_price=None):
        """
        Insert or update a position row.

        IMPORTANT: entry_date is intentionally excluded from the
        ON CONFLICT ... DO UPDATE SET clause. It should be written once,
        on the initial buy, and never overwritten by later calls (e.g.
        the peak-price-tracking calls made every iteration). Overwriting
        it on every update would reset MAX_HOLD_DAYS tracking constantly.

        On the very first insert, if entry_date is None, we default to
        now() so the holding-period clock still starts somewhere sane.
        """
        if entry_date is None:
            entry_date = datetime.utcnow()

        def _fn(cur):
            cur.execute("""
                INSERT INTO positions
                (symbol, quantity, entry_price, current_price, sector, fundamental_score,
                 entry_date, peak_price)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    current_price = EXCLUDED.current_price,
                    sector = EXCLUDED.sector,
                    fundamental_score = EXCLUDED.fundamental_score,
                    peak_price = EXCLUDED.peak_price,
                    updated_at = CURRENT_TIMESTAMP
            """, (symbol, quantity, entry_price, current_price, sector, fundamental_score,
                  entry_date, peak_price))
        self._run("upsert_position", _fn)

    def update_peak_price(self, symbol, peak_price, current_price=None):
        """
        Lightweight update for just the peak price (and optionally current
        price), called every iteration as prices move. Does NOT touch
        entry_date, entry_price, quantity, sector, or fundamental_score.
        """
        def _fn(cur):
            if current_price is not None:
                cur.execute("""
                    UPDATE positions
                    SET peak_price = %s, current_price = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s
                """, (peak_price, current_price, symbol))
            else:
                cur.execute("""
                    UPDATE positions
                    SET peak_price = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s
                """, (peak_price, symbol))
        self._run("update_peak_price", _fn)

    def remove_position(self, symbol):
        def _fn(cur):
            cur.execute("DELETE FROM positions WHERE symbol = %s", (symbol,))
        self._run("remove_position", _fn)

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """
        Get all currently open positions from the database.
        Used for state reconciliation on bot restart.

        Returns a list of dicts, e.g.:
        [{'symbol': 'AAPL', 'quantity': 10, 'entry_price': 150.0,
          'current_price': 155.0, 'sector': 'Technology',
          'fundamental_score': 0.72,
          'entry_date': datetime(2024, 1, 1, ...),
          'peak_price': 158.0}, ...]

        entry_date comes back as a native Python datetime (psycopg2
        converts TIMESTAMP columns automatically) — no manual string
        parsing needed. Call .date() on it if you need a date object.
        """
        def _fn(cur):
            cur.execute("""
                SELECT symbol, quantity, entry_price, current_price, sector,
                       fundamental_score, entry_date, peak_price
                FROM positions
                WHERE quantity > 0
            """)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in rows]
        return self._run("get_all_positions", _fn, default=[])

    # ── High water mark (HWM) persistence ────────────────────────────
    def update_hwm(self, hwm: float) -> None:
        """
        Store high water mark in the dedicated bot_state table (separate
        from portfolio_snapshots so this doesn't corrupt portfolio
        history with fake zero rows).
        """
        def _fn(cur):
            cur.execute("""
                INSERT INTO bot_state (key, value, updated_at)
                VALUES ('hwm', %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET 
                    value = EXCLUDED.value, 
                    updated_at = CURRENT_TIMESTAMP
            """, (hwm,))
        self._run("update_hwm", _fn)

    def get_latest_hwm(self) -> Optional[float]:
        def _fn(cur):
            cur.execute("SELECT value FROM bot_state WHERE key = 'hwm'")
            row = cur.fetchone()
            return row[0] if row else None
        return self._run("get_latest_hwm", _fn, default=None)

    # ── Generic bot state (future use) ───────────────────────────────
    def update_bot_state(self, key: str, value: float) -> None:
        def _fn(cur):
            cur.execute("""
                INSERT INTO bot_state (key, value, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET 
                    value = EXCLUDED.value, 
                    updated_at = CURRENT_TIMESTAMP
            """, (key, value))
        self._run(f"update_bot_state[{key}]", _fn)

    def get_bot_state(self, key: str) -> Optional[float]:
        def _fn(cur):
            cur.execute("SELECT value FROM bot_state WHERE key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else None
        return self._run(f"get_bot_state[{key}]", _fn, default=None)

    # ── Dashboard read queries ────────────────────────────────────────
    # These replace dashboard/app.py's old ad-hoc `query()` helper so
    # every DB access in the whole project — bot writes and dashboard
    # reads alike — goes through this one class / one connection
    # strategy (`_run`), instead of the dashboard having its own
    # separate open/execute/close pattern.
    def _dict_rows(self, cur) -> List[Dict[str, Any]]:
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in rows]

    def get_latest_snapshot(self) -> Dict[str, Any]:
        def _fn(cur):
            cur.execute("SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT 1")
            rows = self._dict_rows(cur)
            return rows[0] if rows else {}
        return self._run("get_latest_snapshot", _fn, default={})

    def get_trades_today_count(self, today) -> int:
        def _fn(cur):
            cur.execute("SELECT COUNT(*) FROM trades WHERE DATE(timestamp) = %s", (today,))
            row = cur.fetchone()
            return row[0] if row else 0
        return self._run("get_trades_today_count", _fn, default=0)

    def get_pnl_today(self, today) -> float:
        def _fn(cur):
            cur.execute("""
                SELECT 
                    SUM(CASE WHEN action='BUY' THEN -price*quantity 
                             WHEN action='SELL' THEN price*quantity END) as pnl
                FROM trades WHERE DATE(timestamp) = %s
            """, (today,))
            row = cur.fetchone()
            return round(row[0], 2) if row and row[0] is not None else 0
        return self._run("get_pnl_today", _fn, default=0)

    def get_recent_trades(self, limit: int = 5) -> List[Dict[str, Any]]:
        def _fn(cur):
            cur.execute("""
                SELECT symbol, action, price, quantity, 
                       TO_CHAR(timestamp, 'HH24:MI') as time
                FROM trades ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
            return self._dict_rows(cur)
        return self._run("get_recent_trades", _fn, default=[])

    def get_open_positions_view(self) -> List[Dict[str, Any]]:
        def _fn(cur):
            cur.execute("""
                SELECT symbol, quantity, entry_price, current_price,
                       sector, fundamental_score,
                       ROUND(CAST((current_price - entry_price) * quantity AS numeric), 2) as pnl,
                       TO_CHAR(entry_date, 'Mon DD') as entry_date_display,
                       ROUND(CAST(peak_price AS numeric), 2) as peak_price
                FROM positions 
                WHERE quantity > 0
                ORDER BY symbol
            """)
            return self._dict_rows(cur)
        return self._run("get_open_positions_view", _fn, default=[])

    def get_trades_view(self, limit: int = 50) -> List[Dict[str, Any]]:
        def _fn(cur):
            cur.execute("""
                SELECT symbol, action, price, quantity,
                       sentiment, ROUND(CAST(sentiment_prob*100 AS numeric), 1) as confidence,
                       fundamental_score,
                       TO_CHAR(timestamp, 'Mon DD HH24:MI') as time
                FROM trades ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
            return self._dict_rows(cur)
        return self._run("get_trades_view", _fn, default=[])

    def get_performance_snapshot(self) -> Dict[str, Any]:
        def _fn(cur):
            cur.execute("""
                SELECT portfolio_value, equity_exposure, open_positions 
                FROM portfolio_snapshots 
                ORDER BY timestamp DESC LIMIT 1
            """)
            rows = self._dict_rows(cur)
            return rows[0] if rows else {}
        return self._run("get_performance_snapshot", _fn, default={})

    def get_performance_history(self, limit: int = 30) -> List[Dict[str, Any]]:
        def _fn(cur):
            cur.execute("""
                SELECT 
                    TO_CHAR(timestamp, 'Mon DD') as date,
                    portfolio_value,
                    equity_exposure
                FROM portfolio_snapshots 
                ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
            return self._dict_rows(cur)
        return self._run("get_performance_history", _fn, default=[])
