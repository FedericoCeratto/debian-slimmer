#!/usr/bin/env python3
#
# Package disk usage estimation
#
# Copyright 2017 Federico Ceratto <federico.ceratto@gmail.com>
# Released under GPLv3 License, see LICENSE file
#

import apt.cache

# APT is using decimal multiples
MB = 1000 * 1000.0


class Pkg:
    def __init__(self, name, size):
        self.name = name
        self.size = size
        self.dep_children = set()
        self.dep_parents = set()


def list_installed_packages():
    cache = apt.cache.Cache()
    for p in cache:
        if p.is_installed:
            yield p.name, p


def _recurse_reassign_blame(pkg, pkgs_by_name, verbose, depth=0):
    """
    """
    if verbose:
        print("%s" % pkg.name)
    if pkg.size is None:
        return  # already visited

    for d_name in pkg.dep_children:
        if depth == 10:
            if verbose:
                print("  skip child %s -> %s" % (pkg.name, d_name))
            # break dependency loops
            break

        d = pkgs_by_name[d_name]
        if verbose:
            print("  child %s -> %s" % (pkg.name, d_name))
        _recurse_reassign_blame(d, pkgs_by_name, verbose, depth+1)

    if pkg.size is None:
        # This is reached when the current package is in a dependency loop,
        # the maximum depth has been already reached and we are going back
        # in the recursion stack
        return

    if pkg.dep_parents:
        np = len(pkg.dep_parents)
        blame_up = pkg.size / np
        if verbose:
            print("  uploading blame to %d parents" % (np))

        for parent_name in pkg.dep_parents:
            parent = pkgs_by_name[parent_name]
            if parent.size is None:
                if verbose:
                    print("  ERROR blaming %s" % parent_name)
            else:
                parent.size += blame_up

        pkg.size = None


def reassign_blame(pkgs_by_name, verbose=False):
    """Blame disk space usage from dependencies to their parents
    """
    for pkg in pkgs_by_name.values():
        _recurse_reassign_blame(pkg, pkgs_by_name, verbose)


def print_blame_tree(pkg_name, pkgs_by_name, nesting=1):
    """Print dependency tree for a package
    """
    print("%s%s" % ("  " * nesting, pkg_name))
    if nesting < 2:
        for c in pkgs_by_name[pkg_name].dep_children:
            print_blame_tree(c, pkgs_by_name, nesting+1)


def print_summary(pkgs_by_name):
    """Print package disk usage summary
    """
    root_packages = []
    for pkg_name, pkg in pkgs_by_name.items():
        if len(pkg.dep_parents) == 0:
            root_packages.append((pkg.size, pkg_name))
    root_packages.sort(reverse=True)

    for size, pkg_name in root_packages[:50]:
        print("%-30s  %5.1f MB" % (pkg_name, size / MB))
        # print_blame_tree(pkg_name, pkgs_by_name)


def main():
    pkgs_by_name = {}  # name -> Pkg

    installed_packages = list(list_installed_packages())
    for pkg_name, p in installed_packages:
        size = p.installed.installed_size
        pkgs_by_name[pkg_name] = Pkg(pkg_name, size)

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

    reassign_blame(pkgs_by_name)
    print_summary(pkgs_by_name)
    print("done")


if __name__ == '__main__':
    print("running...")
    main()
