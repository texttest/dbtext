'''
Created on Dec 8, 2021

@author: Geoff Bache
'''

import os, subprocess, json, time
from . import jsonutils, increments, wait
import shutil
import sys
try:
    # comes with pymongo
    import bson
except ModuleNotFoundError:
    pass

        
class MongoTextClient:
    ignore_db_names = [ "admin", "config", "local" ]
    def __init__(self, *args, **kw):
        self.client = self.make_client(*args, **kw)
        
    @classmethod
    def make_client(cls, *args, **kw):
        from pymongo import MongoClient
        return MongoClient(*args, **kw)
        
    def run_admin_command(self, *args):
        self.client.admin.command(*args)
        
    def __getattr__(self, name):
        return getattr(self.client, name)
            
    def dump_data_directory(self, rootDir):
        origDir = rootDir + "_orig"
        if os.path.isdir(rootDir):
            os.rename(rootDir, origDir)
        data = self.parse_mongo()
        for dbName, dbdata in data.items():
            dbdir = os.path.join(rootDir, dbName)
            os.makedirs(dbdir)
            for collName, collection in dbdata.items():
                fn = os.path.join(dbdir, collName + ".json")
                with open(fn, "w") as f:
                    jsonutils.dump_json_table(f, collection)
        increments.IncrementConverter().convert_to_increment(rootDir, origDir)
    
    @classmethod
    def parse_data_directory(cls, rootDir, dbMapping):
        data = {}
        if os.path.isdir(rootDir):
            for dbName in os.listdir(rootDir):
                dbDir = os.path.join(rootDir, dbName)
                if os.path.isdir(dbDir):
                    dbdata = {}
                    for collectionFn in os.listdir(dbDir):
                        if collectionFn.endswith(".json"):
                            collectionPath = os.path.join(rootDir, dbName, collectionFn)
                            docs = json.load(open(collectionPath))
                            if dbMapping:
                                cls.apply_mapping(docs, dbMapping)
                            dbdata[collectionFn[:-5]] = docs
                    if len(dbdata) > 0:
                        data[dbName] = dbdata
        return data
    
    @classmethod
    def apply_mapping(cls, docs, dbMapping):
        ix = 0
        for doc in docs:
            for field, value in doc.items():
                if isinstance(value, str) and value in dbMapping:
                    doc[field] = dbMapping[value][ix]
                    ix += 1
    
    def parse_mongo(self, ignoreDbs=None):
        data = {}
        if ignoreDbs:
            ignore = self.ignore_db_names + [ db.lower() for db in ignoreDbs ]
        else:
            ignore = self.ignore_db_names
        for databaseName in self.client.list_database_names():
            if databaseName.lower() not in ignore:
                database = self.client[databaseName]
                dbdata = {}
                for collectionName in database.list_collection_names():
                    collection = database[collectionName]
                    colldata = [ doc for doc in collection.find({}) ]
                    if len(colldata) > 0:
                        dbdata[collectionName] = colldata
                if len(dbdata) > 0:
                    data[databaseName] = dbdata
        return data
    
    def has_collection(self, collectionName):
        for databaseName in self.client.list_database_names():
            if databaseName.lower() not in self.ignore_db_names:
                coll = self.client[databaseName].get_collection(collectionName)
                if coll and coll.count_documents({}) > 0:
                    return True
        return False
                
    def categorise(self, data1, data2):
        if isinstance(data1, dict):
            created, updated, deleted = {}, {}, {}
            for key, value1 in data1.items():
                value2 = data2.get(key)
                if value2 is None:
                    deleted[key] = value1
                elif value2 != value1:
                    c, u, d = self.categorise(value1, value2)
                    if c:
                        created[key] = c
                    if u:
                        updated[key] = u
                    if d:
                        deleted[key] = d
            for key, value in data2.items():
                if key not in data1:
                    created[key] = value
        elif isinstance(data1, list):
            created, updated, deleted = [], [], []
            ids1 = set([ doc["_id"] for doc in data1 ])
            ids2 = set([ doc["_id"] for doc in data2 ])
            for doc in data1:
                docId = doc["_id"]
                if docId not in ids2:
                    deleted.append(doc)
            for doc in data2:
                docId = doc["_id"]
                if docId in ids1:
                    if doc not in data1:
                        updated.append(doc)
                else:
                    created.append(doc)
        return created, updated, deleted

    def isAutogeneratedId(self, docObjId):
        if isinstance(docObjId, bson.ObjectId):
            return True
        
        if not isinstance(docObjId, str):
            return False
        
        if not docObjId.isdigit():
            return True
        
        # can be a pure integer, just by chance. But should be very large if so
        return int(docObjId) > 1000000

    def swap_out_ids(self, data):
        if len(data) == 0:
            return
        idMap = {}
        for _, database in sorted(data.items()):
            for collName, collection in sorted(database.items()):
                count = 1
                for doc in collection:
                    docObjId = doc.get("_id")
                    if docObjId and self.isAutogeneratedId(docObjId):
                        docId = str(docObjId)
                        newId = idMap.get(docId)
                        if newId is None:
                            newId = collName.upper() + "_ID_" + str(count)
                            idMap[docId] = newId
                            count += 1
                            doc["_id"] = newId
        for _, database in sorted(data.items()):
            for _, collection in sorted(database.items()):
                for doc in collection:
                    for key, value in doc.items():
                        if type(value) == str and value in idMap:
                            doc[key] = idMap.get(value)

    def dump_change_files(self, fn_template, new_data):
        if len(new_data) > 0:
            for databaseName, database in sorted(new_data.items()):
                change_fn = fn_template.format(db=databaseName)
                jsonutils.dump_json_tables(database, change_fn, sort_keys=True)

    def dump_changes(self, cmp_data, ext, ignore_dbs=None):
        new_data = self.parse_mongo(ignore_dbs)
        created, updated, deleted = self.categorise(cmp_data, new_data)
        self.swap_out_ids(created)
        self.dump_change_files("db_{db}_created." + ext, created)
        self.dump_change_files("db_{db}_updated." + ext, updated)
        self.dump_change_files("db_{db}_deleted." + ext, deleted)
        
    def insert_data(self, data):
        for databaseName, db_data in data.items():
            db = self.client.get_database(databaseName)
            for collectionName, docs in db_data.items():
                collection = db.get_collection(collectionName)
                for doc in docs:
                    if "_id" in doc:
                        try:
                            doc["_id"] = bson.ObjectId(doc["_id"])
                        except bson.errors.InvalidId:
                            # IDs are not necessarily object ids, if they aren't just assume they're strings...
                            pass
                collection.insert_many(docs)

class Mongo_DBText:
    def __init__(self, port=None, dbMapping=None, transactions=True, logfile=None, **kw):
        self.port = port
        self.dbdir = os.path.abspath("mongo")
        if not os.path.isdir(self.dbdir):
            os.mkdir(self.dbdir)
        self.start_mongo(transactions, logfile)
        self.data_dir = os.path.abspath("mongodata")
        self.initial_data = MongoTextClient.parse_data_directory(self.data_dir, dbMapping)
        self.text_client = self.make_text_client(**kw)
        if self.wait_for_all_primary():
            self.text_client.insert_data(self.initial_data)
        else:
            print("Database was not primary even after waiting 60 seconds, aborting.", file=sys.stderr)
            self.text_client = None
            
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.drop()
    
    def drop(self):
        pass
    
    def setup_succeeded(self):
        return self.text_client is not None
    
    def start_mongo(self, *args):
        pass
    
    def filter_initial_data(self, ignore_dbs):
        cmp_data = {}
        ignore_dbs_lower = [ db.lower() for db in ignore_dbs ]
        for db, dbdata in self.initial_data.items():
            if db.lower() not in ignore_dbs_lower:
                cmp_data[db] = dbdata
        return cmp_data
    
    def dump_changes(self, ext, ignore_dbs=None):
        cmp_data = self.filter_initial_data(ignore_dbs) if ignore_dbs else self.initial_data
        self.text_client.dump_changes(cmp_data, ext, ignore_dbs)
        
    def dump_data_directory(self, dump_dir=None):
        self.text_client.dump_data_directory(dump_dir or self.data_dir)
    
    def make_text_client(self, *args, **kw):
        return MongoTextClient(*args, **kw)
    
    def wait_for_collections_empty(self, collectionName, maxTime):
        attempts = 10
        sleepLength = float(maxTime) / attempts
        for _ in range(attempts):
            if not self.text_client.has_collection(collectionName):
                return True
            time.sleep(sleepLength)
        return False
    
    def wait_for_all_primary(self):
        for databaseName in self.initial_data:
            db = self.text_client.get_database(databaseName)
            # If you want to see all of the queries, uncomment
            # db.command('profile', 2, filter={'op': 'query'})
            if not self.wait_for_primary(db):
                return False
        return True
            
    def wait_for_primary(self, db):
        for _ in range(600):
            values = db.command("ismaster")
            if values['ismaster']:
                return True
            time.sleep(0.1)
        return False


        
class LocalMongo_DBText(Mongo_DBText):
    mongo_exe = None
    def start_mongo(self, transactions, logfile):
        if not self.set_mongo_exe():
            raise RuntimeError("Could not find MongoDB, have you installed it?")

        # must use replica set to allow transactions. Use unique one based on process id
        self.rsId = None
        cmdArgs = [ self.mongo_exe, "--port", "0", "--dbpath", self.dbdir, "--quiet" ]
        if transactions:
            self.rsId = "rs" + str(os.getpid())
            cmdArgs += [ "--replSet", self.rsId ]
        self.proc = subprocess.Popen(cmdArgs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.pipeThread = wait.PipeReaderThread(self.proc, "Waiting for connections", logfile)
        self.pipeThread.start()

    def parse_port(self, line):
        lineDict = json.loads(line.strip())
        attrDict = lineDict.get("attr", {})
        port = attrDict.get("port")
        if port:
            return port

    def make_text_client(self):
        port_line = self.pipeThread.wait_for_text()
        self.port = self.parse_port(port_line)
        if self.rsId:
            self.enable_transactions(self.port, self.rsId)
        return MongoTextClient("localhost", self.port)
        
    def enable_transactions(self, port, rsId):
        admin_client = MongoTextClient.make_client("mongodb://localhost:" + str(self.port) + "/admin")
        config = {'_id': rsId, 'members': [ {'_id': 0, 'host': 'localhost:' + str(port) } ]}
        admin_client.admin.command("replSetInitiate", config)
        admin_client.close()
        
    def drop(self):
        self.pipeThread.terminate()

    @classmethod
    def set_mongo_exe(cls):
        if cls.mongo_exe is None:
            cls.mongo_exe = cls.find_exe()
        return cls.mongo_exe is not None
        
    @classmethod
    def find_exe(cls):
        if os.name == "nt":
            roots = [ r"C:\Program Files", r"C:\Program Files (x86)" ]
            for root in roots:
                mongodir = os.path.join(root, "MongoDB")
                if os.path.isdir(mongodir):
                    for dirroot, _, files in os.walk(mongodir):
                        if "mongod.exe" in files:
                            return os.path.join(dirroot, "mongod.exe")
        else:
            return shutil.which("mongod")
                                
