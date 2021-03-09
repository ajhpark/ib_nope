from ib_insync import *

# For this example, must have TWS running

ib = IB()
ib.connect("127.0.0.1", 7497, clientId=1)
ib.reqMarketDataType(4)

# get SPY option chain
symbol = "SPY"
stock = Stock(symbol, "SMART", currency="USD")
contracts = ib.qualifyContracts(stock)
# print(contracts)
[ticker] = ib.reqTickers(stock)
tickerValue = ticker.marketPrice()
# print(tickerValue)
chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
chain = next(c for c in chains if c.exchange == "SMART")
# print(chain)

# get call options for all expirations and strikes within range
# strikes = [strike for strike in chain.strikes
#            if strike % 5 == 0
#            and tickerValue - 20 < strike < tickerValue + 20]
# contracts = [Option(symbol, expiration, strike, "C", "SMART", tradingClass=chain.tradingClass)
#              for expiration in chain.expirations
#              for strike in strikes]
strikes = [strike for strike in chain.strikes
        if strike % 5 == 0
        and tickerValue - 2 < strike < tickerValue + 2]
expirations = sorted(exp for exp in chain.expirations)[:3]
rights = ['P', 'C']

contracts = [Option('SPY', expiration, strike, right, 'SMART', tradingClass='SPY')
        for right in rights
        for expiration in expirations
        for strike in strikes]

contracts = ib.qualifyContracts(*contracts)
# tickers = ib.reqTickers(*contracts)
print(len(contracts))
print(contracts[0])
print(contracts[1])
