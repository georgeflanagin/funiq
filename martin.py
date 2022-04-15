# -*- coding: utf-8 -*-
"""
This is a simple program to find duplicate files.
"""

from    collections import defaultdict
from    functools import partial
import  hashlib
import  os
from    os.path import join, getsize
import  sys

def md5sum(filename:str) -> str:
    """Given a filename, return the MD5 hash """
    
    with open(filename, mode='rb') as f:
        d = hashlib.md5()
        for buf in iter(partial(f.read, 128), b''):
            d.update(buf)
    return d.hexdigest()


def print_duplicates(file_list:list) -> None:
    """Given a list of files, use MD5 to look for duplicates"""
    
    dups = defaultdict(list)
    for file in file_list:
        dups[md5sum(file)].append(file)
    
    for key in dups:
        if len(dups[key]) > 1:
            print("Duplicates: " + ",".join(dups[key]))

            
min_size = 100000
all_files = defaultdict(list)
for root, dirs, files in os.walk('/home/milesdavis'):
    for file in files:
        path = os.path.join(root, file)
        if os.path.isfile(path):
            size = os.path.getsize(path) 
            if size > min_size:
                all_files[size].append(path)

print(f"We looked at {len(all_files)} files.")
for key in all_files:
    if len(all_files[key]) > 1:
        print_duplicates(all_files[key])



