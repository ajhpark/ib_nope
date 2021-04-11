import asyncio
import threading
from functools import reduce

from ib_insync import IB, Option, Stock, TagValue, util
from ib_insync.order import LimitOrder, StopOrder

from qt.qtrade_client import QuestradeClient
from utils.util import (
    get_datetime_diff_from_now,
    get_datetime_for_logging,
    log_exception,
    log_fill,
    midpoint_or_market_price,
    stop_order_price,
)


class NopeStrategy:
    QT_ACCESS_TOKEN = "qt/access_token.yml"
    SYMBOL = "SPY"

    def __init__(self, config, ib: IB):
        self.config = config
        self.ib = ib
        self._nope_value = 0
        self._underlying_price = 0
        self.ib_tasks_dict = dict()
        self.qt = QuestradeClient(token_yaml=self.QT_ACCESS_TOKEN)
        self.run_qt_tasks()

    def console_log(self, s):
        if self.config["debug"]["verbose"]:
            _, curr_dt = get_datetime_for_logging()
            print(s, f"| {self._nope_value} | {self._underlying_price} | {curr_dt}")

    def get_tasks_dict(self):
        return self.ib_tasks_dict

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
        portfolio = [item for item in portfolio if item.contract.symbol == self.SYMBOL]
        return portfolio

    def get_trades(self):
        trades = self.ib.openTrades()
        trades = [
            t for t in trades if t.isActive() and t.contract.symbol == self.SYMBOL
        ]
        return trades

    # From thetagang
    # https://github.com/brndnmtthws/thetagang
    def find_eligible_contracts(self, symbol, right):
        EXCHANGE = "SMART"
        MAX_STRIKE_OFFSET = 5

        stock = Stock(symbol, EXCHANGE, currency="USD")
        self.ib.qualifyContracts(stock)
        [ticker] = self.ib.reqTickers(stock)
        ticker_value = ticker.marketPrice()
        chains = self.ib.reqSecDefOptParams(
            stock.symbol, "", stock.secType, stock.conId
        )
        chain = next(c for c in chains if c.exchange == EXCHANGE)

        def valid_strike(strike):
            if strike % 1 == 0:
                if right == "C":
                    max_ntm_call_strike = ticker_value + MAX_STRIKE_OFFSET
                    return (
                        ticker_value - MAX_STRIKE_OFFSET
                        <= strike
                        <= max_ntm_call_strike
                    )
                elif right == "P":
                    min_ntm_put_strike = ticker_value - MAX_STRIKE_OFFSET
                    return (
                        min_ntm_put_strike <= strike <= ticker_value + MAX_STRIKE_OFFSET
                    )
            return False

        strikes = [strike for strike in chain.strikes if valid_strike(strike)]

        if self.config["nope"]["contract_auto_select"]:
            min_dte = self.config["nope"]["auto_min_dte"]
            expirations = sorted(exp for exp in chain.expirations)[
                min_dte : min_dte + 5
            ]
        else:
            exp_offset = self.config["nope"]["expiry_offset"]
            expirations = sorted(exp for exp in chain.expirations)[
                exp_offset : exp_offset + 1
            ]

        contracts = [
            Option(
                self.SYMBOL,
                expiration,
                strike,
                right,
                EXCHANGE,
                tradingClass=self.SYMBOL,
            )
            for expiration in expirations
            for strike in strikes
        ]

        return contracts

    def get_num_open_buy_orders(self, right):
        trades = self.get_trades()
        return sum(
            map(
                lambda t: t.order.totalQuantity,
                filter(
                    lambda t: t.contract.right == right and t.order.action == "BUY",
                    trades,
                ),
            )
        )

    def get_total_position(self, right):
        held_contracts = self.get_held_contracts_info(right)
        return sum(map(lambda c: c["position"], held_contracts))

    def cancel_order_type(self, action, order_type="LMT"):
        trades = self.get_trades()
        filtered = list(
            filter(
                lambda t: t.order.action == action and t.order.orderType == order_type,
                trades,
            )
        )
        for trade in filtered:
            self.ib.cancelOrder(trade.order)

    def get_open_stop_orders(self):
        trades = self.get_trades()
        return list(filter(lambda t: t.order.orderType == "STP", trades))

    def cancel_stop_loss_task(self):
        if "set_stop_loss" in self.ib_tasks_dict:
            stop_loss_task = self.ib_tasks_dict.pop("set_stop_loss")
            stop_loss_task.cancel()

    def set_stop_loss(self, right):
        self.console_log("Check stop loss conditions")
        existing_stop_orders = self.get_open_stop_orders()
        if len(existing_stop_orders) == 0:
            total_position = self.get_total_position(right)
            buy_limit = (
                self.config["nope"]["call_limit"]
                if right == "C"
                else self.config["nope"]["put_limit"]
            )
            if total_position >= buy_limit:
                held_contracts_info = self.get_held_contracts_info(right)
                for contract_info in held_contracts_info:
                    position = contract_info["position"]
                    avg_price = contract_info["avg"] / 100
                    contract = contract_info["contract"]
                    qualified_contracts = self.ib.qualifyContracts(contract)
                    order_price = stop_order_price(
                        avg_price, self.config["nope"]["stop_loss_percentage"]
                    )

                    if len(qualified_contracts) > 0:
                        stop_loss_order = StopOrder(
                            "SELL",
                            position,
                            order_price,
                            tif="GTC",
                        )
                        qualified_contract = qualified_contracts[0]
                        self.ib.placeOrder(qualified_contract, stop_loss_order)
                        self.log_order(
                            qualified_contract, position, order_price, "STOP"
                        )
                        self.cancel_stop_loss_task()

    def on_buy_fill(self, trade):
        async def stop_loss_periodic():
            async def schedule_stop_loss():
                try:
                    fill = trade.fills[0]
                    self.set_stop_loss(fill.contract.right)
                except Exception as e:
                    log_exception(e, "on_buy_fill")

            while True:
                await asyncio.gather(asyncio.sleep(120), schedule_stop_loss())

        if "set_stop_loss" not in self.ib_tasks_dict:
            loop = asyncio.get_event_loop()
            self.ib_tasks_dict["set_stop_loss"] = loop.create_task(stop_loss_periodic())

    def check_acc_balance(self, price, quantity):
        ib_account = self.config["ib"]["account"]
        if not ib_account:
            return True
        acc_values = self.ib.accountValues(account=ib_account)
        buy_power = list(
            filter(lambda a: a.tag == "BuyingPower" and a.currency == "USD", acc_values)
        )
        try:
            balance = buy_power[0]
        except Exception as e:
            log_exception(e, "check_acc_balance")
            return False

        return float(balance.value) > price * 100 * quantity

    def select_contract(self, contracts, right):
        if self.config["nope"]["contract_auto_select"]:
            target = self.config["nope"]["auto_target_delta"] / 100
            target_delta = target if right == "C" else -target

            def reducer(ticker_prev, ticker):
                greeks_prev = ticker_prev.modelGreeks
                greeks = ticker.modelGreeks
                if greeks_prev is None and greeks is None:
                    return ticker_prev
                elif greeks_prev is None:
                    return ticker
                elif greeks is None:
                    return ticker_prev

                ticker_next = (
                    ticker
                    if abs(ticker.modelGreeks.delta - target_delta)
                    < abs(ticker_prev.modelGreeks.delta - target_delta)
                    else ticker_prev
                )

                return ticker_next

            qualified_contracts = self.ib.qualifyContracts(*contracts)
            tickers = self.ib.reqTickers(*qualified_contracts)
            if len(tickers) > 0:
                closest = reduce(reducer, tickers)
                return closest
        else:
            offset = (
                self.config["nope"]["call_strike_offset"]
                if right == "C"
                else -self.config["nope"]["put_strike_offset"] - 1
            )
            contract_to_buy = contracts[offset]
            qualified_contracts = self.ib.qualifyContracts(contract_to_buy)
            tickers = self.ib.reqTickers(*qualified_contracts)
            if len(tickers) > 0:
                return tickers[0]
        return None

    def buy_contracts(self, right):
        action = "BUY"
        contracts = self.find_eligible_contracts(self.SYMBOL, right)
        ticker = self.select_contract(contracts, right)
        if ticker is not None:
            price = midpoint_or_market_price(ticker)
            quantity = (
                self.config["nope"]["call_quantity"]
                if right == "C"
                else self.config["nope"]["put_quantity"]
            )
            if not util.isNan(price) and self.check_acc_balance(price, quantity):
                contract = ticker.contract
                order = LimitOrder(
                    action,
                    quantity,
                    price,
                    algoStrategy="Adaptive",
                    algoParams=[TagValue(tag="adaptivePriority", value="Normal")],
                    tif="DAY",
                )
                trade = self.ib.placeOrder(contract, order)
                trade.filledEvent += log_fill
                trade.filledEvent += self.on_buy_fill
                self.log_order(contract, quantity, price, action)
            else:
                with open("logs/errors.txt", "a") as f:
                    f.write(
                        f"Error buying {right} at {self._nope_value} | {self._underlying_price}\n"
                    )

    def get_total_buys(self, right):
        held_puts = self.get_total_position(right)
        existing_order_quantity = self.get_num_open_buy_orders(right)
        return held_puts + existing_order_quantity

    def enter_positions(self):
        self.console_log("Check enter thresholds")
        if self._nope_value < self.config["nope"]["long_enter"]:
            total_buys = self.get_total_buys("C")
            if total_buys < self.config["nope"]["call_limit"]:
                self.buy_contracts("C")
        elif self._nope_value > self.config["nope"]["short_enter"]:
            total_buys = self.get_total_buys("P")
            if total_buys < self.config["nope"]["put_limit"]:
                self.buy_contracts("P")

    def get_held_contracts_info(self, right):
        portfolio = self.get_portfolio()
        return [
            c
            for c in map(
                lambda p: {
                    "contract": p.contract,
                    "position": p.position,
                    "avg": p.averageCost,
                },
                portfolio,
            )
            if c["contract"].right == right and c["position"] > 0
        ]

    def get_existing_order_ids(self, right, action):
        trades = self.get_trades()
        return set(
            map(
                lambda t: t.contract.conId,
                filter(
                    lambda t: t.contract.right == right
                    and t.order.action == action
                    and t.order.orderType != "STP",
                    trades,
                ),
            )
        )

    def log_order(self, contract, quantity, price, action, avg=0):
        curr_date, curr_dt = get_datetime_for_logging()
        log_str = f"Placed {action} order {quantity} {contract.strike}{contract.right}{contract.lastTradeDateOrContractMonth}"
        if action == "SELL":
            log_str += f" ({round(avg, 2)} average)"
        log_str += f" for {round(price * 100, 2)} each, {self._nope_value} | {self._underlying_price} | {curr_dt}\n"
        with open(f"logs/{curr_date}-trade.txt", "a") as f:
            f.write(log_str)

    def sell_held_contracts(self, right):
        action = "SELL"
        held_contracts_info = self.get_held_contracts_info(right)
        existing_contract_order_ids = self.get_existing_order_ids(right, action)
        remaining_contracts_info = list(
            filter(
                lambda c: c["contract"].conId not in existing_contract_order_ids,
                held_contracts_info,
            )
        )

        if len(remaining_contracts_info) > 0:
            remaining_contracts_info.sort(key=lambda c: c["contract"].conId)
            remaining_contracts = [c["contract"] for c in remaining_contracts_info]
            qualified_contracts = self.ib.qualifyContracts(*remaining_contracts)
            tickers = self.ib.reqTickers(*qualified_contracts)
            tickers.sort(key=lambda t: t.contract.conId)
            for idx, ticker in enumerate(tickers):
                price = midpoint_or_market_price(ticker)
                avg = remaining_contracts_info[idx]["avg"]
                if not util.isNan(price) and price > (avg / 100):
                    quantity = remaining_contracts_info[idx]["position"]
                    order = LimitOrder(
                        action,
                        quantity,
                        price,
                        algoStrategy="Adaptive",
                        algoParams=[TagValue(tag="adaptivePriority", value="Normal")],
                        tif="DAY",
                    )
                    contract = ticker.contract
                    trade = self.ib.placeOrder(contract, order)
                    trade.filledEvent += log_fill
                    self.log_order(contract, quantity, price, action, avg)
                    self.cancel_order_type("SELL", "STP")
                    self.cancel_stop_loss_task()
                else:
                    with open("logs/errors.txt", "a") as f:
                        f.write(
                            f"Error selling {right} at {self._nope_value} | {self._underlying_price}\n"
                        )

    def exit_positions(self):
        self.console_log("Check exit thresholds")
        if self._nope_value > self.config["nope"]["long_exit"]:
            self.sell_held_contracts("C")
        if self._nope_value < self.config["nope"]["short_exit"]:
            self.sell_held_contracts("P")

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

        async def check_orders():
            async def cancel_unfilled_orders():
                cancellable_statuses = ["PreSubmitted", "Submitted"]
                trades = self.get_trades()
                for trade in trades:
                    submit_logs = list(
                        filter(lambda l: l.status in cancellable_statuses, trade.log)
                    )
                    try:
                        submit_log = submit_logs[0]
                    except Exception as e:
                        log_exception(e, "cancel_unfilled_orders")
                        return

                    diff = get_datetime_diff_from_now(submit_log.time)
                    if diff > self.config["nope"]["minutes_cancel_unfilled"]:
                        self.ib.cancelOrder(trade.order)
                        self.console_log("Cancelled old order")

            while True:
                await asyncio.gather(asyncio.sleep(600), cancel_unfilled_orders())

        loop = asyncio.get_event_loop()
        self.ib_tasks_dict["run_ib"] = loop.create_task(ib_periodic())
        self.ib_tasks_dict["check_orders"] = loop.create_task(check_orders())

    def run_qt_tasks(self):
        async def nope_periodic():
            async def fetch_and_report():
                try:
                    self.set_nope_value()
                except Exception as e:
                    log_exception(e, "set_nope_value")

                self.console_log("Updated NOPE and stock price")
                curr_date, curr_dt = get_datetime_for_logging()
                with open(f"logs/{curr_date}.txt", "a") as f:
                    f.write(
                        f"NOPE @ {self._nope_value} | Stock Price @ {self._underlying_price} | {curr_dt}\n"
                    )

            while True:
                await asyncio.gather(asyncio.sleep(60), fetch_and_report())

        async def token_refresh_periodic():
            async def refresh_token():
                try:
                    self.qt.refresh_access_token()
                except Exception as e:
                    log_exception(e, "refresh_token")

            while True:
                await asyncio.sleep(120)
                await refresh_token()

        def run_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.create_task(nope_periodic())
            loop.create_task(token_refresh_periodic())
            loop.run_forever()

        thread = threading.Thread(target=run_thread)
        thread.start()

    def execute(self):
        self.req_market_data()
        self.run_ib()
