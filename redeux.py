# -*- coding: utf-8 -*-

# Credits
__author__ =        'George Flanagin'
__copyright__ =     'Copyright 2021 George Flanagin'
__credits__ =       'None. This idea has been around forever.'
__version__ =       '1.1'
__maintainer__ =    'George Flanagin'
__email__ =         'me+redeux@georgeflanagin.com'
__status__ =        'continual development.'
__license__ =       'MIT'

import os
import sys

min_py = (3, 8)

if sys.version_info < min_py:
    print(f"This program requires at least Python {min_py[0]}.{min_py[1]}")
    sys.exit(os.EX_SOFTWARE)

import typing
from   typing import *

import argparse
import collections
import contextlib
from   datetime import datetime
import enum
import fcntl
from   functools import total_ordering
import gc
import hashlib
import math
import pwd
import resource
import shutil
import time
import textwrap
from   urllib.parse import urlparse

#####################################
# From HPCLIB
#####################################

from   dorunrun import dorunrun, ExitCode
import fileutils
import fname
import linuxutils
from   linuxutils import dump_cmdline

import sloppytree
from   sloppytree import SloppyTree

#####################################
# Some Global data structures.      #
#####################################

####
# To look for pseudo duplicates that are actually hard links.
####
by_inode    = collections.defaultdict(list)

####
# To look for files that are the same size
####
by_size     = collections.defaultdict(list)

####
# For files that are the same size, we check the hashes.
####
by_edge_hash = collections.defaultdict(list)
by_hash     = collections.defaultdict(list)

duplicates  = SloppyTree()
hardlinks   = collections.defaultdict(list)

redeux_help = """
    Let's provide more info on a few of the key arguments and the
        display while the program runs.

    .  :: Unless you are running --quiet, the program will display
        a period for every 1000 files that are "stat-ed" when the
        directory is being browsed.

    +  :: Hashing is shown with a + for every 100 files that are 
        hashed. 

    --big-file :: Files larger than this are computationally intensive
        to hash. YMMV, so this value is up to you. Often, if there is
        a difference between two large files with the same size, the 
        differences are in the final bytes or the first few. Before 
        these files are hashed, redeux will check the ends of the file 
        for ordinary differences.

    --exclude :: This parameter can be used multiple times. Remember
        that hidden files will not require an explicit exclusion in 
        most cases. Simple pattern matching is used, so if you put
        in "--exclude A", then any file with a "A" any where in its
        fully qualified name will be excluded. If you type
        "--exclude /private", then any file in any directory that
        begins with "private" will be excluded.

        Given that one may want to run this program as root, redeux
        will always ignore files that are owned by root, as well as
        files in the top level directories like /dev, /proc, /mnt, 
        /sys, /boot, and /var.

    --include-hidden :: This switch is generally off, and hidden files
        will be excluded. They are often part of a git repo, or a part
        of some program's cache. Why bother? 

    --small-file :: Some programs create hundreds or thousands of very
        small files. Many may be short lived duplicates. The default value
        of 4097 bytes means that a file must be at least that large
        to even figure into our calculus.

    --young-file :: The value is in days, so if a long calculation is
        running, then we may want to exclude files that are younger
        than the time it has been running. The files are in use, and
        if they are duplicates, then there is probably a reason.
    
    """

def tprint(s:str) -> None:
    global start_time

    e = round(time.time() - start_time, 3)
    sys.stderr.write(f"{e} : {s}\n")
    sys.stderr.flush()


def redeux_main(pargs:argparse.Namespace) -> int:

    outfile = open(pargs.output, 'w')

    pargs.exclude.extend(('/proc/', '/dev/', '/mnt/', '/sys/', '/boot/', '/var/'))

    ############################################################
    # Use the generator to collect the files so that we do not
    # build a useless list in memory. 
    ############################################################
    sys.stderr.write(f"Looking at files in {pargs.dir}. Each dot is 1000 files.\n")
    try:
        for i, f in enumerate(fileutils.all_files_in(pargs.dir, pargs.include_hidden), start=1):
            if not pargs.quiet and not i % 1000: 
                sys.stderr.write('.')
                sys.stderr.flush()
            if i > pargs.limit: break

            ######################################################
            # 1. Is it something the user wants to exclude?
            # 2. Is it a symlink that we are not following?
            # 3. Is it qualified after stat-ing it?
            ######################################################

            if pargs.exclude and any(_ in f for _ in pargs.exclude): continue 
            if not pargs.follow_links and os.path.islink(f): continue

            f = fname.Fname(f)
            by_inode[f._inode].append(str(f))
            by_size[len(f)].append(str(f))
            
        tprint(f"All {i} files have been stat-ed")

    except KeyboardInterrupt as e:
        pass


    tprint("Looking for pseudo-duplicates.")
    hardlinks = {k:v for k,v in by_inode.items() if len(v) > 1}
    tprint(f"There were {len(hardlinks)} pseudo-duplicates found.")
    
    tprint(f"Filtering size duplicates.")
    size_dups = {k:v for k,v in by_size.items() if len(v) > 1}
    n_potential_duplicates = sum(len(v) for v in size_dups.values())
    tprint(f"{n_potential_duplicates} files to examine in {len(size_dups)} groups.")

    # The next step is to remove any files that are the in the potential 
    # duplicate list that are just links (have the same inode). Note that
    # we don't care about modifying the hardlinks dict because we are
    # removing these files from consideration, anyway.
    for k, v in hardlinks.items():
        firstfile = fname.Fname(v[0])
        size_key = len(firstfile)
        try:
            same_size_files = size_dups[size_key]
            remainder = list(set(same_size_files) - set(v))
            if not len(remainder):
                size_dups.pop(size_key)
            else:
                size_dups[size_key] = remainder
            
        except Exception as e:
            tprint(f"Unknown exception {e}")

    n_potential_duplicates = sum(len(v) for v in size_dups.values())
    tprint(f"{n_potential_duplicates} files left to examine in {len(size_dups)} groups.")
            
        

    # Now we need to hash the files that remain. Edges first.
    return os.EX_OK


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='redeux',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(redeux_help),
        description='redeux: Find probable duplicate files.')

    parser.add_argument('-?', '--explain', action='store_true')

    parser.add_argument('--dir', type=str, 
        default=fileutils.expandall(os.getcwd()),
        help="directory to investigate (if not *this* directory)")

    parser.add_argument('-x', '--exclude', action='append', 
        default=[],
        help="""one or more directories or patterns to ignore.""")

    parser.add_argument('--follow-links', action='store_true',
        help="follow symbolic links -- the default is not to.")

    parser.add_argument('--include-hidden', action='store_true',
        help="search hidden directories as well.")

    parser.add_argument('--limit', type=int, default=sys.maxsize,
        help="Limit the number of files considered for testing purposes.")

    parser.add_argument('--nice', type=int, default=20, choices=range(0, 21),
        help="by default, this program runs /very/ nicely at nice=20")

    parser.add_argument('-o', '--output', type=str, default="duplicatefiles.csv",
        help="Output file with the duplicates named")

    parser.add_argument('--quiet', action='store_true',
        help="eliminates narrative while running except for errors.")

    parser.add_argument('--small-file', type=int, 
        default=resource.getpagesize()+1,
        help=f"files less than this size (default {resource.getpagesize()+1}) are not evaluated.")

    parser.add_argument('--units', type=str, 
        default="X", 
        choices=('B', 'G', 'K', 'M', 'X'),
        help="""file sizes are in bytes by default. Report them in 
K, M, G, or X (auto scale), instead""")

    parser.add_argument('--verbose', action='store_true',
        help="go into way too much detail.")

    parser.add_argument('--version', action='store_true', 
        help='Print the version and exit.')

    pargs = parser.parse_args()
    if pargs.version:
        print(f"Version 1.1")
        sys.exit(os.EX_OK)

    dump_cmdline(pargs, split_it=True)
    try:
        r = input("Does this look right to you? ")
        if not "yes".startswith(r.lower()): sys.exit(os.EX_CONFIG)

    except KeyboardInterrupt as e:
        print("Apparently it does not. Exiting.")
        sys.exit(os.EX_CONFIG)

    start_time = time.time()
    os.nice(pargs.nice)
    sys.exit(redeux_main(pargs))
