# -*- coding: utf-8 -*-

#pragma pylint=off
    
# Credits
__author__ =        'George Flanagin'
__copyright__ =     'Copyright 2017 George Flanagin'
__credits__ =       'None. This idea has been around forever.'
__version__ =       '1.0'
__maintainer__ =    'George Flanagin'
__email__ =         'me+undeux@georgeflanagin.com'
__status__ =        'continual development.'
__license__ =       'MIT'

import typing
from   typing import *

import argparse
import cmd
import collections
import contextlib
from   datetime import datetime
import math
import os
import pprint
import sys
import time

import fname
import gkflib as gkf
from   help import undeux_help
import score
import undeuxlib

def undeux_main() -> int:
    """
    This function loads the arguments, creates the console output,
    and runs the program. IOW, this is it.
    """

    # If someone has supplied no arguments, then show the help.
    if len(sys.argv)==1: return undeux_help()

    parser = argparse.ArgumentParser(description='Find probable duplicate files.')

    parser.add_argument('-?', '--explain', action='store_true')

    parser.add_argument('--dir', action='append', 
        help="directory to investigate (if not your home dir)")

    parser.add_argument('-x', '--exclude', action='append', default=[],
        help="one or more directories to ignore. Defaults to exclude hidden dirs.")

    parser.add_argument('--export', type=str, default='csv',
        choices=('csv', 'pack', 'msgpack', None),
        help="if present, export the results in this format.")

    parser.add_argument('--follow-links', action='store_true',
        help="follow symbolic links -- default is not to.")

    parser.add_argument('--include-hidden', action='store_true',
        help="search hidden directories as well.")

    parser.add_argument('--link-dir', type=str, 
        help="if present, we will create symlinks to the older files in this dir.")

    parser.add_argument('--just-do-it', action='store_true',
        help="run the program using the defaults.")

    parser.add_argument('--nice', type=int, default=20, choices=range(0, 21),
        help="by default, this program runs /very/ nicely at nice=20")

    parser.add_argument('--output', type=str, default='.',
        help="where to write the log file. The default is $PWD.")

    parser.add_argument('--quiet', action='store_true',
        help="eliminates narrative while running.")

    parser.add_argument('--small-file', type=int, default=4096,
        help="files less than this size (default 4096) are not evaluated.")

    parser.add_argument('--verbose', action='store_true',
        help="go into way too much detail.")

    parser.add_argument('--version', action='store_true', 
        help='Print the version and exit.')

    parser.add_argument('--young-file', type=int, default=30,
        help="default is 30 days. You are clearly using it.")

    pargs = parser.parse_args()
    if pargs.explain: return undeux_help()
    gkf.show_args(pargs)

    # We need to fix up a couple of the arguments. Let's convert the
    # youth designation from days to seconds.
    pargs.young_file = pargs.young_file * 60 * 60 * 24
    
    # And let's take care of env vars and other symbols in dir names. Be
    # sure to eliminate duplicates.
    pargs.output = str(fname.Fname(pargs.output))
    if not pargs.dir: pargs.dir = ['.']
    pargs.dir = list(set([ str(fname.Fname(_)) for _ in pargs.dir]))
    pargs.exclude = list(set(pargs.exclude))

    print("arguments after translation:")
    gkf.show_args(pargs)

    if pargs.version:
        print('UnDeux (c) 2019. George Flanagin and Associates.')
        print('  Version of {}'.format(datetime.utcfromtimestamp(os.stat(__file__).st_mtime)))
        return os.EX_OK

    if not pargs.just_do_it:
        r = input('\nDoes this look right to you? ')
        if r.lower() not in "yes": sys.exit(os.EX_OK)

    # OK, we have the green light.
    # Always be nice.
    os.nice(pargs.nice)

    summary = gkf.sloppy(dict.fromkeys([
        'total_files', 'unique_sizes', 
        'hashed_files', 'duplicated_files', 
        'wasted_space', 'biggest_waste'], 0))

    with contextlib.redirect_stdout(sys.stderr):
        # This function takes a while to execute. :-)
        file_info = undeuxlib.scan_sources(pargs)
        summary.total_files = len(file_info)

        hashes = collections.defaultdict(list)
        print("examining {} items".format(summary.total_files))

        # NOTE: if you want to change the way the scoring operates,
        # this is the place to do it. The Scorer.__init__ function
        # takes keyword parameters to alter its operation.
        scorer = score.Scorer()
        now = time.time()

        while True:
            try:
                # This data structure is huge, so let's shrink it as
                # we go.
                k, v = file_info.popitem()
                try:
                    # If there is only one file this size on the system, then
                    # it must be unique.
                    if len(v) == 1: 
                        summary.unique_sizes += 1
                        continue

                    # Things get interesting.
                    if pargs.verbose: 
                        print("checking {} possible duplicates matching {}".format(len(v), k))
                    for t in v:
                        try:
                            f = fname.Fname(t[0])
                            stats = os.stat(str(f))
                            my_stats = [stats.st_size,
                                int(now-stats.st_ctime), 
                                int(now-stats.st_mtime), 
                                int(now-stats.st_atime + 1)]

                            # For convenience, Scorer.__call__ is the appropriate
                            # way to evaluate the score.
                            ugliness = scorer(*my_stats)

                            # Put the ugliness first in the tuple for ease of
                            # sorting by most ugly first.
                            hashes[f.hash].append((ugliness, str(f), my_stats))

                        except FileNotFoundError as e:
                            # It got deleted while we were working. No big deal.
                            pass

                        except Exception as e:
                            # something uncorrectable happened, but let's not bail out.
                            gkf.tombstone(str(e))
                            raise OuterBlock()

                except OuterBlock as e:
                    continue

            except KeyError as e:
                # we are finished.
                break
        
        summary.hashed_files = len(hashes)
        print(80*"=")
        while True:
            try:
                i, file_info = hashes.popitem()
                if len(file_info) == 1: continue

                summary.duplicated_files += 1
                # Sort by ugliness, most ugly first.
                v = sorted(file_info, reverse=True)
                waste = sum(_[2][0] for _ in file_info[1:])
                summary.wasted_space += waste
                if waste > summary.biggest_waste: summary.biggest_waste = waste

                target = v[0][1]
                if pargs.verbose: print("{} -> {}".format(target, i, v))
                for vv in v:
                    print("{}".format(vv))
                print(80*'-')

            except KeyError as e:
                # we are finished.
                print(80*"=")
                break

        print("{}".format(summary))
        

if __name__ == '__main__':
    if not os.getuid(): 
        print('You cannot run this program as root.')
        sys.exit(os.EX_CONFIG)

    sys.exit(undeux_main())
else:
    pass
