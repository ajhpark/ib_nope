# IB NOPE

Automated trading system for NOPE strategy over IBKR TWS

## Setup

1. Follow the [user guide](https://github.com/IbcAlpha/IBC/blob/master/userguide.md) to install IBC
2. Run `pip install -r requirements.txt`
3. **If using Questrade for NOPE**:
   Edit `qt/generate_token.py` so that it uses your access code, and then run it to generate `access_token.yml`
   **If using TDA for NOPE**:
   Edit `conf.toml` with your TDA info and follow the steps [here](https://github.com/ajhpark/ib_nope/issues/39) to edit `nope_strategy.py` to use `TDAClient` instead of the default `QuestradeClient`

## Start

Run `main.py`

## Development

We're using [ib_insync](https://github.com/erdewit/ib_insync) to connect to the TWS API. Read the [docs](https://ib-insync.readthedocs.io/api.html) for more details. For connecting to Questrade API for NOPE data we use [qtrade](https://github.com/jborchma/qtrade). Inspired by [thetagang](https://github.com/brndnmtthws/thetagang)

## Why Questrade

See [here](https://github.com/ajhpark/ib_nope/issues/39)
