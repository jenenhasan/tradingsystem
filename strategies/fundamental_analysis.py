import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time


# Helper functions for logging
class data_fetcher:
    def __init__(self, tickers=None, file_path=None):
        self.tickers = tickers
        self.file_path = file_path
        self.data = []

    # Fetch the S&P 500 list
    def fetch_sp500_ticker(self):
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        tickers = df['Symbol'].tolist()
        np.savetxt("tickers.csv", tickers, fmt="%s")
        return tickers

    # Fetch data from the API
    def fetch_financial_data(self, ticker):
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            "ticker": ticker,
            "pe_ratio": info.get("trailingPE"),
            "revenue_growth": info.get("revenueGrowth"),
            "roe": info.get("returnOnEquity"),
            "debt_to_equity": info.get("debtToEquity"),
            "dividend_yield": info.get("dividendYield"),
            "industry": info.get("industry"),
            "sector": info.get("sector")
        }

    def update_wrong_tickers(self, ticker):
        symbol_map = {
            'BRK.B': 'BRK-B',
            'BF.B': 'BF-B'
        }
        return symbol_map.get(ticker, ticker)

    # Loop through the S&P 500 tickers and fetch data
    def fetch_sp500_fdata(self, tickers):
        data = []
        for ticker in tickers:
            updated_ticker = self.update_wrong_tickers(ticker)
            try:
                data.append(self.fetch_financial_data(updated_ticker))
            except Exception as e:
                print(f"Error fetching data for {updated_ticker}: {e}")

        self.data = pd.DataFrame(data)

        # Log missing data and drop counts
        
        return self.data

    # Save the fetched data to CSV
    def save_sp500_data_to_csv(self, tickers):
        sp500_data = self.fetch_sp500_fdata(tickers)
        if sp500_data.empty:
            raise ValueError("No data fetched for the provided tickers.")
        df = pd.DataFrame(sp500_data)
        df.to_csv(self.file_path, index=False)
        print(f"Saved S&P 500 financial data to {self.file_path}")
        return df

class fundamental_analyzer:
    def __init__(self, data, fill_missing=True):
        self.data = pd.DataFrame(data)
        self.fill_missing = fill_missing
  
    def handle_missing_data(self):
        print("Handling missing data...")
        if self.fill_missing:
            columns_to_check = ['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']
            self.data['industry'] = self.data['industry'].astype('category')
            industry_medians = {}
            for column in columns_to_check: 
                if column in self.data.columns:
                    self.data[column] = pd.to_numeric(self.data[column], errors='coerce')
                    for idx, row in self.data.iterrows():
                        industry = row['industry']
                        value = row[column]
                        if pd.notna(value):
                            continue
                        if industry not in industry_medians:
                            industry_values = self.data[self.data['industry'] == industry][column].dropna()
                            if not industry_values.empty:
                                industry_medians[industry] = industry_values.median()

                        if industry in industry_medians:
                            self.data.at[idx, column] = industry_medians[industry]
            if 'FSLR' in self.data['ticker'].unique():
                median_dividend_yield = self.data['dividend_yield'].median()
                self.data.loc[self.data['ticker'] == 'FSLR', 'dividend_yield'] = median_dividend_yield
        
    def calculate_scores(self):
        scores = []
        for _, row in self.data.iterrows():
            score = 0
            #Lower PE ratios are better as they suggest that a company might be undervalued.
            #investing in the stock with better return 
            pe_ratio = row['pe_ratio']
            if pe_ratio <= self.data['pe_ratio'].quantile(0.25):
                score += 2
            elif pe_ratio <= self.data['pe_ratio'].quantile(0.5):
                score += 1
            #Higher revenue growth is better, with scores reflecting strong (≥ 10%) or moderate growth.
            revenue_growth = row['revenue_growth']
            if revenue_growth >= 0.1:    #more than 10% growth 
                score += 2
            elif revenue_growth >= 0:  # 1 to 10 % growth 
                score += 1
            
            #Companies in the top 25% of ROE get the highest score, while those in the bottom 25% get no score.
            #how much return it generate
            roe = row['roe']
            if roe >= self.data['roe'].quantile(0.75):  # Top 25% performers
                score += 2
            elif roe >= self.data['roe'].quantile(0.5):  # Middle performers
                score += 1
            elif roe >= self.data['roe'].quantile(0.25):  # Lower performers
                score += 0


            # Lower debt-to-equity ratios are preferred, as they suggest lower financial risk.
            #how much investing in this comoany is risky 
            debt_to_equity = row['debt_to_equity']
            if debt_to_equity <= self.data['debt_to_equity'].quantile(0.25):
                score += 2
            elif debt_to_equity <= self.data['debt_to_equity'].quantile(0.5):
                score += 1

            # Higher dividend yield rewards companies that offer better returns to shareholders.
            # how much cash a company is returning to its shareholders
            dividend_yield = row['dividend_yield']
            if dividend_yield >= self.data['dividend_yield'].quantile(0.75):
                score += 2
            elif dividend_yield >= self.data['dividend_yield'].quantile(0.5):
                score += 1

            scores.append(score)
        self.data['score'] = scores
        return self.data
    
    def handle_data_completeness(self):
        required_columns = ['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield' ]
        initial_missing = self.data[required_columns].isna().sum()
        print("Initial missing data count:", initial_missing)
        for column in required_columns:
            missing_count = self.data[column].isna().sum()
            if missing_count > 0:
                print(f'missing data in : {column} with {missing_count} missing ')
            else: 
                print(f"Column {column} is complete.")
    
        final_missing = self.data[required_columns].isna().sum()
        if final_missing.any():  # check if any value is True (missing)
            return final_missing
        else:
            return "No missing data."
        
         
    def perform_fundamental_analysis(self):

        print("Starting fundamental analysis...")
        print(f'this is the initial data missing   {self.handle_data_completeness()}')

        # Step 2: Handle missing data
        print("Handling missing data...")
        self.handle_missing_data()
        print(f'this is data missing after handling missing data {self.handle_data_completeness()}')
        # Log rows dropped specifically during missing data handling
        

        # Step 3: Calculate scores
        print("Calculating scores...")
        self.calculate_scores()

        # Step 4: Filter by scores
        print("Filtering by score...")
        filtered_df = self.data[self.data['score'] >= self.data['score'].quantile(0.75)]
        print(f'this is data missing after filtering according to score {self.handle_data_completeness()}')
        

        # Step 5: Log final state
        print(f'this is data missing at the final  {self.handle_data_completeness()}')

        # Step 6: Save filtered data for review
        filtered_df.to_csv('filtered.csv', index=False)
        return filtered_df
        

def main():
    sp500_file_path = 'C:\\Users\\jenen\\Desktop\\Atomatedtradingbot\\sp500_financail_data.csv'
    start_time = time.time()

    fetcher = data_fetcher(file_path=sp500_file_path)
    tickers = fetcher.fetch_sp500_ticker()

    print("Fetching financial data for S&P 500 companies...")
    sp500_df = fetcher.save_sp500_data_to_csv(tickers)
    if sp500_df.empty:
        raise ValueError("Failed to fetch or save S&P 500 financial data.")

    print("Performing fundamental analysis...")
    stock_analyzer = fundamental_analyzer(sp500_df)
    scored_df = stock_analyzer.perform_fundamental_analysis()

    end_time = time.time()
    print(f"Execution time: {end_time - start_time} seconds")

if __name__ == '__main__':
    main()






