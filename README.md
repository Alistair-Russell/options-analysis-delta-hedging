# Options Analysis and Delta-Hedging 

## Description

A project exploring options analysis, Black-Scholes pricing, and implementation of a delta-hedging strategy. This project involves downloading market data, calculating volatility, applying the Black-Scholes model for option pricing, and simulating the execution of a delta-hedged options trade.

## Getting Started

### Prerequisites

* Basic understanding of options trading concepts.
* Access to a financial data source (e.g., Yahoo Finance, Market Watch, etc).
* Knowledge of a programming language suitable for data analysis and calculations (e.g., Python).
* (Optional) Access to a simulated brokerage account. I use a free Interactive Brokers paper trading account here - this project is **not** meant for live trading.

### Installation

This project uses common data analysis libraries (numpy, pandas, scipy) as well as a jupyter notebook for trade execution and visualization.

```pip install -r requirements.txt```

## Usage

1. **Data Collection:** Download adjusted close daily prices for a SPY ETF the past year.
2. **Volatility Calculation:** Calculate the annual volatility of the S&P 500 index using 252 trading days.
3. **Option Pricing:** Use the Black-Scholes model to price selected call options on SPY.
4. **Trade Simulation:** Simulate the sale of the option with the largest pricing discrepancy.
5. **Delta-Hedging:** Implement a delta-hedging strategy, rebalancing as needed each trading day.
6. **Analysis:** After four weeks, analyze the outcome and reflect on the strategy's effectiveness.

## Technologies Used

* Python
* Libraries for data analysis (e.g., pandas, numpy)
* Async library [ib-insync](https://pypi.org/project/ib-insync/) for calling Interactive Brokers Trader Workstation API

## Roadmap

* *Optional:* A method for evaluating trading execution costs against the cost of remaining delta-neutral.
