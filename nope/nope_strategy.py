import asyncio
from datetime import datetime

from ib_insync import IB
from qt.qtrade_client import QuestradeClient

class NopeStrategy:
    QT_ACCESS_TOKEN = 'qt/access_token.yml'

    def __init__(self, config, ib: IB):
        self.config = config
        self.ib = ib
        self._nope_value = 0
        self._underlying_price = 0
        self.qt = QuestradeClient(token_yaml=self.QT_ACCESS_TOKEN)
        self.run_qt_tasks()

    def req_market_data(self):
        # https://interactivebrokers.github.io/tws-api/market_data_type.html
        self.ib.reqMarketDataType(4)

    def set_nope_value(self):
        self._nope_value, self._underlying_price = self.qt.get_nope()

    def get_portfolio_positions(self):
        portfolio_positions = self.ib.portfolio()
        return portfolio_positions

    def report_open_positions(self):
        # TODO: Implement this
        pass

    def enter_positions(self):
        # TODO: Implement this
        # If _nope_value < config["nope"]["long_enter"] or _nope_value > config["nope"]["short_enter"]
        #     Place buy order for call/put respectively
        pass

    def exit_positions(self):
        # TODO: Implement this
        # If _nope_value > config["nope"]["long_exit"] or _nope_value < config["nope"]["short_exit"]
        #     Place sell for call/put respectively
        pass

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
        self.report_open_positions()


