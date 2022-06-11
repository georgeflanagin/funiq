# -*- coding: utf-8 -*-

# Credits
__author__ =        'George Flanagin'
__copyright__ =     'Copyright 2021 George Flanagin'
__credits__ =       'None. This idea has been around forever.'
__version__ =       '2.0'
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
import resource
import time
import textwrap

#####################################
# From HPCLIB
#####################################

import fileutils
import fname
import linuxutils
from   linuxutils import dump_cmdline

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


def funiq_main(pargs:argparse.Namespace) -> int:

    outfile = open(pargs.output, 'w')

    pargs.exclude.extend(('/proc/', '/dev/', '/mnt/', '/sys/', '/boot/', '/var/'))

    ############################################################
    # Use the generator to collect the files so that we do not
    # build a useless list in memory. 
    ############################################################
    sys.stderr.write(f"Looking at files in {pargs.dir}. Each dot is 1000 files.\n")
    small_files = 0
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
            if len(f) < pargs.small_file: 
                small_files += 1
                continue
            if f._nlink > 1: 
                by_inode[f._inode].append(f)
            else:
                by_size[len(f)].append(f)
            
        sys.stderr.write('\n')
        sys.stderr.flush()
        tprint(f"All {i} files have been stat-ed")

    except KeyboardInterrupt as e:
        pass


    tprint(f"{small_files} ignored due to small size")
    tprint(f"There were {len(by_inode)} pseudo-duplicates found.")
    tprint(f"Filtering files by size.")

    ###
    # by_size is a dict(int, list(fname)) If the len of the list(fname) is
    #   only 1, then that file is unique.
    ###
    size_dups = {k:v for k,v in by_size.items() if len(v) > 1}
    n_potential_duplicates = sum(len(v) for v in size_dups.values())
    tprint(f"{n_potential_duplicates} files to examine in {len(size_dups)} groups.")
    tprint("Each # represents 1000 files hashed.")

    # No need to the look through the whole dict at once, the 
    # potential duplicates are all associated with the same 
    # size_dups key.
    true_duplicates = collections.defaultdict()
    edge_detections = 0
    
    ###
    # size_dups is a dict(int, list(fname))
    ###
    hash_count = 0
    for _, candidates in size_dups.items():
        temp = collections.defaultdict(list)

        # Let's build an table of the hashes of the edges of 
        # the file to start. If the edges differ, we will not
        # need to hash the whole file. Put the whole Fname obj
        # as the value so that we can invoke the full hash
        # if we need to in the next step.
        for f in candidates:
            temp[f._edge_hash].append(f)
 
        ###
        # temp is a dict(hash, list(fname))
        ###
        unique_hashes = {k for k in temp if len(temp[k]) == 1}
        edge_detections += len(unique_hashes)

        # Shrink temp a little, we hope. We are keeping the ones
        # that had the same edge hash.

        ###
        # temp is a dict(hash, list(fname)) where the edge_hash was identical.
        ###
        temp = {k:v for k, v in temp.items() if k not in unique_hashes}
        
        # Note that we don't care about the value of the edge_hash,
        # and that means we can use a view of the values.
        full_hashes = collections.defaultdict(list)
        for v in temp.values():
            for f in v:
                hash_count += 1
                if not hash_count % 1000: 
                    sys.stderr.write('#')
                    sys.stderr.flush()
                full_hashes[f.hash].append(f)

        ###
        # full_hashes is a dict(hash, list(fname))
        ###
        unique_hashes = {k for k in full_hashes if len(full_hashes[k]) == 1}
        duplicate_hashes = {k:v for k, v in full_hashes.items() if k not in unique_hashes}
        for v in duplicate_hashes.values():
            true_duplicates[len(v[0])] = v

    num_dups = sum(len(v) for v in true_duplicates.values())
    hogs = sorted(true_duplicates.keys(), reverse=True)
    print("\n")
    tprint(f"Eliminated {edge_detections} files with edge hashing.")
    tprint(f"Found {num_dups} duplicated files representing {len(hogs)} unique files.")    

    tprint(f"Writing results to {pargs.output}")
    with open(pargs.output, 'w') as outfile:
        for hog in hogs:
            names = tuple(_.fqn for _ in true_duplicates[hog])
            outfile.write(f"{hog}:{names}\n")

    # Now we need to hash the files that remain. Edges first.
    return os.EX_OK


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='redeux',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(redeux_help),
        description='funiq: Find probable duplicate files.')

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

    parser.add_argument('--batch', action='store_true', help='no user prompts.')

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
        print(f"Version {__version__}")
        sys.exit(os.EX_OK)
    else:
        pargs.version = __version__

    dump_cmdline(pargs, split_it=True)
    try:
        if not pargs.batch:
            r = input("Does this look right to you? ")
            if not "yes".startswith(r.lower()): sys.exit(os.EX_CONFIG)

    except KeyboardInterrupt as e:
        print("Apparently it does not. Exiting.")
        sys.exit(os.EX_CONFIG)

    start_time = time.time()
    os.nice(pargs.nice)
    sys.exit(funiq_main(pargs))
