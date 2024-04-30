"""VIX Futures

Hedging VIX futures with E-mini S&P futures.
"""

__version__ = "0.1"
__author__ = "Alistair Russell"

import datetime as dt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import itertools as it
from ib_insync import Index, Future, 

from basealgorithm import BaseAlgo


def bus_day_delta(future_date):
    today = dt.date.today()
    future = dt.datetime.strptime(future_date, "%Y%m%d").date()
    return np.busday_count(today, future_date)


class VIXFuturesHedgeAlgo(BaseAlgo):
    """Hedging of VIX futures with E-mini-S&P futures"""

    def __init__(self, vix_future_date, es_future_date, **kwargs):
        super(VIXFuturesHedgeAlgo, self).__init__(**kwargs)

        # initialize vix spot and futures dictionaries
        self.vix_spot = {}
        self.vix_future = {}
        self.es_future = {}

        # request delayed market data
        self.ibconn.reqMarketDataType(4)

        # vix future contract for date provided
        future = Future("VIX", vix_future_date, "CFE")
        self.ibconn.qualifyContracts(future)
        [future_con] = self.ibconn.reqContractDetails(future)
        self.vix_future["contract"] = future_con
        [future_tic] = self.ibconn.reqTickers(future)
        self.vix_future["ticker"] = future_tic

        # vix spot contract for date provided
        index = Index("VIX")
        self.ibconn.qualifyContracts(index)
        [spot_con] = self.ibconn.reqContractDetails(index)
        self.vix_spot["contract"] = spot_con
        [spot_tic] = self.ibconn.reqTickers(index)
        self.vix_spot["ticker"] = spot_tic

        # es future contract for date provided
        es = Future("ES", es_future_date, "GLOBEX")
        self.ibconn.qualifyContracts(es)
        [es_con] = self.ibconn.reqContractDetails(es)
        self.es_future["contract"] = es_con
        [es_tic] = self.ibconn.reqTickers(es)
        self.es_future["ticker"] = es_tic

    def _get_es_beta(self):
        ## Q4- E-mini and VIX Futures Historical Data
        today = dt.date.today()
        today_str = today.strftime("%m/%d/%Y")
        a_year_ago = today - dt.timedelta(days=365)
        a_year_ago_str = a_year_ago.strftime("%m/%d/%Y")

        # WSJ database didn't work for futures, I got the data from marketwatch for vx00 and es00
        vix_futures_data = pd.read_csv(
            "https://www.marketwatch.com/investing/future/vx00/downloaddatapartial?startdate="
            + a_year_ago_str
            + "%2000:00:00&enddate="
            + today_str
            + "%2000:00:00&daterange=d30&frequency=p1d&csvdownload=true&downloadpartial=false&newdates=false"
        )
        sp500_futures = pd.read_csv(
            "https://www.marketwatch.com/investing/future/es00/downloaddatapartial?startdate="
            + a_year_ago_str
            + "%2000:00:00&enddate="
            + today_str
            + "%2000:00:00&daterange=d30&frequency=p1d&csvdownload=true&downloadpartial=false&newdates=false"
        )
        # I will use open prices to calculate the percentage changes
        sample = pd.DataFrame(columns=["Date", "sp_mini_change", "vix_futures_change"])
        sample["Date"] = vix_futures_data["Date"]
        sample["sp_mini_change"] = (
            sp500_futures["Open"].str.replace(",", "").astype(float)
            / sp500_futures["Open"].str.replace(",", "").astype(float).shift(periods=-1)
            - 1
        )
        sample["vix_futures_change"] = (
            vix_futures_data["Open"] / vix_futures_data["Open"].shift(periods=-1) - 1
        )

        # regress change in vix futures on the change in the E-mini
        model = smf.ols("vix_futures_change~sp_mini_change", sample).fit()

        # get the model beta
        beta = model.params.values[1]
        return beta

    def hedge(self, quantity, dryrun=False):
        # calculate hedge amount
        beta = self._get_es_beta()
        hedge_amt = (
            -1
            * quantity
            * round(
                (beta * float(self.vix_future["ticker"].last) * 1000)
                / (float(self.es_future["ticker"].last) * 50)
            )
        )

        # place hedge trade
        es_con = self.es_future["contract"].contract
        if abs(hedge_amt) > 0:
            print(f"Attempting to hedge with E-mini: amount {hedge_amt}")
            trade = self.market_order(es_con, hedge_amt, dryrun=dryrun)

            if not dryrun:
                while not trade.isDone():
                    self.ibconn.waitOnUpdate()
            else:
                print(f"[DRYRUN] trade would have been: {trade}")
        else:
            print("Already hedged, no trade required.")

    def enter_positions(self, quantity):
        # if there are open vix positions then return, otherwise attempt to enter
        vix_positions = [
            p for p in self.ibconn.positions() if p.contract.symbol == "VIX"
        ]
        if len(vix_positions) > 0:
            print(f"VIX positions already entered: {vix_positions}")
            return

        # get contract
        vix_con = self.vix_future["contract"].contract
        vixf_price = self.vix_future["ticker"].last
        vixs_price = self.vix_spot["ticker"].last

        # calculate the contango/backwardation signal
        signal = (vixf_price / vixs_price) - 1

        # calculate the daily roll
        future_date = vix_con.lastTradeDateOrContractMonth
        days = bus_day_delta(future_date)
        daily_roll = (vixf_price - vixs_price) / days

        # initial trade
        if signal < 0 and daily_roll < -0.10:
            print(
                "Market backwardation - daily roll is less than -0.10. Purchasing VIX Futures."
            )
            trade = self.market_order(vix_con, quantity)
            self.hedge(self, -1 * quantity)
        elif signal > 0 and daily_roll > 0.10:
            print(
                "Market contango - daily roll is more than 0.10. Shorting VIX Futures."
            )
            trade = self.market_order(vix_con, -1 * quantity)
            self.hedge(self, quantity)
        else:
            print(
                f"Signal is {signal} and daily roll is {daily_roll}. No action taken."
            )

    def exit_positions(self):
        f = [
            p
            for p in self.ibconn.positions()
            if p.contract.secType == "FUT" and p.contract.symbol == "VIX"
        ]
        e = [
            p
            for p in self.ibconn.positions()
            if p.contract.secType == "FUT" and p.contract.symbol == "ES"
        ]
        if len(f) == 0 and len(e) == 0:
            print("No positions to exit.")
            return
        elif len(f) == 0 or len(e) == 0:
            print(f"There are unhedged positions: {f} {e}.")
            print(
                "Please hedge manually or use VIXFuturesHedgeAlgo.hedge(position) and retry"
            )
            return

        # take the first positions
        vixf = f[0]
        esf = e[0]

        d = vixf.contract.lastTradeDateOrContractMonth
        days = bus_day_delta(d)
        daily_roll = (
            self.vix_future["ticker"].last - self.vix_spot["ticker"].last
        ) / days  # TODO make a daily roll fn

        is_contango_takeprofit = vixf.position < 0 and (days <= 9 or daily_roll < 0.05)
        is_backwd_takeprofit = vixf.position > 0 and (days <= 9 or daily_roll > -0.05)

        # in either takeprofit scenario, liquidate the positions
        if is_contango_takeprofit or is_backwd_takeprofit:
            print("Exiting VIX and ES positions")
            self.market_order(vixf.contract, -1 * vixf.position)
            self.market_order(esf.contract, -1 * esf.position)
