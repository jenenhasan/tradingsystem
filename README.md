# Automated Trading System

## Description
This project is an Automated Trading System designed to simplify trading decisions using AI-powered sentiment analysis and fundamental financial metrics. It integrates sentiment analysis of financial news with a robust fundamental analysis framework to make informed trading decisions. 

## Features
- **Sentiment Analysis:** Uses FinBERT to classify news sentiment as positive, negative, or neutral.
- **Fundamental Analysis:** Evaluates key financial metrics such as earnings growth, P/E ratios, and debt-to-equity ratios.
- **Risk Management:** Implements stop-loss orders and position sizing to minimize potential losses in volatile markets.
- **Backtesting:** Simulates trading strategies on historical data for optimization.

## Technologies Used
- **Python**: Core programming language.
- **FinBERT**: Transformer-based model for sentiment analysis.
- **Yahoo Finance API (yfinance)**: Fetches financial news and stock data.
- **Alpaca API**: Executes trades.
- **Pandas**: Data manipulation and analysis.
- **Matplotlib/Seaborn**: Visualization tools for data analysis.

## Setup Instructions
### 1. Clone the Repository
Start by cloning the project repository to your local machine:
git clone https://github.com/YourUsername/automated-trading-system.git
cd automated-trading-system
2. Install Dependencies
Make sure you have Python 3.8+ installed. Then, create a virtual environment (optional but recommended) and install the required dependencies:

bash
Copy
Edit
python3 -m venv venv
source venv/bin/activate  # On Windows, use 'venv\Scripts\activate'
pip install -r requirements.txt
3. Set Up API Keys
The project requires the following API keys:

Alpaca API: Sign up for an Alpaca account at Alpaca Markets and generate your API keys.
Yahoo Finance API: Sign up for a Yahoo Finance API key (if necessary).
After obtaining the keys, create a .env file in the root directory of the project and add the following environment variables:

makefile
Copy
Edit
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
YAHOO_FINANCE_API_KEY=your_yahoo_finance_api_key
4. Run the Application
Once you've set up the API keys, you can run the bot and start automated trading:

bash
Copy
Edit
python main.py
5. Optional: Backtest the Strategy
If you'd like to test the strategy using historical data before executing live trades, use the backtesting script:

bash
Copy
Edit
python backtest.py
Technologies Used
Python 3.8+
FinBERT: Sentiment analysis of financial news.
Alpaca API: Execution of live trades.
Yahoo Finance API: Fetching stock data and news articles.
Pandas & NumPy: Data manipulation and analysis.
Matplotlib: Visualization (optional for backtesting results).
TensorFlow/PyTorch: For machine learning models (if applicable).

