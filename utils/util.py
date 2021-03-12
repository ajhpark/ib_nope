from ib_insync import util
from datetime import datetime


# From thetagang
# https://github.com/brndnmtthws/thetagang
def while_n_times(pred, body, remaining):
    if remaining <= 0:
        raise RuntimeError(
            "Exhausted retries waiting on predicate. This shouldn't happen.")
    if pred() and remaining > 0:
        body()
        while_n_times(pred, body, remaining - 1)


# From thetagang
# https://github.com/brndnmtthws/thetagang
def midpoint_or_market_price(ticker):
    if util.isNan(ticker.midpoint()):
        return ticker.marketPrice()

    return ticker.midpoint()


def get_datetime_for_logging():
    now = datetime.now()
    curr_date = now.strftime("%Y-%m-%d")
    curr_dt = now.strftime("%Y-%m-%d at %H:%M:%S")
    return [curr_date, curr_dt]


def log_exception(e: Exception):
    str_err = "Error {0}".format(str(e))
    _, curr_dt = get_datetime_for_logging()
    with open("logs/errors.txt", "a") as f:
        f.write(f'{str_err} | {curr_dt}\n')
