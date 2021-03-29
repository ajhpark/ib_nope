from ib_insync import IB, Option, Stock

# For this example, must have TWS running

ib = IB()
ib.connect("127.0.0.1", 7497, clientId=1)
ib.reqMarketDataType(4)

# get SPY option chain
symbol = "SPY"
stock = Stock(symbol, "SMART", currency="USD")
contracts = ib.qualifyContracts(stock)
[ticker] = ib.reqTickers(stock)
tickerValue = ticker.marketPrice()
print(tickerValue)
chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
chain = next(c for c in chains if c.exchange == "SMART")
print(chain)

# get call options for all expirations and strikes within range
strikes = [
    strike
    for strike in chain.strikes
    if strike % 5 == 0 and tickerValue - 20 < strike < tickerValue + 20
]
contracts = [
    Option(symbol, expiration, strike, "C", "SMART", tradingClass=chain.tradingClass)
    for expiration in chain.expirations
    for strike in strikes
]

contracts = ib.qualifyContracts(*contracts)
tickers = ib.reqTickers(*contracts)
print(tickers[0])
