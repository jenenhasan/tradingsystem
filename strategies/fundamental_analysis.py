import yfinance as yf
import pandas as pd 
from datetime import datetime
import os 
import time 



class data_fetcher : 
    def __init__(self, tickers=None, file_path=None):
        self.tickers = tickers
        self.file_path = file_path

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

        stock = yf.Ticker(ticker)   # ticker is the stock symbol
        info = stock.info   # info is dict for all comp inf
        return {
        "ticker": ticker,
        "pe_ratio": info.get("trailingPE"),
        "revenue_growth": info.get("revenueGrowth"),
        "roe": info.get("returnOnEquity"),
        "debt_to_equity": info.get("debtToEquity"),
        "dividend_yield": info.get("dividendYield"),
        'industry' : info.get('industry'),
        'sector' : info.get('sector')
        }

    # Loop through the S&P 500 tickers and fetch data
    def fetch_sp500_fdata(self , tickers):
        data = []
        for ticker in tickers:
            try: 
                data.append(self.fetch_financial_data(ticker))
            except Exception as e:
                print(f"Error fetching data for {ticker}: {e}")

        self.data = pd.DataFrame(data)
        return self.data
    # Save the fetched data to CSV
    def save_sp500_data_to_csv(self , tickers):

        sp500_data = self.fetch_sp500_fdata(tickers)
        if sp500_data.empty :  # Check if data is empty
            raise ValueError("No data fetched for the provided tickers.")
        df = pd.DataFrame(sp500_data)
        df.to_csv(self.file_path, index=False)
        print(f"Saved S&P 500 financial data to {self.file_path}")
        return df


class fundamental_analyzer : 

    def __init__(self, data , fill_missing=True):
        self.data = pd.DataFrame(data)
        self.fill_missing = fill_missing


    def handle_missing_data(self):


        #just to check for missing data 
        #print('checking for missing values')
        #print(self.data[['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']].isnull().sum())


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
                        # Get all the existing non-NaN values for that industry
                        industry_values = self.data[self.data['industry'] == industry][column].dropna()
                        if not industry_values.empty:
                            industry_medians[industry] = industry_values.median()

                    # If we have a median for the industry, fill the missing value
                    if industry in industry_medians:
                        self.data.at[idx, column] = industry_medians[industry]

        # Drop rows with missing values in specific columns if required
        self.data = self.data.dropna(subset=columns_to_check)
            #this is a correct approach but it is slowing the performance (groupby) so i will try to use same logic but without using group by 
            # for i in ['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield'] : 
            #     if i in self.data.columns : 
            #         self.data[i] = pd.to_numeric(self.data[i] , errors= 'coerce')
            #         self.data[i] = self.data.groupby('industry')[i].transform(lambda x : x.fillna(x.median()))
            #     else : 
            #         self.data = self.data.dropna(subset =['pe_ratio', 'roe', 'debt_to_equity', 'dividend_yield'] )
            ## i will use the dict approach 

        #just to check for missing data
        #print("Checking for missing values after handling:")
        #print(self.data[['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']].isnull().sum())


    def calculate_scores(self):
        scores = []
        for _, row in self.data.iterrows():
            score = 0
            pe_ratio = row['pe_ratio']
            if pe_ratio <= self.data['pe_ratio'].quantile(0.25) : 
                score +=2 
            elif pe_ratio <=self.data['pe_ratio'].quantile(0.5):
                score+=1
            else:
                score+=0 


            revenue_growth = row['revenue_growth'] 
            if revenue_growth >= 0.1 :
                score+=2 
            elif revenue_growth >=0 :
                score+=1 
            else : score+=0



            roe = row['roe']
            if roe >=0.2  : 
                score +=2
            elif roe > 0.1 : 
                score +=1 
            else : 
                score +=0 

                
            debt_to_equity = row['debt_to_equity']
            if debt_to_equity <= self.data['debt_to_equity'].quantile(0.25):
                score += 2 
            elif debt_to_equity <= self.data['debt_to_equity'].quantile(0.5):
                score += 1  
            else:
                score += 0 

            dividend_yield = row['dividend_yield']
            if dividend_yield >= self.data['dividend_yield'].quantile(0.75):
                score += 2 
            elif dividend_yield >= self.data['dividend_yield'].quantile(0.5):
                score += 1 
            else:
                score += 0  
            scores.append(score)
        self.data['score'] = scores
        return self.data

    
    # Apply fundamental analysis filter
    def perform_fundamental_analysis(self):

        #just to check for missing data 
        #print("Before handling missing data:")
        #print(self.data[['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']].isnull().sum()) 

        print(self.data.dtypes)
        self.handle_missing_data()

        #just to check for missing data
        #print("After handling missing data:")
        #print(self.data[['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']].isnull().sum())

        self.calculate_scores()
        filtered_df = self.data[self.data['score'] >= self.data['score'].quantile(0.75) ]
        return filtered_df
        # self.handle_missing_data()
        # # Convert relevant columns to numeric, invalid values to NaN
        # df['pe_ratio'] = pd.to_numeric(df['pe_ratio'], errors='coerce')
        # df['revenue_growth'] = pd.to_numeric(df['revenue_growth'], errors='coerce')
        # df['roe'] = pd.to_numeric(df['roe'], errors='coerce')
        # df['debt_to_equity'] = pd.to_numeric(df['debt_to_equity'], errors='coerce')
        # df['dividend_yield'] = pd.to_numeric(df['dividend_yield'], errors='coerce')

    
        # print(df[['pe_ratio', 'revenue_growth', 'roe', 'debt_to_equity', 'dividend_yield']].describe())

        # #it still need enhancement about the comparison stratigie 
        # #calculate the dynamic values from the database
        # pe_ratio_threshold = df['pe_ratio'].quantile(0.5)  # how much investors are willing to pay for each dollar of earnings.
        # debt_to_equity_threshold = df['debt_to_equity'].quantile(0.5)  # total debt to its equity
        # dividend_yield_threshold = df['dividend_yield'].quantile(0.5)  #how much income an investor can expect to receive from dividends as a percentage of the stock price
        # roe_threshold = 0.10 #how effectively a company uses shareholder equity to generate profits
        # revenue_growth_threshold = 0    # shows the company’s ability to increase sales over time

        # #the filter is strict (chose it i want to focus on quality over quantity )
        # # for now focusing on value investing , if we want faster but more risky i  will focus on growth investing  
        # filtered_df = df[
        #     (df['pe_ratio'] <= pe_ratio_threshold) &  #Lower P/E ratio
        #     (df['revenue_growth'] >= revenue_growth_threshold) & # Positive or neutral revenue growth 
        #     (df['roe'] >= roe_threshold) &   # At least 10% ROE
        #     (df['debt_to_equity'] <= debt_to_equity_threshold) & # Lower debt-to-equity ratio
        #     (df['dividend_yield'] >= dividend_yield_threshold)  # Higher dividend yield
        #     ]
        

        # if self.data is None or self.data.empty:
        #     raise ValueError("The DataFrame is empty or not loaded.")
        # return filtered_df
        



def main():
    
    scored_file_path = 'C:\\Users\\jenen\\Desktop\\Atomatedtradingbot\\scored_file.csv'
    sp500_file_path = 'C:\\Users\\jenen\\Desktop\\Atomatedtradingbot\\sp500_financail_data.csv'
    start_time = time.time()
    fetcher =  data_fetcher(file_path=sp500_file_path)

    tickers  = fetcher.fetch_sp500_ticker() 


    sp500_df= fetcher.save_sp500_data_to_csv(tickers)
    if sp500_df.empty:
        raise ValueError("Failed to fetch or save S&P 500 financial data.")
    end_time = time.time()
    print(f"Execution time: {end_time - start_time} seconds")
    
    # Initialize the StockAnalyzer class
    stock_analyzer = fundamental_analyzer(sp500_df)
    #cProfile.run('stock_analyzer.perform_fundamental_analysis()')
    
    # Perform fundamental analysis and get filtered data
    scored_df = stock_analyzer.perform_fundamental_analysis()

    # Save filtered data to CSV with a timestamp
    
    scored_df.to_csv(scored_file_path, index=False)
    
    return scored_df


if __name__ == '__main__':
    main()







