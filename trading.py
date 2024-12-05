from lumibot.brokers import Alpaca # broker is what will make the execution 
from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies.strategy import Strategy #for the actual trading bot
from lumibot.traders import Trader # for deployement capability 
from datetime import datetime    #we will need this for the backtesting
from dotenv import load_dotenv
import os 
import pandas as pd 
import numpy as np
import cProfile   #for performance 
#from alpaca.trading.client import TradingClient


from strategies.fundamental_analysis import  data_fetcher , fundamental_analyzer





#from alpaca_trade_api import REST  
#from timedelta import Timedelta 
#from finbert_utils import estimate_sentiment
load_dotenv()
#variables needed
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

class trading_strategy (Strategy):

    
    #instance method (this will run once )
    def initialize(self ,cash_at_risk:float = .5): 
      
        
        self.sleep_time = "24H"
        self.last_trade = {}
        self.cash_at_risk = cash_at_risk 
        self.filtered_df = None
        #use dict 
        self.symbol_to_score = {}

    def load_filtered_data(self):
        fetcher = data_fetcher()
        tickers = fetcher.fetch_sp500_ticker()
        sp00_df = fetcher.fetch_sp500_fdata(tickers)
        analyzer = fundamental_analyzer(sp00_df)
        self.filtered_df = analyzer.perform_fundamental_analysis()
        #debugging
        print(f'loaded Data :\n {self.filtered_df.head()}')
        print(f"Number of rows in filtered data: {len(self.filtered_df)}")
        print(f"Missing values in filtered data:\n{self.filtered_df.isnull().sum()}")
        print(f"Data types of filtered data:\n{self.filtered_df.dtypes}")

        #use dict more effiecnet than the set or list 
        self.Symbol_to_score = dict(zip(self.filtered_df['ticker'], self.filtered_df['score']))

        #method how many cash we want to place for each trade
    def postion_sizing (self , symbol) : 

        cash = self.get_cash()   # cash in the account 
        last_price = self.get_last_price(symbol)
        quantity = round(cash * self.cash_at_risk / last_price,0) 
        return cash, last_price, quantity
    
    def stop_loss (self ):
        stop_loss_amm = (self.last_price ) * (1 - self.cash_at_risk)
        return stop_loss_amm
    #it still need to be connected to the iternation 


    def create_order (self , symbol , quantity , price , side , type = 'market'):
        order = {
            'symbol': symbol,
            'quantity': quantity,
            'price': price,
            'side': side,
            'type': type
            
        }
        return order
    def submit_order(self , order):
        print(f'order submitted : {order}')

    def get_fundamental_score (self , symbol):
       return self.symbol_to_score.get(symbol , None)
        
        
#####################try to fix the overlooping 

    #run every time we get new data
    def on_trading_iteration(self):
        #cProfile.run('self.on_trading_iteration()', 'profile_results.prof')
        if self.filtered_df is None  or self.filtered_df.empty: 
            print("Filtered data is empty or not loaded. Loading data now...")
            self.load_filtered_data()

        print(f"Filtered Symbols: {list(self.symbol_to_score.keys())}")   # debugging

        for symbol in self.symbol_to_score : 
            print(f"Processing symbol: {symbol}") #debugging

            cash, last_price, quantity  = self.postion_sizing(symbol)
            fundamental_score = self.get_fundamental_score(symbol)
            print(f"Fundamental score for {symbol}: {fundamental_score}")  # Debugging

            if cash > last_price and self.last_trade.get(symbol) is None:
                if fundamental_score is not None and fundamental_score >= 7 : 
                    print(f"Executing buy for {symbol}") #debugging
                    order = self.create_order(symbol , quantity , last_price , 'buy' , type = 'market')
                    self.submit_order(order)
                    self.last_trade[symbol] = 'buy'

                    print(f"Executed buy order for {symbol} with quantity {quantity} at price {last_price}")
                else:
                    print(f"Skipping {symbol} due to technical conditions.")
            
                
            elif symbol in self.last_trade and self.last_trade[symbol] == 'buy':
                if fundamental_score is not None and fundamental_score < 5:  # For example, sell if the fundamental score drops below 5
                    order = self.create_order(symbol,quantity,last_price, 'sell',type='market')
                    self.submit_order(order)
                    self.last_trade[symbol] = 'sell'
                    print(f"Executed sell order for {symbol} due to low fundamental score.")
              
                   

    def buy ():
        pass
    def sell():
        pass


    
    #analysis stratigies 
    def setintemt_analysis():
        pass

    def techniqual_analysis():
        pass
    def fundemental_analysis():
        pass

 
backtesting_start_date = datetime(2022 ,11 , 15 )
backtesting_end_date = datetime(2024,11 ,23)
broker = Alpaca(ALPACA_CREDS)
strategy= trading_strategy(name = 'mlstrat' , broker= broker , 
                           parameters = {'cash_at_risk' :.5  })

print(f"Backtest Start Date: {backtesting_start_date}") #debugging 
print(f"Backtest End Date: {backtesting_end_date}") # debugging
#run the backtesting
strategy.backtest(
    YahooDataBacktesting , 
    backtesting_start_date , 
    backtesting_end_date , 
    parameters = {
                  'cash_at_risk' :.5 }   #higher cash at risk men more cash per trade 
)


# Yes, it is possible that the conditional statements in this section could be contributing to performance issues, especially if they are being executed repeatedly in each iteration. Let's break it down:

# Repeated Condition Checks:

# The code has multiple if checks inside the method. In particular:
# Checking if cash > last_price
# Checking if self.symbol in self.filtered_df['ticker'].values
# Checking if self.last_trade == None These checks are being executed every time the method on_trading_iteration is called. If this method is being called frequently (e.g., in every iteration of a trading loop), these checks can accumulate and take significant time if there are many symbols or orders involved.
# Dataframe Filtering (self.symbol in self.filtered_df['ticker'].values):

# The line self.symbol in self.filtered_df['ticker'].values can be particularly slow if self.filtered_df['ticker'] contains a large number of rows. The in operation with a large DataFrame column is an O(n) operation, meaning it could be slow for large datasets.
# If this check is happening often, it could cause the program to lag.
# Order Creation (self.create_order()) and Submission (self.submit_order()):

# Even though these functions may not directly cause performance issues, they can be part of the problem if they are tied to external processes like API calls or database operations. If these functions are performing network operations or heavy computations, it will add to the overall time spent in each iteration.
# Suggestions to Improve Performance:
# Optimize in Checks:

# Instead of checking self.symbol in self.filtered_df['ticker'].values every iteration, consider pre-processing the filtered symbols into a set or list (which has O(1) lookup time) before the loop starts.
# Refactor Conditionals:

# Try to minimize the number of if checks in each iteration, especially if they are not necessary for every trade iteration. For example, if the condition self.last_trade == None only needs to be checked once per session, move that check outside of the main loop.
# Profile Your Code:

# Use Python's cProfile module or a similar profiler to determine which part of the code consumes the most time. This can help you pinpoint the bottleneck more effectively.
# Asynchronous Calls:

# If there are network calls or slow external processes, you could make the order submission process asynchronous to prevent blocking other operations.
# By refactoring the logic and making these optimizations, you should be able to reduce the time taken per iteration and improve the performance of your trading algorithm.
