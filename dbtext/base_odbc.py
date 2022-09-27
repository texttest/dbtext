#!/usr/bin/python

"""
Base class for all dbtext instances that use pyodbc

"""

import os, sys, filecmp
import codecs
import shutil, struct
from string import Template
from glob import glob
from fnmatch import fnmatch
from . import jsonutils, increments
from datetime import datetime, date
import json
import logging
try:
    import pyodbc
except ModuleNotFoundError:
    # gets imported even for MongoDB, which doesn't need it
    pass

class DBText:
    """
    This is an abstract class - use one of the subclasses specific to your database server.
    """
    connectionStringTemplate = None
    enforceVersion = None
    def __init__(self, database=None, master_connection=None):
        self.logger = logging.getLogger("dbtext")
        self.database_name = database
        self.master_connection = master_connection
        self.maxval = {}
        self.iscreated = master_connection is not None
        self.isconnected = False
        self.startrv = ""
        try:
            self.cnxn = self.master_connection or self.make_connection("master")
            self.isconnected = True
        except pyodbc.Error as e:
            self.logger.error(f"Unexpected error opening connection to db {self.database_name}: %s", e)
            raise
        
    def get_create_db_args(self, **kw):
        return ""
        
    def create(self, sqlfile=None, encoding=None, tables_dir=None, **kw):
        self.create_empty_db(**kw)
        self.populate_empty_db(sqlfile, tables_dir, encoding)

    def create_empty_db(self, **kw):
        try:
            attachsql = "CREATE DATABASE " + self.quote(self.database_name) + self.get_create_db_args(**kw) + ";"
            self.query(attachsql)
        except pyodbc.Error as e:
            self.logger.error(f"Unexpected error for create db {self.database_name}:\n{attachsql}\n", e)
            raise

    def populate_empty_db(self, sqlfile, tables_dir=None, encoding=None):
        try:
            self.iscreated = True
            with self.make_connection(self.database_name) as ttcxn:
                if sqlfile:
                    if os.path.isfile(sqlfile):
                        self.read_sql_file(ttcxn, sqlfile, encoding)
                    else:
                        raise ValueError(f"file {sqlfile} not found")

                tables_dir = tables_dir or self.get_tables_dir_name()
                if os.path.isdir(tables_dir):
                    self.read_tables_dir(ttcxn, tables_dir)
                else:
                    self.logger.info(f"No data folder found for database {tables_dir}")

                self.readrv(ttcxn)
        except pyodbc.Error as e:
            self.logger.error(f"Unexpected error for populate empty db {self.database_name}:\n", e)
            raise

    def execute_setup_query(self, ttcxn, currQuery):
        try:
            ttcxn.cursor().execute(currQuery)
        except pyodbc.Error:
            self.logger.error("Failed to execute query:\n" + repr(currQuery))
            raise
            
    def read_sql_file(self, ttcxn, sqlfile, encoding=None):
        currQuery = ''
        inComment = False
        with open(sqlfile, encoding=encoding) as f:
            for line in f:
                line = line.strip()
                if not line or "USE [" in line or line.startswith("--"):
                    continue
                if line.startswith("/*"):
                    inComment = True
                if inComment:
                    if line.endswith("*/"):
                        inComment = False
                    continue
               
                if line in [ "go", "GO" ]:
                    if currQuery:
                        self.execute_setup_query(ttcxn, currQuery)
                        currQuery = ''
                else:
                    if currQuery:
                        currQuery += "\n"
                    currQuery += line
        if currQuery.strip():
            self.execute_setup_query(ttcxn, currQuery)

    def read_tables_dir(self, ttcxn, tables_dir_name):
        failedFiles = []
        for tableFile in glob(os.path.join(tables_dir_name, "*.table")) + glob(os.path.join(tables_dir_name, "*.json")):
            try:
                self.logger.debug(f"Loading data from {tableFile}")
                self.add_table_data(tableFile, ttcxn)
            except pyodbc.IntegrityError as ex:
                fk_constraint_string = "FOREIGN KEY constraint"
                if fk_constraint_string in ex.args[1]:
                    self.logger.debug(f"error when loading data for table {tableFile}: {fk_constraint_string}, will retry this table later")
                    failedFiles.append(tableFile)
                else:
                    raise ex
                
        # Things often fail due to constraints, insert everything else and then try them again
        for tableFile in failedFiles:
            self.logger.debug(f"retrying data insert for table {tableFile}")
            self.add_table_data(tableFile, ttcxn)
              
    @classmethod
    def expand_value(cls, value, *args):
        if "${" in value:
            return os.path.expandvars(value)
        elif "###NOWDATETIME###" in value:
            return value.replace('###NOWDATETIME###', datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
        else: 
            return value

    @classmethod      
    def parse_table_file(cls, fn):
        rows = []
        currRowData = []
        tablesDir = os.path.dirname(fn) 
        with open(fn) as f:
            for line in f:
                if line.startswith("ROW"):
                    if currRowData:
                        rows.append(currRowData)
                    currRowData = []
                elif ":" in line:
                    key, value = [ part.strip() for part in line.split(":", 1) ]
                    value = cls.expand_value(value, tablesDir, currRowData)    
                    currRowData.append((key, value))
        rows.append(currRowData)
        return rows
    
    @classmethod
    def write_table_file(self, rows, fn, asUpdate=False):
        with open(fn, 'w') as f:
            for il, row in enumerate(rows):
                row_id = "+" if asUpdate else str(il)
                header = "ROW:" + row_id + "\n"
                f.write(header)
                for colname, value in row:
                    rowStr = '   ' + colname + ": " + value + "\n"
                    f.write(rowStr)
                    
    @classmethod
    def package_blobs(cls, blobs, *args):
        return blobs[0]
        
    @classmethod                
    def make_blob(cls, blobFiles, blobType):
        blobs = [ open(fn, "rb").read() for fn in blobFiles ]
        blob_bytes = cls.package_blobs(blobs, blobType)
        return pyodbc.Binary(blob_bytes)

    def parse_blob(self, currRowDict, tablesDir):
        blobFileName, blobType = self.get_blob_file_name(currRowDict, self.get_blob_patterns())
        blobPath = os.path.join(tablesDir, blobFileName)
        if not os.path.isfile(blobPath):
            sys.stderr.write("ERROR: Could not find any blob files named " + blobFileName + "!\n")
            return pyodbc.Binary(b"")
        return self.make_blob([ blobPath ], blobType)
                    
    def parse_row_value(self, value, currRowDict, tablesDir):
        if value == "None":
            return None
        elif value == "<blob data>":
            return self.parse_blob(currRowDict, tablesDir)
        elif value.startswith("0x"): # hex string, convert to binary
            return pyodbc.Binary(struct.pack('<Q', int(value, 16)))
        else:
            return value
    
    def parse_table_file_to_rowdicts(self, fn, primaryKeys):
        if fn.endswith(".json"):
            with open(fn, "r") as f:
                json_table_data = json.load(f)
                ids = [self.evaluate_primary_key(primaryKeys, row_data) for row_data in json_table_data]
                if len(primaryKeys) == 1 and () in ids:
                    self.logger.info(f"source data file {fn} did not contain primary keys for every record, adding them")
                    for i, row_data in enumerate(json_table_data):
                        for pk in primaryKeys:
                            if not pk in row_data:
                                row_data[pk] = i
                return json_table_data
        else:
            tablesDir = os.path.dirname(fn)
            rows = []
            for currRowData in self.parse_table_file(fn):
                currRowDict = {}
                for key, value in currRowData:
                    currRowDict[key] = self.parse_row_value(value, currRowDict, tablesDir)
                rows.append(currRowDict)
            return rows
        
    def add_table_data(self, fn, ttcxn):
        table_name = os.path.basename(fn).rsplit(".", 1)[0]
        pkeys = self.get_primary_key_columns(ttcxn, table_name)
        rowData = self.parse_table_file_to_rowdicts(fn, pkeys)
        for currRowDict in rowData:
            self.insert_row(ttcxn, table_name, currRowDict)
          
    def insert_row(self, ttcxn, table_name, data, identity_insert=False):
        if not data:
            return
        
        valueStr = ("?," * len(data))[:-1]
        keys = ", ".join([ self.quote(k) for k in data.keys() ])
        quoted_table = self.quote(table_name)
        sql = f"INSERT INTO {quoted_table} ({keys}) VALUES ({valueStr})"
        if identity_insert:
            sql = "SET IDENTITY_INSERT " + quoted_table + " ON; " + sql + "; SET IDENTITY_INSERT " + quoted_table + " OFF"  
        self.insert_row_data(ttcxn, sql, data, table_name)

    def insert_row_data(self, ttcxn, sql, data, table_name):
        try:
            ttcxn.cursor().execute(sql, *list(data.values()))
        except pyodbc.DatabaseError as e:
            if "Cannot insert explicit value for identity column" in str(e):
                self.logger.debug("Error when inserting data: 'Cannot insert explicit value for identity column'. "
                                  "Will retry with IDENTITY_INSERT")
                return self.insert_row(ttcxn, table_name, data, identity_insert=True)
            elif "conflicted with the FOREIGN KEY constraint" in str(e):
                raise
            else:
                from pprint import pformat
                self.logger.error("Failed to insert data into " + table_name + ":\n" + pformat(data) + "\n")
                raise

    def update_start_rv(self):
        try:
            with self.make_connection(self.database_name) as ttcxn:
                self.readrv(ttcxn)
        except pyodbc.Error as e:
            self.logger.error("Unexpected error for update rv " + self.database_name + ":", e)
            pass
    
    def cursor(self):
        return self.cnxn.cursor()

    def query(self, s):
        return self.cursor().execute(s)

    def single(self):
        pass # no generic way to do this in sql

    def multi(self):
        pass # no generic way to do this in sql
    
    def query_single(self, q):
        try:
            self.single()
        except pyodbc.Error:
            self.logger.warning("Failed to go into single user mode.")
        try:
            self.query(q)
        finally:
            self.multi()
            
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.drop()

    def drop(self):
        if self.iscreated:
            self.single()
            try:
                self.query("DROP DATABASE " + self.database_name + ";")
                self.iscreated = False
            except pyodbc.Error as e:
                self.logger.warning("Unexpected error for drop db " + self.database_name + ":", e)
               
    def get_connection_string(self, driver=True):
        connstr = self.connectionStringTemplate % self.database_name
        if not driver:
            return connstr.split(";", 1)[-1]
        return connstr
                
    @classmethod
    def make_connection(cls, dbname):
        if cls.connectionStringTemplate is None:
            cls.connectionStringTemplate = cls.make_connection_string_template()
        connstr = cls.connectionStringTemplate % dbname
        return pyodbc.connect(connstr, autocommit=True)
            
    def readrv(self, ttcxn):
        pass # Really an MSSQL concept
        
    def readmax(self):
        if 'TEXTTEST_DUMPTABLES' not in os.environ:
            return
   
        dumpnames = os.environ['TEXTTEST_DUMPTABLES'].split(',')
    
        ttcnxn = self.make_connection(self.database_name)
        for descname in dumpnames:
            descparts = descname.split(':')
            tabname = descparts[0]
            maxcolname = descparts[1]
            notabmax = descparts[2]
            try:
                rows = ttcnxn.cursor().execute('select MAX(' + maxcolname + ') AS maxval FROM ' + tabname).fetchall()
                self.maxval[tabname] = rows[0].maxval
            except:
                self.maxval[tabname] = notabmax
        ttcnxn.close()
    
    def append_to_sql_query(self, column_tuple):
        column_name, column_type = column_tuple
        quoted_column_name = self.quote(str(column_name))
        if column_type in [ "binary", "timestamp" ]:
            return "master.sys.fn_varbintohexstr(%s)" % quoted_column_name
        else:
            return quoted_column_name

    def get_row_data(self, row, column_names, col_name):
        for i, (name, _) in enumerate(column_names):
            if col_name == name:
                return str(row[i]).strip()

    def extract_blobs(self, column_value):
        return [ column_value ]

    def get_row_data_based_on_type(self, column_name, column_type, column_value):
        blobs = []
        try:
            if column_type in [ "image", "varbinary" ] and column_value is not None:
                try:
                    blobs = self.extract_blobs(column_value)
                    column_value_str = "<blob data>"
                except:
                    column_value_str = column_value
            elif column_type == "datetime" and column_value is not None:
                column_value_str = column_value.strftime("%Y-%m-%d %H:%M:%S")
            else:
                column_value_str = str(column_value)
        finally: 
            return "%s: %s" % (column_name, column_value_str), blobs
        
    def parse_row_data_based_on_type(self, column_type, column_value):
        if column_type.startswith("datetime"):
            return datetime.fromisoformat(column_value)
        else:
            return column_value

    def getColumnSortKey(self, coldata):
        # Column ordering can vary a lot, depending on how the db was created. We always show the columns in a standard order
        # The IDs come at the top, with other stuff sorted alphabetically
        name = coldata[0]
        if name.endswith("_id") or name == "id":
            return "000" + name
        elif name.endswith("_image"):
            return "zzz" + name
        else:
            return name
        
    def get_tables_dir_name(self, json_format=False):
        prefix = self.database_name.split("db_")[0]
        if json_format:
            return prefix
        postfix = "db_tables"
        if prefix in [ "tt", "database" ]:
            return postfix
        else:
            return prefix + postfix
        
    def get_blob_patterns(self):
        return []
        
    def make_empty_tables_dir(self, writeDir, json_format=False):
        localName = self.get_tables_dir_name(json_format)
        dirName = os.path.join(writeDir, localName)
        if os.path.isdir(dirName):
            shutil.rmtree(dirName)
        dirsToMake = set()
        blob_patterns = []
        for blob_pattern_local in self.get_blob_patterns():
            pattern = os.path.normpath(os.path.join(dirName, blob_pattern_local))
            blob_patterns.append(pattern)
            dirsToMake.add(os.path.dirname(pattern))
            
        if len(dirsToMake) == 0:
            dirsToMake.add(dirName)
        for d in dirsToMake:
            os.makedirs(d)
        ext = "json" if json_format else "table"
        table_file_pattern = os.path.join(dirName, "${table_name}." + ext)
        return table_file_pattern, blob_patterns
        
    def write_data_subset(self, writeDir, subset_data):
        table_file_pattern, blob_patterns = self.make_empty_tables_dir(writeDir)
        table_data = {}
        with self.make_connection(self.database_name) as ttcxn:
            for tablespec, constraint in subset_data:
                self.logger.info("Getting data for table(s)", repr(tablespec), ",", repr(constraint))
                rows, colnames = self.extract_data_for_dump(ttcxn, tablespec, constraint)
                if len(rows) > 0:
                    self.store_table_data(table_data, tablespec, rows, colnames)
        for tablename, (rows, colnames) in table_data.items():
            self.write_dump_data(rows, colnames, tablename, table_file_pattern, blob_patterns)
            
    def store_table_data(self, table_data, tablespec, rows, colnames):
        if "," not in tablespec:
            table_data[tablespec] = list(map(tuple, rows)), colnames 
            return
                
        for tablename in tablespec.split(","):
            tablecolnames = []
            tablecolindices = []
            for ix, (colname, coltype) in enumerate(colnames):            
                currtable, colname = colname.split(".", 1)
                if currtable == tablename:
                    tablecolnames.append((colname, coltype))
                    tablecolindices.append(ix)
            if tablename in table_data:
                tablerows, _ = table_data.get(tablename)
            else:
                tablerows = []
                table_data[tablename] = tablerows, tablecolnames
            firstcol = min(tablecolindices)
            lastcol = max(tablecolindices)
            for row in rows:
                newRow = row[firstcol:lastcol + 1]
                if newRow not in tablerows:
                    tablerows.append(newRow)
                    
    def write_all_tables(self, table_file_pattern, blob_pattern, ttcxn, exclude=""):
        for tablename in self.expand_table_names(ttcxn, "*", exclude):
            self.logger.debug("Making file for table %s", repr(tablename))
            self.dumptable(ttcxn, tablename, "", table_file_pattern, blob_pattern)

    def write_data(self, writeDir, use_master_connection=False, json_format=False, **kw):
        table_file_pattern, blob_pattern = self.make_empty_tables_dir(writeDir, json_format)
        if use_master_connection:
            self.write_all_tables(table_file_pattern, blob_pattern, self.master_connection, **kw)
        else:
            with self.make_connection(self.database_name) as ttcxn:
                self.write_all_tables(table_file_pattern, blob_pattern, ttcxn, **kw)

    def get_table_names(self, ttcxn):
        cursor = ttcxn.cursor()
        return [ row.table_name for row in cursor.tables(tableType="TABLE") ]
    
    def in_exclude_patterns(self, tn, patterns):
        return any((fnmatch(tn, pattern) for pattern in patterns))

    def expand_table_names(self, ttcxn, table_str, exclude):
        tables = []
        exclude_names = exclude.split(',')
        for pattern in table_str.split(','):
            if "*" in pattern:
                for tn in self.get_table_names(ttcxn):
                    if fnmatch(tn, pattern):
                        tables.append(tn)
            else:
                tables.append(pattern)
        if "*" in exclude:
            return [t for t in tables if not self.in_exclude_patterns(t, exclude_names) ]
        else:
            return [t for t in tables if t not in exclude_names]

    def get_blob_patterns_for_dump(self, sut_ext):
        return []

    def dumptables(self, sut_ext, table_str, usemaxcol='rv', exclude="", dumpwholenamestr="", dumpableBlobs=True):
        if not self.iscreated:
            self.logger.info(f"unable to dump tables for {self.database_name}, it is not created yet.")
            return
        dumpwholenames = dumpwholenamestr.split(',')
        with self.make_connection(self.database_name) as ttcxn:
            for descname in self.expand_table_names(ttcxn, table_str, exclude):
                descparts = descname.split(':')
                tablename = descparts[0]
                table_fn_pattern = 'db_${table_name}.' + sut_ext
                maxval = self.startrv
                if tablename in self.maxval:
                    maxval = "'" + self.maxval[tablename] + "'"
                    usemaxcol = descparts[1]
                dumpwhole = tablename in dumpwholenames
                constraint = 'WHERE ' + usemaxcol + ' > ' + maxval if usemaxcol and not dumpwhole else ""
                blob_patterns = self.get_blob_patterns_for_dump(sut_ext)
                self.dumptable(ttcxn, tablename, constraint, table_fn_pattern, blob_patterns, dumpableBlobs)
                
    def get_primary_key_columns(self, ttcxn, tableName):
        # Sqlite3 cursor doesn't have 'primaryKeys' attribute
        if hasattr(ttcxn.cursor(), "primaryKeys"):
            return tuple([ info[3] for info in ttcxn.cursor().primaryKeys(tableName) ])
        return ()
        
    def evaluate_primary_key(self, pkeys, row_data):
        return tuple(row_data[key] for key in pkeys if key in row_data)

    def categorise(self, data1, data2, pkeys):
        created, updated, deleted = [], [], []
        
        ids1 = set([ self.evaluate_primary_key(pkeys, row_data) for row_data in data1 ])
        ids2 = set([ self.evaluate_primary_key(pkeys, row_data) for row_data in data2 ])
        for row in data1:
            val = self.evaluate_primary_key(pkeys, row)
            if val not in ids2:
                deleted.append(row)
        for row in data2:
            val = self.evaluate_primary_key(pkeys, row)
            if val in ids1:
                if row not in data1:
                    updated.append(row)
            else:
                created.append(row)
        return created, updated, deleted
    
    def dump_change_file(self, fn_template, change_type, new_data):
        if len(new_data) > 0:
            fn = fn_template.format(type=change_type)
            jsonutils.dump_json_tables(new_data, fn, sort_keys=True)

    def convert_to_row_dicts(self, rows, colinfo):
        table_data = []
        colnames = [col[0] for col in colinfo]
        for row in rows:
            row_data = {}
            for colname, value in zip(colnames, row):
                valueToUse = value.isoformat() if isinstance(value, (datetime, date)) else value
                row_data[colname] = valueToUse
            table_data.append(row_data)
        
        return table_data

    def dumpchanges(self, table_fn_pattern, tables_dir=None, exclude=""):
        if not self.iscreated:
            self.logger.info(f"unable to dump tables for {self.database_name}, it is not created yet.")
            return
        tables_dir = tables_dir or self.get_tables_dir_name()
        self.logger.info(f"will dump changes compared with tables_dir {tables_dir}")
        created, updated, deleted = {}, {}, {}
        with self.make_connection(self.database_name) as ttcxn:
            for tableName in self.expand_table_names(ttcxn, "*", exclude):
                self.logger.debug(f"examining changes in table {tableName}")
                rows, colinfo = self.extract_data_for_dump(ttcxn, tableName, "")
                tableFile = os.path.join(tables_dir, tableName + ".json") # TODO: make this also work with rowdata in other format
                pkeys = self.get_primary_key_columns(ttcxn, tableName)
                initial_table_data = self.parse_table_file_to_rowdicts(tableFile, pkeys) if os.path.isfile(tableFile) else []
                final_table_data = self.convert_to_row_dicts(rows, colinfo)
                c, u, d = self.categorise(initial_table_data, final_table_data, pkeys)
                if c:
                    created[tableName] = c
                if u:
                    updated[tableName] = u
                if d:
                    deleted[tableName] = d
        self.dump_change_file(table_fn_pattern, "created", created)
        self.dump_change_file(table_fn_pattern, "updated", updated)
        self.dump_change_file(table_fn_pattern, "deleted", deleted)        
        
    def get_column_names_for_spec(self, ttcxn, tablespec):
        if "," in tablespec:
            colnames = []
            table_names = tablespec.split(",")
            timestamp_col = None
            for table_name in table_names:
                table_col_names, table_timestamp_col = self.get_column_names(ttcxn, table_name)
                for colname, coltype in table_col_names:
                    colnames.append((table_name + "." + colname, coltype))
                if timestamp_col is None and table_timestamp_col is not None:
                    timestamp_col = table_name + "." + table_timestamp_col
            return colnames, timestamp_col
        else:
            return self.get_column_names(ttcxn, tablespec)
        
    def get_column_index(self, ttcxn, tablename, colname):
        cols = ttcxn.cursor().columns(table=tablename)
        for i, col in enumerate(cols):
            if col.column_name == colname:
                return i
    
    def get_column_names(self, ttcxn, tablename):
        cols = self.query_for_columns(ttcxn, tablename)
        colnames = []
        timestampcol = None 
        include_timestamp_var = os.getenv("DB_TABLE_DUMP_INCLUDE_TIMESTAMP")
        include_timestamp_tables = []
        if include_timestamp_var:
            include_timestamp_tables = include_timestamp_var.split(',')
        for col in cols:
            if col.type_name == "timestamp":
                timestampcol = col.column_name
                if tablename in include_timestamp_tables:
                    colnames.append((col.column_name, col.type_name))
            if col.type_name != "timestamp":
                colnames.append((col.column_name, col.type_name))
        
        colnames.sort(key=self.getColumnSortKey)
        return colnames, timestampcol

    def query_for_columns(self, ttcxn, tablename):
        return ttcxn.cursor().columns(table=tablename)

    def quote(self, tablespec):
        return '"' + tablespec + '"'
     
    def extract_data_for_dump(self, ttcxn, tablespec, constraint=""):
        colnames, usemaxcol = self.get_column_names_for_spec(ttcxn, tablespec)
        if len(colnames) == 0:
            return [], []
        select_values = [ self.append_to_sql_query(col) for col in colnames ]
        sqltext = 'SELECT '+ ",".join(select_values) + ' from ' + self.quote(tablespec) + ' ' + constraint
        if usemaxcol:
            sqltext += ' ORDER BY ' + usemaxcol
        try:
            rows = ttcxn.cursor().execute(sqltext).fetchall()
        except pyodbc.DatabaseError as e:
            if "Invalid column name 'rv'" in str(e):
                # Table has no rv, dump the constraint and assume the whole table is relevant
                return self.extract_data_for_dump(ttcxn, tablespec)
            else:
                sys.stderr.write(f"ERROR: could not write table(s) {tablespec} due to problems with query:\n{sqltext}\n")
                sys.stderr.write(str(e) + "\n")
                return [], colnames
        
        return rows, colnames
     
    def dumptable(self, ttcxn, tablename, constraint, table_fn_pattern, blob_pattern, dumpableBlobs=True):
        rows, colnames = self.extract_data_for_dump(ttcxn, tablename, constraint) 
        if len(rows) > 0:
            self.write_dump_data(rows, colnames, tablename, table_fn_pattern, blob_pattern, dumpableBlobs)
        
    def write_json_dump(self, rows, colinfo, fileName):
        table_data = self.convert_to_row_dicts(rows, colinfo)
        with open(fileName, "w") as f:
            jsonutils.dump_json_table(f, table_data)
        
    def write_dump_data(self, rows, colnames, tablename, table_fn_pattern, blob_patterns, dumpableBlobs=True):
        fileName = Template(table_fn_pattern).substitute(table_name=tablename)
        if fileName.endswith(".json"):
            self.write_json_dump(rows, colnames, fileName)
        else:
            self.write_tableformat_dump(rows, colnames, fileName, blob_patterns, dumpableBlobs)
            
    def write_tableformat_dump(self, rows, colnames, fileName, blob_patterns, dumpableBlobs):
        with codecs.open(fileName, mode='a', encoding='cp1252', errors='replace') as f:
            # Note "codecs.open" implicitly opens files in binary mode! Hence the normal handling of "\n" is disabled
            # Use os.linesep instead or we get unix line endings...
            for il, row in enumerate(rows):
                header = "ROW:%s" % str(il) + os.linesep
                f.write(header)
                blobs = []
                for ci, (colname, coltype) in enumerate(colnames):
                    fdata, currBlobs = self.get_row_data_based_on_type(colname, coltype, row[ci])
                    value = '   %s' % fdata + os.linesep
                    f.write(value)
                    blobs += currBlobs
                if dumpableBlobs and blobs:
                    self.dumpblobs(blobs, blob_patterns, row, colnames)
                    
    def get_blob_file_name(self, fileNameData, blob_patterns):
        for blob_pattern in blob_patterns:
            fn = Template(blob_pattern).safe_substitute(fileNameData)
            if "$" not in fn:
                return fn, os.path.dirname(blob_pattern)
            
        sys.stderr.write("Failed to find blob given patterns " + repr(blob_patterns) + " and " + repr(fileNameData) + "\n")
        return None, None

    def dumpblobs(self, blobs, blob_patterns, row, column_names):
        class FileNameData:
            def __getitem__(innerself, key): # @NoSelf
                return self.get_row_data(row, column_names, key)
            
            def __contains__(innerself, key): # @NoSelf
                return self.get_row_data(row, column_names, key) is not None
            
        fileNameData = FileNameData()
        for b in blobs:
            blobFileName, _ = self.get_blob_file_name(fileNameData, blob_patterns)
            if blobFileName:
                with open(blobFileName, "wb") as f:
                    f.write(b)
                    
    def write_data_increment(self, writeDir):
        localName = self.get_tables_dir_name()
        fullDir = os.path.join(writeDir, localName)
        origDir = fullDir + "_orig"
        if os.path.isdir(fullDir):
            shutil.move(fullDir, origDir)
        self.write_data(writeDir) # should write to "fullDir"
        converter = self.get_increment_converter()
        converter.convert_to_increment(fullDir, origDir)
        
    def get_increment_converter(self):
        return increments.IncrementConverter(self.parse_table_file)
        
