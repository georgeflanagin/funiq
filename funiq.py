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
import datetime
import resource
import time
import textwrap

###
# Installed libraries.
###
import pandas

import fname
from   urdecorators import trap

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


converters = {
    'stata':('to_stata', 'dta'),
    'excel':('to_excel','xls'),
    'json':('to_json','json'),
    'csv':('to_csv', 'csv'),
    'feather': ('to_feather','feather'),
    'pickle':('to_pickle', 'pickle')
    }

funiq_help = """
    Let's provide more info on a few of the key arguments and the
        display while the program runs.

    Unless you are running --quiet, the program will display
        a period for every 1000 files that are "stat-ed" when the
        directory is being browsed.

    Hashing is shown with a # for every 1000 files that are 
        hashed. 

    --batch :: The program never prompts the user for any confirmations
        and assumes the user understands the operation.

    --defcon :: by default, this value is 5. Files that are the same
        size are stochastically examined for differences. The level will
        compare the first page (DEFAULT_BUFFER_SIZE bytes) of the files. 
        Level 4 will compare the first 64 pages. Level 3 will subprocess
        $(which diff) on the files, and Level 2 will calculate the SHA1 
        hash of the contents in a subprocess. Level 1 runs the process
        in exclusive access mode as root, if the call to setuid succeeds. 

    --dir :: The top level directory to check if not the $PWD. The idea
        is that every file system has a mount point, and this program
        is only designed to check a single file system. Thus, if a
        file is duplicated on a different file system, it is probably 
        required there.

    --exclude, -x :: This parameter can be used multiple times. Remember
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

    --fmt, --format :: One of csv, pickle, pandas, feather, or stata.
        The default is csv in the form of a fact table. The file will
        be given an extension with the same name unless an extension
        is given in the --output directive.

    --follow-links :: If present, symbolic links will be resolved. The 
        default is to treat links and links because the program does
        not check to see if a file has already been stat-ed.

    --include-hidden :: This switch is generally off, and hidden files
        will be excluded. They are often part of a git repo, or a part
        of some program's cache. Why bother? 

    --limit :: if set, the program will stop scanning after this many files
        are stat-ed. This switch facilitates testing.

    --nice :: defaults to 20, which is roughly the equivalent of Canadian.
        Values range from 0 to 20, where 0 is rude.

    --output, -o :: name of the file to contain the output. If no extension,
        it will be imputed from the --format spec.

    --quiet :: no screen output except for errors.

    --small-file :: Some programs create hundreds or thousands of very
        small files. Many may be short lived duplicates. The default value
        of 4097 bytes means that a file must be at least that large
        to even figure into our calculus.

    --units :: By default, file sizes are reported in the bytes (B). However,
        G, M, K and X are availble, where X is autoscale. 

    --verbose :: Provides more information as the program runs. This 
        switch is superseded by --quiet.

    --version :: The program always prints its version at the beginning
        of (non-quiet) execution, but if this switch is given on the 
        command line, the program prints its version and stops.

    --young-file :: The value is in days, so if a long calculation is
        running, then we may want to exclude files that are younger
        than the time it has been running. The files are in use, and
        if they are duplicates, then there is probably a reason.
    
    """

quiet = False

def all_files_in(s:str, include_hidden:bool=False) -> str:
    """
    A generator to cough up the full file names for every
    file in a directory.
    """
    s = expandall(s)
    for c, d, files in os.walk(s):
        for f in files:
            s = os.path.join(c, f)
            if not include_hidden and '/.' in s: continue
            yield s


byte_symbols = tuple(list('YZEPTGMB'))
byte_values = tuple((2<<10)**i for i in range(8,0,-1))
byte_scaling = dict(zip(byte_symbols, byte_values))

def byte_scale(i:int, key:str='X') -> str:
    """
    i -- an integer to scale.
    key -- a character to use for scaling.
    """
    global byte_scaling

    try:
        if (divisor := byte_scaling[key]) == 1: return i
    except:
        return ""

    try:
        return f"{round(i/divisor, 3)}{key}"
    except:
        for k, v in byte_scaling.items():
            if i > v: return f"{round(i/v, 3)}{k}"
        else:
            # How did this happen?
            return f"Error: byte_scale({i}, {k})"


def dump_cmdline(args:argparse.ArgumentParser, return_it:bool=False, split_it:bool=False) -> str:
    """
    Print the command line arguments as they would have been if the user
    had specified every possible one (including optionals and defaults).
    """
    if not return_it: print("")
    opt_string = ""
    sep='\n' if split_it else ' '
    for _ in sorted(vars(args).items()):
        opt_string += f"{sep}--"+ _[0].replace("_","-") + " " + str(_[1])
    if not return_it: print(opt_string + "\n")
    
    return opt_string if return_it else ""


def expandall(s:str) -> str:
    """
    Expand all the user vars into an absolute path name. If the 
    argument happens to be None, it is OK.
    """
    return s if s is None else os.path.abspath(os.path.expandvars(os.path.expanduser(s)))
    

def tprint(s:str) -> None:
    global start_time
    global quiet
    if quiet: return

    e = round(time.time() - start_time, 3)
    sys.stderr.write(f"{e} : {s}\n")
    sys.stderr.flush()


@trap
def funiq_main(pargs:argparse.Namespace) -> int:

    pargs.exclude.extend(('/proc/', '/dev/', '/mnt/', '/sys/', '/boot/', '/var/'))

    ############################################################
    # Use the generator to collect the files so that we do not
    # build a useless list in memory. 
    ############################################################
    tprint(f"Stating directory entries in {pargs.dir}. Each dot represents 1000 files.\n")
    small_files = 0
    young_files = 0
    excluded_files = 0
    youngest_file = time.time() - pargs.young_file*86400
    try:
        for i, f in enumerate(all_files_in(pargs.dir, pargs.include_hidden), start=1):
            if not pargs.quiet and not i % 1000: 
                sys.stderr.write('.')
                sys.stderr.flush()
            if i > pargs.limit: break

            ######################################################
            # 1. Is it something the user wants to exclude?
            # 2. Is it a symlink that we are not following?
            # 3. Is it qualified after stat-ing it?
            ######################################################
            if pargs.exclude and any(_ in f for _ in pargs.exclude): 
                excluded_files += 1
                continue 
            if not pargs.follow_links and os.path.islink(f): continue

            f = fname.Fname(f)
            if len(f) < pargs.small_file: 
                small_files += 1
                continue

            if pargs.young_file and f.DoB > youngest_file:
                young_files += 1
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


    tprint(f"{excluded_files} files not considered due to explicit exclusion.")
    tprint(f"{small_files} files not considered due to small size.")
    tprint(f"{young_files} files not considered due to recent activity.")
    tprint(f"There were {len(by_inode)} pseudo-duplicates found.")
    tprint(f"Filtering {len(by_size)} file sizes.")

    ###
    # by_size is a dict(int, list(fname)) If the len of the list(fname) is
    #   only 1, then that file is unique.
    ###
    size_dups = {k:v for k,v in by_size.items() if len(v) > 1}
    n_potential_duplicates = sum(len(v) for v in size_dups.values())
    blocks = 64 if pargs.defcon == 4 else 1
    tprint(f"{n_potential_duplicates} files to examine in {len(size_dups)} size groups.")
    tprint(f"Hashing {blocks} blocks of each file. Each # represents 1000 files hashed.")

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
            hash_count += 1
            if not hash_count % 1000: 
                sys.stderr.write('#')
                sys.stderr.flush()
            not pargs.quiet and pargs.verbose and print(f)
            temp[f.edge_hash(blocks)].append(f)
 
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
        
        if pargs.defcon < 4:
            # Note that we don't care about the value of the edge_hash,
            # and that means we can use a view of the values.
            full_hashes = collections.defaultdict(list)
            for v in temp.values():
                for f in v:
                    full_hashes[f.hash].append(f)
        else:
            full_hashes = temp

        ###
        # full_hashes is a dict(hash, list(fname))
        ###
        unique_hashes = {k for k in full_hashes if len(full_hashes[k]) == 1}
        duplicate_hashes = {k:v for k, v in full_hashes.items() if k not in unique_hashes}
        for v in duplicate_hashes.values():
            true_duplicates[len(v[0])] = v

    num_dups = sum(len(v) for v in true_duplicates.values())
    hogs = sorted(true_duplicates.keys(), reverse=True)
    sys.stderr.write("\n")
    tprint(f"Eliminated {edge_detections} files with edge hashing.")
    tprint(f"Found {num_dups} (probable) duplicated files representing {len(hogs)} unique files.")    

    tprint(f"Writing results to {pargs.output}")

    # The for-loop will be empty if there are no hogs, so no need to
    # purposefully ignore this statement.
    true_duplicates = dict(sorted(true_duplicates.items(), reverse=True))

    # Note: the str(f) is for clarity. When passing the Fname object to
    # pandas, pandas cannot makes sense of it, and its default
    # behavior is to invoke the object's str representation, which
    # Python guarantees us is available. 
    row_generator = ((byte_scale(hogsize, pargs.units), 
            str(f), 
            datetime.date.fromtimestamp(int(f.DoB))) 
        for hogsize, files in true_duplicates.items() 
            for f in files)

    df = pandas.DataFrame(row_generator,
        columns=('hogsize', 'hogname', 'date'))
    
    foo, ext = converters[pargs.format]
    outfile_name = fname.Fname(pargs.output)
    text = ( f"{str(outfile_name)}.{ext}" 
        if outfile_name.fqn == outfile_name.all_but_ext else
        outfile_name.fqn )
    
    result = getattr(df, foo)(text, index=False)
        
    # Now we need to hash the files that remain. Edges first.
    return os.EX_OK


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='redeux',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(funiq_help),
        description='funiq: Find probable duplicate files.')

    parser.add_argument('-?', '--explain', action='store_true')

    parser.add_argument('--batch', action='store_true', help='no user prompts.')

    parser.add_argument('--defcon', type=int, choices=(5, 4, 3, 2, 1),
        default=5, help="The defcon level. For more info, use help.")

    parser.add_argument('--dir', type=str, 
        default=expandall(os.getcwd()),
        help="directory to investigate (if not *this* directory)")

    parser.add_argument('-x', '--exclude', action='append', 
        default=[],
        help="""one or more directories or patterns to ignore.""")

    parser.add_argument('--follow-links', action='store_true',
        help="follow symbolic links -- the default is not to.")

    parser.add_argument('-f', '--format', type=str, default='csv',
        choices=('csv', 'pandas', 'pickle', 'stata', 'feather', 'json', 'excel'),
        help="Format for the report on activities.")

    parser.add_argument('--include-hidden', action='store_true',
        help="search hidden directories as well.")

    parser.add_argument('--limit', type=int, default=sys.maxsize,
        help="Limit the number of files considered for testing purposes.")

    parser.add_argument('--nice', type=int, default=20, choices=range(0, 21),
        help="by default, this program runs /very/ nicely at nice=20")

    parser.add_argument('-o', '--output', type=str, default="duplicatefiles.csv",
        help="Output file with the duplicates files' names. Default is <duplicatefiles.csv>")

    parser.add_argument('--quiet', action='store_true',
        help="eliminates narrative while running except for errors.")

    parser.add_argument('--small-file', type=int, 
        default=resource.getpagesize()+1,
        help=f"files less than this size (default {resource.getpagesize()+1}) are not evaluated.")

    parser.add_argument('--units', type=str, 
        default="B", 
        choices=byte_sizes.keys(),
        help="""file sizes are in bytes by default. Report them in 
K, M, G, or X (auto scale), instead""")

    parser.add_argument('--verbose', action='store_true',
        help="go into way too much detail.")

    parser.add_argument('--version', action='store_true', 
        help='Print the version and exit.')

    parser.add_argument('--young-file', type=int, default=0, 
        help="If a file is younger than this value in days, "\
            "it is ignored for the purpose of determining duplicates. "\
            "The default is to consider all files.")

    pargs = parser.parse_args()
    if pargs.version:
        print(f"Version {__version__}")
        sys.exit(os.EX_OK)
    else:
        pargs.version = __version__

    dump_cmdline(pargs, split_it=True)
    quiet = pargs.quiet
    try:
        if not pargs.batch:
            r = input("Does this look right to you? ")
            if not "yes".startswith(r.lower()): sys.exit(os.EX_CONFIG)

    except (KeyboardInterrupt, EOFError) as e:
        print("Apparently it does not. Exiting.")
        sys.exit(os.EX_CONFIG)

    start_time = time.time()
    os.nice(pargs.nice)
    sys.exit(funiq_main(pargs))
