#!/usr/bin/python

from .base_odbc import DBText
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

