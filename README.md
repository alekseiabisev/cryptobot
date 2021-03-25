# cryptobot

## Disclaimer
```
I am not responsible for anything done with this bot.
You use it at your own risk.
There are no warranties or guarantees expressed or implied.
You assume all responsibility and liability.
```

## Description
Bot for automated trading on Kraken. Was done as a fun project. My first Python project.

Bot has a simple strategy based on two factors:
-   Keep balance between fiat(or stablecoins) and crypto
-   Buy/sell once EMA short and long term trends are crossing or once RSI signals about overbought / oversold
Trade orders info is stored in PostgreSQL.

**Once there is a signal to buy or sell and portfolio is not balanced - trade is executed.**

![Trades example](Docs/Screenshot%202021-03-19%20at%2010.09.43.png)

### Instalation:

```bash
cd cryptobot
sudo pip3 install -r requirements.txt
sudo apt-get install libatlas-base-dev
```
note: pandas requires libatlas-base-dev

if you want to use postgree:
```bash
cd cryptobot
sudo pip3 install -r requirements-postgree.txt
```



### Kraken configuration:
We recommend to at it on ~/.bashrc

```bash
export KRAKEN_KEY=YOUR_KRAKEN_KEY
export KRAKEN_SECRET=YOUR_KRAKEN_SECRET
```

### Kraken configuration:
We recommend to at it on ~/.bashrc
Default value: 'postgres://localhost/bot'

For sqlight3:
```bash
export DATABASE_URL=sqlite3
```
### run configuration:
We recommend to at it on ~/.bashrc
Default value: 'postgres://localhost/bot'


### running:
When you execute:

```bash
cp config_template.json configs/btc_eur.json
```
The application why try to find a bt-usd.json (so you must create it) in the application directory.

When it comes to the database:
using postgree: it will try to find the database name bt-usd (check if this database exists)
using sqlite3:  it will try to find the database file bt-usd.db

So that you can run many boots parallel.

Open the file btc_eur.json and adjust your parameters
```bash
nano configs/btc_eur.json
```

Run the application:
```bash
python3 ./cryptobot.py bt-usd
```
Tip:
Test the key pars using this address https://api.kraken.com/0/public/Ticker?pair=XXBTZEUR

More information on:
https://support.kraken.com/hc/en-us/articles/360000678446-Cryptocurrencies-available-on-Kraken
https://api.kraken.com/0/public/AssetPairs


### Signals:
- EWM. Exponential moving averages trends crossing signal:
Currently set to 10 and 20 (can be changed in config). EMA crosses are giving a signal to buy / sell.
- RSI signal:
The relative strength index (RSI) is a momentum indicator used in technical analysis that measures the magnitude of recent price changes to evaluate overbought or oversold conditions in the price of a stock or other asset.
Default setting (config): sell if RSI > 80, buy if RSI is less than 20. Window: 14 periods


|EWM signal | RSI signal |
| --- | --- |
|![EWM signal](Docs/Screenshot%202021-03-19%20at%2011.04.22.png) | ![RSI signal](Docs/Screenshot%202021-03-19%20at%2011.02.46.png) |


### Amount:
Amount required for the trade is calculated based on the portfolio balance. Set in config (current: 50/50). Required amount is amount needed to balance up portfolio.
As for stable coins (BTC) volatility is quite moderate and most of the trades were just +/-0.5% of portfolio size - power option was added. With power option you can add a virtual balance on top of the existing one. Note: that using a power can deplete actual balance in case of a high volatility.
> For example if virtual balance initialization price was 47'500. Bot will be sold out of BTC once price will reach 95'000 USDT. And will be out of USDT once price will be below of 22'500 USDT.
> In case if power is not used bot can run in any range of crypto price (0 to unlimited)

## Config explanation
- TREND_PAIR - Pair is used to define trends. Can be the same as Trading pair. Use different pair in case if trading pair doesn't have enough liquidity. Can case small deviations in market price trading. For example XXBTZUSD
- TRADING_PAIR - Pair which will be used for trading. For example: XBTUSDT
- CRYPTO_TRADING_SYMBOL - Example: XXBT
- MONEY_TRADING_SYMBOL - USDT
- CONFIG_BALANCE - Balance of the portfolio required, in case if portfolio need to be balanced 50%/50% between crypto / "fiat" then use 0.5, in case if crypto amount need to be 80% - use 0.8. Example: 0.5
- POWER. Amount of the virtual balance from actual balance. In case if actual balance is 2'000 USD with a power of 4 - Bot will initialize additional 8k USD. Balancing will be done assuming that total balance is 10k. In case if virtual balance is not required - use 1. Example: 4
- MIN_TRANSACTION_VOLUME - Exchange minimum allowed volume of Crypto. Example: 0.0002
- TRANSACTION_FEE - Exchange fee for transactions. Example: 0.0026,
- INTERVAL - Interval of data checks in minutes. 1M, 3M, 5M, 15M, 30M, 1H, etc. Use 1 of frequent trading. Example: 1
- EWM: - Exponential moving averages settings.
	- window_length - Required of continuous lengths of the short-term trend appearance above or below long-term trend. Helping to ignore to quickly changing.  trends.
	- long - periods of EWM. Default 20
	- short - periods of EWM. Default 10
- RSI - Relative strength index settings
	- type: ewm|sma. Exponential moving weighed average or Simple moving average.
    - window_length: 14,
    - overbought_level: 80,
    - oversold_level: 20

## Outcomes
With a power of 4, interval 1 (high frequency) trading on BTC/USDT pair measured annual return is about 15%.
With a 2k budget bot was doing about 10-15 trades a day.

## TODO
Current volatility between BTC and USDT is not enough for high frequency trading. Using other coins with a high volatility is an option but could lead you for getting a lot of cheap coins with 0 liquidity.

Alternative option: Round trading keeping a balance between multiple pairs of potentially perspective coins. For example:
- BTC/USDT/ETH - will increase amount of trades X3 (Pairs: BTCUSD, BTCETH, ETHUSD)
- BTC/USDT/ETH/XRP - will increase amount of trades X6 (Pairs: BTCUSD, BTCETH, BTCXRP, ETHUSD, ETHXRP, XRPUSD)
- BTC/USDT/ETH/XRP/ADA - X10
