import asyncio
import logging
import toml

from ib_insync import IB, IBC, Watchdog, util
from nope.nope_strategy import NopeStrategy

util.patchAsyncio()

with open("conf/conf.toml", "r") as f:
    config = toml.load(f)

if config["debug"]["enabled"]:
    asyncio.get_event_loop().set_debug(True)
    util.logToConsole(logging.DEBUG)

def onConnected():
    nope_strategy.execute()

ibc = IBC(978, tradingMode='paper')
ib = IB()
ib.connectedEvent += onConnected

nope_strategy = NopeStrategy(config, ib)

watchdog = Watchdog(ibc, ib)
watchdog.start()
ib.run()
