from lumibot.brokers import Alpaca # broker is what will make the execution 
from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies.strategy import Strategy #for the actual trading bot
from lumibot.traders import Trader # for deployement capability 
from datetime import datetime    #we will need this for the backtesting
from dotenv import load_dotenv
import os 
#from alpaca.trading.client import TradingClient


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
    def initialize(self ,symbol:str = "SPY"): 
      
        self.symbol = symbol
        self.sleep_time = "24H"
        self.last_trade = None


    #run every time we get new data
    def on_trading_iteration(self):
        if self.last_trade == None :
            order = self.create_order(
                self.symbol,
                10, 
                'buy',
                type = 'market'
            )
            self.submit_order(order)
            self.last_trade = 'buy '

    #method to mangange the ammount of money we want to risk 
    def postion_sizing (self) : 
        # cash = self.get_cash()
        # last_price_stock = self.get_last_price(self.symbol)
        # risk_per_trade  = cash * riskperc
        
        # share_to_buy = round(risk_per_trade /last_price_stock , 0 )
        # return cash , last_price_stock , share_to_buy

        cash = self.get_cash() 
        last_price = self.get_last_price(self.symbol)
        quantity = round(cash * self.cash_at_risk / last_price,0)
        return cash, last_price, quantity


    
    #analysis stratigies 
    def setintemt_analysis():
        pass

    def techniqual_analysis():
        pass
    def fundemental_analysis():
        pass


    


  
       

backtesting_start_date = datetime(2022 ,11 , 15 )
backtesting_end_date = datetime(2023,12 , 20)
broker = Alpaca(ALPACA_CREDS)
strategy= trading_strategy(name = 'mlstrat' , broker= broker , 
                           parameters = {'symbol' : 'SPY'})


#run the backtesting
strategy.backtest(
    YahooDataBacktesting , 
    backtesting_start_date , 
    backtesting_end_date , 
    parameters = {'symbol' : 'SPY'}
)




