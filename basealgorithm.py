"""Base Trading Algorithm

This module implements basic trading functionality using Interactive Brokers
"""

__version__ = "0.1"
__author__ = "Alistair Russell"

import datetime as dt
import numpy as np
from ib_insync import IB, MarketOrder


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
