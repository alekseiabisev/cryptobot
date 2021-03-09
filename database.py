import psycopg2
import os


def connect():
    ''' Connect to the PostgreSQL database server based on required environment
    '''
    conn = None
    if 'DATABASE_URL' in os.environ:
        DATABASE_URL = os.environ['DATABASE_URL']
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    else:
        conn = psycopg2.connect(host="localhost", database="bot")
    return conn


def execute_sql(statement, statement_data=''):
    ''' str, tuple -> None

        Execute sql query with given data load.
        To be used for changers requiring commit and not returning anything
        (INSERT, UPDATE, CREATE)
    '''

    conn = None
    try:
        conn = connect()
        cur = conn.cursor()
        cur.execute(statement, statement_data)
        conn.commit()
        cur.close()
    finally:
        if conn is not None:
            conn.close()


def execute_fetch_sql(statement, statement_data=''):
    ''' str, tuple -> list of tuples

        Execute sql query with given data load
        And fetch given answer. To be used for SELECT statements
    '''

    conn = None
    try:
        conn = connect()
        cur = conn.cursor()
        cur.execute(statement, statement_data)
        query_res = cur.fetchall()
        cur.close()
        return query_res

    finally:
        if conn is not None:
            conn.close()


# if __name__ == '__main__':
#     check_table_exists('trades')
