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


def execute_sql(statement, parameters=''):
    ''' str, tuple -> str

    Execute sql query with given data load '''

    conn = None
    try:
        # connect to the PostgreSQL server
        conn = connect()
        # create a cursor
        cur = conn.cursor()
        # execute a statement
        # for command in commands:
        cur.execute(statement, parameters)
        # commit the changes
        conn.commit()
        # close communication with the PostgreSQL database server
        cur.close()
        return('Done')

    finally:
        if conn is not None:
            conn.close()


# sql1 = (
#     """
#     CREATE TABLE trades (
#         id SERIAL PRIMARY KEY,
#         txid VARCHAR(255),
#         created_at TIMESTAMPTZ,
#         pair VARCHAR(255),
#         type VARCHAR(255),
#         signal VARCHAR(255),
#         expected_price DECIMAL,
#         status VARCHAR(255),
#         actual_price DECIMAL
#     )
#     """)


if __name__ == '__main__':
    None
