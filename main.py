import krakenex
import pandas as pd
import logging
import os
import sys
import json
import sentry_sdk
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler

from DBConn import Orders

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


# Initialising Sentry
sentry_sdk.init(os.environ['SENTRY_DSN'])


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
    ''' int -> float, float
        Initialise required virtual balance.
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
    # Add add technical indicators to dataframe
    df = add_technical_indicators(df)
    # Get last price
    price = df['close'][-1:].values[0]

    # Check EWM signal
    last = df['ewm_diff'][-1:].values[0]
    previous = df['ewm_diff'][-EWM['window_length']-1:-1]
    ewm_signal = check_ewm_signal(last, previous)

    # Check RSI signal
    last_rsi = df['rsi'][-1:].values[0]
    rsi_signal = check_rsi_signal(last_rsi)

    # Cancel all still not executed orders
    # kraken.query_private('CancelAll')

    # Get current balances.
    # Will be used to check if assets are in balance with a current price
    balance = get_balance()
    crypto_amount, money_amount = balance
    balance_percentage = \
        (crypto_amount * price) / (crypto_amount * price + money_amount)
    # Add virtual balance to actual balamce
    if 'virtual_balance' in globals():
        crypto_amount += virtual_balance[0]
        money_amount += virtual_balance[1]
    virtual_balance_percentage = \
        crypto_amount * price / (crypto_amount * price + money_amount)

    # Calculate required crypto amount
    required_crypto = calculate_required_crypto(price, crypto_amount,
                                                money_amount)
    amount = required_crypto['amount']
    reason = required_crypto['reason']

    logger.info(f'EWM signal is: {ewm_signal}, '
                f'RSI signal is: {rsi_signal}, '
                f'Actual Balance is: {balance_percentage:0.2%}. '
                f'Virtual Balance is: {virtual_balance_percentage:0.2%}.')

    # Create a new order
    # in case if it is a right time and there is a balance to allocate
    if ewm_signal == 'no action' and rsi_signal == 'no action':
        logger.info(f'No action. No trade signal')
    elif amount == 0:
        logger.info(f'No action. Reason: {reason}')
    elif (ewm_signal == 'buy' or rsi_signal == 'buy'):
        if amount > 0 and ewm_signal == 'buy':
            add_order('buy', abs(amount), price, 'EWM')
        elif amount > 0 and rsi_signal == 'buy':
            add_order('buy', abs(amount), price, 'RSI')
        else:
            logger.info(f'No action. We are overbought')
    elif (ewm_signal == 'sell' or rsi_signal == 'sell'):
        if amount < 0 and ewm_signal == 'sell':
            add_order('sell', abs(amount), price, 'EWM')
        elif amount < 0 and rsi_signal == 'sell':
            add_order('sell', abs(amount), price, 'RSI')
        else:
            logger.info(f'No action. We are oversold')
    else:
        logger.info(f'No action.')


def get_balance():
    ''' None -> list
        Requesting balance of assets from exchange.
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
    ''' str -> float
        Checks for the close ('c') price type of the pair.
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
    ''' str -> dataframe
        Requesting data for the last 60 periods starting from now from Kraken
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
    req_data['since'] = datetime.now().timestamp() - 3600*INTERVAL
    res_data = kraken.query_public('OHLC', req_data)
    # Load data to pandas dataframe
    df = pd.DataFrame(res_data['result'][req_data['pair']])
    df.columns = ['time', 'open', 'high', 'low',
                  'close', 'vwap', 'volume', 'count']
    # Convert unix time to readable time
    df['time'] = pd.to_datetime(df['time'], unit='s')
    # Convert other columns to nummeric
    cols = df.columns.drop('time')
    df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')

    return df


def add_technical_indicators(df):
    ''' dataframe -> dataframe
        Add exponential moving averages and signal column(ewm_diff):
        negative - bearish; positive - bullish
        Add RSI indicators based on EWM and SMA:
        less than 30 - oversold -> buy; more than 70 - overbought -> sell
    '''
    # Add Exponential weighted moving average (ewm)
    df['ewm_20'] = df['close'].ewm(span=EWM['long']).mean()
    df['ewm_10'] = df['close'].ewm(span=EWM['short']).mean()
    # Calculate difference between short and long EWM
    df['ewm_diff'] = df['ewm_10'] - df['ewm_20']

    # Add Relative strength index (RSI)
    # Hardcode windows length
    window_length = RSI['window_length']
    # Get the difference in price from previous step
    delta = df['close'].diff()
    # Make the positive gains (up) and negative gains (down) Series
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    # Calculate the EWMA
    roll_up1 = up.ewm(span=window_length).mean()
    roll_down1 = down.abs().ewm(span=window_length).mean()
    # Calculate the RSI based on EWMA
    rsi_ewm = 100.0 - (100.0 / (1.0 + roll_up1 / roll_down1))
    # Calculate the SMA
    roll_up2 = up.rolling(window_length).mean()
    roll_down2 = down.abs().rolling(window_length).mean()
    # Calculate the RSI based on SMA
    rsi_sma = 100.0 - (100.0 / (1.0 + roll_up2 / roll_down2))
    # Add RSI type based on configuration settings
    if RSI['type'] == 'ewm':
        df['rsi'] = rsi_ewm
    elif RSI['type'] == 'sma':
        df['rsi'] = rsi_sma

    return df


def check_rsi_signal(rsi):
    ''' float -> str
        Determine call to action based on RSI level.'''
    if rsi < RSI['oversold_level']:
        rsi_signal = 'buy'
    elif rsi > RSI['overbought_level']:
        rsi_signal = 'sell'
    else:
        rsi_signal = 'no action'

    return rsi_signal


def check_ewm_signal(last, previous):
    ''' (list, float) -> string
        Determines call to action based on received trends.
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


def calculate_required_crypto(price, crypto_amount, money_amount):
    ''' (float, float, float) -> (float, str)
        Returning required amount to balance portfolio
        Checks if it makes sense to change the balance based on minimum
        transaction volume.
        And if potential revenue from trade will cover transaction fees.
        In case if trade is not required also returns reason.
    '''
    # Calculate potentially required crypto amount
    required_amount = ((crypto_amount + money_amount / price)
                       * CONFIG_BALANCE - crypto_amount)
    required_amount = round(required_amount, 5)
    res = {'amount': required_amount, 'reason': ''}

    # Comparing required amount ot buy/sell with minimum allowed volume
    if abs(required_amount) < MIN_TRANSACTION_VOLUME:
        res['amount'] = 0
        res['reason'] = 'Required amount is below minimum transaction volume'
    # Comparing crypto assets avg price during last trade with current price
    # and checking if change percentage will covering transaction fees
    # transaction fee is doubled (in order to earn we need to buy and sell)
    elif (crypto_amount != 0
          and abs((money_amount / crypto_amount - price) / price)
          <= TRANSACTION_FEE*4):
        res['amount'] = 0
        res['reason'] = "Potential revenue won't cover transactionfees"

    return res


def add_order(type, amount, price, signal='N/D'):
    ''' (str, float, float, str) -> None
        Send an order to Exchange.
        Add order transaction information to database
    Args:
        type: string buy/sell
        amount: required amount of crypto to buy/sell
        price:
        signal: EWM / RSI / not defined
    '''
    req_data = dict()
    req_data['type'] = type
    req_data['pair'] = TRADING_PAIR
    req_data['ordertype'] = 'market'
    req_data['trading_agreement'] = 'agree'
    req_data['volume'] = amount

    # Execute order
    res_data = kraken.query_private('AddOrder', req_data)

    # Add logger entry
    logger.info(f'Call {type} function. Required amount: {amount}, Expected price: {price}')

    # Add entry to database
    if 'result' in res_data:
        txid = res_data['result']['txid'][0]
        pair = TRADING_PAIR
        with Orders() as orders:
            orders.add_orders(txid, pair, type, price, amount, signal)


def update_orders_data():
    ''' None -> None
        Check if we have some not update orders. Send request to get data.
        Execute query to update entries.
    '''
    with Orders() as orders:
        # Get not updated orders created with last 60 minutes
        query_res = orders.get_not_update_trades(60)
    txids = [res[0] for res in query_res]
    if len(txids) > 0:
        req_data = dict()
        # list -> comma separated strings
        req_data['txid'] = ','.join(txids)
        query_res = kraken.query_private('QueryOrders', req_data)
        for txid in txids:
            price = query_res['result'][txid]['price']
            status = query_res['result'][txid]['status']
            amount = query_res['result'][txid]['vol_exec']
            with Orders() as orders:
                orders.update_trades(txid, price, status, amount)


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


# Initialise logging
logger = logger_init()

# Check if virtual balance is required but not initialised
if POWER != 1 and ('virtual_balance' not in globals()
                   or virtual_balance == (0, 0)):
    virtual_balance = init_virtual_balance(POWER)

# Start scheduling
sched = BlockingScheduler()
sched.add_job(timed_job, 'interval', minutes=1)
sched.add_job(update_orders_data, 'interval', minutes=10)
sched.start()
