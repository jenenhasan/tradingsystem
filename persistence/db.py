"""
persistence/db.py
===================
Raw Postgres connection helper — the one and only place a connection
string gets built. Both `persistence/repository.py` (bot-side writes)
and `dashboard/app.py` (read-only queries) import from here, so there is
exactly one database, never a bot-writes-to-X / dashboard-reads-from-Y
mismatch.
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )


def return_connection(conn):
    """Close the connection (or return to pool if using connection pooling)."""
    if conn:
        conn.close()


def create_tables():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            action VARCHAR(4) NOT NULL,
            quantity INTEGER NOT NULL,
            price FLOAT NOT NULL,
            sentiment VARCHAR(10),
            sentiment_prob FLOAT,
            fundamental_score INTEGER,
            sector VARCHAR(50),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id SERIAL PRIMARY KEY,
            portfolio_value FLOAT,
            cash FLOAT,
            equity_exposure FLOAT,
            open_positions INTEGER,
            trades_today INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) UNIQUE NOT NULL,
            quantity INTEGER NOT NULL,
            entry_price FLOAT NOT NULL,
            current_price FLOAT,
            sector VARCHAR(50),
            fundamental_score FLOAT,
            entry_date TIMESTAMP,
            peak_price FLOAT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Dedicated bot_state table for HWM and other singleton state
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value FLOAT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Add columns if they don't exist (safe to run every startup)
    cur.execute("""
        ALTER TABLE positions ADD COLUMN IF NOT EXISTS entry_date TIMESTAMP;
    """)
    cur.execute("""
        ALTER TABLE positions ADD COLUMN IF NOT EXISTS peak_price FLOAT;
    """)

    # Safely alter fundamental_score type with USING
    cur.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='positions' AND column_name='fundamental_score' 
                AND data_type != 'double precision'
            ) THEN
                ALTER TABLE positions ALTER COLUMN fundamental_score TYPE FLOAT USING fundamental_score::FLOAT;
            END IF;
        END $$;
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Tables created / verified successfully")


if __name__ == "__main__":
    create_tables()
