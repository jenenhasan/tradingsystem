import yfinance as yf
import pandas as pd 
from datetime import datetime



class data_fetcher : 
    def __init__(self, tickers=None, file_path=None):
        self.tickers = tickers
        self.file_path = 'C:/Users/jenen/Desktop/Atomatedtradingbot/sp500_financail_data.csv'
        self.data = []

    # Fetch the S&P 500 list
    def fetch_sp500_ticker(self):
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)  # .read_html is a function to read the tables and return them in a list of dataframes
        df = tables[0]  # Just access the first column because it has the names 
        tickers = df['Symbol'].tolist()  # Change the first column, 'Symbol', to a list 
        return tickers

    #later i can enhanc it using web scraping 
    # Fetch data from the API
    def fetch_financial_data(self , ticker):
        stock = yf.Ticker(ticker)
        info = stock.inf
        return {
        "ticker": ticker,
        "pe_ratio": info.get("trailingPE"),
        "revenue_growth": info.get("revenueGrowth"),
        "roe": info.get("returnOnEquity"),
        "debt_to_equity": info.get("debtToEquity"),
        "dividend_yield": info.get("dividendYield"),
        }

    # Loop through the S&P 500 tickers and fetch data
    def fetch_sp500_fdata(self , tickers):
        data = []
        for ticker in tickers:
            try:
                data.append(self.fetch_financial_data(ticker))
            except Exception as e:
                print(f"Error fetching data for {ticker}: {e}")
        return data
    # Save the fetched data to CSV
    def save_sp500_data_to_csv(self , tickers):
        sp500_data = self.fetch_sp500_fdata(tickers)
        df = pd.DataFrame(sp500_data)
        df.to_csv('sp500_financail_data.csv', index=False)
        print('Saved sp500 financial data to sp500_financial_data.csv')


    # Load the S&P 500 financial data from the CSV file
    def load_sp500_data_from_csv(self ):
        df = pd.read_csv(self.file_path)
        return df

class fundamental_analyzer : 
    def __init__(self, data):
        self.data = data 
     

    
    # Apply fundamental analysis filter
    def perform_fundamental_analysis(self):
        df = self.data
        # Convert relevant columns to numeric, invalid values to NaN
        df['pe_ratio'] = pd.to_numeric(df['pe_ratio'], errors='coerce')
        df['revenue_growth'] = pd.to_numeric(df['revenue_growth'], errors='coerce')
        df['roe'] = pd.to_numeric(df['roe'], errors='coerce')
        df['debt_to_equity'] = pd.to_numeric(df['debt_to_equity'], errors='coerce')
        df['dividend_yield'] = pd.to_numeric(df['dividend_yield'], errors='coerce')

    
        print(df[['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']].describe())

        #it still need enhancement about the comparison stratigie 
        #calculate the dynamic values from the database
        pe_ratio_threshold = df['pe_ratio'].quantile(0.25)  # how much investors are willing to pay for each dollar of earnings.
        debt_to_equity_threshold = df['debt_to_equity'].quantile(0.25)  # total debt to its equity
        dividend_yield_threshold = df['dividend_yield'].quantile(0.75)  #how much income an investor can expect to receive from dividends as a percentage of the stock price
        roe_threshold = 0.15 #how effectively a company uses shareholder equity to generate profits
        revenue_growth_threshold = 0    # shows the company’s ability to increase sales over time

        #the filter is strict (chose it i want to focus on quality over quantity )
        # for now focusing on value investing , if we want faster but more risky i  will focus on growth investing  
        filtered_df = df[
            (df['pe_ratio'] <= pe_ratio_threshold) &  #Lower P/E ratio
            (df['revenue_growth'] >= revenue_growth_threshold) & # Positive or neutral revenue growth 
            (df['roe'] >= roe_threshold) &   # At least 10% ROE
            (df['debt_to_equity'] <= debt_to_equity_threshold) & # Lower debt-to-equity ratio
            (df['dividend_yield'] >= dividend_yield_threshold)  # Higher dividend yield
            ]
        return filtered_df


def main():
    
    file_path = 'C:\\Users\\jenen\\Desktop\\Atomatedtradingbot\\sp500_financail_data.csv'
    stock_fetcher = data_fetcher(file_path=file_path)
    
    # stock_fetcher.fetch_sp500_tickers()
    # stock_fetcher.fetch_data()
    # stock_fetcher.save_data_to_csv()
    
    # Load data from CSV
    df = stock_fetcher.load_sp500_data_from_csv()

    # Initialize the StockAnalyzer class
    stock_analyzer = fundamental_analyzer(df )
    
    # Perform fundamental analysis and get filtered data
    filtered_df = stock_analyzer.perform_fundamental_analysis()

    # Save filtered data to CSV with a timestamp
    
    filtered_df.to_csv('C:\\Users\\jenen\\Desktop\\Atomatedtradingbot\\filtered_sp500_financial_data_2024-11-29_22-12-26.csv', index=False)
    print(filtered_df.head())

if __name__ == '__main__':
    main()

