"""
REDIS CACHE MODULE — Upstash REST API
High-Performance: Connection pool, short timeouts, fast fallback
Handles 30-100+ concurrent users
"""

import os, json, time, logging, threading
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger('APON.cache')

REDIS_URL   = os.environ.get('UPSTASH_REDIS_REST_URL', '')
REDIS_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN', '')


# ═══════════════════════════════════════════════════
#  UPSTASH REST CLIENT — High Performance
# ═══════════════════════════════════════════════════
class UpstashRedis:
    def __init__(self, url, token):
        self.url   = url.rstrip('/')
        self.token = token
        self._lock = threading.Lock()
        self._ok   = False
        # Persistent session with connection pooling
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        self._sess = requests.Session()
        self._sess.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        # Connection pool: 20 connections, 10 max per host
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=Retry(total=1, backoff_factor=0.1)
        )
        self._sess.mount('https://', adapter)
        self._test_connection()

    def _test_connection(self):
        try:
            r = self._sess.get(f"{self.url}/ping", timeout=3)
            if r.status_code == 200:
                self._ok = True
                logger.info("✅ Upstash Redis connected!")
            else:
                logger.warning(f"⚠️ Redis ping failed: {r.status_code}")
        except Exception as e:
            logger.warning(f"⚠️ Redis unavailable: {e} — using memory fallback")

    def _cmd(self, *args):
        if not self._ok:
            return None
        try:
            r = self._sess.post(
                self.url,
                json=list(args),
                timeout=1.5  # OPTIMIZED: 1.5s instead of 3s — fast fail
            )
            if r.status_code == 200:
                return r.json().get('result')
        except Exception as e:
            logger.debug(f"Redis cmd error: {e}")
        return None

    @property
    def is_available(self):
        return self._ok

    def get(self, key):
        val = self._cmd('GET', key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except Exception:
            return val

    def set(self, key, value, ex=None):
        data = json.dumps(value)
        if ex:
            return self._cmd('SET', key, data, 'EX', ex)
        return self._cmd('SET', key, data)

    def delete(self, *keys):
        return self._cmd('DEL', *keys)

    def exists(self, key):
        return bool(self._cmd('EXISTS', key))

    def expire(self, key, seconds):
        return self._cmd('EXPIRE', key, seconds)

    def incr(self, key):
        return self._cmd('INCR', key)

    def lpush(self, key, *values):
        return self._cmd('LPUSH', key, *[json.dumps(v) for v in values])

    def lrange(self, key, start, end):
        result = self._cmd('LRANGE', key, start, end)
        if not result:
            return []
        out = []
        for item in result:
            try:
                out.append(json.loads(item))
            except Exception:
                out.append(item)
        return out

    def ltrim(self, key, start, end):
        return self._cmd('LTRIM', key, start, end)

    def hset(self, key, field, value):
        return self._cmd('HSET', key, field, json.dumps(value))

    def hget(self, key, field):
        val = self._cmd('HGET', key, field)
        if val is None:
            return None
        try:
            return json.loads(val)
        except Exception:
            return val

    def hgetall(self, key):
        result = self._cmd('HGETALL', key)
        if not result or len(result) % 2 != 0:
            return {}
        return {
            result[i]: json.loads(result[i+1]) if result[i+1] else None
            for i in range(0, len(result), 2)
        }

    def hdel(self, key, *fields):
        return self._cmd('HDEL', key, *fields)

    def keys(self, pattern='*'):
        return self._cmd('KEYS', pattern) or []

    def flushdb(self):
        return self._cmd('FLUSHDB')


# ═══════════════════════════════════════════════════
#  IN-MEMORY FALLBACK — Thread-Safe
# ═══════════════════════════════════════════════════
class MemoryCache:
    def __init__(self):
        self._store  = {}
        self._expiry = {}
        self._lock   = threading.RLock()
        self.is_available = False
        # Background cleanup every 5 min
        threading.Thread(target=self._cleanup_loop, daemon=True).start()

    def _cleanup_loop(self):
        while True:
            time.sleep(300)
            try:
                self._purge_expired()
            except Exception:
                pass

    def _purge_expired(self):
        now = time.monotonic()
        with self._lock:
            expired = [k for k, exp in self._expiry.items() if now > exp]
            for k in expired:
                self._store.pop(k, None)
                self._expiry.pop(k, None)

    def _expired(self, key):
        exp = self._expiry.get(key)
        if exp and time.monotonic() > exp:
            self._store.pop(key, None)
            self._expiry.pop(key, None)
            return True
        return False

    def get(self, key):
        with self._lock:
            if self._expired(key):
                return None
            return self._store.get(key)

    def set(self, key, value, ex=None):
        with self._lock:
            self._store[key] = value
            if ex:
                self._expiry[key] = time.monotonic() + ex
            elif key in self._expiry:
                del self._expiry[key]
        return True

    def delete(self, *keys):
        with self._lock:
            for k in keys:
                self._store.pop(k, None)
                self._expiry.pop(k, None)

    def exists(self, key):
        return self.get(key) is not None

    def incr(self, key):
        with self._lock:
            val = self._store.get(key, 0) + 1
            self._store[key] = val
            return val

    def hset(self, key, field, value):
        with self._lock:
            if key not in self._store:
                self._store[key] = {}
            self._store[key][field] = value

    def hget(self, key, field):
        with self._lock:
            return self._store.get(key, {}).get(field)

    def hgetall(self, key):
        with self._lock:
            return dict(self._store.get(key, {}))

    def hdel(self, key, *fields):
        with self._lock:
            d = self._store.get(key, {})
            for f in fields:
                d.pop(f, None)

    def keys(self, pattern='*'):
        with self._lock:
            if pattern == '*':
                return list(self._store.keys())
            import fnmatch
            return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    def lrange(self, key, start, end):
        with self._lock:
            lst = self._store.get(key, [])
            end = len(lst) if end == -1 else end + 1
            return lst[start:end]

    def lpush(self, key, *values):
        with self._lock:
            if key not in self._store:
                self._store[key] = []
            for v in values:
                self._store[key].insert(0, v)

    def ltrim(self, key, start, end):
        with self._lock:
            lst = self._store.get(key, [])
            self._store[key] = lst[start:end+1]


# ═══════════════════════════════════════════════════
#  INITIALIZE
# ═══════════════════════════════════════════════════
if REDIS_URL and REDIS_TOKEN:
    _redis = UpstashRedis(REDIS_URL, REDIS_TOKEN)
    cache  = _redis if _redis.is_available else MemoryCache()
else:
    logger.warning("⚠️ Redis credentials not set — using memory cache")
    cache = MemoryCache()


# ═══════════════════════════════════════════════════
#  TTL CONSTANTS
# ═══════════════════════════════════════════════════
TTL_SESSION     = 3600
TTL_USER        = 300
TTL_CHANNEL     = 600
TTL_BOT_STATUS  = 60
TTL_RATE        = 60
TTL_STATS       = 120
TTL_PLAN        = 300


# ═══════════════════════════════════════════════════
#  HIGH-LEVEL CACHE HELPERS
# ═══════════════════════════════════════════════════
def session_get(uid):     return cache.get(f"sess:{uid}")
def session_set(uid, d):  cache.set(f"sess:{uid}", d, ex=TTL_SESSION)
def session_del(uid):     cache.delete(f"sess:{uid}", f"pay:{uid}")

def pay_state_get(uid):   return cache.get(f"pay:{uid}")
def pay_state_set(uid,d): cache.set(f"pay:{uid}", d, ex=TTL_SESSION)
def pay_state_del(uid):   cache.delete(f"pay:{uid}")

def user_cache_get(uid):  return cache.get(f"user:{uid}")
def user_cache_set(uid,d):cache.set(f"user:{uid}", d, ex=TTL_USER)
def user_cache_del(uid):  cache.delete(f"user:{uid}")

def channels_cache_get(): return cache.get("channels:active")
def channels_cache_set(d):cache.set("channels:active", d, ex=TTL_CHANNEL)
def channels_cache_invalidate(): cache.delete("channels:active", "channels:all")

def bot_status_set(sk, running): cache.set(f"bstatus:{sk}", running, ex=TTL_BOT_STATUS)
def bot_status_get(sk):          return cache.get(f"bstatus:{sk}")

def stats_cache_get():    return cache.get("admin:stats")
def stats_cache_set(d):   cache.set("admin:stats", d, ex=TTL_STATS)
def stats_cache_invalidate(): cache.delete("admin:stats")

def plan_cache_get(uid):  return cache.get(f"plan:{uid}")
def plan_cache_set(uid,d):cache.set(f"plan:{uid}", d, ex=TTL_PLAN)
def plan_cache_del(uid):  cache.delete(f"plan:{uid}", f"user:{uid}")


def rate_check_redis(uid) -> bool:
    """
    Distributed rate limiter — 30 msgs/min.
    Falls back to True if Redis unavailable.
    """
    if not cache.is_available:
        return True
    key = f"rate:{uid}"
    try:
        count = cache.incr(key)
        if count == 1:
            cache.expire(key, TTL_RATE)
        return count <= 30
    except Exception:
        return True


logger.info(f"🗃️ Cache backend: {'Redis (Upstash)' if getattr(cache, '_ok', False) else 'Memory'}")
