#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>


import os
import re

from .inotify import add_tree_watch
from .utils import generate_directories, realpath, readlines

EXCLUDE_VCS_DIRS = frozenset('qt5'.split())
vcs_props = (
    ('git', '.git', os.path.exists),
    # ('mercurial', '.hg', os.path.isdir),
    # ('bzr', '.bzr', os.path.isdir),
)


def vcs_dir_ok(p):
    for q in EXCLUDE_VCS_DIRS:
        if '/' + q + '/' in p or p.endswith('/' + q):
            return False
    return True


def is_vcs(path):
    for directory in generate_directories(path):
        for vcs, vcs_dir, check in vcs_props:
            repo_dir = os.path.join(directory, vcs_dir)
            if vcs_dir_ok(repo_dir) and check(repo_dir):
                if os.path.isdir(repo_dir) and not os.access(repo_dir, os.X_OK):
                    continue
                return vcs, directory
    return None, None


def git_ignore_modifies(path, name):
    return path.endswith('.git') and name == 'index.lock'


def git_directory(directory):
    path = os.path.join(directory, '.git')
    try:
        with open(path, 'rb') as f:
            raw = f.read().partition(b':')[2].strip().decode('utf-8')
            return os.path.abspath(os.path.join(directory, raw))
    except EnvironmentError:
        return path


def git_branch_name(base_dir):
    head = os.path.join(git_directory(base_dir), 'HEAD')
    try:
        with open(head, 'rb') as f:
            raw = f.read().decode('utf-8')
    except (EnvironmentError, ValueError):
        return None
    m = git_branch_name.ref_pat.match(raw)
    if m is not None:
        return m.group(1)
    return raw[:7]
git_branch_name.ref_pat = re.compile(r'ref:\s*refs/heads/(.+)')


def gitcmd(directory, *args):
    return readlines(('git',) + args, directory)


def git_status(directory, subpath):
    if subpath:
        try:
            return next(gitcmd(directory, 'status', '--porcelain', '--ignored', '--', subpath))[:2]
        except StopIteration:
            return ''
    else:
        wt_column = ' '
        index_column = ' '
        untracked_column = ' '
        for line in gitcmd(directory, 'status', '--porcelain'):
            if line[0] == '?':
                untracked_column = 'U'
                continue
            elif line[0] == '!':
                continue

            if line[0] != ' ':
                index_column = 'I'

            if line[1] != ' ':
                wt_column = 'D'

        r = wt_column + index_column + untracked_column
        return r if r.strip() else ''


class VCSWatcher:

    def __init__(self, path, vcs):
        self.path = path
        self.vcs = vcs
        self.branch_name = None
        self.status = {}

    @property
    def tree_watcher(self):
        if self.vcs == 'git':
            return add_tree_watch(self.path, git_ignore_modifies)
        return add_tree_watch(self.path)

    def data(self, subpath=None):
        if self.branch_name is None or self.status.get(subpath) is None or self.tree_watcher.was_modified_since_last_call():
            self.update(subpath)
        return {'branch': self.branch_name, 'status': self.status[subpath]}

    def update(self, subpath=None):
        self.vcs, self.path = is_vcs(self.path)
        if self.vcs == 'git':
            self.branch_name = git_branch_name(self.path)
            self.status[subpath] = git_status(self.path, subpath)
        else:
            self.branch_name = None
            self.status = {}


watched_trees = {}


def vcs_data(path, subpath=None):
    path = realpath(path)
    w = watched_trees.get(path)
    ans = {'branch': None, 'status': None}
    if w is None:
        vcs, vcs_dir = is_vcs(path)
        if vcs:
            watched_trees[path] = w = VCSWatcher(vcs_dir, vcs)
    if w is not None:
        ans = w.data(subpath)
    return ans
