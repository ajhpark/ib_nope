from qtrade import Questrade
from datetime import datetime

class QuestradeClient:
    TICKER = "SPY"

    def __init__(self, token_yaml):
        self.yaml_path = token_yaml
        self.client = Questrade(token_yaml=token_yaml)
        self.refresh_access_token()

    def refresh_access_token(self):
        self.client.refresh_access_token(from_yaml=True, yaml_path=self.yaml_path)

    def get_nope(self):
        call_option_filters = []
        put_option_filters = []
        chain = self.client.get_option_chain(self.TICKER)
        quote = self.client.get_quote(self.TICKER)
        underlying_id = quote['symbolId']

        for optionChain in chain['optionChain']:
            exp_date = optionChain['expiryDate']
            call_option_filters.append({
                'optionType': 'Call',
                'expiryDate': exp_date,
                'underlyingId': underlying_id
            })
            put_option_filters.append({
                'optionType': 'Put',
                'expiryDate': exp_date,
                'underlyingId': underlying_id
            })

        call_option_quotes = self.client.get_option_quotes(call_option_filters, [])
        put_option_quotes = self.client.get_option_quotes(put_option_filters, [])

        total_call_delta = sum(map(lambda q: q['volume'] * q['delta'], call_option_quotes['optionQuotes']))
        total_put_delta = sum(map(lambda q: q['volume'] * q['delta'], put_option_quotes['optionQuotes']))

        try:
            nope = ((total_call_delta + total_put_delta) * 10000) / quote['volume']
        except ZeroDivisionError:
            curr_dt = datetime.now().strftime("%Y-%m-%d at %H:%M:%S")
            with open("logs/errors.txt", "a") as f:
                f.write(f'No volume data on {quote["symbol"]} | {curr_dt}\n')
            return [0, 0]

        return [nope, quote['lastTradePrice']]





