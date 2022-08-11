#!/usr/bin/python

import sqlite3
from .base_odbc import DBText

class Sqlite3_DBText(DBText):

    @classmethod
    def make_connection(cls, dbname):
        return sqlite3.connect(f"{dbname}.db")

    def create_empty_db(self):
        pass

    def drop(self):
        pass

    def execute_setup_query(self, ttcxn, currQuery):
        ttcxn.executescript(currQuery)

    def get_table_names(self, ttcxn):
        cursor = ttcxn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [name[0] for name in cursor.fetchall()]
        return tables

    def query_for_columns(self, ttcxn, tablename):
        cursor = ttcxn.cursor()
        cursor.execute(f"PRAGMA TABLE_INFO({tablename})")

        class Sqlite3Column:
            def __init__(self, pragma_data):
                self.column_name = pragma_data[1]
                self.type_name = pragma_data[2].lower()
            def __repr__(self):
                return f"Sqlite3Column({self.column_name}, {self.type_name})"

        cols = [Sqlite3Column(pragma_data) for pragma_data in cursor.fetchall()]
        return cols

    def insert_row_data(self, ttcxn, sql, data, table_name):
        ttcxn.cursor().execute(sql, list(data.values()))





