#!/usr/bin/python

from .base_odbc import DBText
try:
    import pyodbc
except ModuleNotFoundError:
    # gets imported even for MongoDB, which doesn't need it
    pass
   
    
class MySQL_DBText(DBText):

    def __init__(self, database=None, master_connection=None, ansi_sql_mode=False):
        """
        Use this class when the database you want to set up for testing is MySQL
        :param database: the name of the database to create for testing. You should give a name that is unique to your test case run, for example include the current process id in the name
        :param master_connection: a connection to a database that already exists, that dbtext can use to create new databases.
        By default it will try to connect to a database named 'master'. If one doesn't exist, you could just create an empty one with that name.
        :param ansi_sql_mode: if the MySQL database is configured to have ANSI mode you should set this flag since it affects the syntax of the SQL you use
        (see https://dev.mysql.com/doc/refman/5.7/en/sql-mode.html for more information about modes)
        """
        super().__init__(database, master_connection)
        self.ansi_sql_mode=ansi_sql_mode

    def quote(self, tablespec):
        if self.ansi_sql_mode:
            return super().quote(tablespec)
        else:
            # A default installation of MySQL does not use ANSI mode and uses backticks to escape reserved words in column names etc
            return '`' + tablespec + '`'

    @classmethod
    def get_driver(cls):
        drivers = []
        for driver in pyodbc.drivers():
            if driver.startswith("MySQL"):
                drivers.append(driver)

        if drivers:
            return max(drivers)
        else:
            raise RuntimeError("No suitable drivers found for MySQL, is it installed?")
               
    @classmethod
    def make_connection_string_template(cls):
        driver = cls.get_driver()
        return 'DRIVER={' + driver + '};SERVER=localhost;USER=root;OPTION=3;DATABASE=%s;'

