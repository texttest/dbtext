
import os, shutil, filecmp
import json

class IncrementConverter:
    def __init__(self, parse_table_file=None):
        self.parse_table_file = parse_table_file
    
    def convert_to_increment(self, fullDir, origDir):
        shutil.copytree(fullDir, fullDir + "_prereduce")
        self.compare_and_reduce(origDir, fullDir)
        
    def find_matching_row(self, row, newRows, discard = []):
        discardKeySet = set(discard)
        for newRow in newRows:
            unmatched_items = set(row) ^ set(newRow)
            unmatched_keys = set(( k for k, v in unmatched_items ))
            unmatched_keys -= discardKeySet
            if len(unmatched_keys) == 0:
                return newRow

    def get_field_names_to_ignore(self):
        return []
    
    def get_table_names_for_rename_check(self):
        return []
    
    def get_dbdir_comparison(self, origdir, dbdir):
        toCompare = []
        toRemove = []
        for root, _, files in os.walk(dbdir):
            origroot = root.replace(dbdir, origdir)
            for fn in files:
                path = os.path.join(root, fn)
                origpath = os.path.join(origroot, fn)
                if os.path.isfile(origpath):
                    if filecmp.cmp(origpath, path, shallow=False):
                        toRemove.append(path)
                    elif path.endswith(".table"):
                        toCompare.append((origpath, path))
        
        toReduce = []
        renameCheck = []
        for origFile, newFile in toCompare:
            origRows = self.parse_table_file(origFile)
            newRows = self.parse_table_file(newFile)
            unmatched = []
            for row in origRows:
                newRow = self.find_matching_row(row, newRows, self.get_field_names_to_ignore())
                if newRow:
                    newRows.remove(newRow)
                else:
                    unmatched.append(row)
            if len(newRows) == 0:
                toRemove.append(newFile)
            elif len(unmatched) == 0:
                toReduce.append((newFile, newRows))
            elif os.path.basename(newFile).split(".")[0] in self.get_table_names_for_rename_check():
                renameCheck.append((newFile, unmatched, newRows))
                        
        toRename = self.check_for_renames(renameCheck, dbdir, toRemove, toReduce)
        return toRemove, toReduce, toRename
    
    def check_for_renames(self, *args):
        return [] # hook for context-specific logic
    
    def compare_and_reduce(self, origdir, dbdir):
        toRemove, toReduce, toRename = self.get_dbdir_comparison(origdir, dbdir)
        for path in toRemove:
            os.remove(path)
            
        for oldPath, newPath in toRename:
            os.rename(oldPath, newPath)
            
        # clean empty directories
        for root, dirs, files in os.walk(dbdir):
            if len(dirs) == 0 and len(files) == 0:
                os.rmdir(root)

        for fn, contents in toReduce:
            with open(fn, mode='w', errors='replace') as f:
                for rowData in contents:
                    f.write("ROW:+\n")
                    for col, value in rowData:
                        f.write('   ' + col + ": " + value + '\n')

