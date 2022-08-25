#!/usr/bin/env python
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
def main(database_type, text_format, updates_only):
    handler = logging.StreamHandler(sys.stdout)
    logging.getLogger().addHandler(handler)
    dbtext_logger = logging.getLogger("ddbtext")
    dbtext_logger.setLevel(logging.DEBUG)
    logger = logging.getLogger("birds_test_rig")
    logger.setLevel(logging.INFO)

    logger.info(f"testing against {database_type} database")

    if database_type == "MSSQL":
        dbtext_engine = dbtext.MSSQL_DBText
    elif database_type == "Sqlite3":
        dbtext_engine = dbtext.Sqlite3_DBText
    else:
        raise Exception(f"db engine {database_type} not yet supported by this test rig")

    testdbname = "db_" + str(os.getpid())  # temporary name not to clash with other tests
    with dbtext_engine(testdbname) as db:
        # Arrange
        db.create(sqlfile="empty_db.sql")

        # Act
        if database_type == "Sqlite3":
            conn_str = f'sqlite:///{testdbname}.db'
            logger.info(f"connecting to database with str {conn_str}")
            engine = sqlalchemy.create_engine(conn_str)
        else:
            connection_string = db.get_connection_string()
            engine = create_sqlalchemy_engine(connection_string)

        load_observations("observations.csv", engine)

        # Assert
        if text_format == "json":
            extension = "json"
        else:
            extension = "dbtext"
        if updates_only:
            db.dumpchanges("{type}.json", exclude="trace*")
        else:
            db.dumptables(extension, "*", exclude="trace*", usemaxcol="")

if __name__ == "__main__":
    main()