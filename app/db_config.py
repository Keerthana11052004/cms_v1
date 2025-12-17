import os
from dotenv import load_dotenv
import pymysql

# Load environment variables from .env file
load_dotenv()

def get_db_connection(auto_commit=True):
    """
    Create and return a database connection using environment variables.
    
    Returns:
        pymysql.Connection: A database connection object
    """
    conn = pymysql.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DB', 'CMS'),
        cursorclass=getattr(pymysql.cursors, os.getenv('MYSQL_CURSORCLASS', 'DictCursor')),
        autocommit=auto_commit
    )
    return conn