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
    '''Events logger initialisation'''

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
    # Get price data
    df = get_data(trend_pair)

    # Get exponential moving average trends difference (EMA 10 - EMA 20). Form trade decision
    last = float(df['ewm_diff'][-1:])
    previous = df['ewm_diff'][-7:-1]
    trend = check_trend(last, previous)

    price = float(df['close'][-1:])

    # Cancel all still not executed orders
    kraken.query_private('CancelAll')

    # Create a new order in case if it is a right time and there is a balance to allocate
    required_crypto_amount = balancer(price)

    if trend == 'buy' and required_crypto_amount > 0:
        add_order('buy', abs(required_crypto_amount))
    elif trend == 'sell' and required_crypto_amount < 0:
        add_order('sell', abs(required_crypto_amount))
    else:
        logger.info('Trend is: '+trend+'. Buy/sell function is not called.')

def get_balance():
    '''Returns json with balance'''
    res_balance = kraken.query_private('Balance')
    current_balance = res_balance['result']

    # Changing pair value type from string to float
    current_balance.update((k, float(v)) for k, v in current_balance.items())

    return current_balance

def get_price(pair):
    req_data = dict()
    req_data['pair'] = pair

    price_type = 'c'

    res_data = kraken.query_public("Ticker",req_data)
    # If Kraken replied with an error, show it
    #if handle_api_error(res_data, update):
        #    return
    last_trade_price = float(res_data['result'][req_data['pair']][price_type][0])
    return last_trade_price

def get_data(pair):
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
    df['ewm_20'] = df['close'].ewm(span=20).mean()
    df['ewm_10'] = df['close'].ewm(span=10).mean()
    df['ewm_diff'] = df['ewm_10'] - df['ewm_20']

    return df

def determine_trend(trend_list):
    pos_count, neg_count = 0, 0
    for trend in trend_list:
        if trend >= 0:
            pos_count += 1
        else:
            neg_count += 1
    if pos_count == len(trend_list) and len(trend_list) > 0:
        return sum(trend_list)
    elif neg_count == len(trend_list) and len(trend_list) > 0:
        return sum(trend_list)
    return 0

def check_trend(last, previous):
    '''Make a decision about trade.
    Possible values: 'sell', 'buy', 'wait'
    '''
    if (previous[previous > 0].count() == len(previous) and last < 0):
        return 'sell'
    elif (previous[previous < 0].count() == len(previous) and last > 0):
        return 'buy'
    return 'no action'

def balancer(price):
    '''
    Returning required amount to balance out assets.
    If amount negative - crypto assets are > money assets.
    '''
    # Get current balances. Will be used to check if assets are in balance with a current price
    current_balance = get_balance()
    crypto_amount = current_balance[crypto_trading_sumbol]
    money_amount = current_balance[money_trading_sumbol]

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
