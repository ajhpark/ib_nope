import atexit
from datetime import datetime
from functools import reduce

import toml

from tda.auth import easy_client

with open("conf/conf.toml", "r") as f:
    config = toml.load(f)

# Use conf.toml for these values
token_path = config["tda"]["token_path"]
api_key = config["tda"]["api_key"]
redirect_uri = config["tda"]["redirect_uri"]
account_id = config["tda"]["account_id"]


class OptionType:
    CALL = "call"
    PUT = "put"


# only using tda for data access, not trading
# papertrading is not available with tda api
class TDAClient:
    ticker = "SPY"

    def __init__(self):
        def make_webdriver():
            from selenium import webdriver

            driver = webdriver.Chrome()
            atexit.register(lambda: driver.quit())
            return driver

        self.client = easy_client(
            api_key=api_key,
            redirect_uri=redirect_uri,
            token_path=token_path,
            webdriver_func=make_webdriver,
        )

    def get_nope(self):
        chain = self.client.get_option_chain(self.ticker).json()
        quote = self.client.get_quote(self.ticker).json()[self.ticker]
        if not chain["status"] == "SUCCESS":
            print("error getting chain")
            return [0, 0]

        def add(x, y):
            return x + y

        def gen_deltas_at_exp(type: OptionType):
            # Loop through chains at each expiry
            chain_map_key = f"{type}ExpDateMap"
            for exp_date in chain[chain_map_key]:

                def delta_factor(q):
                    return q["delta"] * q["totalVolume"]

                call_options_delta = reduce(
                    add,
                    (
                        delta_factor(chain[chain_map_key][exp_date][strike][0])
                        for strike in chain[chain_map_key][exp_date].keys()
                    ),
                )
                yield call_options_delta

        total_call_delta = reduce(add, gen_deltas_at_exp(OptionType.CALL))
        total_put_delta = reduce(add, gen_deltas_at_exp(OptionType.PUT))

        try:
            nope = (total_call_delta + total_put_delta) * 10_000 / quote["totalVolume"]
        except ZeroDivisionError:
            curr_dt = datetime.now().strftime("%Y-%m-%d at %H:%M:%S")
            with open("logs/errors.txt", "a") as f:
                f.write(f'no volume data on {quote["symbol"]} | {curr_dt}\n')
            return [0, 0]

        return [nope, quote["lastPrice"]]
