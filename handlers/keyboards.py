"""
KEYBOARDS MODULE v12.0 — FINAL
─────────────────────────────────────────────────────────
সব বাটনে callback_data/url আছে
─────────────────────────────────────────────────────────
"""
from telebot import types
from config import PLAN_LIMITS, PAYMENT_METHODS
from core.state import state
from handlers.premium_emoji import btn, premiumize_emoji_html, strip_custom_emoji

_db = None


def init_keyboards(db_instance):
    global _db
    _db = db_instance


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════════
def main_menu_kb(uid, is_premium=False):
    """Normal unicode emoji on all buttons (is_premium ignored)."""
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("My Bots",      style="primary", emoji_key="robot",  callback_data="menu_mybots"),
        btn("Deploy Bot",   style="success", emoji_key="send",   callback_data="menu_deploy"),
    )
    m.add(
        btn("Subscription", style="primary", emoji_key="gem",    callback_data="menu_sub"),
        btn("Wallet",       style="primary", emoji_key="money",  callback_data="menu_wallet"),
    )
    m.add(
        btn("Referral",     style="primary", emoji_key="gift",   callback_data="menu_ref"),
        btn("Promo Code",   style="success", emoji_key="promo",  callback_data="menu_promo"),
    )
    m.add(
        btn("Statistics",   style="primary", emoji_key="chart",  callback_data="menu_stats"),
        btn("Running Bots", style="success", emoji_key="green",  callback_data="menu_running"),
    )
    m.add(
        btn("Speed Test",   style="primary", emoji_key="flash",  callback_data="menu_speed"),
        btn("Help",         style="primary", emoji_key="book",   callback_data="menu_help"),
    )
    m.add(
        btn("Settings",     style="primary", emoji_key="gear",   callback_data="menu_settings"),
        btn("Support",      style="primary", emoji_key="speech", callback_data="menu_support"),
    )
    notif_count = _db.unread_count(uid) if _db else 0
    notif_label = f"Notifications ({notif_count})" if notif_count > 0 else "Notifications"
    m.add(btn(notif_label, style="primary", emoji_key="bell", callback_data="menu_notif"))
    if state.is_admin(uid):
        m.add(btn("Admin Panel", style="danger", emoji_key="crown", callback_data="menu_admin"))
    m.add(btn("Contact Developer", url="https://t.me/shihab23",
              style="primary", emoji_key="contact"))
    return m


# ═══════════════════════════════════════════════════════════════════════════════
#  HELP MENU
# ═══════════════════════════════════════════════════════════════════════════════
def help_menu_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("How to Deploy",   style="primary", emoji_key="send",    callback_data="help_deploy"),
        btn("Managing Bots",   style="primary", emoji_key="robot",   callback_data="help_bots"),
    )
    m.add(
        btn("Plans & Pricing", style="primary", emoji_key="gem",     callback_data="help_plans"),
        btn("Payment Guide",   style="primary", emoji_key="card",    callback_data="help_payment"),
    )
    m.add(
        btn("Referral System", style="primary", emoji_key="gift",    callback_data="help_referral"),
        btn("Wallet Guide",    style="primary", emoji_key="money",   callback_data="help_wallet"),
    )
    m.add(
        btn("Auto Detection",  style="primary", emoji_key="search",  callback_data="help_detect"),
        btn("Supported Files", style="primary", emoji_key="box",     callback_data="help_files"),
    )
    m.add(
        btn("FAQ",             style="primary", emoji_key="speech",  callback_data="help_faq"),
        btn("Troubleshoot",    style="primary", emoji_key="gear",    callback_data="help_trouble"),
    )
    m.add(
        btn("All Commands",    style="primary", emoji_key="logs",    callback_data="help_commands"),
        btn("Contact Support", style="primary", emoji_key="contact", callback_data="help_contact"),
    )
    m.add(btn("Back to Main Menu", style="primary", emoji_key="home", callback_data="go_home"))
    return m


# ═══════════════════════════════════════════════════════════════════════════════
#  BACK BUTTONS
# ═══════════════════════════════════════════════════════════════════════════════
def back_btn(cb="go_home", text="Main Menu"):
    m = types.InlineKeyboardMarkup()
    m.add(btn(text, style="primary", emoji_key="home", callback_data=cb))
    return m


def back_help_btn():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("Back to Help", style="primary", emoji_key="back", callback_data="menu_help"),
        btn("Main Menu",    style="primary", emoji_key="home", callback_data="go_home"),
    )
    return m


# ═══════════════════════════════════════════════════════════════════════════════
#  BOT ACTION
# ═══════════════════════════════════════════════════════════════════════════════
def bot_action_kb(bid, is_live, auto_restart=False, approval_status='approved',
                  allow_auto_restart=True):
    m = types.InlineKeyboardMarkup(row_width=2)
    if approval_status == 'pending':
        m.add(btn("Info", style="primary", emoji_key="bulb", callback_data=f"bot_detail:{bid}"))
        m.add(btn("Back", style="primary", emoji_key="back", callback_data="menu_mybots"))
        return m
    if approval_status == 'rejected':
        m.add(btn("Delete", style="danger", emoji_key="trash", callback_data=f"bot_del:{bid}"))
        m.add(btn("Back",   style="primary", emoji_key="back", callback_data="menu_mybots"))
        return m

    if auto_restart:
        ar_label, ar_style, ar_key = "Auto Restart: ON",  "success", "refresh"
    else:
        ar_label, ar_style, ar_key = "Auto Restart: OFF", "danger",  "refresh"

    if is_live:
        m.add(
            btn("Stop",      style="danger",  emoji_key="stop",    callback_data=f"bot_stop:{bid}"),
            btn("Restart",   style="success", emoji_key="refresh", callback_data=f"bot_restart:{bid}"),
        )
        m.add(
            btn("Logs",      style="primary", emoji_key="logs",    callback_data=f"bot_logs:{bid}"),
            btn("Resources", style="primary", emoji_key="chart",   callback_data=f"bot_res:{bid}"),
        )
        m.add(
            btn("Pip Install", style="success", emoji_key="pip", callback_data=f"bot_pip:{bid}"),
        )
        if allow_auto_restart:
            m.add(btn(ar_label, style=ar_style, emoji_key=ar_key,
                      callback_data=f"bot_autorestart:{bid}"))
    else:
        if allow_auto_restart:
            m.add(
                btn("Start",  style="success", emoji_key="play", callback_data=f"bot_start:{bid}"),
                btn(ar_label, style=ar_style,  emoji_key=ar_key, callback_data=f"bot_autorestart:{bid}"),
            )
        else:
            m.add(btn("Start", style="success", emoji_key="play", callback_data=f"bot_start:{bid}"))
        m.add(
            btn("Logs",      style="primary", emoji_key="logs",     callback_data=f"bot_logs:{bid}"),
            btn("Download",  style="primary", emoji_key="download", callback_data=f"bot_dl:{bid}"),
        )
        m.add(
            btn("Pip Install", style="success", emoji_key="pip",    callback_data=f"bot_pip:{bid}"),
            btn("Re-detect",   style="primary", emoji_key="search", callback_data=f"bot_redetect:{bid}"),
        )
        m.add(btn("Delete", style="danger", emoji_key="trash", callback_data=f"bot_del:{bid}"))

    m.add(btn("Back to My Bots", style="primary", emoji_key="back", callback_data="menu_mybots"))
    return m


# ═══════════════════════════════════════════════════════════════════════════════
#  FILE APPROVAL
# ═══════════════════════════════════════════════════════════════════════════════
def file_approval_kb(bid):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("Approve", style="success", emoji_key="check", callback_data=f"approve_file:{bid}"),
        btn("Reject",  style="danger",  emoji_key="cross", callback_data=f"reject_file:{bid}"),
    )
    return m


def pending_files_kb():
    m = types.InlineKeyboardMarkup(row_width=1)
    if not _db:
        return m
    rows = _db.pending_bots()
    for b in rows[:20]:
        m.add(btn(
            f"#{b['bot_id']} {b['bot_name'][:18]} — User {b['user_id']}",
            style="primary", emoji_key="clock",
            callback_data=f"review_file:{b['bot_id']}"
        ))
    if not rows:
        m.add(btn("No pending files", style="primary", emoji_key="box", callback_data="menu_admin"))
    m.add(btn("Back to Admin", style="primary", emoji_key="back", callback_data="menu_admin"))
    return m


# ═══════════════════════════════════════════════════════════════════════════════
#  DEPLOY
# ═══════════════════════════════════════════════════════════════════════════════
def deploy_choice_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("Upload File",  style="success", emoji_key="send",   callback_data="deploy_upload"),
        btn("GitHub Repo",  style="primary", emoji_key="planet", callback_data="deploy_github"),
    )
    m.add(btn("Main Menu", style="primary", emoji_key="home", callback_data="go_home"))
    return m


def github_repo_type_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("Public Repo",  style="success", emoji_key="planet", callback_data="gh_type:public"),
        btn("Private Repo", style="danger",  emoji_key="lock",   callback_data="gh_type:private"),
    )
    m.add(btn("Cancel", style="danger", emoji_key="cross", callback_data="go_home"))
    return m


# ═══════════════════════════════════════════════════════════════════════════════
#  SUBSCRIPTION
# ═══════════════════════════════════════════════════════════════════════════════
def sub_choice_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("Tk (bKash/etc)", style="primary", emoji_key="money", callback_data="sub_tk"),
        btn("Telegram Star",  style="success", emoji_key="star",  callback_data="sub_star"),
    )
    m.add(btn("Main Menu", style="primary", emoji_key="home", callback_data="go_home"))
    return m


def star_plan_kb():
    from config import STAR_PLAN_PRICES
    m = types.InlineKeyboardMarkup(row_width=1)
    for k, stars in STAR_PLAN_PRICES.items():
        p = PLAN_LIMITS.get(k, {})
        slots = '♾️' if p.get('max_bots') == -1 else str(p.get('max_bots'))
        m.add(btn(
            f"{p.get('name', k)} — {slots} bots — {stars} Stars",
            style="success", emoji_key="star",
            callback_data=f"star_buy:{k}"
        ))
    m.add(btn("Back", style="primary", emoji_key="back", callback_data="menu_sub"))
    return m


# ═══════════════════════════════════════════════════════════════════════════════
#  PROMO
# ═══════════════════════════════════════════════════════════════════════════════
def adm_promo_choice_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("Tk (Wallet)",  style="primary", emoji_key="money", callback_data="adm_promo_tk"),
        btn("% (Discount)", style="success", emoji_key="gem",   callback_data="adm_promo_pct"),
    )
    m.add(btn("Admin", style="primary", emoji_key="back", callback_data="menu_admin"))
    return m


def promo_choice_kb():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("Tk Wallet",  style="primary", emoji_key="money", callback_data="promo_tk"),
        btn("% Discount", style="success", emoji_key="gem",   callback_data="promo_pct"),
    )
    m.add(btn("Main Menu", style="primary", emoji_key="home", callback_data="go_home"))
    return m


def promo_discount_plan_kb(code, discount_pct):
    m = types.InlineKeyboardMarkup(row_width=1)
    for k, p in PLAN_LIMITS.items():
        if k == 'free':
            continue
        original = p['price']
        discounted = int(original * (100 - discount_pct) / 100)
        m.add(btn(
            f"{p['name']} — {original}→{discounted} BDT (-{discount_pct}%)",
            style="success", emoji_key="gem",
            callback_data=f"promo_plan:{code}:{k}"
        ))
    m.add(btn("Cancel", style="danger", emoji_key="cross", callback_data="go_home"))
    return m


def promo_pay_method_kb(code, plan, amount):
    m = types.InlineKeyboardMarkup(row_width=2)
    for k, v in PAYMENT_METHODS.items():
        m.add(btn(
            f"{v['name']}", style="primary", emoji_key="card",
            callback_data=f"promo_pay:{code}:{plan}:{k}"
        ))
    m.add(btn("Pay from Wallet", style="success", emoji_key="money",
              callback_data=f"promo_wallet:{code}:{plan}"))
    m.add(btn("Back", style="primary", emoji_key="back", callback_data="go_home"))
    return m


# ═══════════════════════════════════════════════════════════════════════════════
#  PLANS & PAYMENT
# ═══════════════════════════════════════════════════════════════════════════════
def plan_kb():
    m = types.InlineKeyboardMarkup(row_width=1)
    for k, p in PLAN_LIMITS.items():
        if k == 'free':
            continue
        slots = '♾️' if p['max_bots'] == -1 else str(p['max_bots'])
        m.add(btn(
            f"{p['name']} — {slots} bots — {p['price']} BDT",
            style="success", emoji_key="gem",
            callback_data=f"plan_select:{k}"
        ))
    m.add(btn("Main Menu", style="primary", emoji_key="home", callback_data="go_home"))
    return m


def pay_method_kb(pk):
    m = types.InlineKeyboardMarkup(row_width=2)
    for k, v in PAYMENT_METHODS.items():
        m.add(btn(
            f"{v['name']}", style="primary", emoji_key="card",
            callback_data=f"pay_method:{pk}:{k}"
        ))
    m.add(btn("Pay from Wallet", style="success", emoji_key="money",
              callback_data=f"pay_wallet:{pk}"))
    m.add(
        btn("Back to Plans", style="primary", emoji_key="back", callback_data="menu_sub"),
        btn("Main Menu",     style="primary", emoji_key="home", callback_data="go_home"),
    )
    return m


def pay_approve_kb(pid):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("Approve", style="success", emoji_key="check", callback_data=f"pay_approve:{pid}"),
        btn("Reject",  style="danger",  emoji_key="cross", callback_data=f"pay_reject:{pid}"),
    )
    return m


# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════════════════
def admin_kb(approval_on=None):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        btn("All Users",     style="primary", emoji_key="users", callback_data="adm_users"),
        btn("Statistics",    style="primary", emoji_key="chart", callback_data="adm_stats"),
    )
    m.add(
        btn("Pending Payments", style="primary", emoji_key="card",      callback_data="adm_payments"),
        btn("Broadcast",        style="primary", emoji_key="megaphone", callback_data="adm_broadcast"),
    )
    m.add(
        btn("Add Subscription",    style="success", emoji_key="plus",  callback_data="adm_addsub"),
        btn("Remove Subscription", style="danger",  emoji_key="minus", callback_data="adm_remsub"),
    )
    m.add(
        btn("Ban User",   style="danger",  emoji_key="ban",   callback_data="adm_ban"),
        btn("Unban User", style="success", emoji_key="check", callback_data="adm_unban"),
    )
    m.add(
        btn("Force Sub Channels", style="primary", emoji_key="megaphone", callback_data="adm_channels"),
        btn("Promo Codes",        style="primary", emoji_key="promo",     callback_data="adm_promo"),
    )
    m.add(
        btn("Support Tickets", style="primary", emoji_key="speech",  callback_data="adm_tickets"),
        btn("System Info",     style="primary", emoji_key="monitor", callback_data="adm_system"),
    )
    m.add(
        btn("Stop All Bots", style="danger",  emoji_key="stop",     callback_data="adm_stopall"),
        btn("Backup DB",     style="primary", emoji_key="download", callback_data="adm_backup"),
    )
    m.add(
        btn("Admin Logs",    style="primary", emoji_key="logs",  callback_data="adm_logs"),
        btn("Give Balance",  style="success", emoji_key="money", callback_data="adm_give"),
    )
    m.add(
        btn("User Info",          style="primary", emoji_key="search", callback_data="adm_userinfo"),
        btn("Send Notification",  style="primary", emoji_key="bell",   callback_data="adm_notify"),
    )
    m.add(btn("Cleanup Storage", style="danger", emoji_key="trash", callback_data="adm_cleanup"))

    if approval_on is None and _db:
        approval_on = _db.get_setting("approval_required", "1") == "1"
    approval_on = bool(approval_on) if approval_on is not None else True
    approval_label = ("File Approval: ON" if approval_on else "File Approval: OFF")
    approval_style = "success" if approval_on else "danger"
    approval_key   = "lock" if approval_on else "key"

    m.add(btn(approval_label, style=approval_style, emoji_key=approval_key,
              callback_data="adm_toggle_approval"))
    m.add(btn("Pending Files", style="primary", emoji_key="box",
              callback_data="adm_pending_files"))

    fsub_style = "success" if state.force_sub_enabled else "danger"
    lock_style = "danger"  if state.bot_locked         else "success"
    fsub_key   = "green"   if state.force_sub_enabled else "siren"
    lock_key   = "lock"    if state.bot_locked         else "key"

    m.add(
        btn("Force Subscribe", style=fsub_style, emoji_key=fsub_key, callback_data="adm_fsub_toggle"),
        btn("Bot Lock",        style=lock_style, emoji_key=lock_key, callback_data="adm_lock_toggle"),
    )
    m.add(btn("Main Menu", style="primary", emoji_key="home", callback_data="go_home"))
    return m


def channels_manage_kb():
    channels = _db.get_all_channels() if _db else []
    m = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        style = "success" if ch['is_active'] else "danger"
        toggle_key = str(ch.get('channel_id') or ch.get('channel_username', ''))
        key = "green" if ch['is_active'] else "siren"
        m.add(btn(
            f"@{ch['channel_username']} — {ch['channel_name']}",
            style=style, emoji_key=key,
            callback_data=f"ch_toggle:{toggle_key}"
        ))
    m.add(btn("Add Channel",    style="success", emoji_key="plus",  callback_data="ch_add"))
    m.add(btn("Remove Channel", style="danger",  emoji_key="trash", callback_data="ch_remove"))
    m.add(btn("Back to Admin",  style="primary", emoji_key="back",  callback_data="menu_admin"))
    return m