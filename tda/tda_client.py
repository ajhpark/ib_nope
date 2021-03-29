from tda.auth import easy_client
from selenium import webdriver
from datetime import datetime
import pandas as pd
import atexit
import numpy as np


class TDAClient:
    ticker = "SPY"

    def __init__(self):
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.consumer_key = [YOUR_TDA_CONSUMER_KEY]
        self.redirect_uri = [REDIRECT_URI_CHOSEN_FOR_YOUR_APP]  # e.g. 'https://localhost/test'
        self.token_path = [TOKEN_PATH]  # e.g. '/tmp/token.pickle'

        # Creates Webdriver for Selenium (you can use other browsers)
        def make_webdriver():
            driver = webdriver.Safari()
            atexit.register(lambda: driver.quit())
            return driver

        # Sets td-api Client Object.
        # Will Create Refresh Token with OAUTH and Grab With Selenium
        # if it Doesn't Exist in Working Folder.
        self.c = easy_client(self.consumer_key,
                             self.redirect_uri,
                             self.token_path,
                             make_webdriver)

    def options_chain_cleaner(self, options_chain, only_type=False):
        """
        Takes unformatted option chain csv and returns cleaned up df.
        Specify only_type='Calls' or 'Puts' if only wanting one or other,
        specify False if wanting both and 2 dataframes will be returned,
        calls first and puts second.

        i.e. calls, puts = func('file.csv')
        """
        if only_type == 'Calls':
            Calls = options_chain['callExpDateMap'].values()
            call_option_list = []
            for i in Calls:
                for j in i.values():
                    for k in j:
                        call_option_list.append(k)
            Calls_df = pd.DataFrame(call_option_list)
            Calls_df.set_index('description', inplace=True)
            return Calls_df

        elif only_type == 'Puts':
            Puts = options_chain['putExpDateMap'].values()
            put_option_list = []
            for i in Puts:
                for j in i.values():
                    for k in j:
                        put_option_list.append(k)
            Puts_df = pd.DataFrame(put_option_list)
            Puts_df.set_index('description', inplace=True)
            return Puts_df

        elif not only_type:
            Puts = options_chain['putExpDateMap'].values()
            Calls = options_chain['callExpDateMap'].values()

            call_option_list = []
            for i in Calls:
                for j in i.values():
                    for k in j:
                        call_option_list.append(k)
            Calls_df = pd.DataFrame(call_option_list)
            Calls_df.set_index('description', inplace=True)

            put_option_list = []
            for i in Puts:
                for j in i.values():
                    for k in j:
                        put_option_list.append(k)
            Puts_df = pd.DataFrame(put_option_list)
            Puts_df.set_index('description', inplace=True)

            return Calls_df, Puts_df

        else:
            raise ValueError('Incorrect only_type value')

    def nope_calc(self,
                  call_volumes: float or int,
                  put_volumes: float or int,
                  call_deltas: float,
                  put_deltas: float,
                  share_volume: float or int):
        """
        Calculates NOPE, takes volumes
        and deltas as pandas Series and
        share volume as int.
        """
        result = (sum((((call_volumes*100).mul(call_deltas*100, fill_value=0)).values-((put_volumes*100).mul(abs(put_deltas*100), fill_value=0)).values)))/share_volume
        return result

    def get_nope(self):
        # Sets Dictionaries for Call, Put, and Equity Data with format {'Ticker Symbol' : DataFrame of Data}
        call_chains = {}
        put_chains = {}
        equity_quotes = {}

        # Gets option chains for specified symbol. Appends to dictionary
        # as {'Ticker Symbol' : call chain in DataFrame},
        # {'Ticker Symbol' : put chain in DataFrame}
        options_chain = self.c.get_option_chain(symbol=self.ticker, strike_range=self.c.Options.StrikeRange.ALL)
        calls_chain, puts_chain = self.options_chain_cleaner(options_chain.json())
        calls_chain['date'] = self.today
        puts_chain['date'] = self.today
        call_chains[self.ticker] = calls_chain[calls_chain['delta'] != -999.0]
        put_chains[self.ticker] = puts_chain[puts_chain['delta'] != -999.0]

        # Gets quotes for specified equity. Appends to dictionary
        # as {'Ticker Symbol' : quote in DataFrame}.
        quotes = self.c.get_quotes(symbols=self.ticker)
        equity_quotes[self.ticker] = pd.DataFrame(quotes.json()).T
        equity_quotes[self.ticker].drop(columns=['52WkHigh', '52WkLow'], inplace=True)
        equity_quotes[self.ticker].replace({'': np.nan, ' ': np.nan}, inplace=True)

        # Set Dictionary for Call, Put, Share Volume and Delta Data
        call_deltas = {}
        put_deltas = {}

        call_volumes = {}
        put_volumes = {}
        share_volume = {}

        call_delta_sum = {}
        put_delta_sum = {}

        call_volume_sum = {}
        put_volume_sum = {}

        # Appends Call, Put, Share Volume and Delta to Dictionaries
        # with format {'Ticker Symbol' : option delta or volume as series or share volume as int}
        call_deltas[self.ticker] = call_chains[self.ticker]['delta'].astype(float)
        put_deltas[self.ticker] = put_chains[self.ticker]['delta'].astype(float)

        call_volumes[self.ticker] = call_chains[self.ticker]['totalVolume'].astype(float)
        put_volumes[self.ticker] = put_chains[self.ticker]['totalVolume'].astype(float)
        share_volume[self.ticker] = int(equity_quotes[self.ticker]['totalVolume'])

        call_delta_sum[self.ticker] = call_chains[self.ticker]['delta'].astype(float).sum()
        put_delta_sum[self.ticker] = put_chains[self.ticker]['delta'].astype(float).sum()

        call_volume_sum[self.ticker] = call_chains[self.ticker]['totalVolume'].astype(float).sum()
        put_volume_sum[self.ticker] = put_chains[self.ticker]['totalVolume'].astype(float).sum()

        try:
            nope = self.nope_calc(call_deltas=call_deltas[self.ticker],
                                  put_deltas=put_deltas[self.ticker],
                                  call_volumes=call_volumes[self.ticker],
                                  put_volumes=put_volumes[self.ticker],
                                  share_volume=share_volume[self.ticker])
        except ZeroDivisionError:
            curr_dt = datetime.now().strftime("%Y-%m-%d at %H:%M:%S")
            with open("logs/errors.txt", "a") as f:
                f.write(f'No volume data on {self.ticker} | {curr_dt}\n')
            return [0, 0]

        return [nope, equity_quotes[self.ticker]['askPrice']]
