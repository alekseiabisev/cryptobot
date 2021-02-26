# cryptobot
Bot for automated trading on Kraken

Bot has a simple strategy based on two factors:
- Keep balance between fiat(or stablecoins) and crypto
- Buy/sell once EMA short and long term trends are crossing

Buy/sell signal is based on exponential moving averages trends crossing. Currently set to 10 and 20 (hardcoded).
EMA crosses are giving a signal to buy / sell

Amount required ot buy or sell is calculated based on the portfolio balance.
Balance. Set in config (current: 50/50). Is tellling an app how much of each asset (fiat/crypto) application need to have.

Once there is a signal to buy or sell and portfolio is not balanced - trade is executed.
