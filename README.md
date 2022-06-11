funiq
=======================================================

# Table of contents

1. General
2. Options
3. Methods


# General

Unless you are running --quiet, the program will display
    a period for every 1000 files that are "stat-ed" when the
    directory is being browsed.

Hashing is shown with a # for every 1000 files that are
    hashed.

# Options

Let's provide more info on a few of the key arguments and the
    display while the program runs.

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
    begins with "private" will be excluded. Files in the top level 
    directories like /dev, /proc, /mnt, /sys, /boot, and /var are
    ignored by default.

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

# Method


