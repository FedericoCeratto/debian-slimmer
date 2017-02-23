#!/usr/bin/env python3
#
# Package disk usage estimation
#
# Copyright 2017 Federico Ceratto <federico.ceratto@gmail.com>
# Released under GPLv3 License, see LICENSE file
#

from argparse import ArgumentParser
import os.path
import subprocess

import apt.cache

# APT is using decimal multiples
MB = 1000 * 1000.0

DU_BIN_PATH = '/usr/bin/du'


class Pkg:
    def __init__(self, name, size):
        self.name = name
        self.size = size
        self.dep_children = set()
        self.dep_parents = set()

    def __repr__(self):
        return "<Pkg %s %d %d>" % (self.name, len(self.dep_parents),
                                   len(self.dep_children))


def list_installed_packages():
    cache = apt.cache.Cache()
    for p in cache:
        if p.is_installed:
            yield p.name, p


def nprint(depth, msg):
    print("  " * depth + msg)


def _recurse_reassign_blame(current, pkgs_by_name, debug, depth=0):
    """Recursively reassign blame
    """
    MAX_DEPTH = 10
    if debug:
        nprint(depth, "%s" % current)
    if current.size is None:
        return  # already visited

    for d_name in current.dep_children:
        if depth == MAX_DEPTH:
            if debug:
                nprint(depth, "  skip dep %s" % d_name)
            # break dependency loops
            break

        d = pkgs_by_name[d_name]
        _recurse_reassign_blame(d, pkgs_by_name, debug, depth+1)

    if current.size is None:
        # This is reached when the current package is in a dependency loop,
        # the maximum depth has been already reached and we are going back
        # in the recursion stack
        return

    if current.dep_parents:
        # There are parent dependencies: blame them equally for disk usage
        np = len(current.dep_parents)
        blame_up = current.size / np
        current.size = None
        if debug:
            nprint(depth, "  uploading blame to %d parents" % (np))
        for parent_name in current.dep_parents:
            parent = pkgs_by_name[parent_name]
            # While breaking out of dependency loops we'll run into parents
            # with size already set to None. Just skip them and ignore the
            # blame value with negligible loss in accuracy.
            if parent.size is not None:
                parent.size += blame_up


def reassign_blame(root_packages, pkgs_by_name, debug):
    """Blame disk space usage from dependencies to their parents
    """
    for pkg in root_packages:
        _recurse_reassign_blame(pkg, pkgs_by_name, debug)


def print_blame_tree(pkg_name, pkgs_by_name, nesting=1):
    """Print dependency tree for a package
    """
    nprint(nesting, pkg_name)
    if nesting < 2:
        for c in pkgs_by_name[pkg_name].dep_children:
            print_blame_tree(c, pkgs_by_name, nesting+1)


def pick_root_packages(pkgs_by_name):
    """Identify packages with no parent deps
    """
    return [p for p in pkgs_by_name.values()
            if len(p.dep_parents) == 0]


def print_summary(root_packages, num_packages_max):
    """Print package disk usage summary
    """
    for p in root_packages[:num_packages_max]:
        print("%-35s  %5.1f MB" % (p.name, p.size / MB))
        # print_blame_tree(pkg_name, pkgs_by_name)


def recursive_disk_usage(dirname):
    # UNUSED
    size = 0
    try:
        for item in os.scandir(dirname):
            if item.is_file():
                size += item.stat().st_size
            elif item.is_dir():
                size += recursive_disk_usage(item.path)
            else:
                print(item)
    except Exception:  # FileNotFoundError:
        pass

    return size


def disk_usage(path):
    """Measure disk usage using du
    """
    if not os.path.isdir(path):
        return 0
    cmd = '%s -bs %s' % (DU_BIN_PATH, path)
    ec, output = subprocess.getstatusoutput(cmd)
    if ec == 0:
        size = output.split(None, 1)[0]
        return int(size)

    print("Error running %s\n--output--\n%s\n--end--" % (cmd, output))
    return 0


def explore_var(p):
    """Explore /var/{lib|cache|log}
    """
    size = 0
    for installed_fn in p.installed_files:
        tok = installed_fn.split(os.path.sep, 4)
        if len(tok) == 4 and tok[1] == 'var' and \
                tok[2] in ('lib', 'cache', 'log'):
            path = os.path.sep.join(tok)
            path_size = disk_usage(path)
            size += path_size

    return size


def parse_args():
    desc = "Slimmer - Estimate the amount of disk space used by installed " \
        "packages, including dependencies."
    parser = ArgumentParser(description=desc)
    parser.add_argument('-d', '--debug', action='store_true',
                        help="Show debugging output")
    parser.add_argument('-n', type=int, default=50,
                        help="Number of packages to display (default: 50)")
    parser.add_argument(
        '--explore-var', action='store_true',
        help="Account for disk space used by /var/cache, /var/lib, /var/log"
        " It requires read access to /var/* (e.g. running as root)"
    )
    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    pkgs_by_name = {}  # name -> Pkg

    installed_packages = list(list_installed_packages())

    # Build pkgs_by_name dict
    for pkg_name, p in installed_packages:
        size = p.installed.installed_size

        if args.explore_var:
            size += explore_var(p)

        pkgs_by_name[pkg_name] = Pkg(pkg_name, size)

    # Build tree
    for pkg_name, p in installed_packages:
        for dep in p.installed.dependencies:
            for alternative_dep in dep:
                dname = alternative_dep.name
                if dname not in pkgs_by_name:
                    # Alternative deps are not always installed
                    continue
                pkgs_by_name[pkg_name].dep_children.add(dname)
                pkgs_by_name[dname].dep_parents.add(pkg_name)

    del(installed_packages)

    root_packages = pick_root_packages(pkgs_by_name)
    reassign_blame(root_packages, pkgs_by_name, args.debug)
    root_packages.sort(reverse=True, key=lambda p: p.size)
    print_summary(root_packages, args.n)
    print("")


if __name__ == '__main__':
    main()
