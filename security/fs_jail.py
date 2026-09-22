
"""
APON runtime filesystem jail — injected via PYTHONPATH before user code.
Blocks reading/writing anything outside the bot directory.
Even if malware calls os.walk('/'), open('/etc/passwd'), pathlib, etc.
"""
from __future__ import annotations
import os
import sys
import builtins

# Bot dir is set by the sandbox parent via env
_BOT_DIR = os.environ.get('APON_BOT_DIR') or os.getcwd()
try:
    _BOT_DIR = os.path.realpath(_BOT_DIR)
except Exception:
    _BOT_DIR = os.getcwd()

_JAIL_LOG = []


def _inside_jail(path: str) -> bool:
    if not path:
        return False
    try:
        # Expand and resolve
        p = path
        if not os.path.isabs(p):
            p = os.path.join(_BOT_DIR, p)
        real = os.path.realpath(p)
        return real == _BOT_DIR or real.startswith(_BOT_DIR + os.sep)
    except Exception:
        return False


def _blocked(op: str, path: str) -> None:
    msg = f"[APON-JAIL] blocked {op}: {path!r}"
    _JAIL_LOG.append(msg)
    # Soft fail for open/read — raise PermissionError like a real OS jail
    raise PermissionError(msg)


# ── Patch builtins.open ──────────────────────────────────────────
_real_open = builtins.open


def _jailed_open(file, *args, **kwargs):
    path = file if isinstance(file, (str, bytes, os.PathLike)) else getattr(file, 'name', None)
    if path is not None:
        path = os.fspath(path)
        # Allow special fds and pure in-memory
        if path not in ('/dev/null', '/dev/zero', '/dev/urandom', '/dev/stdin',
                        '/dev/stdout', '/dev/stderr'):
            if not _inside_jail(path):
                _blocked('open', path)
    return _real_open(file, *args, **kwargs)


builtins.open = _jailed_open


# ── Patch os.* path ops ──────────────────────────────────────────
_real_walk = os.walk
_real_listdir = os.listdir
_real_scandir = getattr(os, 'scandir', None)
_real_stat = os.stat
_real_lstat = os.lstat
_real_remove = os.remove
_real_unlink = getattr(os, 'unlink', os.remove)
_real_rmdir = os.rmdir
_real_mkdir = os.mkdir
_real_makedirs = os.makedirs
_real_rename = os.rename
_real_replace = getattr(os, 'replace', None)
_real_chmod = os.chmod
_real_chdir = os.chdir
_real_getcwd = os.getcwd


def _jailed_walk(top, *args, **kwargs):
    top_s = os.fspath(top)
    if not _inside_jail(top_s):
        _blocked('os.walk', top_s)
        return
        yield  # pragma: no cover
    # Also prevent walking into symlinks that escape
    for root, dirs, files in _real_walk(top, *args, **kwargs):
        # Filter dirs that would escape
        safe_dirs = []
        for d in dirs:
            full = os.path.join(root, d)
            if _inside_jail(full):
                safe_dirs.append(d)
        dirs[:] = safe_dirs
        yield root, dirs, files


def _jailed_listdir(path='.'):
    path_s = os.fspath(path)
    if not _inside_jail(path_s):
        _blocked('os.listdir', path_s)
    return _real_listdir(path)


def _jailed_scandir(path='.'):
    path_s = os.fspath(path)
    if not _inside_jail(path_s):
        _blocked('os.scandir', path_s)
    return _real_scandir(path)


def _jailed_stat(path, *a, **k):
    path_s = os.fspath(path)
    if not _inside_jail(path_s) and not path_s.startswith('/dev/'):
        _blocked('os.stat', path_s)
    return _real_stat(path, *a, **k)


def _jailed_remove(path):
    path_s = os.fspath(path)
    if not _inside_jail(path_s):
        _blocked('os.remove', path_s)
    return _real_remove(path)


def _jailed_chdir(path):
    path_s = os.fspath(path)
    if not _inside_jail(path_s):
        _blocked('os.chdir', path_s)
    return _real_chdir(path)


def _jailed_mkdir(path, *a, **k):
    path_s = os.fspath(path)
    if not _inside_jail(path_s):
        _blocked('os.mkdir', path_s)
    return _real_mkdir(path, *a, **k)


def _jailed_makedirs(name, *a, **k):
    path_s = os.fspath(name)
    if not _inside_jail(path_s):
        _blocked('os.makedirs', path_s)
    return _real_makedirs(name, *a, **k)


def _jailed_rename(src, dst):
    if not _inside_jail(os.fspath(src)):
        _blocked('os.rename src', src)
    if not _inside_jail(os.fspath(dst)):
        _blocked('os.rename dst', dst)
    return _real_rename(src, dst)


os.walk = _jailed_walk
os.listdir = _jailed_listdir
if _real_scandir:
    os.scandir = _jailed_scandir
os.remove = _jailed_remove
os.unlink = _jailed_remove
os.mkdir = _jailed_mkdir
os.makedirs = _jailed_makedirs
os.rename = _jailed_rename
os.chdir = _jailed_chdir

# glob
try:
    import glob as _glob_mod
    _real_glob = _glob_mod.glob
    _real_iglob = _glob_mod.iglob

    def _jailed_glob(pathname, *a, **k):
        # If pattern is absolute and outside jail, block
        if os.path.isabs(pathname) and not _inside_jail(pathname.split('*')[0] or '/'):
            # allow only if the base is inside
            base = pathname
            for ch in '*?[':
                if ch in base:
                    base = base.split(ch)[0]
            if base and not _inside_jail(base):
                _blocked('glob', pathname)
        # Force results filtered
        results = _real_glob(pathname, *a, **k)
        return [r for r in results if _inside_jail(r)]

    def _jailed_iglob(pathname, *a, **k):
        for r in _real_iglob(pathname, *a, **k):
            if _inside_jail(r):
                yield r

    _glob_mod.glob = _jailed_glob
    _glob_mod.iglob = _jailed_iglob
except Exception:
    pass

# pathlib
try:
    import pathlib as _pathlib_mod

    _OrigPath = _pathlib_mod.Path
    _OrigOpen = _OrigPath.open
    _OrigIterdir = _OrigPath.iterdir
    _OrigGlob = _OrigPath.glob
    _OrigRglob = _OrigPath.rglob
    _OrigReadText = _OrigPath.read_text
    _OrigReadBytes = _OrigPath.read_bytes

    def _p_open(self, *a, **k):
        if not _inside_jail(str(self)):
            _blocked('Path.open', str(self))
        return _OrigOpen(self, *a, **k)

    def _p_iterdir(self):
        if not _inside_jail(str(self)):
            _blocked('Path.iterdir', str(self))
        return _OrigIterdir(self)

    def _p_glob(self, pattern):
        if not _inside_jail(str(self)):
            _blocked('Path.glob', str(self))
        return _OrigGlob(self, pattern)

    def _p_rglob(self, pattern):
        if not _inside_jail(str(self)):
            _blocked('Path.rglob', str(self))
        return _OrigRglob(self, pattern)

    def _p_read_text(self, *a, **k):
        if not _inside_jail(str(self)):
            _blocked('Path.read_text', str(self))
        return _OrigReadText(self, *a, **k)

    def _p_read_bytes(self, *a, **k):
        if not _inside_jail(str(self)):
            _blocked('Path.read_bytes', str(self))
        return _OrigReadBytes(self, *a, **k)

    _OrigPath.open = _p_open
    _OrigPath.iterdir = _p_iterdir
    _OrigPath.glob = _p_glob
    _OrigPath.rglob = _p_rglob
    _OrigPath.read_text = _p_read_text
    _OrigPath.read_bytes = _p_read_bytes
except Exception:
    pass

# shutil.copy / copytree
try:
    import shutil as _shutil_mod
    for _name in ('copy', 'copy2', 'copyfile', 'copytree', 'move', 'rmtree'):
        _orig = getattr(_shutil_mod, _name, None)
        if _orig is None:
            continue

        def _make(n, orig):
            def _wrapped(*args, **kwargs):
                for a in args[:2]:
                    if isinstance(a, (str, bytes, os.PathLike)):
                        if not _inside_jail(os.fspath(a)):
                            _blocked(f'shutil.{n}', a)
                return orig(*args, **kwargs)
            return _wrapped
        setattr(_shutil_mod, _name, _make(_name, _orig))
except Exception:
    pass

# zipfile write of outside paths still goes through open() which is jailed

print(f"[APON-JAIL] active — root={_BOT_DIR}", file=sys.stderr)
