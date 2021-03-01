import krakenex
import pandas as pd
import time
import json
import logging
import os
import sys
from apscheduler.schedulers.blocking import BlockingScheduler

# Config comments:
# min_transaction_volume Consider replacing with API call information about user settings (if there is one)
# transaction_fee Consider replacing with API call: 'TradeVolume' -> fees -> fee


# Connect to Kraken
    # For Cloud environment
if 'KRAKEN_KEY' in os.environ:
    kraken = krakenex.API(os.environ['KRAKEN_KEY'], os.environ['KRAKEN_SECRET'])
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
    # Create logger for application
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler('runtime.log')
    fh.setLevel(logging.DEBUG)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    sh.setFormatter(formatter)
    # Add handler to the logger
    logger.addHandler(fh)
    if 'DYNO' in os.environ:
        logger.addHandler(sh)

    return logger

def monitor_act():
    ''' Monitoring current trends and portfolio balance and
        in case it is a right time - executing trade orders.
    '''
    # Get price data
    df = get_data(trend_pair)
    # Get exponential moving average trends difference (EMA 10 - EMA 20). Form trade decision
    last = float(df['ewm_diff'][-1:])
    previous = df['ewm_diff'][-trend_length-1:-1]
    trend = check_trend(last, previous)
    price = float(df['close'][-1:])

    # Cancel all still not executed orders
    kraken.query_private('CancelAll')

    # Get current balances. Will be used to check if assets are in balance with a current price
    balance = get_balance()
    actual_crypto_amount, actual_money_amount = balance
    actual_balance = round((actual_crypto_amount * price) / (actual_crypto_amount * price + actual_money_amount),3)

    powered_balance = [power * symbol for symbol in balance]
    powered_crypto_amount, powered_money_amount = powered_balance

    required_crypto_amount = required_crypto(price, powered_crypto_amount, powered_money_amount)

    # Create a new order in case if it is a right time and there is a balance to allocate
    if trend == 'buy' and required_crypto_amount > 0:
        add_order('buy', abs(required_crypto_amount))
    elif trend == 'sell' and required_crypto_amount < 0:
        add_order('sell', abs(required_crypto_amount))
    else:
        logger.info('Trend is: '+trend+'. Actual Balance is: '+str(actual_balance)+' Buy/sell function is not called.')

def get_balance():
    ''' Requesting balance of assets from exchange.

    Returns:
        list with balance: crypto, money
    '''
    res_balance = kraken.query_private('Balance')
    current_balance = res_balance['result']
    # Changing pair value type from string to float
    current_balance.update((k, float(v)) for k, v in current_balance.items())
    # Applying power for our balance
    crypto_amount = current_balance[crypto_trading_symbol]
    money_amount = current_balance[money_trading_symbol]
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
    res_data = kraken.query_public("Ticker",req_data)
    last_trade_price = float(res_data['result'][req_data['pair']][price_type][0])
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
    req_data['interval'] = interval
    req_data['since'] = time.time() - 3600*interval
    res_data = kraken.query_public('OHLC',req_data)
    # Load data to pandas dataframe
    df = pd.DataFrame(res_data['result'][req_data['pair']])
    df.columns = ['time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count']
    #Convert unix time to readable time
    df['time'] = pd.to_datetime(df['time'], unit='s')
    # Add exponential moving averages and signal column(ewm_diff): negative - bearish, positive - bullish
    df['ewm_20'] = df['close'].ewm(span=ema_long).mean()
    df['ewm_10'] = df['close'].ewm(span=ema_short).mean()
    df['ewm_diff'] = df['ewm_10'] - df['ewm_20']
    return df

def check_trend(last, previous):
    ''' Determines call to action based on received trends.

    Args:
        last: list of last N trends (defined in config).
        previous: last trend

    Returns:
        String representing current trend. Possible values: 'sell', 'buy', 'wait'
    '''
    if (previous[previous > 0].count() == len(previous) and last < 0):
        return 'sell'
    elif (previous[previous < 0].count() == len(previous) and last > 0):
        return 'buy'
    return 'no action'

def required_crypto(price,crypto_amount,money_amount):
    ''' Returning required amount to balance portfolio
        Checks if it makes sense to change the balance based on minimum transactuion volume.
        And if potential revenue from trade will cover transaction fees.

    Args:
        price: current price of the targeted crypto asset

    Returns:
        float of required amount of crypto (positive if we need to buy, negative if sell)
    '''

    required_crypto_amount = (crypto_amount + money_amount / price) * balance - crypto_amount
    #Comparing required amount ot buy/sell with minimum allowed volume
    if abs(required_crypto_amount) < min_transaction_volume:
        return 0
    # Comparing crypto assets average price during last trade with current price
    # and checking if change percentage will covering transaction fees
    # transaction fee is doubled, because in order to earn we need to buy and sell
    elif crypto_amount != 0 and abs((money_amount / crypto_amount - price) / price) <= transaction_fee*2:
        return 0

    return required_crypto_amount

def add_order(type, amount):
    ''' Sending an order to Exchange.

    Args:
        type: string buy/sell
        amount: required amount of crypto to buy/sell

    Returns:
        Exchnage response of execution.
    '''
    req_data = dict()
    req_data['type'] = type
    req_data['pair'] = trading_pair
    req_data['ordertype'] = 'market'
    req_data['trading_agreement'] = 'agree'
    req_data['volume'] = round(amount, 5)
    # Execute order
    res_data = kraken.query_private('AddOrder', req_data)
    logger.info('Call '+type+' function: required amount: '+str(amount))
    return res_data

def timed_job():
    ''' Checks if loggers are active.
        And execute main function.
    '''
    try:
        # Check if logger is active
        if logging.getLogger().hasHandlers() == False:
            logger_init()
        monitor_act()
    except:
        logger.error('Error in main loop', exc_info=True)

logger = logger_init()

# Start scheduling
sched = BlockingScheduler()
sched.add_job(timed_job, 'interval', minutes=1)
sched.start()
