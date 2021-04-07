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


def onConnect():
    nope_strategy.execute()


def onDisconnect():
    tasks = nope_strategy.get_tasks_dict()
    run_ib_task = tasks.pop("run_ib")
    run_ib_task.cancel()


ibc = IBC(978, tradingMode="paper")
ib = IB()
ib.connectedEvent += onConnect
ib.disconnectedEvent += onDisconnect

nope_strategy = NopeStrategy(config, ib)

watchdog = Watchdog(ibc, ib)
watchdog.start()
ib.run()
