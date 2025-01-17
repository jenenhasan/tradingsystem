from lumibot.brokers import Alpaca # broker is what will make the execution 
from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies.strategy import Strategy #for the actual trading bot
from lumibot.traders import Trader # for deployement capability 
from datetime import datetime    #we will need this for the backtesting
from dotenv import load_dotenv
import os 
import pandas as pd 
import numpy as np
import time 
import yfinance as yf
from alpaca_trade_api import REST 
from datetime import datetime, timedelta 
from strategies.sentiment_analysis import estimate_sentiment
from strategies.fundamental_analysis import  data_fetcher , fundamental_analyzer 

#variables needed
load_dotenv()
API_KEY =os.getenv("API_KEY") 
API_SECRET = os.getenv("API_SECRET")
BASE_URL = os.getenv("BASE_URL")

load_dotenv()
print(f"Loaded .env file: {os.getenv('API_KEY')}")  # This should print the API key from the .env file

print(f"API_KEY: {API_KEY}, API_SECRET: {API_SECRET}, BASE_URL: {BASE_URL}")
ALPACA_CREDS = {
    "API_KEY" : API_KEY, 
    "API_SECRET" : API_SECRET,
    "PAPER": True

}
 
class trading_strategy(Strategy): 
    def initialize(self , cash_at_risk:float=.5): 
        self.sleeptime = "24H" 
        self.last_trade = {}
        self.symbol_to_score = {}
        self.filtered_df = None 
        self.cash_at_risk = cash_at_risk
        self.symbol = None 
        self.api = REST(base_url=BASE_URL, key_id=API_KEY, secret_key=API_SECRET)
    
    

    def load_filtered_data(self):
        fetcher = data_fetcher()
        tickers = fetcher.fetch_sp500_ticker()
        sp500_df = fetcher.fetch_sp500_fdata(tickers)
        analyzer = fundamental_analyzer(sp500_df)
        self.filtered_df = analyzer.perform_fundamental_analysis() 
        self.symbol_to_score = dict(zip(self.filtered_df['ticker'], self.filtered_df['score']))
        


    def position_sizing(self , symbol): 
        cash = self.get_cash() 
        last_price = self.get_last_price(symbol) or 1.0
        quantity = round(cash * self.cash_at_risk / last_price,0)
        return cash, last_price, quantity
    
    def stop_loss (self ):
        stop_loss_amm = (self.last_price ) * (1 - self.cash_at_risk)
        return stop_loss_amm

    def get_dates(self): 
        today = self.get_datetime()
        three_days_prior = today - pd.Timedelta(days=3)
        return today.strftime('%Y-%m-%d'), three_days_prior.strftime('%Y-%m-%d')
    

    def get_sentiment(self , symbol): 
        today, three_days_prior = self.get_dates()
        news = self.api.get_news(symbol=symbol, 
                                 start=three_days_prior, 
                                 end=today) 
        news = [ev.__dict__["_raw"]["headline"] for ev in news]
        probability, sentiment = estimate_sentiment(news)
        return probability, sentiment
   
    def get_fundamental_score (self , symbol):
       return self.symbol_to_score.get(symbol , None)
    # def download_historical_data(self):
    #     for i in range (0 , len(symbols) , batch_size)
    # def download_historical_data(self, symbol, start_date, end_date):
    #     data = yf.download(symbol, start=start_date, end=end_date)
    #     return data



    def on_trading_iteration(self):
        if self.filtered_df is None or self.filtered_df.empty:
            print("Filtered data is empty or not loaded. Loading filtered data now...")
            self.load_filtered_data()
        for symbol in self.filtered_df['ticker']:
            # historical_data = self.download_historical_data(symbol,'2020-01-01' ,'2020-5-31')
            cash, last_price, quantity = self.position_sizing(symbol) 
            fundamental_score = self.get_fundamental_score(symbol)
            probability, sentiment = self.get_sentiment(symbol)
            if cash > last_price: 
                if sentiment == "positive" and probability > .999 and fundamental_score >= 8: 
                    order = self.create_order(
                        symbol, 
                        quantity, 
                        "buy", 
                        type="bracket", 
                        take_profit_price=last_price*1.20, 
                        stop_loss_price=last_price*.95  # ensure that we dont lose more than 5%
                        )
                    self.submit_order(order) 
                    self.last_trade[symbol] = "buy"
                elif sentiment == "negative" and probability > .999 and fundamental_score <= 6 : 
                    order = self.create_order(
                        symbol, 
                        quantity, 
                        "sell", 
                        type="bracket", 
                        take_profit_price=last_price*.8, 
                        stop_loss_price=last_price*1.05 # losses are capped at 5%
                        )
                    self.submit_order(order) 
                    self.last_trade[symbol] = "sell"
                
                

start_date = datetime(2020,1,1) 
end_date = datetime(2020,5,31) 
broker = Alpaca(ALPACA_CREDS) 
strategy = trading_strategy(name='mlstrat', broker=broker, 
                    parameters={"symbol": None, "cash_at_risk": .5})

strategy.load_filtered_data()
symbols = strategy.filtered_df['ticker'].tolist()


strategy.backtest(
    YahooDataBacktesting, 
    start_date, 
    end_date, 
    parameters={"symbol":symbols, "cash_at_risk":.5}
)
# trader = Trader()
# trader.add_strategy(strategy)
# trader.run_all()