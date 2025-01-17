import yfinance as yf
from transformers import AutoTokenizer, AutoModelForSequenceClassification   # library
import torch #library model used to load and run models on the GPU
import pandas as pd

def get_filtered_tickers():
    try:
        filtered_df = pd.read_csv('filtered.csv')
        return filtered_df['ticker'].tolist()  # Assuming the ticker column is named 'ticker'
    except FileNotFoundError:
        print("Error: filtered.csv file not found.")
        return []
    
#Device Setup for Model  
device = "cuda:0" if torch.cuda.is_available() else "cpu"
tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert") # tokenizer help to convert the text data into a fomate that the model can understand
model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert").to(device) # load the model
labels = ["positive", "negative", "neutral"]


def estimate_sentiment(news):
    if news:
        tokens = tokenizer(news, return_tensors="pt", padding=True).to(device) # news is tokenized (changed to a formate that the model can understand )
        result = model(tokens["input_ids"], attention_mask=tokens["attention_mask"])["logits"] # get the output 
        result = torch.nn.functional.softmax(torch.sum(result, 0), dim=-1) # to get the probabilities for each sentiment 
        probability = result[torch.argmax(result)]
        sentiment = labels[torch.argmax(result)]
        return probability, sentiment
    else:
        return 0, labels[-1]

def fetch_news(ticker):
    stock = yf.Ticker(ticker)
    news = stock.news  # Get the latest news for the given stock ticker
    
    # Print the structure of the 'news' data to debug
    print(news)  # Inspect the data structure
    
    # Now try to extract the headlines from the nested 'content' dictionary
    headlines = []
    for article in news:
        # Accessing 'title' inside 'content' dictionary
        if 'content' in article and 'title' in article['content']:
            headlines.append(article['content']['title'])
        else:
            print("No title field in article:", article)  # Print article structure for debugging
    
    return headlines

def main():
    tickers = get_filtered_tickers()
    if not tickers:
        print("No tickers found for sentiment analysis.")
        return
    print(f"Fetching news for {tickers}...")
    for ticker in tickers:
        print(f"Fetching news for {ticker}...")
        
        # Fetch the news for the given ticker
        news_list = fetch_news(ticker)
        
        if news_list:
            for news in news_list:
                print(f"Analyzing sentiment for: {tickers} , newa : {news}")
                probability, sentiment = estimate_sentiment([news])
                print(f"Sentiment: {sentiment} with probability: {probability.item()}")
        else:
            print(f"No news available for {ticker}.")
        #time.sleep(2)
    
    
    
    # Check CUDA availability
    print(torch.cuda.is_available())  
    if torch.cuda.is_available():
        print(torch.cuda.get_device_name(0))

if __name__ == "__main__":
    main()
