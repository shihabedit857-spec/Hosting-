"""
KEYBOARDS MODULE — All inline keyboard builders
Telegram Bot API 9.0+ button styles
+ File approval + GitHub + Tk/Star + Promo (Tk / %)
+ Auto-restart hide for Free users
"""

from telebot import types
from config import PLAN_LIMITS, PAYMENT_METHODS, BUTTON_STYLES_ENABLED
from core.state import state


if BUTTON_STYLES_ENABLED:
    _orig_init    = types.InlineKeyboardButton.__init__
    _orig_to_dict = types.InlineKeyboardButton.to_dict

    def _patched_init(self, *args, **kwargs):
        style = kwargs.pop('style', None)
        _orig_init(self, *args, **kwargs)
        self._style = style

    def _patched_to_dict(self):
        d = _orig_to_dict(self)
        s = getattr(self, '_style', None)
        if s:
            d['style'] = s
        return d

    types.InlineKeyboardButton.__init__  = _patched_init
    types.InlineKeyboardButton.to_dict   = _patched_to_dict


def _btn(text, style=None, **kwargs):
    return types.InlineKeyboardButton(text, style=style, **kwargs)


_db = None

def init_keyboards(db_instance):
    global _db
    _db = db_instance


# ═══════════════════════════════════════════════════
#  MAIN MENU
# ═══════════════════════════════════════════════════
def main_menu_kb(uid):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("🤖 My Bots",      callback_data="menu_mybots",  style="primary"),
        _btn("📤 Deploy Bot",   callback_data="menu_deploy",  style="success"),
    )
    m.add(
        _btn("💎 Subscription", callback_data="menu_sub",     style="primary"),
        _btn("💰 Wallet",       callback_data="menu_wallet",  style="primary"),
    )
    m.add(
        _btn("🎁 Referral",     callback_data="menu_ref",     style="primary"),
        _btn("🎟 Promo Code",   callback_data="menu_promo",   style="success"),
    )
    m.add(
        _btn("📊 Statistics",   callback_data="menu_stats",   style="primary"),
        _btn("🟢 Running Bots", callback_data="menu_running", style="success"),
    )
    m.add(
        _btn("⚡ Speed Test",    callback_data="menu_speed",   style="primary"),
        _btn("📚 Help",         callback_data="menu_help",    style="primary"),
    )
    m.add(
        _btn("⚙️ Settings",      callback_data="menu_settings", style="primary"),
        _btn("🎫 Support",      callback_data="menu_support", style="primary"),
    )
    notif_count = _db.unread_count(uid) if _db else 0
    notif_label = f"🔔 Notifications ({notif_count})" if notif_count > 0 else "🔔 Notifications"
    m.add(_btn(notif_label, callback_data="menu_notif", style="primary"))
    if state.is_admin(uid):
        m.add(_btn("👑 Admin Panel", callback_data="menu_admin", style="danger"))
    m.add(_btn("📞 Contact Developer",
               url="https://t.me/shihab23", style="primary"))
    return m


def help_menu_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("📤 How to Deploy",   callback_data="help_deploy",   style="primary"),
        _btn("🤖 Managing Bots",   callback_data="help_bots",     style="primary"),
    )
    m.add(
        _btn("💎 Plans & Pricing", callback_data="help_plans",    style="primary"),
        _btn("💳 Payment Guide",   callback_data="help_payment",  style="primary"),
    )
    m.add(
        _btn("🎁 Referral System", callback_data="help_referral", style="primary"),
        _btn("💰 Wallet Guide",    callback_data="help_wallet",   style="primary"),
    )
    m.add(
        _btn("🔍 Auto Detection",  callback_data="help_detect",   style="primary"),
        _btn("📦 Supported Files", callback_data="help_files",    style="primary"),
    )
    m.add(
        _btn("❓ FAQ",             callback_data="help_faq",      style="primary"),
        _btn("🛠 Troubleshoot",    callback_data="help_trouble",  style="primary"),
    )
    m.add(
        _btn("📋 All Commands",    callback_data="help_commands", style="primary"),
        _btn("📞 Contact Support", callback_data="help_contact",  style="primary"),
    )
    m.add(_btn("🏠 Back to Main Menu", callback_data="go_home", style="primary"))
    return m


def back_btn(cb="go_home", text="🏠 Main Menu"):
    m = types.InlineKeyboardMarkup()
    m.add(_btn(text, callback_data=cb, style="primary"))
    return m


def back_help_btn():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("📚 Back to Help", callback_data="menu_help", style="primary"),
        _btn("🏠 Main Menu",    callback_data="go_home",   style="primary"),
    )
    return m


# ═══════════════════════════════════════════════════
#  BOT ACTIONS — Auto-restart only if plan allows
# ═══════════════════════════════════════════════════
def bot_action_kb(bid, is_live, auto_restart=False, approval_status='approved',
                  allow_auto_restart=True):
    m = types.InlineKeyboardMarkup(row_width=2)

    if approval_status == 'pending':
        m.add(_btn("ℹ️ Info", callback_data=f"bot_detail:{bid}", style="primary"))
        m.add(_btn("🔙 Back", callback_data="menu_mybots",       style="primary"))
        return m
    if approval_status == 'rejected':
        m.add(_btn("🗑️ Delete", callback_data=f"bot_del:{bid}", style="danger"))
        m.add(_btn("🔙 Back",   callback_data="menu_mybots",    style="primary"))
        return m

    if auto_restart:
        ar_label, ar_style = "🔄 Auto Restart: ON",  "success"
    else:
        ar_label, ar_style = "🔄 Auto Restart: OFF", "primary"

    if is_live:
        m.add(
            _btn("🛑 Stop",      callback_data=f"bot_stop:{bid}",    style="danger"),
            _btn("🔄 Restart",   callback_data=f"bot_restart:{bid}", style="primary"),
        )
        m.add(
            _btn("📋 Logs",      callback_data=f"bot_logs:{bid}",    style="primary"),
            _btn("📊 Resources", callback_data=f"bot_res:{bid}",     style="primary"),
        )
        if allow_auto_restart:
            m.add(_btn(ar_label, callback_data=f"bot_autorestart:{bid}", style=ar_style))
    else:
        if allow_auto_restart:
            m.add(
                _btn("▶️ Start",     callback_data=f"bot_start:{bid}",   style="success"),
                _btn(ar_label, callback_data=f"bot_autorestart:{bid}", style=ar_style),
            )
        else:
            m.add(_btn("▶️ Start", callback_data=f"bot_start:{bid}", style="success"))

        m.add(
            _btn("📋 Logs",      callback_data=f"bot_logs:{bid}",    style="primary"),
            _btn("📥 Download",  callback_data=f"bot_dl:{bid}",      style="primary"),
        )
        m.add(
            _btn("🔍 Re-detect Entry",
                 callback_data=f"bot_redetect:{bid}", style="primary"),
            _btn("🗑️ Delete",    callback_data=f"bot_del:{bid}",     style="danger"),
        )

    m.add(_btn("🔙 Back to My Bots",
               callback_data="menu_mybots", style="primary"))
    return m


# ═══════════════════════════════════════════════════
#  FILE APPROVAL KB
# ═══════════════════════════════════════════════════
def file_approval_kb(bid):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("✅ Approve", callback_data=f"approve_file:{bid}", style="success"),
        _btn("❌ Reject",  callback_data=f"reject_file:{bid}",  style="danger"),
    )
    return m


def pending_files_kb():
    m = types.InlineKeyboardMarkup(row_width=1)
    if not _db:
        return m
    rows = _db.pending_bots()
    for b in rows[:20]:
        m.add(_btn(
            f"⏳ #{b['bot_id']} {b['bot_name'][:18]} — User {b['user_id']}",
            callback_data=f"review_file:{b['bot_id']}",
            style="primary"
        ))
    if not rows:
        m.add(_btn("📭 No pending files", callback_data="menu_admin", style="primary"))
    m.add(_btn("🔙 Back to Admin", callback_data="menu_admin", style="primary"))
    return m


# ═══════════════════════════════════════════════════
#  DEPLOY CHOICE + GITHUB
# ═══════════════════════════════════════════════════
def deploy_choice_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("📤 Upload File", callback_data="deploy_upload", style="success"),
        _btn("🐙 GitHub Repo", callback_data="deploy_github", style="primary"),
    )
    m.add(_btn("🏠 Main Menu", callback_data="go_home", style="primary"))
    return m


def github_repo_type_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("🌐 Public Repo",  callback_data="gh_type:public",  style="success"),
        _btn("🔒 Private Repo", callback_data="gh_type:private", style="danger"),
    )
    m.add(_btn("❌ Cancel", callback_data="go_home", style="danger"))
    return m


# ═══════════════════════════════════════════════════
#  SUBSCRIPTION CHOICE (Tk / Star)
# ═══════════════════════════════════════════════════
def sub_choice_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("💵 Tk (bKash/etc)", callback_data="sub_tk",   style="primary"),
        _btn("⭐ Telegram Star",   callback_data="sub_star", style="success"),
    )
    m.add(_btn("🏠 Main Menu", callback_data="go_home", style="primary"))
    return m


def star_plan_kb():
    from config import STAR_PLAN_PRICES
    m = types.InlineKeyboardMarkup(row_width=1)
    for k, stars in STAR_PLAN_PRICES.items():
        p = PLAN_LIMITS.get(k, {})
        slots = '♾️' if p.get('max_bots') == -1 else str(p.get('max_bots'))
        m.add(_btn(
            f"{p.get('name', k)} — {slots} bots — ⭐ {stars}",
            callback_data=f"star_buy:{k}",
            style="success"
        ))
    m.add(_btn("🔙 Back", callback_data="menu_sub", style="primary"))
    return m


# ═══════════════════════════════════════════════════
#  PROMO (Admin + User)
# ═══════════════════════════════════════════════════
def adm_promo_choice_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("💵 Tk (Wallet)",  callback_data="adm_promo_tk",  style="primary"),
        _btn("💰 % (Discount)", callback_data="adm_promo_pct", style="success"),
    )
    m.add(_btn("🔙 Admin", callback_data="menu_admin", style="primary"))
    return m


def promo_choice_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("💵 Tk Wallet",  callback_data="promo_tk",  style="primary"),
        _btn("💰 % Discount", callback_data="promo_pct", style="success"),
    )
    m.add(_btn("🏠 Main Menu", callback_data="go_home", style="primary"))
    return m


def promo_discount_plan_kb(code, discount_pct):
    m = types.InlineKeyboardMarkup(row_width=1)
    for k, p in PLAN_LIMITS.items():
        if k == 'free': continue
        original = p['price']
        discounted = int(original * (100 - discount_pct) / 100)
        m.add(_btn(
            f"{p['name']} — {original}→{discounted} BDT (-{discount_pct}%)",
            callback_data=f"promo_plan:{code}:{k}",
            style="success"
        ))
    m.add(_btn("❌ Cancel", callback_data="go_home", style="danger"))
    return m


def promo_pay_method_kb(code, plan, amount):
    m = types.InlineKeyboardMarkup(row_width=2)
    for k, v in PAYMENT_METHODS.items():
        m.add(_btn(
            f"{v['icon']} {v['name']}",
            callback_data=f"promo_pay:{code}:{plan}:{k}",
            style="primary",
        ))
    m.add(_btn("💰 Pay from Wallet",
               callback_data=f"promo_wallet:{code}:{plan}", style="success"))
    m.add(_btn("🔙 Back", callback_data="go_home", style="primary"))
    return m


# ═══════════════════════════════════════════════════
#  PLANS / PAYMENTS
# ═══════════════════════════════════════════════════
def plan_kb():
    m = types.InlineKeyboardMarkup(row_width=1)
    for k, p in PLAN_LIMITS.items():
        if k == 'free': continue
        slots = '♾️' if p['max_bots'] == -1 else str(p['max_bots'])
        m.add(_btn(
            f"{p['name']} — {slots} bots — {p['price']} BDT",
            callback_data=f"plan_select:{k}",
            style="success",
        ))
    m.add(_btn("🏠 Main Menu", callback_data="go_home", style="primary"))
    return m


def pay_method_kb(pk):
    m = types.InlineKeyboardMarkup(row_width=2)
    for k, v in PAYMENT_METHODS.items():
        m.add(_btn(
            f"{v['icon']} {v['name']}",
            callback_data=f"pay_method:{pk}:{k}",
            style="primary",
        ))
    m.add(_btn("💰 Pay from Wallet",
               callback_data=f"pay_wallet:{pk}", style="success"))
    m.add(
        _btn("🔙 Back to Plans", callback_data="menu_sub", style="primary"),
        _btn("🏠 Main Menu",     callback_data="go_home",  style="primary"),
    )
    return m


def pay_approve_kb(pid):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("✅ Approve", callback_data=f"pay_approve:{pid}", style="success"),
        _btn("❌ Reject",  callback_data=f"pay_reject:{pid}",  style="danger"),
    )
    return m


# ═══════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════
def admin_kb(approval_on=None):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        _btn("👥 All Users",          callback_data="adm_users",     style="primary"),
        _btn("📊 Statistics",         callback_data="adm_stats",     style="primary"),
    )
    m.add(
        _btn("💳 Pending Payments",   callback_data="adm_payments",  style="primary"),
        _btn("📢 Broadcast",          callback_data="adm_broadcast", style="primary"),
    )
    m.add(
        _btn("➕ Add Subscription",   callback_data="adm_addsub",    style="success"),
        _btn("➖ Remove Subscription",callback_data="adm_remsub",    style="danger"),
    )
    m.add(
        _btn("🚫 Ban User",           callback_data="adm_ban",       style="danger"),
        _btn("✅ Unban User",         callback_data="adm_unban",     style="success"),
    )
    m.add(
        _btn("📢 Force Sub Channels", callback_data="adm_channels",  style="primary"),
        _btn("🎟 Promo Codes",        callback_data="adm_promo",     style="primary"),
    )
    m.add(
        _btn("🎫 Support Tickets",    callback_data="adm_tickets",   style="primary"),
        _btn("🖥 System Info",        callback_data="adm_system",    style="primary"),
    )
    m.add(
        _btn("🛑 Stop All Bots",      callback_data="adm_stopall",   style="danger"),
        _btn("💾 Backup DB",          callback_data="adm_backup",    style="primary"),
    )
    m.add(
        _btn("📜 Admin Logs",         callback_data="adm_logs",      style="primary"),
        _btn("💰 Give Balance",       callback_data="adm_give",      style="success"),
    )
    m.add(
        _btn("🔍 User Info",          callback_data="adm_userinfo",  style="primary"),
        _btn("🔔 Send Notification",  callback_data="adm_notify",    style="primary"),
    )
    m.add(_btn("🗑️ Cleanup Storage", callback_data="adm_cleanup", style="danger"))

    if approval_on is None and _db:
        approval_on = _db.get_setting("approval_required", "1") == "1"
    approval_on = bool(approval_on) if approval_on is not None else True
    approval_label = ("🟢 File Approval: ON" if approval_on
                      else "🔴 File Approval: OFF")
    approval_style = "success" if approval_on else "danger"

    m.add(_btn(approval_label, callback_data="adm_toggle_approval", style=approval_style))
    m.add(_btn("📥 Pending Files", callback_data="adm_pending_files", style="primary"))

    fsub_style = "success" if state.force_sub_enabled else "danger"
    lock_style = "danger"  if state.bot_locked         else "success"
    fsub_icon  = "🟢" if state.force_sub_enabled else "🔴"
    lock_icon  = "🔒" if state.bot_locked        else "🔓"
    m.add(
        _btn(f"{fsub_icon} Force Subscribe",
             callback_data="adm_fsub_toggle", style=fsub_style),
        _btn(f"{lock_icon} Bot Lock",
             callback_data="adm_lock_toggle", style=lock_style),
    )
    m.add(_btn("🏠 Main Menu", callback_data="go_home", style="primary"))
    return m


def channels_manage_kb():
    channels = _db.get_all_channels() if _db else []
    m = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        icon = "🟢" if ch['is_active'] else "🔴"
        toggle_key = str(ch.get('channel_id') or ch.get('channel_username', ''))
        m.add(_btn(
            f"{icon} @{ch['channel_username']} — {ch['channel_name']}",
            callback_data=f"ch_toggle:{toggle_key}",
            style="success" if ch['is_active'] else "danger",
        ))
    m.add(_btn("➕ Add Channel",    callback_data="ch_add",     style="success"))
    m.add(_btn("🗑 Remove Channel", callback_data="ch_remove",  style="danger"))
    m.add(_btn("🔙 Back to Admin",  callback_data="menu_admin", style="primary"))
    return m