#!/usr/bin/env python
import sqlite3

import sqlalchemy

import dbtext, os, sys
import logging
import click

from birds_insects import load_observations
from birds_insects import create_sqlalchemy_engine

db_names = ["MySql", "MSSQL", "Sqlite3"]

@click.command()
@click.option(
    "--database-type",
    default="MSSQL",
    help=f"the type of database to run with - one of  [{db_names}]",
)
@click.option(
    "--text-format",
    help=f"the format for dbtext files: [json, rowdata]",
    default="rowdata"
)
@click.option(
    "--updates-only",
    is_flag=True,
    default=False,
    help="print updates only - if you don't set this then the whole database is printed"
)
@click.option(
    "--dump-only",
    is_flag=True,
    default=False,
    help="don't initialize the db - only dump changes"
)
@click.option(
    "--write-db",
    default=None,
    help="don't run the birds and insects thing, write the contents of the db given. At present is assumes sqlite3."
)
def main(database_type, text_format, updates_only, dump_only, write_db):
    handler = logging.StreamHandler(sys.stdout)
    logging.getLogger().addHandler(handler)
    dbtext_logger = logging.getLogger("dbtext")
    dbtext_logger.setLevel(logging.INFO)
    logger = logging.getLogger("birds_test_rig")
    logger.setLevel(logging.INFO)

    if write_db:
        with sqlite3.connect(write_db) as conn:
            testdb = dbtext.Sqlite3_DBText("", conn)
            use_json = text_format == "json"
            testdb.write_data(".", use_master_connection=True, json_format=use_json)
        return

    logger.info(f"testing against {database_type} database")

    if database_type == "MSSQL":
        dbtext_engine = dbtext.MSSQL_DBText
    elif database_type == "Sqlite3":
        dbtext_engine = dbtext.Sqlite3_DBText
    else:
        raise Exception(f"db engine {database_type} not yet supported by this test rig")

    testdbname = "db_" + str(os.getpid())  # temporary name not to clash with other tests
    with dbtext_engine(testdbname) as db:
        if dump_only:
            db.dumpchanges("{type}.json", exclude="trace*,sqlite*")
            return

        db.create(sqlfile="empty_db.sql")

        if database_type == "Sqlite3":
            conn_str = f'sqlite:///{testdbname}.db'
            logger.info(f"connecting to database with str {conn_str}")
            engine = sqlalchemy.create_engine(conn_str)
        else:
            connection_string = db.get_connection_string()
            engine = create_sqlalchemy_engine(connection_string)

        load_observations("observations.csv", engine)

        if text_format == "json":
            extension = "json"
        else:
            extension = "dbtext"
        if updates_only:
            db.dumpchanges("{type}.json", exclude="trace*,sqlite*")
        else:
            db.dumptables(extension, "*", exclude="trace*,sqlite*", usemaxcol="")

if __name__ == "__main__":
    main()