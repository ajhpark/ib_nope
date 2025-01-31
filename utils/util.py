import sys
import traceback
from datetime import datetime, timezone

from ib_insync import util


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


def get_datetime_diff_from_now(dt):
    diff = datetime.utcnow().replace(tzinfo=timezone.utc) - dt
    return diff.seconds / 60


def get_stack_trace():
    exc = sys.exc_info()[0]
    stack = traceback.extract_stack()[:-1]
    if exc is not None:
        del stack[-1]
    trc = "Traceback (most recent call last):\n"
    stack_str = trc + "".join(traceback.format_list(stack))
    if exc is not None:
        stack_str += "  " + traceback.format_exc().lstrip(trc)
    return stack_str


def log_exception(e: Exception, fn):
    str_err = "Error {0}".format(str(e))
    _, curr_dt = get_datetime_for_logging()
    print(f"{str_err} in {fn} | {curr_dt}")
    print(get_stack_trace())
    with open("logs/errors.txt", "a") as f:
        f.write(f"{str_err} in {fn} | {curr_dt}\n{get_stack_trace()}\n")


def log_fill(filled_trade):
    curr_date, curr_dt = get_datetime_for_logging()

    for fill in filled_trade.fills:
        avg_fill_price = round(fill.execution.avgPrice * 100, 2)
        with open(f"logs/{curr_date}-trade.txt", "a") as f:
            f.write(
                f"{fill.execution.side} {fill.execution.shares} {fill.contract.strike}{fill.contract.right}{fill.contract.lastTradeDateOrContractMonth} for {avg_fill_price} each, {curr_dt}\n"
            )


def stop_order_price(price, stop_loss_percentage):
    return round(price - (price * (stop_loss_percentage / 100)), 2)
