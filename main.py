import krakenex
import pandas as pd
import time
import json
import logging
import os
import sys
from apscheduler.schedulers.blocking import BlockingScheduler

# Config comments:
# MIN_TRANSACTION_VOLUME Consider replacing with API call information
# about user settings (if there is one)
# TRANSACTION_FEE Consider replacing with API call:'TradeVolume'->fees->fee


# Connect to Kraken
if 'KRAKEN_KEY' in os.environ:
    # For Cloud environment
    kraken = krakenex.API(os.environ['KRAKEN_KEY'],
                          os.environ['KRAKEN_SECRET'])
else:
    # For local environment
    kraken = krakenex.API()
    kraken.load_key('kraken.key')

# Load global variables from config file
with open('config.json') as config_file:
    config = json.load(config_file)
globals().update(config)


def logger_init():
    ''' Logger initialisation
    '''

    class NoRunningFilter(logging.Filter):
        def filter(self, record):
            return not record.name == 'apscheduler.executors.default'

    # Create logger for application
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # Adding handlers
    fh = logging.FileHandler('runtime.log')
    fh.setLevel(logging.DEBUG)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)

    my_filter = NoRunningFilter()
    sh.addFilter(my_filter)
    # create formatter and add it to the handlers
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    sh.setFormatter(formatter)
    # Add handler to the logger
    logger.addHandler(sh) if 'DYNO' in os.environ else logger.addHandler(fh)

    return logger


def init_virtual_balance(power):
    ''' Initialise required virtual balance.

    Args:
        power
    Returns:
        pair of numbers of required virtual balance
    '''
    virtual_crypto, virtual_money = 0, 0

    # Get current actual balance
    actual_crypto, actual_money = get_balance()
    price = get_price(TRADING_PAIR)
    actual_total = actual_crypto * price + actual_money
    # Apply additional leverage
    balance_total = actual_total * power

    virtual_crypto = balance_total * CONFIG_BALANCE / price - actual_crypto
    virtual_money = balance_total * CONFIG_BALANCE - actual_money
    logger.info(f'Virtual balance initialised: {virtual_crypto:0.3} | '
                f'{virtual_money:.0f}')

    return virtual_crypto, virtual_money


def monitor_act():
    ''' Monitoring current trends and portfolio balance and
        in case it is a right time - executing trade orders.
    '''
    # Get price data
    df = get_data(TREND_PAIR)
    # Get exponential moving average trends difference (EMA 10 - EMA 20).
    # Form trade decision
    last = float(df['ewm_diff'][-1:])
    previous = df['ewm_diff'][-TREND_LENGTH-1:-1]
    trend = check_trend(last, previous)
    price = float(df['close'][-1:])

    # Cancel all still not executed orders
    kraken.query_private('CancelAll')

    # Get current balances.
    # Will be used to check if assets are in balance with a current price
    balance = get_balance()
    crypto_amount, money_amount = balance
    balance_percentage = \
        (crypto_amount * price) / (crypto_amount * price + money_amount)
    if 'virtual_balance' in globals():
        crypto_amount += virtual_balance[0]
        money_amount += virtual_balance[1]
    virtual_balance_percentage = \
        crypto_amount * price / (crypto_amount * price + money_amount)
    required_crypto_amount = required_crypto(price,
                                             crypto_amount, money_amount)
    # Create a new order
    # in case if it is a right time and there is a balance to allocate
    if trend == 'buy' and required_crypto_amount > 0:
        add_order('buy', abs(required_crypto_amount))
    elif trend == 'sell' and required_crypto_amount < 0:
        add_order('sell', abs(required_crypto_amount))
    else:
        logger.info(f'Trend is: {trend}, '
                    f'Actual Balance is: {balance_percentage:0.2%}. '
                    f'Virtual Balance is: {virtual_balance_percentage:0.2%}. '
                    f'Buy/sell function is not called.')


def get_balance():
    ''' Requesting balance of assets from exchange.

    Returns:
        list with balance: crypto, money
    '''
    crypto_amount, money_amount = 0, 0
    res_balance = kraken.query_private('Balance')
    current_balance = res_balance['result']
    # Changing pair value type from string to float
    current_balance.update((k, float(v)) for k, v in current_balance.items())
    # Applying power for our balance
    crypto_amount = current_balance[CRYPTO_TRADING_SYMBOL]
    money_amount = current_balance[MONEY_TRADING_SYMBOL]
    return crypto_amount, money_amount


def get_price(pair):
    '''Checks for the close ('c') price type of the pair.

    Args:
        pair: pair of symbols, e.g. XXBTZUSD

    Returns:
        Price for the given pair
    '''
    req_data = dict()
    req_data['pair'] = pair
    price_type = 'c'
    res_data = kraken.query_public("Ticker", req_data)
    last_trade_price = float(res_data['result']
                             [req_data['pair']]
                             [price_type][0])
    return last_trade_price


def get_data(pair):
    ''' Requesting data for the last 60 periods starting from now from Kraken
        Converts response to pandas DataFrame
        Adds short, long EMA. Calculates short and long EMA diff.

    Args:
        pair: string representing pair of symbols, e.g. XXBTZUSD

    Returns:
        Pandas dataframe with prices and EMAs.
    '''
    req_data = dict()
    req_data['pair'] = pair
    req_data['interval'] = INTERVAL
    req_data['since'] = time.time() - 3600*INTERVAL
    res_data = kraken.query_public('OHLC', req_data)
    # Load data to pandas dataframe
    df = pd.DataFrame(res_data['result'][req_data['pair']])
    df.columns = ['time', 'open', 'high', 'low',
                  'close', 'vwap', 'volume', 'count']
    # Convert unix time to readable time
    df['time'] = pd.to_datetime(df['time'], unit='s')
    # Add exponential moving averages and signal column(ewm_diff):
    # negative - bearish, positive - bullish
    df['ewm_20'] = df['close'].ewm(span=EMA_LONG).mean()
    df['ewm_10'] = df['close'].ewm(span=EMA_SHORT).mean()
    df['ewm_diff'] = df['ewm_10'] - df['ewm_20']
    return df


def check_trend(last, previous):
    ''' Determines call to action based on received trends.

    Args:
        last: list of last N trends (defined in config).
        previous: last trend

    Returns:
        String representing current trend.
        Possible values: 'sell', 'buy', 'wait'
    '''
    if (previous[previous > 0].count() == len(previous) and last < 0):
        return 'sell'
    elif (previous[previous < 0].count() == len(previous) and last > 0):
        return 'buy'
    return 'no action'


def required_crypto(price, crypto_amount, money_amount):
    ''' Returning required amount to balance portfolio
        Checks if it makes sense to change the balance based on minimum
        transaction volume.
        And if potential revenue from trade will cover transaction fees.

    Args:
        price: current price of the targeted crypto asset

    Returns:
        float of required amount of crypto
        (positive if we need to buy, negative if sell)
    '''

    required_crypto_amount = ((crypto_amount + money_amount / price)
                              * CONFIG_BALANCE - crypto_amount)
    # Comparing required amount ot buy/sell with minimum allowed volume
    if abs(required_crypto_amount) < MIN_TRANSACTION_VOLUME:
        return 0
    # Comparing crypto assets avg price during last trade with current price
    # and checking if change percentage will covering transaction fees
    # transaction fee is doubled (in order to earn we need to buy and sell)
    elif (crypto_amount != 0
          and abs((money_amount / crypto_amount - price) / price)
          <= TRANSACTION_FEE*2):
        return 0

    return required_crypto_amount


def add_order(type, amount):
    ''' Sending an order to Exchange.

    Args:
        type: string buy/sell
        amount: required amount of crypto to buy/sell

    Returns:
        Exchange response of execution.
    '''
    req_data = dict()
    req_data['type'] = type
    req_data['pair'] = TRADING_PAIR
    req_data['ordertype'] = 'market'
    req_data['trading_agreement'] = 'agree'
    req_data['volume'] = round(amount, 5)
    # Execute order
    res_data = kraken.query_private('AddOrder', req_data)
    logger.info(f'Call {type} function. Required amount: {amount}')
    return res_data


def timed_job():
    ''' Checks if loggers are active.
        And execute main function.
    '''
    try:
        # Check if logger is active
        if not logging.getLogger().hasHandlers():
            logger_init()
        monitor_act()
    except Exception:
        logger.error('Error in main loop', exc_info=True)


logger = logger_init()

# Check if virtual balance is required but not initialised
if POWER != 1 and ('virtual_balance' not in globals()
                   or virtual_balance == (0, 0)):
    virtual_balance = init_virtual_balance(POWER)

# Start scheduling
sched = BlockingScheduler()
sched.add_job(timed_job, 'interval', minutes=1)
sched.start()
