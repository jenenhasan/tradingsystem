"""
sentiment_analysis.py
======================
Loads FinBERT and exposes estimate_sentiment() for use by the trading bot.

Changes from original
---------------------
1. estimate_sentiment() — return value cast to float. The original returned a
   raw PyTorch tensor. Comparing a tensor with > 0.8 works in older PyTorch
   but raises a warning/error in newer versions. float() makes it safe everywhere.

2. estimate_sentiment() — added a max-token guard. FinBERT's BERT backbone has
   a hard limit of 512 tokens. Passing a very long list of headlines without
   truncation causes a CUDA/CPU error at runtime. We now cap each headline at
   128 tokens (truncation=True, max_length=128) and limit the total list to 10
   headlines to stay well within the 512-token limit.

3. main() — the original main() had a NameError on `if main != news` (comparing
   a function object to a variable that didn't exist yet). Replaced with clean
   logic that iterates tickers from filtered.csv and prints results.

4. main() — added a clear message when filtered.csv is missing so the user
   knows to run fundamental_analysis.py first.

5. fetch_news_yf() — extracted the yfinance news fetch into its own function
   with a docstring warning that it must NOT be used inside a backtest loop
   because yfinance news has no reliable timestamp (look-ahead risk).

6. Model loading — moved to module level with a try/except so an import error
   (e.g. missing transformers package) gives a clear message instead of a
   cryptic AttributeError later.
"""

import torch
import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Model loading
# FIX 6: wrapped in try/except so a missing package gives a clear message.
# ---------------------------------------------------------------------------
try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    device    = "cuda:0" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    model     = AutoModelForSequenceClassification.from_pretrained(
                    "ProsusAI/finbert"
                ).to(device)
    model.eval()   # put in inference mode — disables dropout, saves memory
    labels = ["positive", "negative", "neutral"]
    print(f"  FinBERT loaded on {device}")

except ImportError as e:
    raise ImportError(
        f"Cannot load FinBERT: {e}. "
        "Run: pip install transformers torch"
    )


# ---------------------------------------------------------------------------
# Core sentiment function
# ---------------------------------------------------------------------------

def estimate_sentiment(news: list) -> tuple:
    """
    Run FinBERT over a list of news headline strings.

    Returns
    -------
    (probability: float, sentiment: str)
        probability — confidence score for the winning class (0.0 – 1.0)
        sentiment   — one of "positive", "negative", "neutral"

    Returns (0.0, "neutral") if news is empty.

    FIX 1: probability is cast to float (was a raw tensor).
    FIX 2: headlines are truncated to 128 tokens each, and capped at 10
           headlines total, to stay within FinBERT's 512-token hard limit.
    """
    if not news:
        return 0.0, "neutral"

    # FIX 2: cap list length to avoid memory issues on large news batches
    headlines = news[:10]

    with torch.no_grad():   # no gradient tracking needed for inference
        tokens = tokenizer(
            headlines,
            return_tensors="pt",
            padding=True,
            truncation=True,        # FIX 2: truncate long headlines
            max_length=128          # FIX 2: stay within BERT's 512-token limit
        ).to(device)

        logits  = model(
            tokens["input_ids"],
            attention_mask=tokens["attention_mask"]
        )["logits"]

        # Sum logits across all headlines, then softmax → probabilities
        result      = torch.nn.functional.softmax(torch.sum(logits, dim=0), dim=-1)
        best_idx    = torch.argmax(result).item()
        probability = float(result[best_idx])   # FIX 1: tensor → float
        sentiment   = labels[best_idx]

    return probability, sentiment


# ---------------------------------------------------------------------------
# News helper (for smoke-testing only — NOT for use in backtests)
# ---------------------------------------------------------------------------

def fetch_news_yf(ticker: str) -> list:
    """
    Fetch recent news headlines for a ticker via yfinance.

    WARNING — FIX 5: Do NOT use this inside a backtesting loop.
    yfinance news has no reliable publication timestamp, so it cannot be
    date-bounded and will introduce look-ahead bias. Use Alpaca's get_news()
    with explicit start/end dates inside the trading bot instead.

    This function is only for local development/smoke-testing.
    """
    stock     = yf.Ticker(ticker)
    news      = stock.news
    headlines = []
    for article in news:
        # yfinance v0.2+ nests the title inside a 'content' dict
        if 'content' in article and 'title' in article['content']:
            headlines.append(article['content']['title'])
        elif 'title' in article:
            headlines.append(article['title'])
    return headlines


# ---------------------------------------------------------------------------
# Standalone smoke-test
# ---------------------------------------------------------------------------

def get_filtered_tickers() -> list:
    try:
        df = pd.read_csv('filtered.csv')
        return df['ticker'].tolist()
    except FileNotFoundError:
        # FIX 4: clear message instead of silent empty list
        print(
            "  filtered.csv not found. "
            "Run `python strategies/fundamental_analysis.py` first."
        )
        return []


def main():
    """
    Smoke-test: run FinBERT on each stock in filtered.csv using yfinance news.
    For development and testing only — the live bot uses Alpaca news instead.
    FIX 3: replaced broken main() logic (NameError on undefined 'news' variable).
    """
    tickers = get_filtered_tickers()
    if not tickers:
        return

    print(f"Running FinBERT sentiment on {len(tickers)} tickers ...")
    print(f"Device: {device}")
    if torch.cuda.is_available():
        print(f"GPU   : {torch.cuda.get_device_name(0)}")
    print()

    for ticker in tickers:
        headlines = fetch_news_yf(ticker)
        if headlines:
            probability, sentiment = estimate_sentiment(headlines)
            print(f"  {ticker:6s} | {sentiment:8s} | {probability:.2%} confidence "
                  f"| {len(headlines)} headlines")
        else:
            print(f"  {ticker:6s} | no news available")


if __name__ == "__main__":
    main()