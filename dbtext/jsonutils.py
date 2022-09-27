'''
Created on Apr 14, 2022

@author: SEGEBAC1
'''

import json
from datetime import datetime, date

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    else:
        return str(obj)


def dump_json_table(f, collection, **kw):
    f.write(json.dumps(collection, indent=2, default=json_serial, **kw) + "\n")

def dump_json_tables(data, fn, **kw):
    with open(fn, "w") as f:
        for tableName, table in sorted(data.items()):
            f.write(tableName + ": ")
            dump_json_table(f, table, **kw)