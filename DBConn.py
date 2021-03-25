''' Database connection interface. '''
import os
import sys
from datetime import datetime, timedelta

DBTYPE='postgres'
config_param='bot'

if len(sys.argv) > 1:
    config_param=sys.argv[1]

if 'DATABASE_URL' in os.environ:
    if os.environ['DATABASE_URL'] == 'sqlite3':
        DBTYPE='sqlite3'
        DATABASE_URL=os.path.dirname(__file__) + '/configs/smarthome.db'
        import sqlite3
    else:
        DATABASE_URL = os.environ['DATABASE_URL'] + '?sslmode=require'
        import psycopg2
else:
    DATABASE_URL = 'postgres://localhost/'+config_param
    import psycopg2


class Orders:
    ''' Class Orders description.'''
    conn = None

    def __init__(self):
        if DBTYPE == 'sqlite3':
            self.conn = sqlite3.connect(DATABASE_URL)
        else:
            self.conn = psycopg2.connect(DATABASE_URL)

        self.cur = self.conn.cursor()
        self.create_table()

    def create_table(self):
        ''' Create table for trades data in case if missing'''
        statement = (
            """
            CREATE TABLE IF NOT EXISTS trades
            (
                id SERIAL PRIMARY KEY,
                txid VARCHAR(255),
                created_at TIMESTAMPTZ,
                pair VARCHAR(255),
                type VARCHAR(255),
                signal VARCHAR(255),
                expected_price DECIMAL,
                status VARCHAR(255),
                actual_price DECIMAL,
                amount DECIMAL
            )
            """)
        self.cur.execute(statement)
        self.conn.commit()

    def add_orders(self, txid, pair, type, price, amount):
        ''' Add new orders to table '''
        statement = """
                    INSERT INTO trades
                    (txid, created_at, pair, type,
                    expected_price, status, amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """
        dt = datetime.now()
        status = 'created'
        statement_data = (txid, dt, pair, type, price, status, amount)
        self.cur.execute(statement, statement_data)
        self.conn.commit()

    def get_not_update_trades(self, minutes_delta):
        ''' Select not updated trades '''

        statement = """
                    SELECT txid
                    FROM trades
                    WHERE status = 'created'
                    AND created_at > %s
                    """
        statement_data = (datetime.now() - timedelta(minutes=minutes_delta),)
        self.cur.execute(statement, statement_data)
        return self.cur.fetchall()

    def update_trades(self, txid, price, status, amount):
        ''' Update trades with actual information'''
        statement = """
                    UPDATE trades
                    SET
                        actual_price = %s,
                        status = %s,
                        amount = %s
                    WHERE txid = %s;
                    """
        statement_data = (price, status, amount, txid)
        self.cur.execute(statement, statement_data)
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, ext_type, exc_value, traceback):
        self.cur.close()
        self.conn.close()
