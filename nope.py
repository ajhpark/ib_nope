from ib_insync import IB

class NopeStrategy:
    def __init__(self, config, ib: IB):
        self.config = config
        self.ib = ib
        self._nope_value = 0

    def req_market_data(self):
        # https://interactivebrokers.github.io/tws-api/market_data_type.html
        self.ib.reqMarketDataType(4)

    def get_portfolio_positions(self):
        portfolio_positions = self.ib.portfolio()
        return portfolio_positions

    def report_open_positions(self):
        # TODO: Implement this
        pass

    def get_total_call_delta(self):
        # TODO: Implement this
        pass

    def get_total_put_delta(self):
        # TODO: Implement this
        pass

    def get_total_traded_volume(self):
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

    def calc_nope(self):
        tcd = self.get_total_call_delta()
        tpd = self.get_total_put_delta()
        ttv = self.get_total_traded_volume()
        self._nope_value = (tcd + tpd) / ttv

    def register_nope_service(self):
        # TODO: Implement this
        # Need to have a thread running set_nope in regular intervals
        # After each update, must open/close positions (if necessary) according to the new nope value
        pass

    def execute(self):
        self.req_market_data()
        self.report_open_positions()
        self.register_nope_service()


