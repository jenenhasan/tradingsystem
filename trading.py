from lumibot.brokers import Alpaca # for APIs 
from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies.strategy import Strategy #for the actual trading bot
from lumibot.traders import Trader # for deployement capability 
from datetime import datetime

API_KEY = "PKC5DHF8RVWA6MZIRIUP"
API_SECRET = "d84JaERm9byLkyxljR0LUE0lzfC3WoOytM8KfzfP"
BASE_URL = "https://paper-api.alpaca.markets/v2"
ALPACA_CREDS = {
    "API_KEY" : API_KEY, 
    "API_SECRET" : API_SECRET,
    "PAPER": True

}



