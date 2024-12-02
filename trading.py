from lumibot.brokers import Alpaca # broker is what will make the execution 
from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies.strategy import Strategy #for the actual trading bot
from lumibot.traders import Trader # for deployement capability 
from datetime import datetime    #we will need this for the backtesting
from dotenv import load_dotenv
import os 
import pandas as pd 
#from alpaca.trading.client import TradingClient


from strategies.fundamental_analysis import main



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
    def initialize(self ,symbol:str = "SPY"  , cash_at_risk:float = .5): 
      
        self.symbol = symbol
        self.sleep_time = "24H"
        self.last_trade = None
        self.cash_at_risk = cash_at_risk 
        self.filtered_df = pd.read_csv('filtered_sp500_financial_data_2024-11-29_22-12-26.csv')
        

        #method how many cash we want to place for each trade
    def postion_sizing (self) : 

        cash = self.get_cash() 
        last_price = self.get_last_price(self.symbol)
        quantity = round(cash * self.cash_at_risk / last_price,0) 
        return cash, last_price, quantity
    
    def stop_loss (self ):
        stop_loss_amm = (self.last_price ) * (1 - self.cash_at_risk)
        return stop_loss_amm
    #it still need to be connected to the iternation 
    def perform_fundamental_analysis(self):
        try : 
            self.filtered_df = main()
            if self.filtered_df is None or self.filtered_df.empty : 
                raise ValueError('filtered data is empty ')
            print('fundamental analysis performed successfully')

        except : 
            print('error in fa')
            
        
        
#####################try to fix the overlooping 

    #run every time we get new data
    def on_trading_iteration(self):
        cash, last_price, quantity  = self.postion_sizing()
        # inorder not to buy when we dont have cash
        if cash > last_price : 
            if self.symbol in self.filtered_df['ticker'].values:
                #if for the first trade 
                if self.last_trade == None : #####fix this it has to check just once 
                    order = self.create_order(
                        self.symbol,
                        quantity,
                        10, 
                        'buy',
                        type = 'market'
                        )
                    self.submit_order(order)
                    self.last_trade = 'buy '
    

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
                           parameters = {'symbol' : 'SPY' ,
                                          'cash_at_risk' :.5  })


#run the backtesting
strategy.backtest(
    YahooDataBacktesting , 
    backtesting_start_date , 
    backtesting_end_date , 
    parameters = {'symbol' : 'SPY', 
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
