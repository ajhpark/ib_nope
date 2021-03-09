import asyncio
from datetime import datetime

from ib_insync import IB, Option, Stock
from ib_insync.order import MarketOrder, Order
from qt.qtrade_client import QuestradeClient


class NopeStrategy:
    QT_ACCESS_TOKEN = 'qt/access_token.yml'

    def __init__(self, config, ib: IB):
        self.config = config
        self.ib = ib
        self._nope_value = 0
        self._underlying_price = 0
        self._portfolio = []
        self.qt = QuestradeClient(token_yaml=self.QT_ACCESS_TOKEN)
        self.run_qt_tasks()

    def req_market_data(self):
        # https://interactivebrokers.github.io/tws-api/market_data_type.html
        self.ib.reqMarketDataType(4)

    def set_nope_value(self):
        self._nope_value, self._underlying_price = self.qt.get_nope()
        # self._nope_value, self._underlying_price = -70, 385.0

    def update_portfolio(self):
        self._portfolio = self.ib.portfolio()

    # From thetagang
    def wait_for_trade_submitted(self, trade):
        while_n_times(
            lambda: trade.orderStatus.status
            not in [
                "Submitted",
                "Filled",
                "ApiCancelled",
                "Cancelled",
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
        return contracts[0]

    def enter_positions(self, quantity=1):

        # TODO: Check portfolio and use adaptive order, add print to file on successful order
        # If _nope_value < config["nope"]["long_enter"] or _nope_value > config["nope"]["short_enter"]
        #     Place buy order for call/put respectively
        if self._nope_value < self.config["nope"]["long_enter"] or self._nope_value > self.config["nope"]["short_enter"]:
            contract = self.find_eligible_contracts("SPY", "P")
            order = MarketOrder(
                "BUY",
                quantity,
                # algoStrategy="Adaptive",
                # algoParams=[TagValue("adaptivePriority", "Patient")],
                # tif="DAY"
            )

            # Submit order
            trade = self.wait_for_trade_submitted(
                self.ib.placeOrder(contract, order)
            )

    def exit_positions(self):
        # TODO: Implement this
        # If _nope_value > config["nope"]["long_exit"] or _nope_value < config["nope"]["short_exit"]
        #     Place sell for call/put respectively
        pass

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
                    f.write(
                        f'NOPE @ {self._nope_value} | Stock Price @ {self._underlying_price} | {curr_dt}\n')
                    # print(
                    #     'NOPE @ ', self._nope_value, ' | Stock Price @ ', self._underlying_price, ' | ', curr_dt, '\n')
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
        self.update_portfolio()
        self.run_ib()


# From thetagang
def while_n_times(pred, body, remaining):
    if remaining <= 0:
        raise RuntimeError(
            "Exhausted retries waiting on predicate. This shouldn't happen.")
    if pred() and remaining > 0:
        body()
        while_n_times(pred, body, remaining - 1)
