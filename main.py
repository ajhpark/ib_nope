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
    restart_tasks = ["run_ib", "check_orders"]
    tasks = nope_strategy.get_tasks_dict()
    for task_name in restart_tasks:
        task = tasks.pop(task_name)
        task.cancel()


ibc = IBC(978, tradingMode="paper")
ib = IB()
ib.connectedEvent += onConnect
ib.disconnectedEvent += onDisconnect

nope_strategy = NopeStrategy(config, ib)

watchdog = Watchdog(ibc, ib)
watchdog.start()
ib.run()
