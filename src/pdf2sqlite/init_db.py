import sqlite_vec
from sqlite3 import Cursor
from importlib import resources

create_statement = resources.read_text("pdf2sqlite.sql", "create_db.sql")

def init_db(cursor : Cursor):
    cursor.connection.enable_load_extension(True)

    # Enable sqlite-vec extension
    sqlite_vec.load(cursor.connection)

    cursor.executescript(create_statement)
