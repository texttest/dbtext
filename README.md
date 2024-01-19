# dbtext
Utility for storing a database as a directory of plain text files, and reading from those text files.
Currently has implementations for MS SQL server, MySQL, Sqlite3 and MongoDB.
The first 3 of these require "pyodbc" to be installed, and MongoDB requires "pymongo" to be installed.

## installation
```
pip install dbtext pyodbc (for MSSQL, MySQL, Sqlite3)
pip install dbtext pymongo (for MongoDB)
```

## usage

First, dump your test database to this format. For example, with MSSQL:

```python
    from dbtext import MSSQL_DBText
    with pyodbc.connect(connStr) as conn:
        with dbtext.MSSQL_DBText("dump", conn) as testdb: # the name "dump" doesn't matter, just a temporary name
            testdb.write_data("db_tables", use_master_connection=True) # creates a directory called db_tables
    
```
For MongoDB:
```python
    from dbtext import Mongo_DBText

    dbClient = Mongo_DBText()
    dbClient.create(host=connStr) # as in pymongo, "host" can be a full connection string
    dbClient.dump_data_directory("mongodata") # creates a directory called mongodata
```

Then you create tests, probably with TextTest, that use this directory as test data ("copy_test_path")

A test harness script might do something like for MSSQL:

```python
    import dbtext, os
    testdbname = "ttdb_" + str(os.getpid()) # some temporary name not to clash with other tests
    with dbtext.MSSQL_DBText(testdbname) as db: # the name you use here will be used for the directory name in the current working directory
        # You need a script 'create_empty.sql' that sets up the schema but no data
        # db.create will set up the schema and read the test data from a directory here called "db_tables"
        db.create(sqlfile="create_empty.sql")
         
        # Then it should take the testdbname and configure your system to start a server against the new database
        # ...
        do_some_setup() 

        # tell it the test is starting for real now. Only necessary if the database is changed by setup via the system
        db.update_start_rv() 

        # do whatever it is the test does

        db.dumptables("myext", "*") # dump changes in all the tables you're interested in. "myext" is whatever extension you want to use, probably the TextTest one 
```

For MongoDB, two classes are provided, Mongo_DBText and LocalMongo_DBText.
For test usage, you generally want to use LocalMongo_DBText, which works like the MSSQL version above,
i.e. it creates you a new MongoDB server running on any free port locally and populates it with the data in question.
Mongo_DBText is used for connecting to already running instances, for example if you need to start it via Docker.

```python
    import dbtext
    with dbtext.LocalMongo_DBText(data_dirname=testdbname) as db: # the name you use here will be used for the directory name in the current working directory
        db.create()
        if not db.setup_succeeded(): # could not start MongoDB, for example
            return False

        testConnStr = "mongodb://localhost:" + str(self.db.port) # provide to your system in some way

        # do whatever it is the test does
        # ...
        
        db.dump_changes("myext") # dump changes in all the tables you're interested in. "myext" is whatever extension you want to use, probably the TextTest one 
```
