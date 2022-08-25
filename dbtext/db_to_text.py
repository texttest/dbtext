

def dump_dataframe(df, tablename, ext="table", prefix=""):
    """Dump a pandas dataframe in dbtext format"""
    with open(f"{prefix}{tablename}.{ext}", "w") as f:
        for i, tup in enumerate(df.itertuples(index=False)):
            print(f"ROW:{i}", file=f)
            for field in tup._fields:
                print(f"    {field}: {getattr(tup, field)}", file=f)
