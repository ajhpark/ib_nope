from ib_insync import util
from datetime import datetime
import traceback
import sys


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
        return round(ticker.marketPrice(), 2)

    return round(ticker.midpoint(), 2)


def get_datetime_for_logging():
    now = datetime.now()
    curr_date = now.strftime("%Y-%m-%d")
    curr_dt = now.strftime("%Y-%m-%d at %H:%M:%S")
    return [curr_date, curr_dt]


def get_stack_trace():
    exc = sys.exc_info()[0]
    stack = traceback.extract_stack()[:-1]
    if exc is not None:
        del stack[-1]
    trc = 'Traceback (most recent call last):\n'
    stack_str = trc + ''.join(traceback.format_list(stack))
    if exc is not None:
        stack_str += '  ' + traceback.format_exc().lstrip(trc)
    return stack_str


def log_exception(e: Exception, fn):
    str_err = "Error {0}".format(str(e))
    _, curr_dt = get_datetime_for_logging()
    print(f'{str_err} in {fn} | {curr_dt}')
    print(get_stack_trace())
    with open("logs/errors.txt", "a") as f:
        f.write(f'{str_err} in {fn} | {curr_dt}\n{get_stack_trace()}\n')
