"""Pairs Trading Algorithm

Basic pairs trading algorithm with rebalancing for an active portfolio.
"""

__version__ = "0.1"
__author__ = "Alistair Russell"

from ast import literal_eval
import datetime as dt
import numpy as np
import pandas as pd
import pandas_datareader as pdr
import statsmodels.api as sm
import itertools as it
from ib_insync import Stock

from basealgorithm import BaseAlgo


class PairsTradingAlgo(BaseAlgo):
    def __init__(self, formation_period=("2021-10-05", "2022-10-05"), **kwargs):
        super(PairsTradingAlgo, self).__init__(**kwargs)
        # read in formation period data or generate it from historical data
        start, end = formation_period
        try:
            self.data = pd.read_csv("pairs-data.csv")
            print("Pairs data found in csv file.")
        except FileNotFoundError:
            print("Pairs data file not found. generating from historical data.")
            self.data = self._gen_formation_data(start, end)

    def _universe_selection(self):
        sp_data = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        )[0]
        tickers = sp_data.Symbol.to_list()
        return tickers

    def _form_pairs(self, num_pairs):
        sorted_pairs = []
        distances = {}
        for pair in self.ticker_pairs:
            distances[pair] = sum(
                (self.return_data[pair[0]] - self.return_data[pair[1]]) ** 2
            )
            sorted_pairs = sorted(distances, key=lambda x: distances[x])[:num_pairs]
        return sorted_pairs

    def _gen_formation_data(self, start_date, end_date):
        # get tickers from universe selection
        self.tickers = self._universe_selection()
        self.ticker_pairs = list(it.combinations(self.tickers, 2))
        self.sorted_pairs = None

        panel_data = pdr.DataReader(
            self.tickers, "yahoo", start=start_date, end=end_date
        )["Adj Close"]

        # get a price dataframe
        price_data = pd.DataFrame(panel_data.to_dict())

        # change each column to cumulative returns to get a returns df
        df = price_data.copy(deep=True)
        for col in df:
            df[col] = df[col].pct_change().add(1).cumprod().sub(1)
        self.return_data = df.tail(252)

        # find 20 pairs with the minimum ssd and filter price data
        self.sorted_pairs = self._form_pairs(50)
        unique_tics = list(set([i for tup in self.sorted_pairs for i in tup]))

        # create log price data
        log_price_data = price_data[unique_tics].tail(252)
        for col in log_price_data:
            log_price_data[col] = np.log(log_price_data[col])

        # create a df to hold the formation period data we want to keep
        data = pd.DataFrame(
            columns=["pair", "hedge_ratio", "spread_mean", "spread_std"],
        )
        for pair in self.sorted_pairs:
            # tranform to log prices
            log_price_0 = log_price_data[pair[0]]
            log_price_1 = log_price_data[pair[1]]

            # regress log prices on eachother to get the hedge ratio
            model = sm.OLS(log_price_0, log_price_1).fit()
            hedge_ratio = model.params[0]
            spread = np.array(log_price_0 - hedge_ratio * log_price_1)
            mean = np.mean(spread)
            std = np.std(spread)

            # add data to dataframe
            data.loc[len(data.index)] = [pair, hedge_ratio, mean, std]

        # write pairs formation data out to a file adn return data
        data.to_csv("pairs-data.csv", index=False)
        return data

    def rebalance(self):
        """ Rebalance pairs trades """
        # exit any open pairs traded positions
        positions = [p for p in self.ibconn.positions() if p.contract.secType == "STK"]

        # set a max portfolio allotment based on the number of positions
        max_allotment = min(
            self.portfolio_val / (len(self.data) * 2), self.max_position
        )

        # for each trading pair, calculate the current spread
        for index, row in self.data.iterrows():
            pair = literal_eval(row.pair)
            tic1, tic2 = pair

            # form contracts for the security pair
            sec1 = Stock(tic1, "SMART", "USD")
            sec2 = Stock(tic2, "SMART", "USD")
            self.ibconn.reqMarketDataType(4)
            contracts = self.ibconn.qualifyContracts(sec1, sec2)
            assert sec1 in contracts
            assert sec2 in contracts

            # price each security and calculate the spread and z-score
            [p1, p2] = self.ibconn.reqTickers(*contracts)
            if (p1.last and p2.last) == False:
                print(f"Can't find last price for one of {pair}. Skipping.")
                continue

            spread = np.log(p1.last) - row.hedge_ratio * np.log(p2.last)
            z_score = (spread - row.spread_mean) / row.spread_std

            filter = [p for p in positions if p.contract.symbol in pair]

            # set the allocation based on the first security
            allocation = np.floor(max_allotment / p1.last)

            # if the szcore is small and positions are open, liquidate them
            if abs(z_score) < 1 and len(filter) > 0:
                for stk in filter:
                    print(f"Zscore is {z_score} - closing {pair} positions...")
                    self.market_order(stk.contract, -1 * stk.position)
            # if the zscore exceeds 1 and no positions are open, long or short the spread
            elif z_score > 1 and len(filter) == 0:
                print(
                    f"Zscore is {z_score} - shorting {pair} spread with allocation of {allocation}"
                )
                self.market_order(sec1, -1 * allocation)
                self.market_order(sec2, np.floor(allocation * row.hedge_ratio))
            elif z_score < -1 and len(filter) == 0:
                print(
                    f"Zscore is {z_score} - long {pair} spread with allocation of {allocation}"
                )
                self.market_order(sec1, allocation)
                self.market_order(sec2, np.floor(-1 * allocation * row.hedge_ratio))
            else:
                print(f"Zscore is {z_score} - no action for {pair} spread...")
