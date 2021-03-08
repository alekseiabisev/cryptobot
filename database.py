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
        return 'Done'

    finally:
        if conn is not None:
            conn.close()


def check_table_exists(tablename):
    ''' str -> bool

        Checks if table exists in the database
    '''
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) \
                 FROM information_schema.tables \
                 WHERE table_name = %s", (tablename,))
    if cur.fetchone()[0] == 1:
        cur.close()
        return True

    cur.close()
    return False


# if __name__ == '__main__':
#     check_table_exists('trades')
