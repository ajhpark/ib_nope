import asyncio
from datetime import datetime

from ib_insync import IB, Option, Stock, TagValue, util
from ib_insync.order import LimitOrder, MarketOrder

from qt.qtrade_client import QuestradeClient
from utils.util import while_n_times, midpoint_or_market_price


class NopeStrategy:
    QT_ACCESS_TOKEN = 'qt/access_token.yml'
    SYMBOL = "SPY"

    def __init__(self, config, ib: IB):
        self.config = config
        self.ib = ib
        self._nope_value = 0
        self._underlying_price = 0
        self.qt = QuestradeClient(token_yaml=self.QT_ACCESS_TOKEN)
        self.run_qt_tasks()

    def req_market_data(self):
        # https://interactivebrokers.github.io/tws-api/market_data_type.html
        self.ib.reqMarketDataType(1)
        self.ib.reqAllOpenOrders()
        self.ib.reqPositions()

    def set_nope_value(self):
        self._nope_value, self._underlying_price = self.qt.get_nope()

    def get_portfolio(self):
        portfolio = self.ib.portfolio()
        # Filter out non-SPY contracts
        portfolio = [item for item in portfolio
                     if item.contract.symbol == self.SYMBOL]
        return portfolio

    def get_trades(self):
        trades = self.ib.openTrades()
        trades = [t for t in trades
                  if t.isActive() and t.contract.symbol == self.SYMBOL]
        return trades

    # From thetagang
    # https://github.com/brndnmtthws/thetagang
    def wait_for_trade_submitted(self, trade):
        while_n_times(
            lambda: trade.orderStatus.status
            not in [
                "Submitted",
                "Filled",
                "ApiCancelled",
                "Cancelled",
                "PreSubmitted"
            ],
            lambda: self.ib.waitOnUpdate(timeout=5),
            25
        )
        return trade

    def find_eligible_contracts(self, symbol, right, min_strike=0, excluded_expirations=[]):
        stock = Stock(symbol, "SMART", currency="USD")
        contracts = self.ib.qualifyContracts(stock)

        [ticker] = self.ib.reqTickers(stock)
        tickerValue = ticker.marketPrice()
        chains = self.ib.reqSecDefOptParams(
            stock.symbol, "", stock.secType, stock.conId)
        chain = next(c for c in chains if c.exchange == "SMART")
        strikes = [strike for strike in chain.strikes
                   if strike % 5 == 0
                   and tickerValue - 2 < strike < tickerValue + 2]

        expirations = sorted(exp for exp in chain.expirations)[:3]

        contracts = [Option('SPY', expiration, strike, right, 'SMART', tradingClass='SPY')
                     for expiration in expirations
                     for strike in strikes]

        contracts = self.ib.qualifyContracts(*contracts)
        return contracts

    def enter_positions(self, quantity=1):

        # TODO: Check portfolio, use LimitOrder and adaptive strategy, add log to file,
        # implement algorithm to select which contract to buy out of the eligible candidates
        # If _nope_value < config["nope"]["long_enter"] or _nope_value > config["nope"]["short_enter"]
        #     Place buy order for call/put respectively
        if self._nope_value < self.config["nope"]["long_enter"] or self._nope_value > self.config["nope"]["short_enter"]:
            contracts = self.find_eligible_contracts("SPY", "P")
            order = MarketOrder(
                "BUY",
                quantity
            )

            # Submit order
            trade = self.wait_for_trade_submitted(
                self.ib.placeOrder(contracts[0], order)
            )

    def get_held_contracts(self, portfolio, right):
        return [c for c in map(lambda p: {'contract': p.contract, 'position': p.position}, portfolio)
                if c['contract'].right == right
                and c['position'] > 0]

    def exit_positions(self):
        # TODO: Add logging
        portfolio = self.get_portfolio()
        trades = self.get_trades()
        if self._nope_value > self.config["nope"]["long_exit"]:
            held_calls = self.get_held_contracts(portfolio, 'C')
            existing_call_order_ids = set(map(lambda t: t.contract.conId,
                                              filter(lambda t: t.contract.right == 'C' and t.order.action == "SELL", trades)))
            remaining_calls = list(filter(lambda c: c['contract'].conId not in existing_call_order_ids, held_calls))
            remaining_calls.sort(key=lambda c: c['contract'].conId)

            if len(remaining_calls) > 0:
                remaining_call_contracts = [c['contract'] for c in remaining_calls]
                qualified_contracts = self.ib.qualifyContracts(*remaining_call_contracts)
                tickers = self.ib.reqTickers(*qualified_contracts)
                tickers.sort(key=lambda t: t.contract.conId)
                for idx, ticker in enumerate(tickers):
                    price = midpoint_or_market_price(ticker)
                    if not util.isNan(price):
                        order = LimitOrder("SELL", remaining_calls[idx]['position'], price,
                                           algoStrategy="Adaptive",
                                           algoParams=[TagValue(tag='adaptivePriority', value='Normal')],
                                           tif="DAY")
                        self.wait_for_trade_submitted(self.ib.placeOrder(ticker.contract, order))
        elif self._nope_value < self.config["nope"]["short_exit"]:
            held_puts = self.get_held_contracts(portfolio, 'P')
            existing_put_order_ids = set(map(lambda t: t.contract.conId,
                                             filter(lambda t: t.contract.right == 'P' and t.order.action == "SELL", trades)))
            remaining_puts = list(filter(lambda c: c['contract'].conId not in existing_put_order_ids, held_puts))
            remaining_puts.sort(key=lambda c: c['contract'].conId)

            if len(remaining_puts) > 0:
                remaining_put_contracts = [c['contract'] for c in remaining_puts]
                qualified_contracts = self.ib.qualifyContracts(*remaining_put_contracts)
                tickers = self.ib.reqTickers(*qualified_contracts)
                tickers.sort(key=lambda t: t.contract.conId)
                for idx, ticker in enumerate(tickers):
                    price = midpoint_or_market_price(ticker)
                    if not util.isNan(price):
                        order = LimitOrder("SELL", remaining_puts[idx]['position'], price,
                                           algoStrategy="Adaptive",
                                           algoParams=[TagValue(tag='adaptivePriority', value='Normal')],
                                           tif="DAY")
                        self.wait_for_trade_submitted(self.ib.placeOrder(ticker.contract, order))

    def run_ib(self):
        async def ib_periodic():
            async def enter_pos():
                self.enter_positions()

            async def exit_pos():
                self.exit_positions()
            while True:
                await asyncio.gather(asyncio.sleep(60), enter_pos(), exit_pos())

        loop = asyncio.get_event_loop()
        loop.create_task(ib_periodic())

    def run_qt_tasks(self):
        # TODO: Implement this
        # After each update, must open/close positions (if necessary) according to the new nope value
        async def nope_periodic():
            async def fetch_and_report():
                self.set_nope_value()
                now = datetime.now()
                curr_date = now.strftime("%Y-%m-%d")
                curr_dt = now.strftime("%Y-%m-%d at %H:%M:%S")
                with open(f"logs/{curr_date}.txt", "a") as f:
                    f.write(f'NOPE @ {self._nope_value} | Stock Price @ {self._underlying_price} | {curr_dt}\n')
            while True:
                await asyncio.gather(asyncio.sleep(60), fetch_and_report())

        async def token_refresh_periodic():
            async def refresh_token():
                self.qt.refresh_access_token()
            while True:
                await asyncio.sleep(600)
                await refresh_token()

        loop = asyncio.get_event_loop()
        loop.create_task(nope_periodic())
        loop.create_task(token_refresh_periodic())

    def execute(self):
        self.req_market_data()
        self.run_ib()
