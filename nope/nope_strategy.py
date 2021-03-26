import asyncio

from ib_insync import IB, Option, Stock, TagValue, util
from ib_insync.order import LimitOrder

from qt.qtrade_client import QuestradeClient
from utils.util import midpoint_or_market_price, get_datetime_for_logging, log_exception, log_fill


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
    def find_eligible_contracts(self, symbol, right):
        EXCHANGE = 'SMART'
        MAX_STRIKE_OFFSET = 5

        stock = Stock(symbol, EXCHANGE, currency="USD")
        self.ib.qualifyContracts(stock)
        [ticker] = self.ib.reqTickers(stock)
        ticker_value = ticker.marketPrice()
        chains = self.ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
        chain = next(c for c in chains if c.exchange == EXCHANGE)

        def valid_strike(strike):
            if strike % 1 == 0:
                if right == 'C':
                    max_ntm_call_strike = ticker_value + MAX_STRIKE_OFFSET
                    return ticker_value <= strike <= max_ntm_call_strike
                elif right == 'P':
                    min_ntm_put_strike = ticker_value - MAX_STRIKE_OFFSET
                    return min_ntm_put_strike <= strike <= ticker_value
            return False

        strikes = [strike for strike in chain.strikes if valid_strike(strike)]

        # TODO: Remove slicing once contract selection algorithm implemented
        exp_offset = self.config["nope"]["expiry_offset"]
        expirations = sorted(exp for exp in chain.expirations)[exp_offset:exp_offset + 1]

        contracts = [Option(self.SYMBOL, expiration, strike, right, EXCHANGE, tradingClass=self.SYMBOL)
                     for expiration in expirations
                     for strike in strikes]

        return contracts

    def get_num_open_buy_orders(self, trades, right):
        return sum(map(lambda t: t.order.totalQuantity,
                   filter(lambda t: t.contract.right == right and t.order.action == 'BUY', trades)))

    def get_total_position(self, portfolio, right):
        held_contracts = self.get_held_contracts_info(portfolio, right)
        return sum(map(lambda c: c['position'], held_contracts))

    def buy_contracts(self, right):
        action = 'BUY'
        contracts = self.find_eligible_contracts(self.SYMBOL, right)
        # TODO: Improve contract selection https://github.com/ajhpark/ib_nope/issues/21
        offset = self.config["nope"]["call_strike_offset"] if right == 'C' else -self.config["nope"]["put_strike_offset"] - 1
        contract_to_buy = contracts[offset]
        qualified_contracts = self.ib.qualifyContracts(contract_to_buy)
        tickers = self.ib.reqTickers(*qualified_contracts)
        if len(tickers) > 0:
            price = midpoint_or_market_price(tickers[0])
            if not util.isNan(price):
                contract = qualified_contracts[0]
                quantity = self.config["nope"]["call_quantity"] if right == 'C' else self.config["nope"]["put_quantity"]
                order = LimitOrder(action, quantity, price,
                                   algoStrategy="Adaptive",
                                   algoParams=[TagValue(tag='adaptivePriority', value='Normal')],
                                   tif="DAY")
                trade = self.ib.placeOrder(contract, order)
                trade.filledEvent += log_fill
                self.log_order(contract, quantity, price, action)
            else:
                with open("logs/errors.txt", "a") as f:
                    f.write(f'Error buying {right} at {self._nope_value} | {self._underlying_price}\n')

    def get_total_buys(self, right):
        portfolio = self.get_portfolio()
        trades = self.get_trades()
        held_puts = self.get_total_position(portfolio, right)
        existing_order_quantity = self.get_num_open_buy_orders(trades, right)
        return held_puts + existing_order_quantity

    def enter_positions(self):
        if self._nope_value < self.config["nope"]["long_enter"]:
            total_buys = self.get_total_buys('C')
            if total_buys < self.config["nope"]["call_limit"]:
                self.buy_contracts('C')
        elif self._nope_value > self.config["nope"]["short_enter"]:
            total_buys = self.get_total_buys('P')
            if total_buys < self.config["nope"]["put_limit"]:
                self.buy_contracts('P')

    def get_held_contracts_info(self, portfolio, right):
        return [c for c in map(lambda p: {'contract': p.contract, 'position': p.position, 'avg': p.averageCost}, portfolio)
                if c['contract'].right == right
                and c['position'] > 0]

    def get_existing_order_ids(self, trades, right, buy_or_sell):
        return set(map(lambda t: t.contract.conId,
                       filter(lambda t: t.contract.right == right and t.order.action == buy_or_sell, trades)))

    def log_order(self, contract, quantity, price, action, avg=0):
        curr_date, curr_dt = get_datetime_for_logging()
        log_str = f'Placed {action} order {quantity} {contract.strike}{contract.right}{contract.lastTradeDateOrContractMonth}'
        if action == 'SELL':
            log_str += f' ({round(avg, 2)} average)'
        log_str += f' for {round(price * 100, 2)} each, {self._nope_value} | {self._underlying_price} | {curr_dt}\n'
        with open(f"logs/{curr_date}-trade.txt", "a") as f:
            f.write(log_str)

    def sell_held_contracts(self, right):
        portfolio = self.get_portfolio()
        trades = self.get_trades()
        action = 'SELL'

        held_contracts_info = self.get_held_contracts_info(portfolio, right)
        existing_contract_order_ids = self.get_existing_order_ids(trades, right, action)
        remaining_contracts_info = list(filter(lambda c: c['contract'].conId not in existing_contract_order_ids, held_contracts_info))

        if len(remaining_contracts_info) > 0:
            remaining_contracts_info.sort(key=lambda c: c['contract'].conId)
            remaining_contracts = [c['contract'] for c in remaining_contracts_info]
            qualified_contracts = self.ib.qualifyContracts(*remaining_contracts)
            tickers = self.ib.reqTickers(*qualified_contracts)
            tickers.sort(key=lambda t: t.contract.conId)
            for idx, ticker in enumerate(tickers):
                price = midpoint_or_market_price(ticker)
                avg = remaining_contracts_info[idx]['avg']
                if not util.isNan(price):
                    quantity = remaining_contracts_info[idx]['position']
                    order = LimitOrder(action, quantity, price,
                                       algoStrategy="Adaptive",
                                       algoParams=[TagValue(tag='adaptivePriority', value='Normal')],
                                       tif="DAY")
                    contract = ticker.contract
                    trade = self.ib.placeOrder(contract, order)
                    trade.filledEvent += log_fill
                    self.log_order(contract, quantity, price, action, avg)
                else:
                    with open("logs/errors.txt", "a") as f:
                        f.write(f'Error selling {right} at {self._nope_value} | {self._underlying_price}\n')

    def exit_positions(self):
        if self._nope_value > self.config["nope"]["long_exit"]:
            self.sell_held_contracts('C')
        if self._nope_value < self.config["nope"]["short_exit"]:
            self.sell_held_contracts('P')

    def run_ib(self):
        async def ib_periodic():
            async def enter_pos():
                try:
                    self.enter_positions()
                except Exception as e:
                    log_exception(e, "enter_positions")

            async def exit_pos():
                try:
                    self.exit_positions()
                except Exception as e:
                    log_exception(e, "exit_positions")

            while True:
                await asyncio.gather(asyncio.sleep(60), enter_pos(), exit_pos())

        loop = asyncio.get_event_loop()
        return loop.create_task(ib_periodic())

    def run_qt_tasks(self):
        async def nope_periodic():
            async def fetch_and_report():
                try:
                    self.set_nope_value()
                except Exception as e:
                    log_exception(e, "set_nope_value")

                curr_date, curr_dt = get_datetime_for_logging()
                with open(f"logs/{curr_date}.txt", "a") as f:
                    f.write(f'NOPE @ {self._nope_value} | Stock Price @ {self._underlying_price} | {curr_dt}\n')
            while True:
                await asyncio.gather(asyncio.sleep(60), fetch_and_report())

        async def token_refresh_periodic():
            async def refresh_token():
                try:
                    self.qt.refresh_access_token()
                except Exception as e:
                    log_exception(e, "refresh_token")

            while True:
                await asyncio.sleep(600)
                await refresh_token()

        loop = asyncio.get_event_loop()
        loop.create_task(nope_periodic())
        loop.create_task(token_refresh_periodic())

    def execute(self):
        self.req_market_data()
        return self.run_ib()
