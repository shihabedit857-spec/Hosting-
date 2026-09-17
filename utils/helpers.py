"""
UTILITIES MODULE — High-Performance Helper Functions
Optimized for 1000+ concurrent users
"""

import os, psutil, hashlib, string, time, logging, threading
from collections import deque
from datetime import datetime
from config import UPLOAD_DIR, LOGS_DIR
from core.state import state, bot_scripts

logger = logging.getLogger('APON.utils')

# ═══════════════════════════════════════════════════
#  CPU CACHE — Non-blocking background refresh
# ═══════════════════════════════════════════════════
_cpu_cache = {'val': 0.0, 'ts': 0.0}
_cpu_lock = threading.Lock()

def _refresh_cpu_background():
    def _worker():
        while True:
            try:
                val = psutil.cpu_percent(interval=1)
                with _cpu_lock:
                    _cpu_cache['val'] = val
                    _cpu_cache['ts'] = time.monotonic()
            except Exception:
                pass
            time.sleep(5)
    threading.Thread(target=_worker, daemon=True, name='cpu_monitor').start()

_refresh_cpu_background()

def _get_cpu_cached():
    with _cpu_lock:
        return _cpu_cache['val']


# ═══════════════════════════════════════════════════
#  UPTIME
# ═══════════════════════════════════════════════════
def get_uptime():
    d = datetime.now() - state.bot_start_time
    h, r = divmod(d.seconds, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d.days:
        parts.append(f"{d.days}d")
    if h:
        parts.append(f"{h}h")
    parts.append(f"{m}m {s}s")
    return " ".join(parts)


def fmt_size(b):
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def gen_ref_code(uid):
    uid = int(uid)
    chars = string.digits + string.ascii_uppercase
    enc = ''
    t = uid
    if t == 0:
        enc = '0'
    else:
        while t > 0:
            enc = chars[t % 36] + enc
            t //= 36
    salt = hashlib.md5(f"{uid}_apon_hosting".encode()).hexdigest()[:2].upper()
    return f"AHP{enc}{salt}"


def time_left(e):
    if not e:
        return "♾️ Lifetime"
    try:
        end = datetime.fromisoformat(e)
        if end <= datetime.now():
            return "❌ Expired"
        d = end - datetime.now()
        if d.days > 0:
            return f"{d.days}d {d.seconds // 3600}h"
        return f"{d.seconds // 3600}h {(d.seconds % 3600) // 60}m"
    except Exception:
        return "?"


def user_folder(uid):
    f = os.path.join(UPLOAD_DIR, str(uid))
    os.makedirs(f, exist_ok=True)
    return f


# ═══════════════════════════════════════════════════
#  PROCESS STATUS
# ═══════════════════════════════════════════════════
def is_running(sk):
    i = bot_scripts.get(sk)
    if not i:
        return False
    proc = i.get('process')
    if not proc:
        return False
    if proc.poll() is not None:   # instant check
        return False
    try:
        p = psutil.Process(proc.pid)
        return p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except Exception:
        return False


def bot_running(uid, name):
    return is_running(f"{uid}_{name}")


# ═══════════════════════════════════════════════════
#  CLEANUP SCRIPT
# ═══════════════════════════════════════════════════
def cleanup_script(sk):
    i = bot_scripts.pop(sk, None)
    if not i:
        return
    try:
        lf = i.get('log_file')
        if lf and hasattr(lf, 'close') and not lf.closed:
            lf.flush()
            lf.close()
    except Exception:
        pass


# ═══════════════════════════════════════════════════
#  KILL PROCESS TREE
# ═══════════════════════════════════════════════════
def kill_tree(pi):
    if not pi:
        return
    try:
        lf = pi.get('log_file')
        if lf and hasattr(lf, 'close') and not lf.closed:
            lf.flush()
            lf.close()
    except Exception:
        pass
    p = pi.get('process')
    if not p or not hasattr(p, 'pid'):
        return
    try:
        parent = psutil.Process(p.pid)
        children = parent.children(recursive=True)
        for c in children:
            try:
                c.terminate()
            except psutil.NoSuchProcess:
                pass
        gone, alive = psutil.wait_procs(children, timeout=3)
        for c in alive:
            try:
                c.kill()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.terminate()
            parent.wait(timeout=3)
        except psutil.TimeoutExpired:
            parent.kill()
        except psutil.NoSuchProcess:
            pass
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        logger.debug(f"kill_tree: {e}")


# ═══════════════════════════════════════════════════
#  BOT RESOURCES — Non-blocking
# ═══════════════════════════════════════════════════
def bot_res(sk):
    i = bot_scripts.get(sk)
    if not i or not i.get('process'):
        return 0, 0
    try:
        p = psutil.Process(i['process'].pid)
        mem = p.memory_info().rss / (1024 * 1024)
        cpu = p.cpu_percent(interval=None)   # Non-blocking
        for c in p.children(recursive=True):
            try:
                mem += c.memory_info().rss / (1024 * 1024)
                cpu += c.cpu_percent(interval=None)
            except psutil.NoSuchProcess:
                pass
        return round(mem, 1), round(cpu, 1)
    except psutil.NoSuchProcess:
        return 0, 0
    except Exception:
        return 0, 0


# ═══════════════════════════════════════════════════
#  SYSTEM STATS — Non-blocking
# ═══════════════════════════════════════════════════
def sys_stats():
    try:
        c = _get_cpu_cached()
        m = psutil.virtual_memory()
        d = psutil.disk_usage('/')
        return {
            'cpu': c, 'mem': m.percent,
            'disk': round(d.used / d.total * 100, 1),
            'up': get_uptime(),
            'mem_total': fmt_size(m.total),
            'mem_used': fmt_size(m.used),
            'disk_total': fmt_size(d.total),
            'disk_used': fmt_size(d.used),
        }
    except Exception:
        return {
            'cpu': 0, 'mem': 0, 'disk': 0, 'up': get_uptime(),
            'mem_total': '?', 'mem_used': '?',
            'disk_total': '?', 'disk_used': '?'
        }


# ═══════════════════════════════════════════════════
#  RATE LIMITER — O(1) with deque
# ═══════════════════════════════════════════════════
# Thread-safe rate check lock
_rate_lock = threading.Lock()

def rate_check(uid):
    """
    High-performance rate limiter — thread-safe with lock.
    Limits: 30 msgs/min, min 0.2s between messages.
    """
    # Try Redis first (distributed, survives restarts)
    try:
        from core.cache import rate_check_redis
        if not rate_check_redis(uid):
            return False
    except Exception:
        pass

    now = time.monotonic()
    with _rate_lock:
        times = state.user_msg_times[uid]
        # Pop old entries from left — O(1) each
        while times and now - times[0] > 60:
            times.popleft()
        if len(times) >= 30:
            return False
        if times and now - times[-1] < 0.2:  # OPTIMIZED: 0.2s instead of 0.3s
            return False
        times.append(now)
    return True
