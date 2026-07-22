"""
dashboard/app.py
==================
Read-only dashboard. All DB access goes through persistence.repository.Repository
(same class the bot itself writes through) instead of the old ad-hoc
`query()` helper — one connection strategy for the whole project.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify
from datetime import date

from persistence.repository import Repository
from persistence.db import create_tables

app = Flask(__name__)
repo = Repository()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/overview")
def overview():
    snapshot = repo.get_latest_snapshot()
    hwm = repo.get_bot_state("hwm")
    trades_today = repo.get_trades_today_count(date.today())
    pnl_today = repo.get_pnl_today(date.today())
    recent = repo.get_recent_trades(limit=5)

    return jsonify({
        "snapshot": snapshot,
        "hwm": hwm,
        "trades_today": trades_today,
        "pnl_today": pnl_today,
        "recent_trades": recent,
    })


@app.route("/api/positions")
def positions():
    return jsonify(repo.get_open_positions_view())


@app.route("/api/trades")
def trades():
    return jsonify(repo.get_trades_view(limit=50))


@app.route("/api/performance")
def performance():
    """Get performance metrics including drawdown and current exposure."""
    snapshot = repo.get_performance_snapshot()
    hwm = repo.get_bot_state("hwm")
    history = repo.get_performance_history(limit=30)

    result = {
        "current_value": snapshot.get("portfolio_value"),
        "hwm": hwm,
        "equity_exposure": snapshot.get("equity_exposure"),
        "open_positions": snapshot.get("open_positions"),
        "history": list(reversed(history)) if history else [],
    }

    if result["current_value"] and result["hwm"] and result["hwm"] > 0:
        drawdown = (result["hwm"] - result["current_value"]) / result["hwm"]
        result["drawdown"] = round(drawdown * 100, 2)
    else:
        result["drawdown"] = 0

    return jsonify(result)


@app.route("/api/scan/<ticker>")
def scan(ticker):
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
    create_tables()
    app.run(debug=True, port=5000)
