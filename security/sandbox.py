"""
UNIFIED SANDBOX v2.1 — Per-plan rlimits + Jail + Quota Terminal
═══════════════════════════════════════════════════════════════════
Layer-1: run_sandboxed() — spawn bot inside bwrap jail
Layer-2: get_terminal() — PTY shell inside same jail with quota
Both share: bwrap args, clean env, per-plan rlimits, dir hardening
═══════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import os, sys, re, shlex, select, shutil, signal, time, functools
import logging, subprocess, threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import resource
except ImportError:
    resource = None

try:
    import pty as _pty
    _PTY_OK = True
except ImportError:
    _PTY_OK = False

logger = logging.getLogger('APON.security.sandbox')

_IS_LINUX  = sys.platform.startswith('linux')
_BWRAP_BIN = shutil.which('bwrap')
_UNSHARE   = shutil.which('unshare')


def _probe_cmd(cmd, timeout=3) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        return r.returncode == 0
    except Exception:
        return False


_BWRAP_OK = bool(_BWRAP_BIN) and _probe_cmd(
    [_BWRAP_BIN, '--ro-bind', '/', '/', '--dev', '/dev',
     '--unshare-pid', '--die-with-parent', 'true']
) if _BWRAP_BIN else False

_UNSHARE_OK = bool(_UNSHARE) and _probe_cmd(
    [_UNSHARE, '--pid', '--fork', '--', 'true']
) if _UNSHARE else False

if _UNSHARE and not _UNSHARE_OK:
    logger.warning("[sandbox] unshare present but NOT permitted")
if _BWRAP_BIN and not _BWRAP_OK:
    logger.warning("[sandbox] bwrap present but NOT permitted")
if _BWRAP_OK:
    logger.info("[sandbox] capability: bwrap OK")
elif _UNSHARE_OK:
    logger.info("[sandbox] capability: unshare OK")
else:
    logger.info("[sandbox] capability: rlimits-only (safe fallback)")


# ═══════════════════════════════════════════════════
#  RLIMITS — per-plan
# ═══════════════════════════════════════════════════
class SandboxDefaults:
    """Fallback values if caller doesn't pass plan-specific limits."""
    CPU_SECONDS   = 3600
    ADDRESS_SPACE = 512 * 1024 * 1024      # 512 MB
    DATA_SEGMENT  = 256 * 1024 * 1024
    STACK_SIZE    = 16 * 1024 * 1024
    NUM_PROCS     = 32
    NUM_FILES     = 256
    FILE_SIZE     = 100 * 1024 * 1024
    CORE_DUMP     = 0


def _apply_rlimits(ram_mb: int = None, cpu_sec: int = None, procs: int = None):
    """
    Applied in the child process before exec.
    ram_mb, cpu_sec, procs are plan-specific (caller passes via functools.partial).
    If any is None, fall back to SandboxDefaults.
    """
    try:
        os.setsid()
    except Exception:
        pass

    # Prevent privilege escalation
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(38, 1, 0, 0, 0)   # PR_SET_NO_NEW_PRIVS
        libc.prctl(47, 4, 0, 0, 0)   # PR_CAP_AMBIENT_CLEAR_ALL
    except Exception:
        pass

    if resource is None:
        return

    ram_mb  = int(ram_mb)  if ram_mb  else (SandboxDefaults.ADDRESS_SPACE // (1024*1024))
    cpu_sec = int(cpu_sec) if cpu_sec else SandboxDefaults.CPU_SECONDS
    procs   = int(procs)   if procs   else SandboxDefaults.NUM_PROCS

    ram_bytes = ram_mb * 1024 * 1024
    nfiles    = 1024 if ram_mb >= 512 else 512
    stack     = min(16 * 1024 * 1024, ram_bytes // 8)

    for name, val in (
        ('RLIMIT_CPU',    cpu_sec),
        ('RLIMIT_AS',     ram_bytes),               # ← plan RAM
        ('RLIMIT_DATA',   ram_bytes * 3 // 4),      # 75% of plan RAM
        ('RLIMIT_STACK',  stack),
        ('RLIMIT_NPROC',  procs),                    # ← plan procs
        ('RLIMIT_NOFILE', nfiles),
        ('RLIMIT_FSIZE',  SandboxDefaults.FILE_SIZE),
        ('RLIMIT_CORE',   SandboxDefaults.CORE_DUMP),
    ):
        res = getattr(resource, name, None)
        if res is None:
            continue
        try:
            resource.setrlimit(res, (val, val))
        except (ValueError, OSError):
            pass


# ═══════════════════════════════════════════════════
#  ENV STRIPPING
# ═══════════════════════════════════════════════════
_FORBIDDEN_ENV = {
    'BOT_TOKEN', 'OWNER_ID', 'ERROR_BOT_TOKEN',
    'MONGO_URL', 'MONGO_URL_BACKUP', 'DB_NAME',
    'GITHUB_TOKEN', 'GITHUB_REPO', 'GITHUB_KEY_REPO', 'GITHUB_BRANCH',
    'UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN',
    'SESSION_SECRET', 'DATABASE_URL', 'PGPASSWORD',
}
_SECRET_FRAGMENTS = ('SECRET', 'PASSWORD', 'PASSWD', 'API_KEY',
                     'PRIVATE_KEY', 'ACCESS_KEY', 'AUTH_TOKEN', 'CREDENTIAL')


def _build_clean_env(base_env: Dict[str, str], bot_dir: Path,
                     extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    allow_pass = {'PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'PYTHONPATH'}
    clean: Dict[str, str] = {}
    for k, v in (base_env or {}).items():
        if k in allow_pass:
            clean[k] = v

    clean['HOME']   = str(bot_dir)
    clean['PWD']    = str(bot_dir)
    clean['TMPDIR'] = str(bot_dir / '.tmp_run')
    clean['TMP']    = str(bot_dir / '.tmp_run')
    clean['TEMP']   = str(bot_dir / '.tmp_run')
    clean['PATH']   = '/usr/local/bin:/usr/bin:/bin'
    clean['LANG']   = 'C.UTF-8'
    clean['LC_ALL'] = 'C.UTF-8'
    clean['PYTHONUNBUFFERED'] = '1'
    clean['PYTHONDONTWRITEBYTECODE'] = '1'
    clean['PYTHONNOUSERSITE'] = '1'
    clean['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    clean['NODE_ENV'] = 'production'
    clean['TERM'] = 'xterm-256color'
    clean['APON_SANDBOX'] = '1'
    clean['APON_BOT_DIR'] = str(bot_dir)

    if extra:
        for k, v in extra.items():
            if k == 'BOT_TOKEN':
                clean[k] = str(v)
                continue
            ku = k.upper()
            if k in _FORBIDDEN_ENV:
                continue
            if any(frag in ku for frag in _SECRET_FRAGMENTS):
                continue
            clean[k] = str(v)
    return clean


# ═══════════════════════════════════════════════════
#  BWRAP BUILDER
# ═══════════════════════════════════════════════════
def _build_bwrap_args(bot_dir: Path) -> List[str]:
    if not _BWRAP_BIN:
        return []
    home_dir = bot_dir / '.home'
    tmp_dir = bot_dir / '.tmp_run'
    try:
        home_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return []
    args = [
        str(_BWRAP_BIN),
        '--ro-bind', '/usr', '/usr',
        '--ro-bind', '/bin', '/bin',
        '--ro-bind', '/sbin', '/sbin',
        '--ro-bind', '/lib', '/lib',
    ]
    if os.path.isdir('/lib64'):
        args += ['--ro-bind', '/lib64', '/lib64']
    args += [
        '--ro-bind', '/etc/resolv.conf', '/etc/resolv.conf',
        '--ro-bind', '/etc/hosts', '/etc/hosts',
        '--ro-bind', '/etc/ssl', '/etc/ssl',
        '--proc', '/proc',
        '--dev', '/dev',
        '--tmpfs', '/tmp',
        '--tmpfs', '/var',
        '--tmpfs', '/home',
        '--tmpfs', '/root',
        '--bind', str(bot_dir), str(bot_dir),
        '--bind', str(home_dir), '/home/bot',
        '--bind', str(tmp_dir), str(tmp_dir),
        '--unshare-pid', '--unshare-ipc', '--unshare-uts',
        '--unshare-cgroup',
        '--die-with-parent', '--new-session',
        '--hostname', 'bot-sandbox',
        '--chdir', str(bot_dir),
        '--setenv', 'HOME', str(bot_dir),
        '--',
    ]
    return args


# ═══════════════════════════════════════════════════
#  DIR HARDENING + ESCAPE SCAN
# ═══════════════════════════════════════════════════
def _harden_dir_perms(bot_dir: Path) -> None:
    try: os.chmod(bot_dir, 0o700)
    except OSError: pass
    try:
        for root, dirs, files in os.walk(bot_dir):
            for d in dirs:
                try: os.chmod(os.path.join(root, d), 0o700)
                except OSError: pass
            for f in files:
                try: os.chmod(os.path.join(root, f), 0o600)
                except OSError: pass
    except Exception: pass


def _scan_escape_attempts(bot_dir: Path) -> List[str]:
    alerts = []
    try:
        bdir_real = str(bot_dir.resolve())
        for root, dirs, files in os.walk(bot_dir, followlinks=False):
            for name in dirs + files:
                p = Path(root) / name
                if name in ('.ssh', '.aws', '.config', '.netrc',
                            'id_rsa', 'id_dsa', 'authorized_keys'):
                    alerts.append(f"suspicious: {name}")
                if p.is_symlink():
                    try:
                        tgt = str(p.resolve())
                        if not tgt.startswith(bdir_real):
                            alerts.append(f"escaping symlink: {name} -> {tgt}")
                    except Exception: pass
    except Exception: pass
    return alerts


# ═══════════════════════════════════════════════════
#  LAYER-1: RUN BOT INSIDE JAIL
# ═══════════════════════════════════════════════════
def run_sandboxed(bot_dir: Path, cmd: List[str],
                  user_env: Optional[Dict[str, str]] = None,
                  log_file=None, bot_id: Optional[str] = None,
                  on_scan_alert=None,
                  ram_mb: int = 512,
                  cpu_sec: int = 3600,
                  procs: int = 32,
                  **_) -> subprocess.Popen:
    """
    ram_mb, cpu_sec, procs — plan-specific limits from config.resolve_limits().
    Defaults are safe for free plan.
    """
    bot_dir = Path(bot_dir).resolve()
    bot_dir.mkdir(parents=True, exist_ok=True)
    (bot_dir / '.tmp_run').mkdir(exist_ok=True)
    (bot_dir / '.home').mkdir(exist_ok=True)
    _harden_dir_perms(bot_dir)

    env = _build_clean_env(dict(os.environ), bot_dir, user_env)

    # Filesystem jail
    try:
        _jail_dir = str(Path(__file__).resolve().parent)
        deps = str(bot_dir / '.deps')
        parts = [_jail_dir]
        if os.path.isdir(deps):
            parts.append(deps)
        _pp = env.get('PYTHONPATH', '')
        if _pp:
            parts.append(_pp)
        env['PYTHONPATH'] = os.pathsep.join(parts)
        env['APON_BOT_DIR'] = str(bot_dir)
        env['APON_SANDBOX'] = '1'
    except Exception:
        pass

    # Pre-exec with plan limits
    preexec = (
        functools.partial(_apply_rlimits, ram_mb, cpu_sec, procs)
        if _IS_LINUX else None
    )

    modes_try = []
    if _BWRAP_OK:
        modes_try.append(('bwrap-jailed',
            _build_bwrap_args(bot_dir) + list(cmd)))
    if _UNSHARE_OK:
        modes_try.append(('unshare-jailed',
            [str(_UNSHARE), '--pid', '--fork', '--mount',
             '--uts', '--ipc', '--kill-child', '--'] + list(cmd)))
    modes_try.append(('rlimits-only', list(cmd)))

    proc = None
    mode = 'rlimits-only'
    for m, final_cmd in modes_try:
        try:
            proc = subprocess.Popen(
                final_cmd, cwd=str(bot_dir), env=env,
                stdout=log_file if log_file is not None else subprocess.PIPE,
                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                preexec_fn=preexec,
                close_fds=True,
            )
            if m == 'unshare-jailed':
                try:
                    ret = proc.poll()
                    if ret is not None and ret != 0:
                        try:
                            out = proc.communicate(timeout=1)[0] or b''
                        except Exception:
                            out = b''
                        logger.warning(
                            f"[sandbox] unshare failed (exit={ret}): "
                            f"{out[:200]!r} — falling back")
                        proc = None
                        continue
                except Exception:
                    pass
            mode = m
            break
        except OSError as e:
            logger.warning(f"[sandbox] {m} spawn failed: {e}")
            proc = None
            continue

    if proc is None:
        mode = 'rlimits-only'
        proc = subprocess.Popen(
            list(cmd), cwd=str(bot_dir), env=env,
            stdout=log_file if log_file is not None else subprocess.PIPE,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            preexec_fn=preexec,
            close_fds=True,
        )

    logger.info(
        f"[sandbox] spawn mode={mode} bot={bot_id or bot_dir.name} "
        f"ram={ram_mb}MB procs={procs} cpu={cpu_sec}s")

    if bot_id is not None and on_scan_alert:
        stop_evt = threading.Event()
        def _watch():
            time.sleep(20)
            while not stop_evt.is_set():
                try:
                    for msg in _scan_escape_attempts(bot_dir):
                        try: on_scan_alert(bot_id, msg)
                        except Exception: pass
                except Exception: pass
                if stop_evt.wait(30): break
        threading.Thread(target=_watch, daemon=True,
                         name=f"watch-{bot_dir.name}").start()

    return proc


def sandbox_status() -> Dict[str, Any]:
    return {
        'is_linux': _IS_LINUX,
        'bwrap':    bool(_BWRAP_OK),
        'unshare':  bool(_UNSHARE_OK),
        'bwrap_bin': bool(_BWRAP_BIN),
        'unshare_bin': bool(_UNSHARE),
        'mode': ('bwrap' if _BWRAP_OK else
                 'unshare' if _UNSHARE_OK else 'rlimits-only'),
    }


def install_hint() -> str:
    if _BWRAP_OK: return "bubblewrap active — MAX isolation"
    if _UNSHARE_OK: return "unshare active — kernel namespaces"
    if _UNSHARE or _BWRAP_BIN:
        return "rlimits only — unshare/bwrap present but not permitted"
    return "only rlimits — install bubblewrap for MAX isolation"


# ═══════════════════════════════════════════════════
#  DISK USAGE
# ═══════════════════════════════════════════════════
def dir_size_mb(path: str, max_files: int = 200_000) -> float:
    total = 0
    count = 0
    skip_dirs = {'.tmp_run', '.home', '__pycache__', '.git',
                 'node_modules', '.cache', '.npm', '.local'}
    try:
        if not path or not os.path.exists(path):
            return 0.0
        if os.path.isfile(path):
            return round(os.path.getsize(path) / (1024 * 1024), 2)
        for root, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                count += 1
                if count > max_files:
                    return round(total / (1024 * 1024), 2)
                fp = os.path.join(root, f)
                try:
                    if os.path.islink(fp):
                        continue
                    total += os.path.getsize(fp)
                except OSError:
                    continue
    except Exception:
        pass
    return round(total / (1024 * 1024), 2)


# ═══════════════════════════════════════════════════
#  TERMINAL COMMAND RULES
# ═══════════════════════════════════════════════════
ALLOWED_CMDS = {
    'ls', 'cat', 'head', 'tail', 'wc', 'grep', 'find', 'file', 'stat',
    'pwd', 'whoami', 'echo', 'printf', 'date', 'clear', 'exit',
    'du', 'tree', 'less', 'more',
    'mkdir', 'touch', 'cp', 'mv', 'rm', 'rmdir',
    'python', 'python3', 'pip', 'pip3',
    'node', 'npm', 'npx',
    'git', 'zip', 'unzip', 'tar', 'gzip', 'gunzip',
    'sed', 'awk', 'sort', 'uniq', 'cut', 'tr',
    'diff', 'cmp', 'timeout', 'sleep',
    'curl', 'wget',
    'ps', 'free',
}

WRITE_TOKENS = (
    ' >', ' >>', '>', '>>',
    ' tee ', ' cp ', ' mv ', ' touch ', ' mkdir ', ' rm ', ' rmdir ',
    ' wget ', ' curl ', ' pip install', ' pip3 install',
    ' npm install', ' npm i ',
    ' tar -x', ' tar x', ' unzip ', ' gunzip ',
    ' git clone', ' git pull', ' git fetch',
)

HARD_BAN = [
    r'\bsudo\b', r'\bsu\b(?:\s|$)', r'\bdoas\b', r'\bsudoedit\b',
    r'\bchroot\b', r'\bmount\b', r'\bumount\b', r'\bnsenter\b',
    r'\bunshare\b', r'\bbwrap\b', r'\bfirejail\b',
    r'\biptables\b', r'\bufw\b', r'\bnft\b',
    r'\bsystemctl\b', r'\bservice\s', r'\bjournalctl\b',
    r'\breboot\b', r'\bshutdown\b', r'\bhalt\b', r'\bpoweroff\b',
    r'\bpasswd\b', r'\buseradd\b', r'\buserdel\b', r'\bgroupadd\b',
    r'\bcrontab\b', r'\bvisudo\b',
    r'/etc/passwd', r'/etc/shadow', r'/etc/sudoers', r'/etc/ssh',
    r'(?:^|\s)/root(?:/|\s|$)', r'/proc/sys', r'/sys/',
    r'/proc/self/environ', r'/proc/\d+/mem',
    r'\.\./\.\.',
    r'rm\s+-rf\s+/',
    r':\(\)\s*\{',
    r'>\s*/dev/sd[a-z]',
    r'\bdd\s+',
    r'\bmkfs\b', r'\bmknod\b', r'\binsmod\b', r'\bmodprobe\b',
    r'\bnc\s+', r'\bnetcat\s+', r'\bnmap\b',
    r'\bchmod\s+[0-7]*[675]',
    r'\bchown\b', r'\bchgrp\b',
    r'\bln\s+-s', r'\bsymlink\b',
    r'\bkill\b', r'\bpkill\b', r'\bkillall\b',
    r'\bpython[0-9.]*\s+-c\b',
    r'\bnode\s+-e\b',
    r'\beval\b', r'\bexec\s+/',
    r'\bbash\s+-i\b', r'\bsh\s+-i\b',
    r'config\.py\b', r'\bTOKEN\b', r'MONGO_URL', r'OWNER_ID',
    r'apon_data\b', r'upload_bots\b', r'\.env\b',
    r'bot_token', r'ERROR_BOT_TOKEN',
]


def _panel_roots() -> List[Path]:
    roots = []
    try:
        from config import BASE_DIR, DATA_DIR, LOGS_DIR, BACKUP_DIR
        for p in (BASE_DIR, DATA_DIR, LOGS_DIR, BACKUP_DIR):
            try:
                roots.append(Path(p).resolve())
            except Exception:
                pass
    except Exception:
        pass
    for p in ('/root', '/etc', '/proc', '/sys', '/var/log', '/home'):
        roots.append(Path(p))
    return roots


def _path_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _escape_jail(path_str: str, bot_dir: Path) -> Optional[str]:
    if not path_str or path_str in ('.', './'):
        return None
    if path_str.startswith('-') and '/' not in path_str:
        return None
    if '://' in path_str:
        return None
    raw = path_str
    try:
        if os.path.isabs(raw):
            target = Path(raw).resolve()
        else:
            target = (bot_dir / raw).resolve()
    except Exception:
        return f"invalid path: {raw[:40]}"
    if not _path_inside(target, bot_dir):
        return f"outside bot folder: {raw[:50]}"
    name = target.name.lower()
    if name in ('config.py', '.env', 'token', 'credentials', 'id_rsa',
                'shadow', 'passwd', 'sudoers'):
        if not _path_inside(target, bot_dir):
            return f"sensitive file blocked: {name}"
    return None


def _has_write(cmd: str) -> bool:
    low = ' ' + cmd.lower() + ' '
    return any(t in low for t in WRITE_TOKENS)


def _is_banned(cmd: str) -> Optional[str]:
    for pat in HARD_BAN:
        try:
            if re.search(pat, cmd, re.IGNORECASE):
                return pat[:40]
        except re.error:
            pass
    return None


# ═══════════════════════════════════════════════════
#  LAYER-2: ISOLATED PTY TERMINAL
# ═══════════════════════════════════════════════════
class IsolatedTerminal:
    def __init__(self, bot_id: str, bot_dir: Path,
                 user_dir: Path, quota_mb: int,
                 ram_mb: int = 512, procs: int = 32):
        self.bot_id   = bot_id
        self.bot_dir  = Path(bot_dir).resolve()
        self.user_dir = Path(user_dir).resolve()
        self.quota_mb = int(quota_mb)
        self.ram_mb   = int(ram_mb)
        self.procs    = int(procs)
        self.master_fd: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.buffer: List[str] = []
        self.lock   = threading.Lock()
        self.alive  = False
        self.simple = False
        self.reader: Optional[threading.Thread] = None
        self.watcher: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self.blocked_by_quota = False

    def start(self) -> bool:
        _harden_dir_perms(self.bot_dir)
        self._stop_evt.clear()

        preexec = (
            functools.partial(_apply_rlimits, self.ram_mb, 1800, self.procs)
            if _IS_LINUX else None
        )

        if _PTY_OK and _IS_LINUX:
            try:
                master_fd, slave_fd = _pty.openpty()
                env = _build_clean_env(dict(os.environ), self.bot_dir)
                bash_cmd = ['/bin/bash', '--noprofile', '--norc', '-i']

                if _BWRAP_OK:
                    full_cmd = _build_bwrap_args(self.bot_dir) + bash_cmd
                    mode = 'bwrap'
                else:
                    full_cmd = bash_cmd
                    mode = 'pty'

                self.proc = subprocess.Popen(
                    full_cmd, cwd=str(self.bot_dir), env=env,
                    stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                    preexec_fn=preexec,
                    close_fds=True)
                os.close(slave_fd)
                self.master_fd = master_fd
                self.alive = True
                self.simple = False

                self.reader = threading.Thread(
                    target=self._read_loop, daemon=True, name=f"pty-{self.bot_id}")
                self.reader.start()
                self.watcher = threading.Thread(
                    target=self._quota_watch, daemon=True, name=f"quota-{self.bot_id}")
                self.watcher.start()

                logger.info(
                    f"[term] mode={mode} bot={self.bot_id} "
                    f"quota={self.quota_mb}MB ram={self.ram_mb}MB procs={self.procs}")
                return True
            except Exception as e:
                logger.warning(f"[term] PTY start failed ({e}) — using simple mode")

        self.simple = True
        self.alive = True
        self.watcher = threading.Thread(
            target=self._quota_watch, daemon=True, name=f"quota-{self.bot_id}")
        self.watcher.start()
        logger.info(f"[term] mode=simple bot={self.bot_id} quota={self.quota_mb}MB")
        return True

    def _read_loop(self) -> None:
        while self.alive and self.master_fd is not None:
            try:
                r, _, _ = select.select([self.master_fd], [], [], 0.5)
                if not r:
                    if self.proc and self.proc.poll() is not None: break
                    continue
                data = os.read(self.master_fd, 4096)
                if not data: break
                text = data.decode('utf-8', errors='replace')
                with self.lock:
                    self.buffer.append(text)
                    total = sum(len(x) for x in self.buffer)
                    while total > 65536 and self.buffer:
                        total -= len(self.buffer.pop(0))
            except OSError: break
            except Exception: break
        self.alive = False

    def _quota_watch(self) -> None:
        while not self._stop_evt.is_set():
            if self._stop_evt.wait(2): break
            try:
                size = dir_size_mb(str(self.user_dir))
                if size >= self.quota_mb and self.master_fd is not None:
                    try: os.write(self.master_fd, b'\x03')
                    except Exception: pass
                    with self.lock:
                        self.buffer.append(
                            f"\n\033[31m⚠️ QUOTA EXCEEDED: "
                            f"{size:.1f}MB / {self.quota_mb}MB — "
                            f"command interrupted\033[0m\n")
                    self.blocked_by_quota = True
            except Exception: pass

    def send(self, raw_cmd: str) -> Tuple[bool, str]:
        if not self.alive:
            return False, "terminal not running"
        if not self.simple and self.master_fd is None:
            return False, "terminal not running"

        cmd = (raw_cmd or "").strip()
        if not cmd:
            return False, "empty command"
        if len(cmd) > 512:
            return False, "command too long (max 512 chars)"

        banned = _is_banned(cmd)
        if banned:
            return False, f"blocked: {banned}"

        if self.simple:
            for meta in ("`", "$(", "${", "&&", "||", ";", "|", "\n"):
                if meta in cmd:
                    return False, f"blocked shell meta: {meta!r}"

        try:
            tokens = shlex.split(cmd)
        except ValueError:
            return False, "unparseable command"
        if not tokens:
            return False, "empty command"

        base = os.path.basename(tokens[0])
        if base not in ALLOWED_CMDS:
            return False, f"'{base}' is not allowed in bot terminal"

        for tok in tokens[1:]:
            reason = _escape_jail(tok, self.bot_dir)
            if reason:
                return False, reason
            if ".." in tok:
                return False, "path traversal blocked (..)"

        for m in re.finditer(r"(?:>>?|2>>?)\s*(\S+)", cmd):
            reason = _escape_jail(m.group(1), self.bot_dir)
            if reason:
                return False, f"redirect {reason}"

        if _has_write(cmd):
            size = dir_size_mb(str(self.bot_dir))
            if size >= self.quota_mb:
                self.blocked_by_quota = True
                return False, (f"quota full: {size:.1f}MB / {self.quota_mb}MB. "
                               f"Delete some files first")

        with self.lock:
            self.buffer.clear()

        preexec = (
            functools.partial(_apply_rlimits, self.ram_mb, 1800, self.procs)
            if _IS_LINUX else None
        )

        if self.simple or self.master_fd is None:
            try:
                env = _build_clean_env(dict(os.environ), self.bot_dir)
                env["HOME"] = str(self.bot_dir)
                env["PWD"] = str(self.bot_dir)
                r = subprocess.run(
                    ["/bin/bash", "--noprofile", "--norc", "-c", cmd],
                    cwd=str(self.bot_dir), env=env,
                    capture_output=True, text=True, timeout=30,
                    preexec_fn=preexec,
                )
                out = (r.stdout or "") + (r.stderr or "")
                if not out.strip():
                    out = f"(exit {r.returncode}, no output)"
                with self.lock:
                    self.buffer.append(out)
                return True, ""
            except subprocess.TimeoutExpired:
                return False, "command timed out (30s)"
            except Exception as e:
                return False, str(e)

        try:
            os.write(self.master_fd, (cmd + "\n").encode("utf-8"))
            return True, ""
        except Exception as e:
            return False, str(e)

    def read_output(self, wait: float = 1.5) -> str:
        time.sleep(wait)
        with self.lock:
            out = "".join(self.buffer)
            self.buffer.clear()
        return out

    def clear(self) -> None:
        with self.lock: self.buffer.clear()

    def usage_mb(self) -> float:
        return dir_size_mb(str(self.user_dir))

    def stop(self) -> None:
        self.alive = False
        self._stop_evt.set()
        if self.proc:
            try: os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
            except Exception:
                try: self.proc.kill()
                except Exception: pass
            try: self.proc.wait(timeout=2)
            except Exception: pass
        if self.master_fd is not None:
            try: os.close(self.master_fd)
            except Exception: pass
            self.master_fd = None


# ═══════════════════════════════════════════════════
#  TERMINAL REGISTRY
# ═══════════════════════════════════════════════════
_TERMINALS: Dict[str, IsolatedTerminal] = {}
_TERM_LOCK = threading.Lock()


def get_terminal(bot_id: str, bot_dir: Path,
                 user_dir: Path, quota_mb: int,
                 ram_mb: int = 512, procs: int = 32) -> IsolatedTerminal:
    with _TERM_LOCK:
        t = _TERMINALS.get(bot_id)
        if t and t.alive:
            t.quota_mb = int(quota_mb)
            t.ram_mb   = int(ram_mb)
            t.procs    = int(procs)
            return t
        t = IsolatedTerminal(bot_id, bot_dir, user_dir, quota_mb, ram_mb, procs)
        t.start()
        _TERMINALS[bot_id] = t
        return t


def shutdown_terminal(bot_id: str) -> None:
    with _TERM_LOCK:
        t = _TERMINALS.pop(bot_id, None)
    if t:
        try: t.stop()
        except Exception: pass


def shutdown_all_terminals() -> None:
    with _TERM_LOCK:
        terms = list(_TERMINALS.values())
        _TERMINALS.clear()
    for t in terms:
        try: t.stop()
        except Exception: pass


def quota_bar(pct: int) -> str:
    filled = max(0, min(10, pct // 10))
    return "▰" * filled + "▱" * (10 - filled)


def cleanup_all() -> None:
    shutdown_all_terminals()
