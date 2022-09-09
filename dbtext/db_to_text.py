
import os


def dump_dataframe_as_json(df, tablename, folder="db_tables", prefix=""):
    """Dump a pandas dataframe in json format suitable to use with dbtext"""
    path = os.path.join(folder, f"{prefix}{tablename}.json")
    df.to_json(path, orient="records", indent=2)


def dump_dataframe_as_rowdata(df, tablename, ext="table", prefix=""):
    """Dump a pandas dataframe in dbtext format"""
    with open(f"{prefix}{tablename}.{ext}", "w") as f:
        for i, tup in enumerate(df.itertuples(index=False)):
            print(f"ROW:{i}", file=f)
            for field in tup._fields:
                print(f"    {field}: {getattr(tup, field)}", file=f)
