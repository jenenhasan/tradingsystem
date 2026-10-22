# 📈 Automated Trading System

> *Combining financial sentiment analysis, fundamental screening, and risk-aware trading decisions.*

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FinBERT](https://img.shields.io/badge/NLP-FinBERT-8A2BE2)](https://huggingface.co/ProsusAI/finbert)
[![Pandas](https://img.shields.io/badge/Data-Pandas-150458?logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![Alpaca](https://img.shields.io/badge/Broker-Alpaca-FFCE00)](https://alpaca.markets/)
[![Lumibot](https://img.shields.io/badge/Trading-Lumibot-2E8B57)](https://lumibot.lumiwealth.com/)
[![License](https://img.shields.io/badge/License-See_Repository-lightgrey)](LICENSE)

---

## 🚀 What Is This Project?

The **Automated Trading System** is a Python-based algorithmic trading research project that combines financial news sentiment analysis with fundamental stock screening to evaluate trading opportunities in the S&P 500 universe.

Instead of relying on a single indicator, the system combines multiple information sources:

- 🧠 **Financial sentiment:** FinBERT-based analysis of positive and negative financial sentiment.
- 📊 **Fundamental analysis:** Evaluation of company financial metrics to score potential stock candidates.
- 🛡️ **Risk management:** Position sizing, stop-loss rules, and portfolio drawdown controls.
- 📈 **Backtesting:** Historical strategy evaluation and comparison with the SPY benchmark.
- 🔌 **API integration:** Connections to financial data providers and Alpaca's paper-trading infrastructure.
- ⚙️ **Operational reliability:** Caching, retries, structured logging, and heartbeat monitoring.

The project explores how financial data, machine learning, and systematic trading rules can work together in a single application.

---

## ✨ Feature Highlights

| Feature | Description |
|---|---|
| 🧠 **Financial Sentiment Analysis** | Uses FinBERT to classify financial text sentiment. |
| 📊 **Fundamental Stock Screening** | Evaluates company financial metrics and generates fundamental scores. |
| 🎯 **Signal Generation** | Combines sentiment confidence, fundamental scores, and configured trading conditions. |
| 🛡️ **Risk Management** | Implements position-sizing parameters, stop-loss rules, and drawdown protection. |
| 📈 **Historical Backtesting** | Evaluates the strategy over historical market data. |
| ⚖️ **SPY Benchmarking** | Compares the strategy's historical return with the SPY benchmark. |
| ⚡ **Caching** | Reduces repeated financial-data retrieval and supports faster processing. |
| 🔄 **Retry Mechanism** | Retries selected operations when external API requests fail. |
| 📝 **Structured Logging** | Records application events and trading activity for troubleshooting. |
| 💓 **Heartbeat Monitoring** | Writes periodic heartbeat updates while the paper-trading process runs. |
| 🧪 **Paper Trading** | Supports strategy evaluation through Alpaca's paper-trading integration. |

---

## 🏗️ Architecture

The application separates the main trading workflow from sentiment analysis, fundamental analysis, data retrieval, and supporting services.

### High-Level Workflow

```text
             Financial Data
                   │
          ┌────────┴────────┐
          ▼                 ▼
   Market Price Data   Company Fundamentals
          │                 │
          ▼                 ▼
   Trading Strategy   Fundamental Analysis
          │                 │
          │           Fundamental Score
          │                 │
          ▼                 │
   FinBERT Sentiment         │
          │                 │
          └────────┬────────┘
                   ▼
            Trading Conditions
                   │
                   ▼
               Risk Checks
                   │
                   ▼
             Trading Decision
                   │
          ┌────────┴────────┐
          ▼                 ▼
     Backtesting       Paper Trading
          │                 │
          ▼                 ▼
   Performance Report   Logs & Monitoring
```

### Repository Structure

```text
tradingsystem/
│
├── trading.py
│   └── Main entry point and strategy orchestration
│
├── strategies/
│   ├── sentiment_analysis.py
│   │   └── Financial sentiment analysis
│   │
│   └── fundamental_analysis.py
│       └── Fundamental data retrieval and stock scoring
│
├── data_fetcher/
│   └── Financial data retrieval components
│
├── persistence/
│   └── Data persistence components
│
├── dashboard/
│   └── Dashboard-related components
│
├── alerts.py
│   └── Alert functionality
│
├── pre_backtest_cache.py
│   └── Cache preparation for backtesting
│
├── tickers.csv
│   └── Stock ticker input data
│
├── requirements.txt
│   └── Project dependencies
│
├── .gitignore
│
└── README.md
```

*This tree highlights the main components. Individual module responsibilities may evolve as the project develops.*

---

## 🛠️ Tech Stack

| Category | Technology | Purpose |
|---|---|---|
| Language | Python | Core application logic |
| NLP | FinBERT | Financial sentiment analysis |
| Machine Learning | PyTorch / Transformers | Transformer model execution |
| Data Processing | Pandas / NumPy | Financial data processing |
| Market Data | Yahoo Finance / `yfinance` | Historical price data |
| Broker Integration | Alpaca API | Paper-trading integration and market-data access |
| Trading Framework | Lumibot | Strategy execution and backtesting |
| Configuration | `python-dotenv` | Environment variable loading |
| Monitoring | Python logging | Application diagnostics and event logging |

---

## ⚡ Getting Started

### Prerequisites

Before running the project, you need:

- Python installed.
- Git installed.
- An Alpaca account with paper-trading API credentials.
- Internet access for external financial data and model downloads.

### 1. Clone the Repository

```bash
git clone https://github.com/jenenhasan/tradingsystem.git
cd tradingsystem
```

### 2. Create a Virtual Environment

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The FinBERT model and its dependencies may require additional download time and disk space.

### 4. Configure Environment Variables

Create a `.env` file in the repository root:

```dotenv
API_KEY=your_alpaca_api_key
API_SECRET=your_alpaca_api_secret
BASE_URL=https://paper-api.alpaca.markets
```

Replace the placeholder values with your own **Alpaca paper-trading credentials**.

The application expects all three variables to be present.

> 🔐 **Security:** Never commit your `.env` file or API credentials to Git. Keep `.env` in `.gitignore`. If credentials were previously committed or exposed, revoke and replace them.

### 5. Run a Historical Backtest

```bash
python trading.py backtest
```

The current entry point configures a historical backtest covering **January 1–May 31, 2020**.

The script attempts to retrieve historical market data and compare the strategy with SPY. When available, the output includes:

- Strategy return
- Sharpe ratio
- Maximum drawdown
- Compound annual growth rate (CAGR)
- SPY benchmark return
- Return difference versus SPY

Actual results depend on data availability, dependencies, and execution conditions.

### 6. Run Paper Trading

```bash
python trading.py paper
```

This starts the strategy's paper-trading workflow.

The strategy is configured for paper trading rather than live-money execution. Review your broker configuration and credentials before starting the process.

**Note:** The command starts a running trading process; it is not simply a one-time prediction.

---

## 🛡️ Risk Management

Automated trading systems need controls beyond the ability to generate buy and sell signals.

The strategy includes configurable risk-related parameters:

| Parameter | Current Configuration |
|---|---:|
| Base cash-at-risk parameter | 2% |
| Stop-loss threshold | 2% |
| Maximum portfolio allocation to positions | 80% |
| Drawdown halt threshold | 15% |

These are strategy configuration values, not guarantees of maximum loss. Actual results depend on execution behavior, market conditions, and the implementation of the relevant controls.

The system also combines sentiment confidence and fundamental scores when evaluating trading decisions.

---

## 📈 Backtesting & Evaluation

Historical backtesting allows the strategy to be evaluated against past market data before further experimentation.

The current implementation includes:

- A defined historical evaluation window.
- Historical data retrieval through Yahoo Finance and Lumibot.
- SPY benchmark comparison.
- Strategy performance metrics when provided by the backtesting result.

### Important Evaluation Considerations

Backtesting alone cannot establish that a strategy will perform well in live markets.

A stronger evaluation should consider:

- Transaction costs and slippage.
- Look-ahead bias and point-in-time financial data.
- Performance across different market conditions.
- Parameter sensitivity and overfitting.
- Out-of-sample testing.
- Reproducibility of data and results.

No performance figure is presented here as a verified result. Actual results should be generated and reviewed before being published.

---

## ⚙️ Engineering Decisions

### 🔄 Retry with Exponential Backoff

External APIs can fail temporarily because of network issues, rate limits, or service interruptions.

The project includes a retry decorator that increases the delay between failed attempts. This helps avoid immediate repeated requests when a retryable operation encounters an error.

### ⚡ Financial Data Caching

Repeatedly retrieving fundamental data can add unnecessary latency and API traffic.

The project includes caching and preloading components to reduce redundant data retrieval, particularly during historical backtesting.

### 📝 Structured Logging

The application writes operational information to the console and a rotating log file.

This helps with:

- Investigating failed operations.
- Reviewing strategy execution.
- Understanding API-related errors.
- Inspecting trading events after execution.

### 💓 Heartbeat Monitoring

During paper trading, the application periodically updates a heartbeat file.

This provides a simple signal that the process is still running and can be useful for basic monitoring.

### 🧩 Separation of Responsibilities

Sentiment analysis, fundamental analysis, data retrieval, and strategy orchestration are handled by separate components.

This separation makes the system easier to inspect and creates a foundation for future improvements, including more automated testing and clearer component-level interfaces.

---

## 🔮 Potential Improvements

Possible next steps for the project include:

- 🧪 Adding automated tests for sentiment classification, scoring, and risk controls.
- 📊 Publishing reproducible backtesting reports and visualizations.
- 📅 Expanding historical and out-of-sample evaluation periods.
- 🔍 Improving point-in-time data validation.
- ⚙️ Moving strategy parameters into a dedicated configuration layer.
- 📉 Evaluating transaction costs, slippage, and sensitivity to parameter changes.
- 📈 Improving performance monitoring and reporting.

These are potential improvements, not claims that the features have already been implemented.

---

## ⚠️ Disclaimer

This project is intended for educational and research purposes only.

- It is not financial advice.
- Historical results do not guarantee future performance.
- Paper trading does not fully reproduce real-market execution.
- Automated trading can incur substantial losses.
- Risk controls cannot eliminate all market or execution risks.

Use paper trading for evaluation. Do not connect the system to a live brokerage account without independently reviewing the code, risk controls, and execution behavior.

---

## 👩‍💻 Author

**Jenen Hasan** — Software Engineering Graduate | Junior Backend Software Engineer

[![GitHub](https://img.shields.io/badge/GitHub-jenenhasan-181717?logo=github&logoColor=white)](https://github.com/jenenhasan)

[View the Automated Trading System repository](https://github.com/jenenhasan/tradingsystem)

---

## 📄 License

Check the repository for the applicable license before redistributing or reusing the project.
