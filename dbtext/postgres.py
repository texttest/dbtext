#!/usr/bin/python

from .base_odbc import DBText
from datetime import datetime
try:
    import pyodbc
except ModuleNotFoundError:
    # gets imported even for MongoDB, which doesn't need it
    pass
   
    
class Postgres_DBText(DBText):
    masterDbName = "postgres"        
    @classmethod
    def get_driver(cls):
        drivers = []
        for driver in pyodbc.drivers():
            if driver.startswith("PostgreSQL"):
                drivers.append(driver)

        if drivers:
            return max(drivers)
        else:
            raise RuntimeError("No suitable drivers found for Postgres, is it installed?")
               
    @classmethod
    def set_connection_string_template(cls, server, user, password):
        driver = cls.get_driver()
        host, port = server.split(",")
        cls.connectionStringTemplate = 'DRIVER={' + driver + '};Host=' + host + ';Port=' + port + ';Database=%s;Username=' + user + ';Password=' + password + ';BoolsAsChar=0;'
        return cls.connectionStringTemplate

    def add_table_data_for(self, fn, ttcxn, table_name, pkeys):
        # Need to reset sequence counters explicitly in Postgres (MS SQL does this automatically behind the scenes)
        DBText.add_table_data_for(self, fn, ttcxn, table_name, pkeys)
        for pkey in pkeys:
            quoted_table = self.quote(table_name)
            sql = f"select pg_get_serial_sequence('{quoted_table}', '{pkey}');"
            seq = ttcxn.cursor().execute(sql).fetchall()[0][0]
            if seq:
                quoted_pkey = self.quote(pkey)
                ttcxn.cursor().execute(f"select setval('{seq}', (select MAX({quoted_pkey}) FROM {quoted_table}));")
                self.logger.debug(f"Primary key has sequence {seq} - resetting its value")
