# IB NOPE

Automated trading system for NOPE strategy over IBKR TWS

## Setup

1. Follow the [user guide](https://github.com/IbcAlpha/IBC/blob/master/userguide.md) to install IBC
2. Run `pip install -r requirements.txt`
3. run `pip install https://github.com/ajhpark/qtrade/archive/yaml-path-fix.zip`
4. Go to qt/ and edit `generate_token.py` so that it uses your access code, and then run it

## Start

Run `main.py`

## Development

We're using [ib_insync](https://github.com/erdewit/ib_insync) to connect to the TWS API. Read the [docs](https://ib-insync.readthedocs.io/api.html) for more details
