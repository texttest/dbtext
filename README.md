# dbtext
Utility for storing a database as a directory of plain text files, and reading from those text files.
Currently works only on MSSQL server (localdb) but much of the code is generic and could be adapted for other databases.

## usage

First, dump your test database to this format:

    with pyodbc.connect(connStr) as conn:
        with dbtext.DBText("dump", conn) as testdb: # the name "dump" doesn't matter, just a temporary name
            testdb.write_data("db_tables", use_master_connection=True) # creates a directory called db_tables
    

Then you create tests, probably with TextTest, that use this directory as test data ("copy_test_path")

A test harness script might do something like:

    import dbtext, os
    testdbname = "ttdb_" + str(os.getpid()) # some temporary name not to clash with other tests
    with dbtext.DBText(testdbname) as db: # the name you use here will be used for the directory name in the current working directory
        # You need a script 'create_empty.sql' that sets up the schema but no data
        # db.create will set up the schema and read the test data from a directory here called "currentdb_tables"
        db.create(sqlfile="create_empty.sql")
         
        # Then it should take the testdbname and configure your system to start a server against the new database
        # ...
        do_some_setup()
        db.update_start_rv() # tell it the test is starting for real now
        # do whatever it is the test does

        db.dumptables("myext", "*") # dump changes in all the tables you're interested in. "myext" is whatever extension you want to use, probably the TextTest one 
