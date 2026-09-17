"""
╔═══════════════════════════════════════════════════════════╗
║  🌟 APON HOSTING PANEL — Premium Edition v6.0 🌟         ║
║  Developer: @developer_apon                               ║
║  Config File — All Settings Here (No .env needed)         ║
╚═══════════════════════════════════════════════════════════╝
"""

import os

# ═══════════════════════════════════════════════════
#  BOT TOKENS
# ═══════════════════════════════════════════════════
TOKEN            = '8653992436:AAHmBSESimnzOxZT7mshxw0X3CQLfXPEbZs'          # ← এখানে তোমার BOT_TOKEN দাও
ERROR_BOT_TOKEN  = '8677777628:AAHHbVdhmWOt_39KnTkjwbjd_4cY8PiBTFg'          # ← Error bot token (optional)

if not TOKEN:
    raise ValueError("❌ BOT_TOKEN is not set! TOKEN ভেরিয়েবলে টোকেন দাও।")

# ═══════════════════════════════════════════════════
#  MONGODB — PRIMARY + SECONDARY FALLBACK
# ═══════════════════════════════════════════════════
MONGO_URL         = ''         # ← Primary MongoDB URL
MONGO_URL_BACKUP  = ''         # ← Backup MongoDB URL (optional)
DB_NAME           = 'apon_hosting'

DB_STORAGE_WARN_MB  = 400
DB_STORAGE_LIMIT_MB = 490

# ═══════════════════════════════════════════════════
#  OWNER & ADMIN
# ═══════════════════════════════════════════════════
OWNER_ID       = 6804172454             # ← তোমার Telegram User ID দাও
ADMIN_ID       = 6804172454
BOT_USERNAME   = 'Open_hostingbot'
YOUR_USERNAME  = '@shihab23'
UPDATE_CHANNEL = 'https://t.me/sb_aura'

# ═══════════════════════════════════════════════════
#  DIRECTORIES
# ═══════════════════════════════════════════════════
BASE_DIR   = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'upload_bots')
DATA_DIR   = os.path.join(BASE_DIR, 'apon_data')
LOGS_DIR   = os.path.join(BASE_DIR, 'logs')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

for _d in [UPLOAD_DIR, DATA_DIR, LOGS_DIR, BACKUP_DIR]:
    os.makedirs(_d, exist_ok=True)

# ═══════════════════════════════════════════════════
#  BRANDING
# ═══════════════════════════════════════════════════
BRAND        = "🌟 SB HOSTING PANEL"
BRAND_SHORT  = "SBHP"
BRAND_VER    = "v6.0"
BRAND_TAG    = f"{BRAND} {BRAND_VER}"
BRAND_FOOTER = f"\n━━━━━━━━━━━━━━━━━━━━\n{BRAND_TAG}"

# ═══════════════════════════════════════════════════
#  FORCE SUBSCRIBE
# ═══════════════════════════════════════════════════
DEFAULT_FORCE_CHANNELS = {'sb_aura': 'bot Updates'}

# ═══════════════════════════════════════════════════
#  PLAN LIMITS
# ═══════════════════════════════════════════════════
PLAN_LIMITS = {
    'free':       {'name': '🆓 Free',        'max_bots': 1,  'ram': 128,  'auto_restart': False, 'price': 0},
    'starter':    {'name': '🟢 Starter',     'max_bots': 2,  'ram': 256,  'auto_restart': True,  'price': 99},
    'basic':      {'name': '⭐ Basic',        'max_bots': 5,  'ram': 512,  'auto_restart': True,  'price': 199},
    'pro':        {'name': '💎 Pro',          'max_bots': 15, 'ram': 2048, 'auto_restart': True,  'price': 499},
    'enterprise': {'name': '🏢 Enterprise',   'max_bots': 50, 'ram': 4096, 'auto_restart': True,  'price': 999},
    'lifetime':   {'name': '👑 Lifetime',     'max_bots': -1, 'ram': 8192, 'auto_restart': True,  'price': 1999},
}

# ═══════════════════════════════════════════════════
#  PAYMENT METHODS
# ═══════════════════════════════════════════════════
PAYMENT_METHODS = {
    'bkash':   {'name': 'bKash',       'number': '01306633616',            'type': 'Send Money',       'icon': '🟪'},
    'nagad':   {'name': 'Nagad',       'number': '01306633616',            'type': 'Send Money',       'icon': '🟧'},
    'rocket':  {'name': 'Rocket',      'number': '01306633616',            'type': 'Send Money',       'icon': '🟦'},
    'upay':    {'name': 'Upay',        'number': '01306633616',            'type': 'Send Money',       'icon': '🟩'},
    'binance': {'name': 'Binance Pay', 'number': 'Binance ID: 758637628', 'type': 'Binance Pay/USDT', 'icon': '🟡'},
    'bank':    {'name': 'Bank',        'number': 'Contact Admin',          'type': 'Transfer',         'icon': '🏦'},
}

# ═══════════════════════════════════════════════════
#  REFERRAL SETTINGS
# ═══════════════════════════════════════════════════
REF_BONUS_DAYS = 3
REF_COMMISSION = 20

# ═══════════════════════════════════════════════════
#  MODULE MAP (for auto-install)
# ═══════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════
#  FLASK PORT
# ═══════════════════════════════════════════════════
FLASK_PORT = 5000

# ═══════════════════════════════════════════════════
#  DAILY REPORT
# ═══════════════════════════════════════════════════
DAILY_REPORT_HOUR   = 0
DAILY_REPORT_MINUTE = 0

# ═══════════════════════════════════════════════════
#  FREE PLAN BOT LIMIT
# ═══════════════════════════════════════════════════
FREE_BOT_MAX_HOURS  = 24

# ═══════════════════════════════════════════════════
#  BUTTON STYLES (Telegram Bot API 9.0+)
# ═══════════════════════════════════════════════════
BUTTON_STYLES_ENABLED = True

# ═══════════════════════════════════════════════════
#  FILE APPROVAL
# ═══════════════════════════════════════════════════
APPROVAL_REQUIRED_DEFAULT = True

# ═══════════════════════════════════════════════════
#  GITHUB DEPLOY
# ═══════════════════════════════════════════════════
GITHUB_DEFAULT_BRANCH = 'main'
GITHUB_MAX_ZIP_MB     = 50

# ═══════════════════════════════════════════════════
#  TELEGRAM STARS PRICES (Cheap & affordable)
# ═══════════════════════════════════════════════════
STAR_PLAN_PRICES = {
    'starter':    1,
    'basic':      3,
    'pro':        5,
    'enterprise': 9,
    'lifetime':   15,
}