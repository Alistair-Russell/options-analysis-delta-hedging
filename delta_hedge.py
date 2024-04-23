"""Delta Hedging

This module is for basic trading functionality including an implementation of delta hedging
"""

__version__ = "0.1"
__author__ = "Alistair Russell"

from ast import literal_eval
import datetime as dt
import numpy as np
import pandas as pd
import pandas_datareader as pdr
import statsmodels.api as sm
import statsmodels.formula.api as smf
import itertools as it
from ib_insync import *


def bus_day_delta(future_date):
    today = dt.date.today()
    # REMOVE future_date=dt.datetime.strptime(future.lastTradeDateOrContractMonth, "%Y%m%d").date()
    future = dt.datetime.strptime(future_date, "%Y%m%d").date()
    return np.busday_count(today, future_date)


class BaseAlgo:
    """Base class for algorithmic trading with IBKR Trader Workstation"""

    def __init__(self, url="127.0.0.1", port=7497, client_id=1):
        """Initialize IB connection and create a contract for the underlying

        Args:
            url (str, optional): URL string for TWS or IB gateway. Defaults to "127.0.0.1"
            port (int, optional): Port number for TWS or IB gateway. Defaults to 7497
            client_id (int, optional): Client ID. Defaults to 1
        """
        # ibkr connection
        self.ibconn = IB()
        self.ibconn.connect(url, port, clientId=client_id)

        # account value
        act = self.ibconn.accountSummary()
        self.portfolio_val = float(act[19].value)

        # max position size
        self.max_position = 0.05 * self.portfolio_val

    def __del__(self):
        """Disconnects the IBKR session before object deletion"""
        self.ibconn.disconnect()

    def market_order(self, contract, num, dryrun=False):
        """Place a market order for a given contract

        Args:
            contract (obj): contract object for the security to order
            num (int): the number of contracts to sell

        Returns:
            obj: a trade (or what-if trade) object if the order num is not 0, None otherwise.
        """
        if num > 0:
            order = MarketOrder("BUY", num)
        elif num < 0:
            order = MarketOrder("SELL", abs(num))
        else:
            return None

        if dryrun:
            return self.ibconn.whatIfOrder(contract, order)
        else:
            return self.ibconn.placeOrder(contract, order)


class DeltaHedgeAlgo(BaseAlgo):
    """Pricing and hedging of SPY options"""

    def __init__(self, tic, **kwargs):
        """Initialize delta hedge algorithm for a given ticker

        Args:
            tic (string): A ticker for an option in the current portfolio
        """
        super(DeltaHedgeAlgo, self).__init__(**kwargs)

        # get current positions with matching ticker
        self.positions = [
            p for p in self.ibconn.positions() if p.contract.symbol == tic
        ]

        # filter for options and stocks with ticker
        self.opts = [p for p in self.positions if p.contract.secType == "OPT"]
        assert len(self.opts) <= 1
        self.stks = [p for p in self.positions if p.contract.secType == "STK"]
        assert len(self.stks) <= 1

        # initialize contracts
        self.stk_contract = Stock(tic, "SMART", "USD")

    def rebalance(self, dryrun=False):
        """Rebalances the initialized security to a delta neutral hedge

        Args:
            dryrun (bool, optional): Execute a what-if trade instead of a real one. Defaults to False.

        Returns:
            list: current portfolio positions
        """
        # check that open option position exists
        if len(self.opts) == 0:
            print("No open option position to hedge")
            return

        # get current option contract details and ticker
        [option] = self.opts
        contracts = self.ibconn.qualifyContracts(option.contract)
        self.ibconn.reqMarketDataType(4)
        [opt_ticker] = self.ibconn.reqTickers(*contracts)

        # get option delta from modelGreeks to calculate the delta neutral position
        delta = opt_ticker.modelGreeks.delta
        multiplier = int(opt_ticker.contract.multiplier)
        delta_neutral_pos = -round(option.position * delta * multiplier)

        # determine the trade needed to reach the delta neutral position
        if len(self.stks) == 0:
            hedge = delta_neutral_pos
        else:
            [stk] = self.stks
            hedge = delta_neutral_pos - stk.position
        self.ibconn.qualifyContracts(self.stk_contract)

        # make the market order trade
        is_close_to_ATM = (delta >= 0.4 or delta <= 0.6) and hedge > 0
        is_far_from_ATM = (delta < 0.4 or delta > 0.6) and hedge > 10
        if is_close_to_ATM or is_far_from_ATM:
            trade = self.market_order(self.stk_contract, hedge, dryrun=dryrun)
            if not dryrun:
                while not trade.isDone():
                    self.ibconn.waitOnUpdate()
            else:
                print(f"[DRYRUN] delta neutral is: SPY {delta_neutral_pos}")
                print(f"[DRYRUN] trade would have been: SPY {hedge}")
        else:
            print("Already delta-neutral, no trade required.")

        # return list of all current positions

        return self.ibconn.positions()

