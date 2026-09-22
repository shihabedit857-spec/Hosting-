"""CONFIG — Full with disk_mb quota + ADMIN_LIMITS"""
import os

TOKEN            = '8653992436:AAG5nV2X37wbkLzZqIfPzOu9Qn6cwW6Vrd0'
ERROR_BOT_TOKEN  = '8510538370:AAGr6HCGB5Z1VaO95UzSGmMy0908c3xizYw'

if not TOKEN:
    raise ValueError("❌ BOT_TOKEN is not set!")

MONGO_URL        = ''
MONGO_URL_BACKUP = ''
DB_NAME          = 'apon_hosting'
DB_STORAGE_WARN_MB  = 400
DB_STORAGE_LIMIT_MB = 490

OWNER_ID       = 6804172454
ADMIN_ID       = (0)
BOT_USERNAME   = 'Open_hostingbot'
YOUR_USERNAME  = '@shihab23'
UPDATE_CHANNEL = 'https://t.me/sb_aura'

BASE_DIR   = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'upload_bots')
DATA_DIR   = os.path.join(BASE_DIR, 'apon_data')
LOGS_DIR   = os.path.join(BASE_DIR, 'logs')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

for _d in [UPLOAD_DIR, DATA_DIR, LOGS_DIR, BACKUP_DIR]:
    os.makedirs(_d, exist_ok=True)

BRAND        = "🌟 XTC HOSTING PANEL"
BRAND_SHORT  = "XHP"
BRAND_VER    = "v6.5"
BRAND_TAG    = f"{BRAND} {BRAND_VER}"
BRAND_FOOTER = f"\n━━━━━━━━━━━━━━━━━━━━\n{BRAND_TAG}"

DEFAULT_FORCE_CHANNELS = {'sb_aura': 'bot Updates'}

# ═══ PLAN LIMITS — disk_mb + ram + procs added ═══
PLAN_LIMITS = {
    'free':       {'name': '🆓 Free',       'max_bots': 1,  'ram': 256,  'disk_mb': 100,   'auto_restart': False, 'price': 0},
    'starter':    {'name': '🟢 Starter',    'max_bots': 2,  'ram': 384,  'disk_mb': 500,   'auto_restart': True,  'price': 99},
    'basic':      {'name': '⭐ Basic',       'max_bots': 5,  'ram': 768,  'disk_mb': 1024,  'auto_restart': True,  'price': 199},
    'pro':        {'name': '💎 Pro',         'max_bots': 15, 'ram': 1536, 'disk_mb': 3072,  'auto_restart': True,  'price': 499},
    'enterprise': {'name': '🏢 Enterprise',  'max_bots': 50, 'ram': 3072, 'disk_mb': 10240, 'auto_restart': True,  'price': 999},
    'lifetime':   {'name': '👑 Lifetime',    'max_bots': -1, 'ram': 4096, 'disk_mb': 51200, 'auto_restart': True,  'price': 1999},
}

# ═══ OWNER / ADMIN OVERRIDE ═══
# Owner & admins bypass plan limits and get top-tier resources.
# Adjust `ram` to ~75% of your host's total RAM to avoid OS-level OOM.
ADMIN_LIMITS = {
    'name':         '👑 Owner/Admin',
    'max_bots':     -1,       # unlimited
    'ram':          4096,     # 4 GB — safe on 6 GB+ host
    'disk_mb':      51200,    # 50 GB
    'cpu_sec':      7200,     # 2 hours CPU
    'procs':        256,      # 256 threads
    'auto_restart': True,
    'is_admin':     True,
}

# ── Per-plan thread/CPU caps ──
PLAN_PROCS = {
    'free':       32,
    'starter':    32,
    'basic':      48,
    'pro':        64,
    'enterprise': 128,
    'lifetime':   192,
    'admin':      256,
}

PAYMENT_METHODS = {
    'bkash':   {'name': 'bKash',       'number': '01306633616',            'type': 'Send Money',       'icon': '🟪'},
    'nagad':   {'name': 'Nagad',       'number': '01306633616',            'type': 'Send Money',       'icon': '🟧'},
    'rocket':  {'name': 'Rocket',      'number': '01306633616',            'type': 'Send Money',       'icon': '🟦'},
    'upay':    {'name': 'Upay',        'number': '01306633616',            'type': 'Send Money',       'icon': '🟩'},
    'binance': {'name': 'Binance Pay', 'number': 'Binance ID: 758637628', 'type': 'Binance Pay/USDT', 'icon': '🟡'},
    'bank':    {'name': 'Bank',        'number': 'Contact Admin',          'type': 'Transfer',         'icon': '🏦'},
}

REF_BONUS_DAYS = 3
REF_COMMISSION = 20

MODULES_MAP = {
    'telebot': 'pytelegrambotapi', 'telegram': 'python-telegram-bot',
    'pyrogram': 'pyrogram', 'telethon': 'telethon', 'aiogram': 'aiogram',
    'PIL': 'Pillow', 'cv2': 'opencv-python', 'sklearn': 'scikit-learn',
    'bs4': 'beautifulsoup4', 'dotenv': 'python-dotenv', 'yaml': 'pyyaml',
    'aiohttp': 'aiohttp', 'numpy': 'numpy', 'pandas': 'pandas',
    'requests': 'requests', 'flask': 'flask', 'fastapi': 'fastapi',
    'motor': 'motor', 'pymongo': 'pymongo', 'httpx': 'httpx',
    'cryptography': 'cryptography',
}

FLASK_PORT = 5000
DAILY_REPORT_HOUR   = 0
DAILY_REPORT_MINUTE = 0
FREE_BOT_MAX_HOURS  = 24
BUTTON_STYLES_ENABLED = True
APPROVAL_REQUIRED_DEFAULT = True
GITHUB_DEFAULT_BRANCH = 'main'
GITHUB_MAX_ZIP_MB     = 50

STAR_PLAN_PRICES = {
    'starter':    1, 'basic':      3, 'pro':        5,
    'enterprise': 9, 'lifetime':   15,
}


# ═══════════════════════════════════════════════════════════════════════════
#  PLAN → LIMIT RESOLVER
# ═══════════════════════════════════════════════════════════════════════════
def resolve_limits(uid: int, user_obj: dict = None, is_admin: bool = False) -> dict:
    """
    Return the effective resource limits for a user.

    Priority:
      1. Admin/Owner  → ADMIN_LIMITS
      2. Paid plan     → PLAN_LIMITS[plan]
      3. Fallback      → PLAN_LIMITS['free']

    Returns dict with keys: ram, procs, cpu_sec, disk_mb, max_bots, auto_restart.
    """
    if is_admin or (uid is not None and int(uid) in (OWNER_ID, ADMIN_ID)):
        return {
            'ram':          ADMIN_LIMITS['ram'],
            'procs':        ADMIN_LIMITS['procs'],
            'cpu_sec':      ADMIN_LIMITS['cpu_sec'],
            'disk_mb':      ADMIN_LIMITS['disk_mb'],
            'max_bots':     ADMIN_LIMITS['max_bots'],
            'auto_restart': ADMIN_LIMITS['auto_restart'],
            'name':         ADMIN_LIMITS['name'],
        }

    plan_key = (user_obj or {}).get('plan', 'free')
    plan = PLAN_LIMITS.get(plan_key, PLAN_LIMITS['free'])
    ram = int(plan.get('ram', 256))
    procs = PLAN_PROCS.get(plan_key, 32)
    return {
        'ram':          ram,
        'procs':        procs,
        'cpu_sec':      3600,
        'disk_mb':      int(plan.get('disk_mb', 100)),
        'max_bots':     int(plan.get('max_bots', 1)),
        'auto_restart': bool(plan.get('auto_restart', False)),
        'name':         plan.get('name', plan_key),
}
