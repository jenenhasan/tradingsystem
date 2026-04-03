# 📈 AI-Powered Automated Trading Bot

An algorithmic trading system that combines **fundamental analysis**, **NLP-based sentiment analysis**, and **automated order execution** to trade S&P 500 stocks. The bot screens all 500 companies using financial metrics, runs news sentiment analysis via FinBERT, and executes bracket orders through Alpaca — with full backtesting support via Yahoo Finance data.

---

## 🛠️ Built With

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)
![HuggingFace](https://img.shields.io/badge/HuggingFace-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![Alpaca](https://img.shields.io/badge/Alpaca-FFCD00?style=for-the-badge&logoColor=black)

---

## ✨ How It Works

The bot runs on a **24-hour cycle** and makes trading decisions by combining two independent signals:

### 1. 🏦 Fundamental Analysis
Screens all S&P 500 companies using 5 financial metrics fetched from Yahoo Finance:

| Metric | What it measures | Scoring logic |
|---|---|---|
| P/E Ratio | Valuation | Lower = better (cheaper stock) |
| Revenue Growth | Business momentum | ≥10% = full score |
| Return on Equity (ROE) | Profitability efficiency | Top 25% = full score |
| Debt-to-Equity | Financial risk | Lower = better |
| Dividend Yield | Shareholder returns | Higher = better |

Each stock scores 0–10. Only stocks in the **top 25% by score** are passed to the trading engine. Filtered results are saved to `filtered.csv`.

### 2. 📰 Sentiment Analysis (FinBERT)
For each filtered stock, the bot fetches the last 3 days of news headlines from Alpaca and runs them through **[FinBERT](https://huggingface.co/ProsusAI/finbert)** — a finance-specific BERT model trained on financial text.

Returns:
- **Sentiment**: `positive`, `negative`, or `neutral`
- **Probability**: confidence score (0–1)

### 3. 🤖 Trading Decision Logic

```
BUY  if: sentiment == "positive" AND probability > 0.999 AND fundamental_score >= 8
SELL if: sentiment == "negative" AND probability > 0.999 AND fundamental_score <= 6
```

All orders are **bracket orders** with built-in risk management:
- **Buy**: take profit at +20%, stop loss at -5%
- **Sell**: take profit at -20%, stop loss at +5%

---

## 📁 Project Structure

```
trading-bot/
├── trading_bot.py                  # Main strategy — Lumibot trading loop, order execution
├── strategies/
│   ├── fundamental_analysis.py     # data_fetcher + fundamental_analyzer classes
│   └── sentiment_analysis.py       # FinBERT sentiment model (estimate_sentiment)
├── filtered.csv                    # Output of fundamental analysis — top-scored S&P 500 stocks
├── tickers.csv                     # Full S&P 500 ticker list (auto-generated)
├── requirements.txt                # All dependencies
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- An [Alpaca](https://alpaca.markets/) account (paper trading is free)
- GPU recommended for FinBERT (falls back to CPU automatically)

### Installation

```bash
git clone https://github.com/jenenhasan/trading-bot.git
cd trading-bot
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```env
API_KEY=your_alpaca_api_key
API_SECRET=your_alpaca_api_secret
BASE_URL=https://paper-api.alpaca.markets
```

> The bot is configured for **paper trading** by default (`"PAPER": True`). Change to `False` only when ready for live trading.

---

## 🖥️ Usage

### Step 1 — Run Fundamental Analysis

Fetch financial data for all S&P 500 companies and generate `filtered.csv`:

```bash
python strategies/fundamental_analysis.py
```

This will:
1. Scrape the current S&P 500 ticker list from Wikipedia
2. Fetch financial data for each ticker via `yfinance`
3. Handle missing values using industry-level median imputation
4. Score and filter stocks — saving top performers to `filtered.csv`

### Step 2 — Run the Trading Bot (Backtest)

```bash
python trading_bot.py
```

This backtests the strategy from **Jan 1, 2020 to May 31, 2020** using Yahoo Finance historical data via Lumibot.

### Step 3 — Live Trading (Optional)

To switch to live trading, uncomment these lines at the bottom of `trading_bot.py`:

```python
# trader = Trader()
# trader.add_strategy(strategy)
# trader.run_all()
```

And comment out the `strategy.backtest(...)` block above them.

---

## ⚙️ Key Parameters

| Parameter | Default | Description |
|---|---|---|
| `cash_at_risk` | `0.5` | Fraction of available cash used per trade (50%) |
| `sleeptime` | `"24H"` | How often the strategy runs |
| `take_profit (buy)` | `+20%` | Target profit for long positions |
| `stop_loss (buy)` | `-5%` | Max loss allowed on long positions |
| `take_profit (sell)` | `-20%` | Target profit for short positions |
| `stop_loss (sell)` | `+5%` | Max loss allowed on short positions |
| Sentiment threshold | `> 0.999` | Minimum FinBERT confidence to trigger a trade |
| Fundamental threshold (buy) | `>= 8` | Minimum score to consider buying |
| Fundamental threshold (sell) | `<= 6` | Maximum score to consider selling |

---

## 🧠 Models & Data Sources

| Component | Source |
|---|---|
| Sentiment model | [ProsusAI/finbert](https://huggingface.co/ProsusAI/finbert) on HuggingFace |
| News headlines | Alpaca Markets News API |
| Financial data | Yahoo Finance via `yfinance` |
| S&P 500 tickers | Wikipedia (auto-scraped) |
| Backtesting data | Yahoo Finance via Lumibot |
| Order execution | Alpaca Markets API |

---

## ⚠️ Disclaimer

> This project is for **educational purposes only**. It is not financial advice. Always use paper trading before risking real money. Past backtest performance does not guarantee future results.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push and open a Pull Request

---

## 📄 License

This project is open source. See `LICENSE` for details.
