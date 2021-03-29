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

task_run_ib = None


def onConnect():
    global task_run_ib
    task_run_ib = nope_strategy.execute()


def onDisconnect():
    if task_run_ib is not None:
        task_run_ib.cancel()


ibc = IBC(978, tradingMode="paper")
ib = IB()
ib.connectedEvent += onConnect
ib.disconnectedEvent += onDisconnect

nope_strategy = NopeStrategy(config, ib)

watchdog = Watchdog(ibc, ib)
watchdog.start()
ib.run()
