#!/usr/bin/python

"""
Use with MSSQL server
"""


import os, subprocess, locale
import struct
from .base_odbc import DBText
try:
    import pyodbc
except ModuleNotFoundError:
    # gets imported even for MongoDB, which doesn't need it
    pass                 
                    
class MSSQL_DBText(DBText):
    def handle_datetimeoffset(self, dto_value):
        # ref: https://github.com/mkleehammer/pyodbc/issues/134#issuecomment-281739794
        tup = struct.unpack("<6hI2h", dto_value)  # e.g., (2017, 3, 16, 10, 35, 18, 0, -6, 0)
        tweaked = [tup[i] // 100 if i == 6 else tup[i] for i in range(len(tup))]
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}.{:07d} {:+03d}:{:02d}".format(*tweaked)
    
    def get_create_db_args(self, mdffile=None):
        localdbFolder = os.getenv("TEXTTEST_SANDBOX") if "(localdb)" in self.connectionStringTemplate else None
        if mdffile:
            return " ON (FILENAME = '" + mdffile + "') FOR ATTACH_REBUILD_LOG"
        elif localdbFolder:
            if os.name == "nt":
                localdbFolder = localdbFolder.replace('/','\\')
            tmpDbFileName = os.path.join(localdbFolder, self.database_name + ".mdf")
            return " ON (NAME = '" + self.database_name + "', FILENAME='" + tmpDbFileName + "')"
        else:
            return ""
        
    def extract_data_for_dump(self, ttcxn, *args, **kw):
        ttcxn.add_output_converter(-155, self.handle_datetimeoffset)
        return super().extract_data_for_dump(ttcxn, *args, **kw)
    
    def single(self):
        try:
            self.query("ALTER DATABASE " + self.database_name + " SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        except pyodbc.Error as e:
            print("Unexpected error for alter db " + self.database_name + ":", e)
        
    def multi(self):
        self.query("ALTER DATABASE " + self.database_name + " SET MULTI_USER")
        
    def readrv(self, ttcxn):
        rows = ttcxn.cursor().execute('select master.sys.fn_varbintohexstr(@@DBTS) AS maxrv').fetchall()
        self.startrv = rows[0].maxrv
        
    def convert_from_binary(self, col):
        return "master.sys.fn_varbintohexstr(%s)" % col

    @classmethod
    def get_driver(cls):
        odbc, legacy = [], []
        for driver in pyodbc.drivers():
            if driver.startswith("ODBC Driver"):
                odbc.append(driver)
            elif driver.startswith("SQL Server"):
                legacy.append(driver)

        if odbc:
            return max(odbc)
        elif legacy:
            return max(legacy)
        else:
            raise RuntimeError("No suitable drivers found for SQL Server LocalDB, is it installed?")
    
    @classmethod
    def get_localdb_server(cls):
        proc = subprocess.Popen([ "SqlLocalDB", "info"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate()[0]
        installed = [ str(line.strip(), locale.getpreferredencoding()) for line in out.splitlines() ]
        if cls.enforceVersion is not None:
            candidates = [ cls.enforceVersion ]
        else:
            candidates = [ "MSSQLLocalDB", "v11.0" ]
        for candidate in candidates:
            if candidate in installed:
                return candidate
        
        raise RuntimeError("No recognised default LocalDB instance found, is it installed correctly?")
               
    @classmethod
    def make_connection_string_template(cls):
        driver = cls.get_driver()
        server = cls.get_localdb_server()
        return 'DRIVER={' + driver + '};SERVER=(localdb)\\' + server + ';Integrated Security=true;DATABASE=%s;'
    
    @classmethod
    def set_connection_string_template(cls, server, user, password):
        driver = cls.get_driver()
        cls.connectionStringTemplate = 'DRIVER={' + driver + '};SERVER=' + server + ';UID=' + user + ';PWD=' + password + ';DATABASE=%s;'
        return cls.connectionStringTemplate
    
