import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.db import get_connection
from datetime import datetime, date
from typing import Optional

# Setup logger for this module
logger = logging.getLogger(__name__)


def _log_error(msg: str, error: Exception):
    """Helper to log errors consistently."""
    try:
        logger.error(f'"{msg}","error":"{error}"')
    except Exception:
        print(f"{msg}: {error}")


def log_trade(symbol, action, quantity, price, sentiment=None, sentiment_prob=None,
              fundamental_score=None, sector=None):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO trades
            (symbol, action, quantity, price, sentiment, sentiment_prob, fundamental_score, sector)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (symbol, action, quantity, price, sentiment, sentiment_prob, fundamental_score, sector))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _log_error("DB log_trade error", e)


def log_portfolio_snapshot(portfolio_value, cash, equity_exposure, open_positions, trades_today):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO portfolio_snapshots
            (portfolio_value, cash, equity_exposure, open_positions, trades_today)
            VALUES (%s, %s, %s, %s, %s)
        """, (portfolio_value, cash, equity_exposure, open_positions, trades_today))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _log_error("DB log_portfolio_snapshot error", e)


def upsert_position(symbol, quantity, entry_price, current_price=None, sector=None,
                     fundamental_score=None, entry_date=None, peak_price=None):
    """
    Insert or update a position row.

    IMPORTANT: entry_date is intentionally excluded from the
    ON CONFLICT ... DO UPDATE SET clause. It should be written once,
    on the initial buy, and never overwritten by later calls (e.g. the
    peak-price-tracking calls made every iteration). Overwriting it on
    every update would reset MAX_HOLD_DAYS tracking constantly.

    On the very first insert, if entry_date is None, we default to now()
    so the holding-period clock still starts somewhere sane.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()

        if entry_date is None:
            entry_date = datetime.utcnow()

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
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _log_error("DB upsert_position error", e)


def update_peak_price(symbol, peak_price, current_price=None):
    """
    Lightweight update for just the peak price (and optionally current
    price), called every iteration as prices move. Does NOT touch
    entry_date, entry_price, quantity, sector, or fundamental_score.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
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
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _log_error("DB update_peak_price error", e)


def remove_position(symbol):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM positions WHERE symbol = %s", (symbol,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _log_error("DB remove_position error", e)


def get_all_positions():
    """
    Get all currently open positions from the database.
    Used for state reconciliation on bot restart.

    Uses the SAME Postgres connection as everything else in this file —
    NOT a separate SQLite database. If this used a different DB than
    upsert_position/remove_position, it would always return an empty
    list even though real positions exist, because it would be reading
    from a database nothing ever writes to.

    Returns:
        List of dict, e.g.:
        [{'symbol': 'AAPL', 'quantity': 10, 'entry_price': 150.0,
          'current_price': 155.0, 'sector': 'Technology',
          'fundamental_score': 0.72,
          'entry_date': datetime(2024, 1, 1, ...),
          'peak_price': 158.0}, ...]

        entry_date comes back as a native Python datetime (psycopg2
        converts TIMESTAMP columns automatically) — no manual string
        parsing needed. Call .date() on it if you need a date object.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, quantity, entry_price, current_price, sector,
                   fundamental_score, entry_date, peak_price
            FROM positions
            WHERE quantity > 0
        """)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
        return [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        _log_error("DB get_all_positions error", e)
        return []


# ============================================================================
# HIGH WATER MARK (HWM) PERSISTENCE - Dedicated bot_state table
# ============================================================================

def update_hwm(hwm: float) -> None:
    """
    Store high water mark in dedicated bot_state table.
    
    This is stored in a separate table from portfolio_snapshots to avoid
    corrupting portfolio history with fake zero rows. The bot_state table
    is a simple key-value store for singleton bot state that needs to
    survive restarts.
    
    Args:
        hwm: The high water mark (peak portfolio value) to store
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bot_state (key, value, updated_at)
            VALUES ('hwm', %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET 
                value = EXCLUDED.value, 
                updated_at = CURRENT_TIMESTAMP
        """, (hwm,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _log_error("DB update_hwm error", e)


def get_latest_hwm() -> Optional[float]:
    """
    Retrieve the latest high water mark from the dedicated bot_state table.
    
    Returns:
        float: The stored HWM value, or None if no HWM has been stored yet.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT value FROM bot_state WHERE key = 'hwm'
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        _log_error("DB get_latest_hwm error", e)
        return None


def update_bot_state(key: str, value: float) -> None:
    """
    Generic bot state updater for future use.
    
    Args:
        key: The state key (e.g., 'hwm', 'last_run', etc.)
        value: The value to store
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO bot_state (key, value, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET 
                value = EXCLUDED.value, 
                updated_at = CURRENT_TIMESTAMP
        """, (key, value))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _log_error(f"DB update_bot_state error for key={key}", e)


def get_bot_state(key: str) -> Optional[float]:
    """
    Generic bot state getter for future use.
    
    Args:
        key: The state key to retrieve
        
    Returns:
        float: The stored value, or None if not found
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT value FROM bot_state WHERE key = %s
        """, (key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        _log_error(f"DB get_bot_state error for key={key}", e)
        return None