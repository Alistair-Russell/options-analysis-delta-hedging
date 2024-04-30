"""Delta Hedging

This module is for delta hedging SPY options
"""

__version__ = "0.1"
__author__ = "Alistair Russell"

import datetime as dt
from ib_insync import Stock
from basealgorithm import BaseAlgo


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

