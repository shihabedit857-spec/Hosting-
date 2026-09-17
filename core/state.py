"""
STATE MODULE — Redis-backed Thread-Safe State
Sessions survive server restarts via Upstash Redis
"""

import threading
from collections import defaultdict, deque
from datetime import datetime
from config import ADMIN_ID, OWNER_ID


class BotState:
    def __init__(self):
        self._lock         = threading.RLock()
        self.force_sub_enabled = True
        self.bot_locked    = False
        self.bot_start_time = datetime.now()
        self.active_users  = set()
        self.admin_ids     = {ADMIN_ID, OWNER_ID}
        self._user_states  = {}      # local fallback
        self._payment_states = {}    # local fallback
        self.user_msg_times = defaultdict(deque)
        self.bot_scripts   = {}

    def is_admin(self, uid):
        return uid == OWNER_ID or uid in self.admin_ids

    # ── User state — Redis first, memory fallback ──
    def set_state(self, uid, state_data):
        try:
            from core.cache import session_set
            session_set(uid, state_data)
        except Exception:
            pass
        with self._lock:
            self._user_states[uid] = state_data

    def get_state(self, uid):
        try:
            from core.cache import session_get
            val = session_get(uid)
            if val is not None:
                return val
        except Exception:
            pass
        return self._user_states.get(uid)

    def clear_state(self, uid):
        try:
            from core.cache import session_del
            session_del(uid)
        except Exception:
            pass
        with self._lock:
            self._user_states.pop(uid, None)
            self._payment_states.pop(uid, None)

    # ── Payment state — Redis first ──
    def set_pay_state(self, uid, data):
        try:
            from core.cache import pay_state_set
            pay_state_set(uid, data)
        except Exception:
            pass
        with self._lock:
            self._payment_states[uid] = data

    def get_pay_state(self, uid):
        try:
            from core.cache import pay_state_get
            val = pay_state_get(uid)
            if val is not None:
                return val
        except Exception:
            pass
        return self._payment_states.get(uid)

    def clear_pay_state(self, uid):
        try:
            from core.cache import pay_state_del
            pay_state_del(uid)
        except Exception:
            pass
        with self._lock:
            self._payment_states.pop(uid, None)


state      = BotState()
bot_scripts = state.bot_scripts
