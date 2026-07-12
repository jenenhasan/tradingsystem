from flask import Flask, render_template, jsonify
from db import get_connection, return_connection
from datetime import datetime, date
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

def query(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        return_connection(conn)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/overview")
def overview():
    snapshot = query("""
        SELECT * FROM portfolio_snapshots 
        ORDER BY timestamp DESC LIMIT 1
    """)
    
    # Get HWM from dedicated bot_state table
    hwm = query("""
        SELECT value as hwm FROM bot_state WHERE key = 'hwm'
    """)
    
    trades_today = query("""
        SELECT COUNT(*) as count FROM trades 
        WHERE DATE(timestamp) = %s
    """, (date.today(),))
    
    pnl = query("""
        SELECT 
            SUM(CASE WHEN action='BUY' THEN -price*quantity 
                     WHEN action='SELL' THEN price*quantity END) as pnl
        FROM trades WHERE DATE(timestamp) = %s
    """, (date.today(),))
    
    recent = query("""
        SELECT symbol, action, price, quantity, 
               TO_CHAR(timestamp, 'HH24:MI') as time
        FROM trades ORDER BY timestamp DESC LIMIT 5
    """)
    
    result = {
        "snapshot": snapshot[0] if snapshot else {},
        "hwm": hwm[0]["hwm"] if hwm and hwm[0]["hwm"] else None,
        "trades_today": trades_today[0]["count"] if trades_today else 0,
        "pnl_today": round(pnl[0]["pnl"] or 0, 2) if pnl else 0,
        "recent_trades": recent
    }
    return jsonify(result)


@app.route("/api/positions")
def positions():
    data = query("""
        SELECT symbol, quantity, entry_price, current_price,
               sector, fundamental_score,
               ROUND(CAST((current_price - entry_price) * quantity AS numeric), 2) as pnl,
               TO_CHAR(entry_date, 'Mon DD') as entry_date_display,
               ROUND(CAST(peak_price AS numeric), 2) as peak_price
        FROM positions 
        WHERE quantity > 0
        ORDER BY symbol
    """)
    return jsonify(data)


@app.route("/api/trades")
def trades():
    data = query("""
        SELECT symbol, action, price, quantity,
               sentiment, ROUND(CAST(sentiment_prob*100 AS numeric), 1) as confidence,
               fundamental_score,
               TO_CHAR(timestamp, 'Mon DD HH24:MI') as time
        FROM trades ORDER BY timestamp DESC LIMIT 50
    """)
    return jsonify(data)


@app.route("/api/performance")
def performance():
    """Get performance metrics including drawdown and current exposure."""
    # Latest portfolio value
    snapshot = query("""
        SELECT portfolio_value, equity_exposure, open_positions 
        FROM portfolio_snapshots 
        ORDER BY timestamp DESC LIMIT 1
    """)
    
    # HWM
    hwm = query("""
        SELECT value as hwm FROM bot_state WHERE key = 'hwm'
    """)
    
    # Get series for chart (last 30 days)
    history = query("""
        SELECT 
            TO_CHAR(timestamp, 'Mon DD') as date,
            portfolio_value,
            equity_exposure
        FROM portfolio_snapshots 
        ORDER BY timestamp DESC LIMIT 30
    """)
    
    result = {
        "current_value": snapshot[0]["portfolio_value"] if snapshot else None,
        "hwm": hwm[0]["hwm"] if hwm and hwm[0]["hwm"] else None,
        "equity_exposure": snapshot[0]["equity_exposure"] if snapshot else None,
        "open_positions": snapshot[0]["open_positions"] if snapshot else None,
        "history": list(reversed(history)) if history else []
    }
    
    # Calculate drawdown
    if result["current_value"] and result["hwm"] and result["hwm"] > 0:
        drawdown = (result["hwm"] - result["current_value"]) / result["hwm"]
        result["drawdown"] = round(drawdown * 100, 2)
    else:
        result["drawdown"] = 0
    
    return jsonify(result)


@app.route("/api/scan/<ticker>")
def scan(ticker):
    import sys
    sys.path.append("..")
    from strategies.sentiment_analysis import estimate_sentiment
    import yfinance as yf

    try:
        stock = yf.Ticker(ticker)
        news = stock.news[:10]
        headlines = []
        for article in news:
            if 'content' in article and 'title' in article['content']:
                headlines.append(article['content']['title'])
            elif 'title' in article:
                headlines.append(article['title'])

        if headlines:
            prob, sentiment = estimate_sentiment(headlines)
        else:
            prob, sentiment = 0.0, "neutral"

        info = stock.info
        
        # Get historical price for context
        hist = stock.history(period="1mo")
        price_change = 0
        if len(hist) >= 2:
            price_change = ((hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
        
        return jsonify({
            "ticker": ticker.upper(),
            "company": info.get("longName", ticker.upper()),
            "sector": info.get("sector", "Unknown"),
            "price": round(hist['Close'].iloc[-1], 2) if len(hist) > 0 else 0,
            "price_change_1m": round(price_change, 2),
            "sentiment": sentiment,
            "confidence": round(prob * 100, 1),
            "signal": (
                "BUY signal" if sentiment == "positive" and prob > 0.8
                else "SELL signal" if sentiment == "negative" and prob > 0.8
                else "No signal"
            )
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    from db import create_tables
    create_tables()
    app.run(debug=True, port=5000)