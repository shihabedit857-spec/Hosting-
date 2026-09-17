"""
╔═══════════════════════════════════════════════════════════╗
║  🌟 APON HOSTING PANEL — Premium Edition v6.1 🌟         ║
║  Developer: @developer_apon                               ║
║  Full Features: GitHub, Approval, Stars, Promo, Auto-Restart ║
╚═══════════════════════════════════════════════════════════╝
"""

import telebot, subprocess, os, zipfile, tempfile, shutil, time
import logging, signal, threading, re, sys, atexit
import requests, traceback
from telebot import types
from datetime import datetime, timedelta
from flask import Flask, jsonify
from threading import Thread

from config import (
    TOKEN, OWNER_ID, ADMIN_ID, BOT_USERNAME, YOUR_USERNAME,
    UPDATE_CHANNEL, BRAND, BRAND_VER, BRAND_TAG, BRAND_FOOTER,
    PLAN_LIMITS, PAYMENT_METHODS, DEFAULT_FORCE_CHANNELS,
    FLASK_PORT, LOGS_DIR, UPLOAD_DIR, BACKUP_DIR, REF_BONUS_DAYS, REF_COMMISSION,
    STAR_PLAN_PRICES
)
from database import db
from core.state import state, bot_scripts
from core.runner import (
    det, run_bot_script, thread_monitor, thread_backup,
    thread_expiry, thread_storage_monitor, thread_daily_report,
    thread_free_bot_limit, thread_per_bot_auto_restart,
    init_runner
)
from handlers.bot_safe import (
    init_safe, safe_send, safe_edit, safe_delete,
    safe_answer, safe_reply, forward_error, forward_crash
)
from handlers.keyboards import (
    init_keyboards, main_menu_kb, help_menu_kb, back_btn, back_help_btn,
    bot_action_kb, plan_kb, pay_method_kb, admin_kb, pay_approve_kb,
    channels_manage_kb, deploy_choice_kb, github_repo_type_kb,
    file_approval_kb, pending_files_kb,
    sub_choice_kb, star_plan_kb,
    adm_promo_choice_kb, promo_choice_kb,
    promo_discount_plan_kb, promo_pay_method_kb,
)
from utils.helpers import (
    get_uptime, fmt_size, gen_ref_code, time_left, user_folder,
    is_running, bot_running, cleanup_script, kill_tree, bot_res,
    sys_stats, rate_check
)
from utils.github_helper import parse_github_url, download_github_repo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'apon.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('APON')

bot = telebot.TeleBot(
    TOKEN, parse_mode='HTML', threaded=True, num_threads=32,
    use_class_middlewares=True
)

init_safe(bot, OWNER_ID)
init_keyboards(db)
init_runner(bot, db, forward_error, safe_send)

github_sessions = {}

from telebot.handler_backends import BaseMiddleware, CancelUpdate

class PrivateOnlyMiddleware(BaseMiddleware):
    def __init__(self):
        self.update_types = ['message', 'callback_query']

    def pre_process(self, update_obj, data):
        chat = getattr(update_obj, 'chat', None) or getattr(getattr(update_obj, 'message', None), 'chat', None)
        if chat is not None and chat.type != 'private':
            return CancelUpdate()

    def post_process(self, update_obj, data, exception=None):
        pass

bot.setup_middleware(PrivateOnlyMiddleware())


@bot.message_handler(content_types=['new_chat_members'])
def on_added_to_group(msg):
    try:
        bot_id = bot.get_me().id
        added_ids = [m.id for m in (msg.new_chat_members or [])]
        if bot_id in added_ids:
            try:
                bot.send_message(msg.chat.id,
                    f"⚠️ This bot is for <b>personal use only</b>.\n{BRAND_FOOTER}")
            except Exception:
                pass
            bot.leave_chat(msg.chat.id)
    except Exception as e:
        logger.warning(f"on_added_to_group: {e}")

flask_app = Flask('AponHosting')

@flask_app.route('/')
def flask_home():
    return "<h1>🌟 SB HOSTING PANEL 🌟</h1><p>Status: ✅ Online</p>"

@flask_app.route('/health')
def flask_health():
    return jsonify({
        "status": "ok",
        "uptime": get_uptime(),
        "version": "6.1",
        "running_bots": len([k for k in bot_scripts if is_running(k)])
    })

def keep_alive():
    try:
        Thread(target=lambda: flask_app.run(host='0.0.0.0', port=FLASK_PORT),
               daemon=True).start()
    except Exception as e:
        logger.warning(f"Flask keep-alive failed (port {FLASK_PORT}): {e}")


def check_joined(uid):
    if not state.force_sub_enabled:
        return True, []
    if state.is_admin(uid):
        return True, []
    channels = db.get_active_channels()
    if not channels:
        ch_list = [(u, n) for u, n in DEFAULT_FORCE_CHANNELS.items()]
    else:
        ch_list = [(c['channel_username'], c['channel_name']) for c in channels]
    not_joined = []
    for cu, cn in ch_list:
        try:
            mem = bot.get_chat_member(f"@{cu}", uid)
            if mem.status in ['left', 'kicked']:
                not_joined.append((cu, cn))
        except telebot.apihelper.ApiTelegramException:
            not_joined.append((cu, cn))
        except:
            continue
    return len(not_joined) == 0, not_joined


def force_sub_kb(not_joined):
    m = types.InlineKeyboardMarkup(row_width=1)
    for cu, cn in not_joined:
        m.add(types.InlineKeyboardButton(
            f"📢 Join {cn}", url=f"https://t.me/{cu}", style="primary"))
    m.add(types.InlineKeyboardButton(
        "✅ I've Joined — Verify", callback_data="verify_join", style="success"))
    return m


def send_force_sub(cid, nj):
    ch_text = ""
    for i, (cu, cn) in enumerate(nj, 1):
        ch_text += f"  {i}. <b>{cn}</b> — @{cu}\n"
    safe_send(cid,
        f"🔒 <b>CHANNEL VERIFICATION REQUIRED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚠️ You must join our channels to use this bot!\n\n"
        f"{ch_text}\n"
        f"👇 Join all channels, then press <b>Verify</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=force_sub_kb(nj))


def approval_is_on():
    try:
        return db.get_setting("approval_required", "1") == "1"
    except Exception:
        return True


def get_role_label(uid):
    if uid == OWNER_ID:
        return "👑 Owner"
    if state.is_admin(uid):
        return "⭐ Admin"
    u = db.get_user(uid)
    if not u:
        return "🆓 Free"
    pl = PLAN_LIMITS.get(u.get('plan', 'free'), PLAN_LIMITS['free'])
    return pl['name']


def plan_allows_auto_restart(user_id):
    if user_id == OWNER_ID or state.is_admin(user_id):
        return True
    try:
        pl = db.get_plan(user_id)
        return bool(pl.get('auto_restart', False))
    except Exception:
        return False


def show_admin_panel(uid):
    s = db.stats()
    rn = len([k for k in bot_scripts if is_running(k)])
    tickets = len(db.open_tickets())
    safe_send(uid,
        f"👑 <b>ADMIN PANEL</b>\n{BRAND_TAG}\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Total Users: {s['users']} (+{s['today']} today)\n"
        f"🤖 Running Bots: {rn}\n💎 Active Subs: {s['active_subs']}\n"
        f"🚫 Banned: {s['banned']}\n💳 Pending Payments: {s['pending']}\n"
        f"🎫 Open Tickets: {tickets}\n💰 Total Revenue: {s['revenue']} BDT\n\n"
        f"🔐 Force Sub: {'🟢 ON' if state.force_sub_enabled else '🔴 OFF'}\n"
        f"🔒 Bot Lock: {'🔒 LOCKED' if state.bot_locked else '🔓 OPEN'}\n"
        f"📥 File Approval: {'🟢 ON' if approval_is_on() else '🔴 OFF'}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=admin_kb(approval_is_on()))


def show_user_info(admin_uid, target_uid):
    u = db.get_user(target_uid)
    if not u:
        safe_send(admin_uid, f"❌ User <code>{target_uid}</code> not found!")
        return
    pl = PLAN_LIMITS.get(u.get('plan', 'free'), PLAN_LIMITS['free'])
    bc = db.bot_count(target_uid)
    bots_list = db.get_bots(target_uid)
    running = sum(1 for b in bots_list if bot_running(target_uid, b['bot_name']))
    role_label = get_role_label(target_uid)
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("🚫 Ban",   callback_data=f"adm_ban_direct:{target_uid}",   style="danger"),
        types.InlineKeyboardButton("✅ Unban", callback_data=f"adm_unban_direct:{target_uid}", style="success"),
    )
    m.add(types.InlineKeyboardButton("🔙 Admin", callback_data="menu_admin", style="primary"))
    safe_send(admin_uid,
        f"👤 <b>User Info</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{target_uid}</code>\n"
        f"📛 Name: {u.get('full_name', '?')}\n"
        f"👤 @{u.get('username', 'N/A')}\n"
        f"🚫 Banned: {'Yes' if u.get('is_banned') else 'No'}\n\n"
        f"📦 Plan: {role_label}\n"
        f"📅 Expires: {time_left(u.get('subscription_end'))}\n"
        f"👑 Lifetime: {'Yes' if u.get('is_lifetime') else 'No'}\n\n"
        f"🤖 Bots: {bc} (🟢 {running})\n"
        f"💰 Wallet: {u.get('wallet_balance', 0)} BDT\n"
        f"💳 Spent: {u.get('total_spent', 0)} BDT\n\n"
        f"👥 Refs: {u.get('referral_count', 0)}\n"
        f"🔑 Code: <code>{u.get('referral_code', '?')}</code>\n"
        f"📅 Joined: {str(u.get('created_at', '?'))[:16]}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=m)


def do_broadcast_send(admin_uid, text, reply_cid=None):
    users = db.get_all_users()
    sent_count = [0]
    failed_count = [0]
    lock = threading.Lock()
    cid = reply_cid or admin_uid
    prog = safe_send(cid, f"📢 Broadcasting to {len(users)} users...")
    total = len(users)

    def send_one(u):
        try:
            safe_send(u['user_id'], f"📢 <b>Announcement</b>\n\n{text}\n{BRAND_FOOTER}")
            with lock: sent_count[0] += 1
        except Exception:
            with lock: failed_count[0] += 1

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(send_one, u) for u in users]
        for i, future in enumerate(as_completed(futures)):
            if i % 50 == 0 and prog:
                safe_edit(
                    f"📢 Progress: {sent_count[0]+failed_count[0]}/{total}\n"
                    f"✅ {sent_count[0]} | ❌ {failed_count[0]}",
                    cid, prog.message_id)
            time.sleep(0.033)

    if prog:
        safe_edit(
            f"📢 <b>Broadcast Complete!</b>\n\n"
            f"✅ Sent: {sent_count[0]}\n❌ Failed: {failed_count[0]}\n👥 Total: {total}",
            cid, prog.message_id,
            reply_markup=back_btn("menu_admin", "🔙 Admin"))
    db.admin_log(admin_uid, 'broadcast', det=f"sent:{sent_count[0]} failed:{failed_count[0]}")


def handle_pay_text(msg):
    uid = msg.from_user.id
    s = state.get_pay_state(uid)
    if not s or s.get('step') != 'wait_trx':
        return
    try:
        trx = msg.text.strip() if msg.text else 'SCREENSHOT'
        if not trx or len(trx) < 3:
            return safe_reply(msg, "❌ Please send a valid Transaction ID!")

        if s.get('promo_code'):
            code = s['promo_code']
            if db.user_used_promo(uid, code):
                return safe_reply(msg, "❌ This promo code was already used!")
            db.mark_user_promo_used(uid, code)
            try: db.use_promo(code)
            except Exception: pass

        pid = db.add_pay(uid, s['amount'], s['method'], trx, s['plan'], 30)
        state.clear_pay_state(uid)
        user_msg = safe_send(uid,
            f"✅ <b>PAYMENT SUBMITTED!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 Payment ID: #{pid}\n"
            f"💰 Amount: {s['amount']} BDT\n"
            f"💳 Method: {s['method']}\n"
            f"📦 Plan: {PLAN_LIMITS.get(s['plan'], {}).get('name', s['plan'])}\n"
            f"🔖 TRX: <code>{trx}</code>\n\n"
            f"⏳ Waiting for admin approval...\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            reply_markup=back_btn())
        if user_msg:
            try:
                db.set_payment_msgs(pid, user_chat_id=uid, user_msg_id=user_msg.message_id)
            except Exception: pass

        u = db.get_user(uid)
        method_info = PAYMENT_METHODS.get(s['method'], {})
        admin_msg_list = []
        for aid in state.admin_ids:
            am = safe_send(aid,
                f"💳 <b>NEW PAYMENT!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 {u.get('full_name', '?') if u else '?'} (<code>{uid}</code>)\n"
                f"📦 Plan: {s['plan']}\n"
                f"💰 Amount: {s['amount']} BDT\n"
                f"{method_info.get('icon', '💳')} {method_info.get('name', s['method'])}\n"
                f"🔖 TRX: <code>{trx}</code>\n"
                f"🆔 #{pid}\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                reply_markup=pay_approve_kb(pid))
            if am:
                admin_msg_list.append({'cid': aid, 'mid': am.message_id})
        if admin_msg_list:
            try:
                db.set_payment_msgs(pid, admin_list=admin_msg_list)
            except Exception: pass
    except Exception as e:
        forward_crash("handle_pay_text", e, uid)
        state.clear_pay_state(uid)


def handle_github_flow(msg):
    uid = msg.from_user.id
    sess = github_sessions.get(uid)
    if not sess:
        return
    text = (msg.text or '').strip()

    if text.lower() == '/cancel':
        github_sessions.pop(uid, None)
        return safe_reply(msg, "❌ GitHub deploy cancelled.",
                          reply_markup=back_btn("menu_deploy", "🔙 Back"))

    step = sess.get('step')

    if step == 'token':
        if len(text) < 20:
            return safe_reply(msg, "❌ Token too short. Send a valid GitHub PAT\n(or /cancel to abort).")
        sess['token'] = text
        sess['step'] = 'url'
        return safe_reply(msg,
            f"✅ <b>Token saved!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Now send the GitHub repository URL.\n\n"
            f"<b>Examples:</b>\n"
            f"  <code>https://github.com/user/repo</code>\n"
            f"  <code>https://github.com/user/repo/tree/dev</code>\n\n"
            f"✉️ Send <code>/cancel</code> to abort.\n"
            f"━━━━━━━━━━━━━━━━━━━━")

    if step == 'url':
        try:
            owner, repo, branch = parse_github_url(text)
        except Exception as e:
            return safe_reply(msg, f"❌ Invalid GitHub URL: <code>{e}</code>")
        sess.update({'url': text, 'owner': owner, 'repo': repo, 'branch': branch})
        repo_type = sess.get('repo_type', 'public')
        type_icon = "🔒 Private" if repo_type == 'private' else "🌐 Public"
        sent = safe_reply(msg,
            f"🐙 <b>Repo detected</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Owner:  <code>{owner}</code>\n"
            f"📦 Repo:   <code>{repo}</code>\n"
            f"🌿 Branch: <code>{branch}</code>\n"
            f"🔐 Type:   {type_icon}\n\n"
            f"📡 Starting download...")
        if sent:
            threading.Thread(target=_process_github_download,
                             args=(uid, msg.chat.id, sent.message_id),
                             daemon=True, name=f"gh_{uid}").start()
        return


def _gh_progress(chat_id, msg_id, text):
    try:
        safe_edit(f"🐙 <b>GITHUB DEPLOY</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{text}\n━━━━━━━━━━━━━━━━━━━━",
                  chat_id, msg_id)
    except Exception:
        pass


def _process_github_download(uid, chat_id, msg_id):
    sess = github_sessions.get(uid)
    if not sess:
        safe_send(chat_id, "❌ Session expired. Start again.")
        return
    owner  = sess['owner']; repo = sess['repo']
    branch = sess['branch']; url = sess['url']
    token  = sess.get('token')

    try:
        _gh_progress(chat_id, msg_id, "📡 Establishing link...\n[▓▓░░░░░░░░] 20%")
        time.sleep(0.6)
        _gh_progress(chat_id, msg_id, "🔗 Connecting to repo...\n[▓▓▓▓░░░░░░] 40%")
        time.sleep(0.6)
        zip_bytes = download_github_repo(owner, repo, branch, token)
        _gh_progress(chat_id, msg_id, "📥 Downloading repo...\n[▓▓▓▓▓▓▓░░░] 70%")
        time.sleep(0.4)
        _gh_progress(chat_id, msg_id, "📥 Extracting files...\n[▓▓▓▓▓▓▓▓▓░] 90%")
    except Exception as e:
        _gh_progress(chat_id, msg_id, f"❌ Download failed:\n<code>{str(e)[:200]}</code>")
        github_sessions.pop(uid, None)
        return

    try:
        bn = f"{repo}_{branch}".replace(' ', '_')
        uf = user_folder(uid)
        ed = os.path.join(uf, bn)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp.write(zip_bytes)
            tp = tmp.name

        try:
            with zipfile.ZipFile(tp, 'r') as z:
                extract_path = os.path.realpath(ed)
                for n in z.namelist():
                    member = os.path.realpath(os.path.join(extract_path, n))
                    if not member.startswith(extract_path + os.sep) and member != extract_path:
                        _gh_progress(chat_id, msg_id, "❌ Suspicious paths in repo — aborted.")
                        os.unlink(tp); github_sessions.pop(uid, None); return
                if os.path.exists(ed): shutil.rmtree(ed, ignore_errors=True)
                os.makedirs(ed, exist_ok=True)
                z.extractall(ed)
                items = os.listdir(ed)
                if len(items) == 1 and os.path.isdir(os.path.join(ed, items[0])):
                    inner = os.path.join(ed, items[0])
                    for item in os.listdir(inner):
                        src = os.path.join(inner, item)
                        dst = os.path.join(ed, item)
                        if os.path.exists(dst):
                            shutil.rmtree(dst) if os.path.isdir(dst) else os.remove(dst)
                        shutil.move(src, dst)
                    try: os.rmdir(inner)
                    except Exception: pass
        finally:
            try: os.unlink(tp)
            except Exception: pass

        entry, ft, report = det.report(ed)
        if not entry:
            _gh_progress(chat_id, msg_id,
                "❌ No runnable entry file found in the repo!\n\n"
                "Make sure it has main.py / app.py / bot.py / index.js.")
            github_sessions.pop(uid, None)
            return

        bid = db.add_bot(uid, bn, ed, entry, ft, '', len(zip_bytes), '')

        if approval_is_on():
            db.set_approval_status(bid, 'pending')
            _gh_progress(chat_id, msg_id,
                f"✅ <b>Download complete!</b>\n\n"
                f"📦 <code>{bn[:25]}</code>\n🆔 Bot ID: #{bid}\n"
                f"🔍 Detection:\n{report}\n\n⏳ Status: Pending admin approval")
            try:
                db.update_bot(bid, pending_chat_id=chat_id, pending_msg_id=msg_id)
            except Exception: pass
            for aid in state.admin_ids:
                try:
                    safe_send(aid,
                        f"📥 <b>NEW GITHUB REPO — PENDING APPROVAL</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"👤 User: <code>{uid}</code>\n"
                        f"🐙 Repo: <code>{owner}/{repo}</code>\n"
                        f"🌿 Branch: <code>{branch}</code>\n"
                        f"🔑 Token: {'Yes (private)' if token else 'Public'}\n"
                        f"📄 Entry: <code>{entry}</code>\n"
                        f"🆔 Bot ID: #{bid}\n"
                        f"🔗 URL: <code>{url[:60]}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━",
                        reply_markup=file_approval_kb(bid))
                except Exception as ex:
                    forward_error("GH_APPROVAL_NOTIFY", ex, aid)
        else:
            db.set_approval_status(bid, 'approved')
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(
                types.InlineKeyboardButton("▶️ Start Now",
                                           callback_data=f"bot_start:{bid}",
                                           style="success"),
                types.InlineKeyboardButton("🤖 My Bots",
                                           callback_data="menu_mybots",
                                           style="primary"),
            )
            safe_send(chat_id,
                f"✅ <b>GITHUB DEPLOY COMPLETE!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🐙 Repo: <code>{owner}/{repo}</code>\n"
                f"🌿 Branch: <code>{branch}</code>\n"
                f"📦 Bot: <code>{bn[:25]}</code>\n"
                f"🆔 Bot ID: #{bid}\n\n"
                f"🔍 <b>Detection:</b>\n{report}\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                reply_markup=mk)
            u_info = db.get_user(uid)
            for aid in state.admin_ids:
                try:
                    safe_send(aid,
                        f"📥 <b>NEW GITHUB DEPLOY</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 User: {u_info.get('full_name', '?') if u_info else '?'} (<code>{uid}</code>)\n"
                        f"🐙 Repo: <code>{owner}/{repo}</code>\n"
                        f"🌿 Branch: <code>{branch}</code>\n"
                        f"🔑 Type: {'Private' if token else 'Public'}\n"
                        f"📄 Entry: <code>{entry}</code>\n"
                        f"🆔 Bot ID: #{bid}\n"
                        f"📊 Approval: ✅ Auto-approved\n"
                        f"━━━━━━━━━━━━━━━━━━━━")
                except Exception as ex:
                    forward_error("ADMIN_FORWARD_GH", ex, aid)
    except Exception as e:
        logger.error(f"GitHub deploy error: {e}", exc_info=True)
        forward_crash("github_deploy", e, uid)
        _gh_progress(chat_id, msg_id, f"❌ Deploy failed:\n<code>{str(e)[:200]}</code>")
    finally:
        github_sessions.pop(uid, None)


def handle_user_state(msg):
    uid = msg.from_user.id
    s = state.get_state(uid)
    if not s:
        return
    action = s.get('action')

    try:
        if action == 'broadcast':
            if not state.is_admin(uid):
                state.clear_state(uid); return
            threading.Thread(target=do_broadcast_send,
                             args=(uid, msg.text, msg.chat.id),
                             daemon=True, name="broadcast").start()
            state.clear_state(uid)

        elif action == 'adm_addsub_uid':
            try:
                target = int(msg.text.strip())
                target_user = db.get_user(target)
                if not target_user:
                    safe_reply(msg, f"❌ User <code>{target}</code> not found!")
                    state.clear_state(uid); return
                m = types.InlineKeyboardMarkup(row_width=2)
                for k, p in PLAN_LIMITS.items():
                    if k != 'free':
                        m.add(types.InlineKeyboardButton(p['name'],
                                callback_data=f"adm_setplan:{k}:{target}",
                                style="success"))
                m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
                safe_reply(msg,
                    f"👤 User: <code>{target}</code> — {target_user.get('full_name', '?')}\n"
                    f"Current: {PLAN_LIMITS.get(target_user.get('plan', 'free'), PLAN_LIMITS['free'])['name']}\n\n"
                    f"Select new plan:", reply_markup=m)
                state.clear_state(uid)
            except ValueError:
                safe_reply(msg, "❌ Invalid user ID!"); state.clear_state(uid)

        elif action == 'adm_addsub_days':
            try:
                days = int(msg.text.strip()); target = s['target']; plan = s['plan']
                if days == 0:
                    db.set_sub(target, 'lifetime'); plan_name = "👑 Lifetime"
                else:
                    db.set_sub(target, plan, days)
                    plan_name = PLAN_LIMITS.get(plan, {}).get('name', plan)
                safe_reply(msg,
                    f"✅ <b>Subscription Added!</b>\n\n"
                    f"👤 User: <code>{target}</code>\n"
                    f"📦 Plan: {plan_name}\n"
                    f"📅 Duration: {'Lifetime' if days == 0 else f'{days} days'}",
                    reply_markup=back_btn("menu_admin", "🔙 Admin"))
                db.admin_log(uid, 'add_sub', target, f"{plan}/{days}d")
                safe_send(target, f"🎉 <b>Plan Upgraded!</b>\n📦 {plan_name}\n📅 {'Lifetime' if days==0 else f'{days} days'}\n{BRAND_FOOTER}")
            except ValueError:
                safe_reply(msg, "❌ Send a number! (0 = lifetime)")
            state.clear_state(uid)

        elif action == 'adm_remsub_uid':
            try:
                target = int(msg.text.strip()); db.rem_sub(target)
                safe_reply(msg, f"✅ Subscription removed: <code>{target}</code>",
                           reply_markup=back_btn("menu_admin", "🔙 Admin"))
                db.admin_log(uid, 'remove_sub', target)
                safe_send(target, "⚠️ Your subscription has been removed by admin.")
            except: safe_reply(msg, "❌ Invalid user ID!")
            state.clear_state(uid)

        elif action == 'adm_ban_uid':
            parts = msg.text.strip().split(maxsplit=1)
            try:
                target = int(parts[0])
                reason = parts[1] if len(parts) > 1 else "Banned by admin"
                db.ban(target, reason); db.admin_log(uid, 'ban', target, reason)
                for b in db.get_bots(target):
                    sk = f"{target}_{b['bot_name']}"
                    if sk in bot_scripts:
                        kill_tree(bot_scripts[sk]); cleanup_script(sk)
                    db.update_bot(b['bot_id'], status='stopped')
                safe_reply(msg, f"🚫 Banned <code>{target}</code>\nReason: {reason}",
                           reply_markup=back_btn("menu_admin", "🔙 Admin"))
                safe_send(target, f"🚫 <b>You have been banned!</b>\nReason: {reason}\n\nContact {YOUR_USERNAME}")
            except: safe_reply(msg, "❌ Format: USER_ID [REASON]")
            state.clear_state(uid)

        elif action == 'adm_unban_uid':
            try:
                target = int(msg.text.strip()); db.unban(target); db.admin_log(uid, 'unban', target)
                safe_reply(msg, f"✅ Unbanned <code>{target}</code>",
                           reply_markup=back_btn("menu_admin", "🔙 Admin"))
                safe_send(target, "✅ You have been unbanned! Welcome back.")
            except: safe_reply(msg, "❌ Invalid user ID!")
            state.clear_state(uid)

        elif action == 'adm_give_balance':
            parts = msg.text.strip().split()
            if len(parts) >= 2:
                try:
                    target = int(parts[0]); amount = float(parts[1])
                    if not db.get_user(target):
                        safe_reply(msg, f"❌ User {target} not found!")
                    else:
                        db.wallet_tx(target, amount, 'bonus', f"Admin bonus by {uid}")
                        safe_reply(msg, f"✅ +{amount} BDT → <code>{target}</code>",
                                   reply_markup=back_btn("menu_admin", "🔙 Admin"))
                        safe_send(target, f"🎁 <b>Admin Bonus!</b>\n💰 +{amount} BDT\n{BRAND_FOOTER}")
                except: safe_reply(msg, "❌ Error!")
            else: safe_reply(msg, "❌ Format: USER_ID AMOUNT")
            state.clear_state(uid)

        elif action == 'adm_userinfo_uid':
            try:
                target = int(msg.text.strip()); show_user_info(uid, target)
            except ValueError: safe_reply(msg, "❌ Invalid user ID!")
            state.clear_state(uid)

        elif action == 'adm_notify_uid':
            try:
                parts = msg.text.strip().split(maxsplit=1)
                target = int(parts[0])
                text = parts[1] if len(parts) > 1 else "Notification from admin"
                db.add_notif(target, "Admin Notice", text)
                safe_reply(msg, f"✅ Sent to <code>{target}</code>",
                           reply_markup=back_btn("menu_admin", "🔙 Admin"))
                safe_send(target, f"🔔 <b>Notification</b>\n\n{text}\n{BRAND_FOOTER}")
            except: safe_reply(msg, "❌ Format: USER_ID MESSAGE")
            state.clear_state(uid)

        elif action == 'adm_promo_create':
            parts = msg.text.strip().split()
            if len(parts) >= 3:
                try:
                    code = parts[0].upper()
                    discount = int(parts[1]); mx = int(parts[2])
                    db.add_promo_v2(code, 'percent', discount, 0, mx, uid)
                    safe_reply(msg,
                        f"✅ <b>% Promo Created!</b>\n\n"
                        f"🎟 Code: <code>{code}</code>\n"
                        f"💰 Discount: {discount}%\n"
                        f"🔢 Max uses: {mx}",
                        reply_markup=back_btn("adm_promo", "🔙 Promo"))
                    db.admin_log(uid, 'create_promo_pct', det=f"{code}/{discount}%/{mx}")
                except: safe_reply(msg, "❌ Error creating promo!")
            else: safe_reply(msg, "❌ Format: CODE DISCOUNT% MAX_USES\nEx: SAVE50 50 100")
            state.clear_state(uid)

        elif action == 'adm_promo_tk':
            parts = msg.text.strip().split()
            if len(parts) >= 3:
                try:
                    code = parts[0].upper()
                    amount = float(parts[1]); mx = int(parts[2])
                    db.add_promo_v2(code, 'wallet', 0, amount, mx, uid)
                    safe_reply(msg,
                        f"✅ <b>TK Promo Created!</b>\n\n"
                        f"🎟 Code: <code>{code}</code>\n"
                        f"💵 Wallet: {amount} Tk\n"
                        f"🔢 Max uses: {mx}",
                        reply_markup=back_btn("adm_promo", "🔙 Promo"))
                    db.admin_log(uid, 'create_promo_tk', det=f"{code}/{amount}/{mx}")
                except Exception as e: safe_reply(msg, f"❌ Error: {str(e)[:100]}")
            else: safe_reply(msg, "❌ Format: CODE TK MAX_USES\nEx: WELCOME100 100 50")
            state.clear_state(uid)

        elif action == 'promo_tk_code':
            code = msg.text.strip().upper()
            promo = db.get_promo_by_type(code, 'wallet')
            if not promo:
                state.clear_state(uid)
                return safe_reply(msg, f"❌ Invalid promo code: <code>{code}</code>",
                                  reply_markup=back_btn())
            if db.user_used_promo(uid, code):
                state.clear_state(uid)
                return safe_reply(msg, "❌ You have already used this promo code!",
                                  reply_markup=back_btn())
            if promo.get('used_count', 0) >= promo.get('max_uses', 1):
                state.clear_state(uid)
                return safe_reply(msg, "❌ This promo code has reached its limit!",
                                  reply_markup=back_btn())

            amount = float(promo.get('wallet_amount', 0))
            db.wallet_tx(uid, amount, 'bonus', f"Promo code: {code}")
            db.mark_user_promo_used(uid, code)
            db.use_promo(code)
            state.clear_state(uid)

            new_bal = (db.get_user(uid) or {}).get('wallet_balance', 0)
            safe_reply(msg,
                f"✅ <b>PROMO APPLIED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎟 Code: <code>{code}</code>\n"
                f"💵 Added: <b>{amount} BDT</b>\n"
                f"💰 New balance: {new_bal} BDT\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                reply_markup=back_btn())
            for aid in state.admin_ids:
                safe_send(aid,
                    f"🎟 <b>Promo Used (Tk)</b>\n\n"
                    f"👤 User: <code>{uid}</code>\n"
                    f"🎟 Code: <code>{code}</code>\n"
                    f"💵 Amount: {amount} BDT")

        elif action == 'promo_pct_code':
            code = msg.text.strip().upper()
            promo = db.get_promo_by_type(code, 'percent')
            if not promo:
                state.clear_state(uid)
                return safe_reply(msg, f"❌ Invalid promo code: <code>{code}</code>",
                                  reply_markup=back_btn())
            if db.user_used_promo(uid, code):
                state.clear_state(uid)
                return safe_reply(msg, "❌ You have already used this promo code!",
                                  reply_markup=back_btn())
            if promo.get('used_count', 0) >= promo.get('max_uses', 1):
                state.clear_state(uid)
                return safe_reply(msg, "❌ This promo code has reached its limit!",
                                  reply_markup=back_btn())

            discount = int(promo.get('discount_pct', 0))
            state.clear_state(uid)
            safe_reply(msg,
                f"✅ <b>PROMO APPLIED — {discount}% OFF!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎟 Code: <code>{code}</code>\n"
                f"💯 Discount: {discount}%\n"
                f"⚠️ One-time use — expires after purchase.\n\n"
                f"👇 Select a plan to apply discount:",
                reply_markup=promo_discount_plan_kb(code, discount))

        elif action == 'ch_add':
            parts = msg.text.strip().split(maxsplit=1)
            ch_username = parts[0].lstrip('@').lower()
            ch_name = parts[1] if len(parts) > 1 else ch_username
            try:
                chat_info = bot.get_chat(f"@{ch_username}")
                ch_name = chat_info.title or ch_name
            except: pass
            db.add_channel(ch_username, ch_name, uid)
            db.admin_log(uid, 'add_channel', det=f"@{ch_username}")
            safe_reply(msg, f"✅ <b>Channel Added!</b>\n📢 @{ch_username}\n⚠️ Make sure bot is admin!",
                       reply_markup=back_btn("adm_channels", "🔙 Channels"))
            state.clear_state(uid)

        elif action == 'ch_remove':
            text = msg.text.strip().lstrip('@').lower()
            db.remove_channel(text)
            db.admin_log(uid, 'remove_channel', det=f"@{text}")
            safe_reply(msg, f"✅ Removed @{text}",
                       reply_markup=back_btn("adm_channels", "🔙 Channels"))
            state.clear_state(uid)

        elif action == 'ticket':
            text = msg.text.strip()
            if len(text) < 5:
                safe_reply(msg, "❌ Message too short! Min 5 chars.")
                state.clear_state(uid); return
            tid = db.add_ticket(uid, "Support Request", text)
            safe_reply(msg,
                f"✅ <b>Ticket #{tid} Created!</b>\n\n📝 {text[:100]}\n\n"
                f"Our team will respond soon.\n📞 Direct: {YOUR_USERNAME}\n{BRAND_FOOTER}",
                reply_markup=back_btn())
            u = db.get_user(uid)
            for aid in state.admin_ids:
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton(f"💬 Reply #{tid}",
                        callback_data=f"adm_ticket_reply:{tid}", style="primary"))
                safe_send(aid,
                    f"🎫 <b>New Ticket #{tid}</b>\n\n"
                    f"👤 {u.get('full_name', uid) if u else uid} (<code>{uid}</code>)\n"
                    f"📝 {text[:200]}", reply_markup=m)
            state.clear_state(uid)

        elif action == 'ticket_reply':
            tid = s.get('ticket_id'); text = msg.text.strip()
            if not text or not tid: state.clear_state(uid); return
            ticket = db.get_ticket(tid)
            if ticket:
                db.reply_ticket(tid, text)
                safe_reply(msg, f"✅ Replied to ticket #{tid}",
                           reply_markup=back_btn("adm_tickets", "🔙 Tickets"))
                safe_send(ticket['user_id'],
                    f"📩 <b>Ticket #{tid} — Reply</b>\n\n💬 {text}\n{BRAND_FOOTER}")
            state.clear_state(uid)

        else: state.clear_state(uid)

    except Exception as e:
        forward_crash("handle_user_state", e, uid)
        state.clear_state(uid)


@bot.message_handler(commands=['start'])
def cmd_start(msg):
    uid = msg.from_user.id
    un = msg.from_user.username or ''
    fn = f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}".strip()
    state.active_users.add(uid)
    github_sessions.pop(uid, None)

    try:
        rm = bot.send_message(msg.chat.id, "👋", reply_markup=types.ReplyKeyboardRemove())
        bot.delete_message(msg.chat.id, rm.message_id)
    except Exception: pass

    try:
        joined, nj = check_joined(uid)
        if not joined: send_force_sub(msg.chat.id, nj); return

        ex = db.get_user(uid)
        if ex and ex.get('is_banned'):
            return safe_reply(msg,
                f"🚫 <b>You are banned!</b>\nReason: {ex.get('ban_reason', 'N/A')}\n\nContact {YOUR_USERNAME}")
        if state.bot_locked and not state.is_admin(uid):
            return safe_reply(msg, "🔒 <b>Bot is in maintenance mode.</b>\nPlease try again later.")

        is_new = ex is None; ref_by = None
        args = msg.text.split()
        if len(args) > 1:
            rc = args[1].strip()
            rr = db.get_user_by_ref_code(rc)
            if rr and rr['user_id'] != uid and is_new: ref_by = rr['user_id']

        code = gen_ref_code(uid)
        if is_new:
            db.create_user(uid, un, fn, code, ref_by)
            if ref_by:
                db.add_ref(ref_by, uid, REF_BONUS_DAYS, REF_COMMISSION)
                rd = db.get_user(ref_by)
                safe_send(ref_by,
                    f"🎉 <b>NEW REFERRAL!</b>\n\n"
                    f"👤 <b>{fn}</b> joined via your link!\n"
                    f"💰 +{REF_COMMISSION} BDT wallet bonus!\n"
                    f"📅 +{REF_BONUS_DAYS} days premium!\n"
                    f"👥 Total Referrals: {rd.get('referral_count', '?') if rd else '?'}\n"
                    f"{BRAND_FOOTER}")
            for aid in state.admin_ids:
                safe_send(aid, f"👤 <b>New User!</b>\n{fn} (<code>{uid}</code>)\nRef: {ref_by or 'Direct'}")
        else:
            db.update_user(uid, username=un, full_name=fn, last_active=datetime.now().isoformat())

        u = db.get_user(uid)
        role = get_role_label(uid)
        bc = db.bot_count(uid)
        pl = PLAN_LIMITS.get(u.get('plan', 'free') if u else 'free', PLAN_LIMITS['free'])
        mx = '♾️' if pl['max_bots'] == -1 else str(pl['max_bots'])

        welcome = (
            f"🌟 <b>SB HOSTING PANEL</b> {BRAND_VER}\n"
            f"<i>Premium Bot Hosting Platform</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👋 Welcome, <b>{fn}</b>!\n\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📦 Plan: {role}\n"
            f"🤖 Bots: {bc}/{mx}\n"
            f"💰 Wallet: {u.get('wallet_balance', 0) if u else 0} BDT\n"
            f"👥 Referrals: {u.get('referral_count', 0) if u else 0}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🚀 <b>What you can do:</b>\n"
            f"  📤 Deploy Python &amp; Node.js bots\n"
            f"  🐙 Deploy from GitHub repo\n"
            f"  ⭐ Pay with Telegram Stars\n"
            f"  🎟 Redeem promo codes\n"
            f"  🎁 Earn with referrals\n\n"
            f"👇 <b>Choose from the menu below:</b>")
        safe_send(msg.chat.id, welcome, reply_markup=main_menu_kb(uid))
    except Exception as e:
        forward_crash("cmd_start", e, uid)
        safe_send(msg.chat.id, "❌ An error occurred. Please try again.")


@bot.message_handler(commands=['help'])
def cmd_help(msg):
    try: safe_send(msg.from_user.id,
        f"📚 <b>HELP CENTER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Welcome to {BRAND}!\nSelect a topic below.\n━━━━━━━━━━━━━━━━━━━━",
        reply_markup=help_menu_kb())
    except Exception as e: forward_crash("cmd_help", e, msg.from_user.id)

@bot.message_handler(commands=['admin'])
def cmd_admin(msg):
    uid = msg.from_user.id
    if not state.is_admin(uid): return safe_reply(msg, "❌ Admin access only!")
    show_admin_panel(uid)

@bot.message_handler(commands=['id'])
def cmd_id(msg):
    uid = msg.from_user.id
    safe_send(msg.chat.id,
        f"🆔 <b>Your Info</b>\n\n"
        f"👤 ID: <code>{uid}</code>\n"
        f"📛 Name: {msg.from_user.first_name or ''} {msg.from_user.last_name or ''}\n"
        f"👤 Username: @{msg.from_user.username or 'N/A'}\n"
        f"💎 Role: {get_role_label(uid)}\n"
        f"{BRAND_FOOTER}", reply_markup=back_btn())

@bot.message_handler(commands=['ping'])
def cmd_ping(msg):
    start = time.time()
    m = safe_reply(msg, "🏓 Pinging...")
    if m:
        latency = round((time.time() - start) * 1000, 2)
        rn = len([k for k in bot_scripts if is_running(k)])
        safe_edit(f"🏓 <b>Pong!</b>\n\n⚡ Latency: {latency}ms\n⏱️ Uptime: {get_uptime()}\n"
                  f"🤖 Running: {rn} bots\n{BRAND_FOOTER}",
                  msg.chat.id, m.message_id, reply_markup=back_btn())

@bot.message_handler(commands=['status'])
def cmd_status(msg):
    uid = msg.from_user.id
    try:
        bots_list = db.get_bots(uid)
        if not bots_list:
            return safe_reply(msg,
                f"📭 <b>No bots deployed yet!</b>\n\n"
                f"Send a .py, .js or .zip file to deploy your first bot.\n{BRAND_FOOTER}",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📤 Deploy Bot", callback_data="menu_deploy", style="success")))
        running = [(b, bot_running(uid, b['bot_name'])) for b in bots_list]
        active = sum(1 for _, r in running if r); total = len(bots_list)
        t = f"📊 <b>YOUR BOT STATUS</b>\n━━━━━━━━━━━━━━━━━━━━\n\n🟢 Running: {active} / {total}\n\n"
        m = types.InlineKeyboardMarkup(row_width=1)
        for b, r in running:
            icon = "🟢" if r else "🔴"
            ftype = "🐍" if b['file_type'] == 'py' else "🟨"
            t += f"{icon} {ftype} <code>{b['bot_name'][:20]}</code>\n\n"
            m.add(types.InlineKeyboardButton(
                f"{icon} {b['bot_name'][:18]} #{b['bot_id']}",
                callback_data=f"bot_detail:{b['bot_id']}", style="primary"))
        m.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home", style="primary"))
        safe_reply(msg, t + "━━━━━━━━━━━━━━━━━━━━", reply_markup=m)
    except Exception as e: forward_crash("cmd_status", e, uid)

@bot.message_handler(commands=['cancel'])
def cmd_cancel(msg):
    uid = msg.from_user.id
    if uid in github_sessions:
        github_sessions.pop(uid, None)
        return safe_reply(msg, "❌ GitHub deploy cancelled.")
    state.clear_state(uid); state.clear_pay_state(uid)
    safe_reply(msg, "✅ Cancelled.", reply_markup=back_btn())

@bot.message_handler(commands=['ban'])
def cmd_ban(msg):
    if not state.is_admin(msg.from_user.id): return
    p = msg.text.split(maxsplit=2)
    if len(p) < 2: return safe_reply(msg, "Usage: /ban UID [REASON]")
    try:
        target = int(p[1]); reason = p[2] if len(p) > 2 else "Banned by admin"
        db.ban(target, reason); safe_reply(msg, f"🚫 Banned <code>{target}</code>")
    except: safe_reply(msg, "❌ Error!")

@bot.message_handler(commands=['unban'])
def cmd_unban(msg):
    if not state.is_admin(msg.from_user.id): return
    try:
        target = int(msg.text.split()[1]); db.unban(target)
        safe_reply(msg, f"✅ Unbanned <code>{target}</code>")
    except: safe_reply(msg, "❌ Error!")

@bot.message_handler(commands=['broadcast', 'bc'])
def cmd_broadcast(msg):
    uid = msg.from_user.id
    if not state.is_admin(uid): return
    text = msg.text.split(maxsplit=1)
    if len(text) < 2:
        state.set_state(uid, {'action': 'broadcast'})
        return safe_reply(msg, "📢 Send broadcast message now:")
    do_broadcast_send(uid, text[1], msg.chat.id)

@bot.message_handler(commands=['give'])
def cmd_give(msg):
    if not state.is_admin(msg.from_user.id): return
    parts = msg.text.split()
    if len(parts) < 3: return safe_reply(msg, "Usage: /give UID AMOUNT")
    try:
        target = int(parts[1]); amount = float(parts[2])
        if not db.get_user(target): return safe_reply(msg, f"❌ User {target} not found!")
        db.wallet_tx(target, amount, 'bonus', f"Admin bonus by {msg.from_user.id}")
        safe_reply(msg, f"✅ +{amount} BDT → <code>{target}</code>")
        safe_send(target, f"🎁 <b>Admin Bonus!</b>\n💰 +{amount} BDT\n{BRAND_FOOTER}")
    except: safe_reply(msg, "❌ Error!")

@bot.message_handler(commands=['notify'])
def cmd_notify(msg):
    if not state.is_admin(msg.from_user.id): return
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 3: return safe_reply(msg, "Usage: /notify USER_ID MESSAGE")
    try:
        target = int(parts[1]); text = parts[2]
        db.add_notif(target, "Admin Notice", text)
        safe_reply(msg, f"✅ Notification sent to <code>{target}</code>")
        safe_send(target, f"🔔 <b>Notification</b>\n\n{text}\n{BRAND_FOOTER}")
    except: safe_reply(msg, "❌ Error!")

@bot.message_handler(commands=['subscribe'])
def cmd_sub_admin(msg):
    if not state.is_admin(msg.from_user.id): return
    p = msg.text.split()
    if len(p) < 3: return safe_reply(msg, "Usage: /subscribe UID DAYS")
    try:
        tu = int(p[1]); days = int(p[2])
        db.set_sub(tu, 'pro' if days > 0 else 'lifetime', days)
        safe_reply(msg, f"✅ Subscription set for <code>{tu}</code> — {days}d")
    except: safe_reply(msg, "❌ Error!")

@bot.message_handler(commands=['addchannel'])
def cmd_add_channel(msg):
    uid = msg.from_user.id
    if not state.is_admin(uid): return
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 2: return safe_reply(msg, "Usage: /addchannel @username [Channel Name]")
    ch_username = parts[1].lstrip('@').lower()
    ch_name = parts[2] if len(parts) > 2 else ch_username
    try:
        chat_info = bot.get_chat(f"@{ch_username}"); ch_name = chat_info.title or ch_name
    except: pass
    db.add_channel(ch_username, ch_name, uid)
    db.admin_log(uid, 'add_channel', det=f"@{ch_username}")
    safe_reply(msg, f"✅ Channel @{ch_username} added!\n⚠️ Make sure bot is admin!")

@bot.message_handler(commands=['channels'])
def cmd_channels(msg):
    if not state.is_admin(msg.from_user.id): return
    channels = db.get_all_channels()
    t = f"📢 <b>Force Subscribe Channels</b>\nStatus: {'🟢 ON' if state.force_sub_enabled else '🔴 OFF'}\n\n"
    if channels:
        for ch in channels:
            t += f"  {'🟢' if ch['is_active'] else '🔴'} @{ch['channel_username']} — {ch['channel_name']}\n"
    else: t += "No channels. Default: @sb_aura\n"
    safe_send(msg.from_user.id, t, reply_markup=back_btn("menu_admin", "🔙 Admin"))


@bot.message_handler(content_types=['text'])
def handle_text(msg):
    uid = msg.from_user.id
    state.active_users.add(uid)
    try:
        if not rate_check(uid): return
        joined, nj = check_joined(uid)
        if not joined: send_force_sub(msg.chat.id, nj); return
        u = db.get_user(uid)
        if u and u.get('is_banned'): return
        if state.bot_locked and not state.is_admin(uid):
            return safe_reply(msg, "🔒 <b>Maintenance mode.</b> Please wait.")

        if uid in github_sessions: return handle_github_flow(msg)
        if state.get_pay_state(uid): return handle_pay_text(msg)
        if state.get_state(uid): return handle_user_state(msg)
        if not u:
            safe_send(uid, "Please press /start first!"); return
        safe_send(uid, f"🏠 <b>Main Menu</b>\n\nUse the buttons below.\n━━━━━━━━━━━━━━━━━━━━",
                  reply_markup=main_menu_kb(uid))
    except Exception as e:
        forward_crash("handle_text", e, uid)


@bot.message_handler(content_types=['photo'])
def handle_photo(msg):
    uid = msg.from_user.id
    s = state.get_pay_state(uid)
    if s and s.get('step') == 'wait_trx':
        try:
            trx = f"SCREENSHOT_{datetime.now().strftime('%H%M%S')}"
            if s.get('promo_code'):
                code = s['promo_code']
                if not db.user_used_promo(uid, code):
                    db.mark_user_promo_used(uid, code)
                    try: db.use_promo(code)
                    except Exception: pass
            pid = db.add_pay(uid, s['amount'], s['method'], trx, s['plan'], 30)
            state.clear_pay_state(uid)
            user_msg = safe_send(uid,
                f"✅ <b>PAYMENT SUBMITTED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 #{pid}\n📸 Screenshot received\n⏳ Waiting for approval...\n"
                f"━━━━━━━━━━━━━━━━━━━━", reply_markup=back_btn())
            if user_msg:
                try:
                    db.set_payment_msgs(pid, user_chat_id=uid, user_msg_id=user_msg.message_id)
                except Exception: pass
            u = db.get_user(uid)
            admin_msg_list = []
            for aid in state.admin_ids:
                try: bot.forward_message(aid, uid, msg.message_id)
                except: pass
                am = safe_send(aid,
                    f"💳 <b>Payment #{pid}</b> (Screenshot)\n"
                    f"👤 {u.get('full_name', uid) if u else uid} (<code>{uid}</code>)\n"
                    f"💰 {s['amount']} BDT | {s['method']} | {s['plan']}",
                    reply_markup=pay_approve_kb(pid))
                if am: admin_msg_list.append({'cid': aid, 'mid': am.message_id})
            if admin_msg_list:
                try: db.set_payment_msgs(pid, admin_list=admin_msg_list)
                except Exception: pass
        except Exception as e:
            forward_crash("handle_photo", e, uid)
            state.clear_pay_state(uid)


@bot.message_handler(content_types=['document'])
def handle_doc(msg):
    uid = msg.from_user.id
    try:
        joined, nj = check_joined(uid)
        if not joined: send_force_sub(msg.chat.id, nj); return
        u = db.get_user(uid)
        if not u: return safe_reply(msg, "Please /start first!")
        if u.get('is_banned'): return
        pl = db.get_plan(uid); cur = db.bot_count(uid); mx = pl['max_bots']
        if mx != -1 and cur >= mx:
            return safe_reply(msg,
                f"❌ <b>Bot limit reached!</b> ({cur}/{mx})\nUpgrade your plan.",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("💎 Upgrade", callback_data="menu_sub", style="success")))

        fn = msg.document.file_name
        fs = msg.document.file_size
        ext = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''
        allowed = ['py', 'js', 'zip', 'json', 'txt', 'env', 'yml', 'yaml', 'cfg', 'ini', 'toml']
        if ext not in allowed:
            return safe_reply(msg, f"❌ Unsupported file: .{ext}\n\nSupported: {', '.join(allowed)}")
        if fs > 100 * 1024 * 1024:
            return safe_reply(msg, "❌ File too large! Max 100MB.")

        pm = safe_reply(msg, f"📤 Uploading <code>{fn[:25]}</code> ({fmt_size(fs)})...")
        fi = bot.get_file(msg.document.file_id)
        dl = bot.download_file(fi.file_path)
        uf = user_folder(uid)

        if ext == 'zip':
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
                tmp.write(dl); tp = tmp.name
            try:
                with zipfile.ZipFile(tp, 'r') as z:
                    bn = fn.replace('.zip', '').replace(' ', '_')
                    ed = os.path.join(uf, bn)
                    extract_path = os.path.realpath(ed)
                    for n in z.namelist():
                        member_path = os.path.realpath(os.path.join(extract_path, n))
                        if not member_path.startswith(extract_path + os.sep) and member_path != extract_path:
                            if pm: safe_edit("❌ Suspicious file paths in ZIP! Upload rejected.", msg.chat.id, pm.message_id)
                            os.unlink(tp); return
                    if os.path.exists(ed): shutil.rmtree(ed, ignore_errors=True)
                    os.makedirs(ed, exist_ok=True); z.extractall(ed)
                    items = os.listdir(ed)
                    if len(items) == 1 and os.path.isdir(os.path.join(ed, items[0])):
                        inner = os.path.join(ed, items[0])
                        for item in os.listdir(inner):
                            src = os.path.join(inner, item); dst = os.path.join(ed, item)
                            if os.path.exists(dst):
                                shutil.rmtree(dst) if os.path.isdir(dst) else os.remove(dst)
                            shutil.move(src, dst)
                        try: os.rmdir(inner)
                        except: pass
                os.unlink(tp)
                entry, ft, report = det.report(ed)
                if not entry:
                    af = [os.path.relpath(os.path.join(r, f), ed) for r, d_, fs_l in os.walk(ed) for f in fs_l if f.endswith(('.py', '.js'))]
                    err = f"❌ <b>No entry file detected!</b>\n\n📁 Files in ZIP:\n"
                    for f in af[:15]: err += f"  • <code>{f}</code>\n"
                    if not af: err += "  (No .py or .js files)\n"
                    err += "\n💡 Make sure ZIP has main.py, app.py, or bot.py"
                    if pm: safe_edit(err, msg.chat.id, pm.message_id, reply_markup=back_btn())
                    return

                bid = db.add_bot(uid, bn, ed, entry, ft, '', fs, '')
                if approval_is_on():
                    db.set_approval_status(bid, 'pending')
                    if pm:
                        safe_edit(
                            f"⏳ <b>FILE UPLOADED — PENDING APPROVAL</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"📦 <code>{bn[:20]}</code>\n🆔 Bot ID: #{bid}\n"
                            f"🔍 <b>Detection:</b>\n{report}\n\n"
                            f"📊 Status: ⏳ Waiting for admin approval",
                            msg.chat.id, pm.message_id,
                            reply_markup=back_btn("menu_mybots", "🔙 My Bots"))
                        try:
                            db.update_bot(bid, pending_chat_id=msg.chat.id, pending_msg_id=pm.message_id)
                        except Exception: pass
                    for aid in state.admin_ids:
                        try:
                            bot.send_document(aid, msg.document.file_id,
                                caption=(f"📥 <b>NEW FILE — PENDING APPROVAL</b>\n"
                                        f"━━━━━━━━━━━━━━━━━━━━\n"
                                        f"👤 User: <code>{uid}</code>\n"
                                        f"📁 File: <code>{bn[:30]}</code>\n"
                                        f"⚙️ Type: ZIP\n"
                                        f"📄 Entry: <code>{entry}</code>\n"
                                        f"🆔 Bot ID: #{bid}\n"
                                        f"━━━━━━━━━━━━━━━━━━━━"),
                                reply_markup=file_approval_kb(bid))
                        except Exception as ex: forward_error("APPROVAL_SEND", ex, aid)
                    return

                db.set_approval_status(bid, 'approved')
                mk = types.InlineKeyboardMarkup(row_width=2)
                mk.add(
                    types.InlineKeyboardButton("▶️ Start Now", callback_data=f"bot_start:{bid}", style="success"),
                    types.InlineKeyboardButton("🤖 My Bots",   callback_data="menu_mybots",     style="primary"))
                mk.add(types.InlineKeyboardButton("🔍 Re-detect", callback_data=f"bot_redetect:{bid}", style="primary"))
                if pm:
                    safe_edit(f"✅ <b>ZIP DEPLOYED!</b>\n\n📦 <code>{bn[:20]}</code>\n🆔 Bot ID: #{bid}\n\n🔍 <b>Detection:</b>\n{report}",
                              msg.chat.id, pm.message_id, reply_markup=mk)
                u_info = db.get_user(uid)
                for aid in state.admin_ids:
                    try:
                        bot.send_document(aid, msg.document.file_id,
                            caption=(f"📥 <b>NEW FILE UPLOADED</b>\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"👤 {u_info.get('full_name', '?') if u_info else '?'} (<code>{uid}</code>)\n"
                                    f"📁 File: <code>{bn[:30]}</code>\n"
                                    f"⚙️ Type: ZIP\n"
                                    f"📄 Entry: <code>{entry}</code>\n"
                                    f"🆔 Bot ID: #{bid}\n"
                                    f"📊 Approval: ✅ Auto-approved\n"
                                    f"━━━━━━━━━━━━━━━━━━━━"))
                    except Exception as ex: forward_error("ADMIN_FORWARD_ZIP", ex, aid)
            except zipfile.BadZipFile:
                if pm: safe_edit("❌ Invalid or corrupted ZIP file!", msg.chat.id, pm.message_id)
                try: os.unlink(tp)
                except: pass

        elif ext in ['py', 'js']:
            file_path = os.path.join(uf, fn)
            with open(file_path, 'wb') as f: f.write(dl)
            bid = db.add_bot(uid, fn, uf, fn, ext, '', fs, 'exact')

            if approval_is_on():
                db.set_approval_status(bid, 'pending')
                if pm:
                    safe_edit(
                        f"⏳ <b>FILE UPLOADED — PENDING APPROVAL</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"📄 <code>{fn[:25]}</code>\n🆔 Bot ID: #{bid}\n"
                        f"🔤 {'🐍 Python' if ext == 'py' else '🟨 Node.js'}\n"
                        f"📊 Size: {fmt_size(fs)}\n\n"
                        f"📊 Status: ⏳ Waiting for admin approval",
                        msg.chat.id, pm.message_id,
                        reply_markup=back_btn("menu_mybots", "🔙 My Bots"))
                    try:
                        db.update_bot(bid, pending_chat_id=msg.chat.id, pending_msg_id=pm.message_id)
                    except Exception: pass
                for aid in state.admin_ids:
                    try:
                        bot.send_document(aid, msg.document.file_id,
                            caption=(f"📥 <b>NEW FILE — PENDING APPROVAL</b>\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"👤 User: <code>{uid}</code>\n"
                                    f"📁 File: <code>{fn[:30]}</code>\n"
                                    f"⚙️ Type: {ext.upper()}\n"
                                    f"🆔 Bot ID: #{bid}\n"
                                    f"━━━━━━━━━━━━━━━━━━━━"),
                            reply_markup=file_approval_kb(bid))
                    except Exception as ex: forward_error("APPROVAL_SEND", ex, aid)
                return

            db.set_approval_status(bid, 'approved')
            mk = types.InlineKeyboardMarkup(row_width=2)
            mk.add(
                types.InlineKeyboardButton("▶️ Run Now",  callback_data=f"bot_start:{bid}", style="success"),
                types.InlineKeyboardButton("🤖 My Bots",  callback_data="menu_mybots",     style="primary"))
            if pm:
                safe_edit(
                    f"✅ <b>FILE UPLOADED!</b>\n\n📄 <code>{fn[:25]}</code>\n"
                    f"🆔 Bot ID: #{bid}\n"
                    f"🔤 {'🐍 Python' if ext == 'py' else '🟨 Node.js'}\n"
                    f"📊 Size: {fmt_size(fs)}",
                    msg.chat.id, pm.message_id, reply_markup=mk)
            u_info = db.get_user(uid)
            for aid in state.admin_ids:
                try:
                    bot.send_document(aid, msg.document.file_id,
                        caption=(f"📥 <b>NEW FILE UPLOADED</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"👤 {u_info.get('full_name', '?') if u_info else '?'} (<code>{uid}</code>)\n"
                                f"📁 File: <code>{fn[:30]}</code>\n"
                                f"⚙️ Type: {ext.upper()}\n"
                                f"📊 Size: {fmt_size(fs)}\n"
                                f"🆔 Bot ID: #{bid}\n"
                                f"📊 Approval: ✅ Auto-approved\n"
                                f"━━━━━━━━━━━━━━━━━━━━"))
                except Exception as ex: forward_error("ADMIN_FORWARD_FILE", ex, aid)
        else:
            file_path = os.path.join(uf, fn)
            with open(file_path, 'wb') as f: f.write(dl)
            if pm:
                safe_edit(f"✅ Config file <code>{fn}</code> saved!",
                          msg.chat.id, pm.message_id, reply_markup=back_btn())
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        forward_crash("handle_doc", e, uid)
        safe_send(msg.chat.id, f"❌ Upload error: {str(e)[:100]}")


@bot.pre_checkout_query_handler(func=lambda q: True)
def on_pre_checkout(q):
    try: bot.answer_pre_checkout_query(q.id, ok=True)
    except Exception as e: logger.error(f"pre_checkout error: {e}")

@bot.message_handler(content_types=['successful_payment'])
def on_successful_payment(msg):
    uid = msg.from_user.id
    try:
        sp = msg.successful_payment
        payload = sp.invoice_payload
        parts = payload.split(":")
        if len(parts) != 3 or parts[0] != "star": return
        plan = parts[1]; owner_id = int(parts[2])
        if owner_id != uid: return
        if plan not in PLAN_LIMITS: return

        db.set_sub(uid, plan, 0 if plan == 'lifetime' else 30)
        p = PLAN_LIMITS[plan]

        safe_send(uid,
            f"✅ <b>STARS PAYMENT SUCCESSFUL!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 Plan: {p['name']}\n"
            f"⭐ Stars: {sp.total_amount}\n"
            f"🎉 Your plan is now active!\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("📤 Deploy Bot", callback_data="menu_deploy", style="success"),
                types.InlineKeyboardButton("🏠 Menu", callback_data="go_home", style="primary")))

        u = db.get_user(uid)
        for aid in state.admin_ids:
            safe_send(aid,
                f"⭐ <b>NEW STARS PAYMENT!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👤 {u.get('full_name', '?') if u else '?'} (<code>{uid}</code>)\n"
                f"📦 Plan: {p['name']}\n"
                f"⭐ {sp.total_amount} Stars\n"
                f"✅ Auto-approved\n"
                f"━━━━━━━━━━━━━━━━━━━━")
        db.admin_log(uid, 'star_payment', uid, f"{plan}/{sp.total_amount}")
    except Exception as e:
        forward_crash("successful_payment", e, uid)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    uid = call.from_user.id
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    try:
        if data == "go_home":
            safe_answer(call.id); github_sessions.pop(uid, None)
            u = db.get_user(uid)
            if not u:
                db.create_user(uid, call.from_user.username or '',
                               f"{call.from_user.first_name or ''} {call.from_user.last_name or ''}".strip(),
                               gen_ref_code(uid))
            safe_edit(f"🏠 <b>Main Menu</b>\n\nWelcome back!\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=main_menu_kb(uid))

        elif data == "verify_join":
            joined, nj = check_joined(uid)
            if joined:
                safe_answer(call.id, "✅ Verified! Welcome!", show_alert=True)
                safe_delete(chat_id, msg_id)
                u = db.get_user(uid)
                fn = f"{call.from_user.first_name or ''} {call.from_user.last_name or ''}".strip()
                if not u:
                    db.create_user(uid, call.from_user.username or '', fn, gen_ref_code(uid))
                safe_send(uid, f"✅ <b>Verification Successful!</b>\n\nWelcome, <b>{fn}</b>!\n━━━━━━━━━━━━━━━━━━━━",
                          reply_markup=main_menu_kb(uid))
            else:
                safe_answer(call.id, "❌ Join all channels first!", show_alert=True)

        elif data == "menu_mybots":
            safe_answer(call.id)
            bots_list = db.get_bots(uid); pl = db.get_plan(uid)
            mx = '♾️' if pl['max_bots'] == -1 else str(pl['max_bots'])
            if not bots_list:
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(types.InlineKeyboardButton("📤 Deploy Bot", callback_data="menu_deploy", style="success"))
                m.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home", style="primary"))
                safe_edit(f"📭 <b>No bots yet!</b>\n\nDeploy your first bot!\n📦 Slots: 0/{mx}\n━━━━━━━━━━━━━━━━━━━━",
                          chat_id, msg_id, reply_markup=m)
                return
            rn = sum(1 for b in bots_list if bot_running(uid, b['bot_name']))
            t = f"🤖 <b>My Bots</b> ({len(bots_list)})\n🟢 Running: {rn} | 🔴 Stopped: {len(bots_list)-rn}\n📦 Limit: {mx}\n━━━━━━━━━━━━━━━━━━━━\n\n"
            m = types.InlineKeyboardMarkup(row_width=1)
            for b in bots_list:
                r = bot_running(uid, b['bot_name'])
                ic = "🐍" if b['file_type'] == 'py' else "🟨"
                appr = b.get('approval_status', 'approved')
                if appr == 'pending': st_icon = "⏳"
                elif appr == 'rejected': st_icon = "❌"
                else: st_icon = "🟢" if r else "🔴"
                t += f"{st_icon} {ic} <code>{b['bot_name'][:20]}</code> — #{b['bot_id']}\n"
                m.add(types.InlineKeyboardButton(
                    f"{st_icon} {ic} {b['bot_name'][:15]} — #{b['bot_id']}",
                    callback_data=f"bot_detail:{b['bot_id']}",
                    style="success" if (r and appr == 'approved') else "primary"))
            m.add(types.InlineKeyboardButton("📤 Deploy New Bot", callback_data="menu_deploy", style="success"))
            m.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home", style="primary"))
            safe_edit(t, chat_id, msg_id, reply_markup=m)

        elif data == "menu_deploy":
            safe_answer(call.id)
            pl = db.get_plan(uid); cur = db.bot_count(uid); mx = pl['max_bots']
            if mx != -1 and cur >= mx:
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("💎 Upgrade Plan", callback_data="menu_sub", style="success"))
                m.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home", style="primary"))
                safe_edit(f"⚠️ <b>Bot Limit Reached!</b>\n\nCurrent: {cur}/{mx}\nUpgrade your plan.",
                          chat_id, msg_id, reply_markup=m)
                return
            rem = '♾️' if mx == -1 else str(mx - cur)
            safe_edit(
                f"📤 <b>DEPLOY YOUR BOT</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Choose your source:\n\n"
                f"📤 <b>Upload File</b>\n"
                f"  🐍 Python (.py)  🟨 Node.js (.js)  📦 ZIP\n\n"
                f"🐙 <b>GitHub Repo</b>\n"
                f"  🌐 Public  🔒 Private (with token)\n\n"
                f"📊 Slots remaining: <b>{rem}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=deploy_choice_kb())

        elif data == "deploy_upload":
            safe_answer(call.id)
            safe_edit(
                f"📤 <b>UPLOAD YOUR FILE</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📎 Just send the file in this chat!\n\n"
                f"<b>Supported:</b>\n"
                f"  🐍 Python (.py)\n"
                f"  🟨 Node.js (.js)\n"
                f"  📦 ZIP archive\n\n"
                f"🔍 Auto-detects entry file\n"
                f"📦 Auto-installs requirements\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=back_btn("menu_deploy", "🔙 Back"))

        elif data == "deploy_github":
            safe_answer(call.id)
            github_sessions[uid] = {'step': 'type'}
            safe_edit(
                f"🐙 <b>GITHUB DEPLOY</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Choose the repository type:\n\n"
                f"🌐 <b>Public</b>  — anyone can access\n"
                f"🔒 <b>Private</b> — requires GitHub token\n\n"
                f"✉️ Send <code>/cancel</code> anytime to abort.\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=github_repo_type_kb())

        elif data.startswith("gh_type:"):
            kind = data.split(":", 1)[1]
            sess = github_sessions.get(uid)
            if not sess or sess.get('step') != 'type':
                return safe_answer(call.id, "Session expired. Start again.", show_alert=True)
            if kind == "private":
                sess['step'] = 'token'; sess['repo_type'] = 'private'
                safe_edit(
                    f"🔒 <b>PRIVATE REPO</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🔑 Send your GitHub Personal Access Token\n"
                    f"(scope: <code>repo</code>)\n\n"
                    f"💡 <b>How to create:</b>\n"
                    f"GitHub → Settings → Developer settings →\n"
                    f"Personal access tokens → Tokens (classic)\n"
                    f"→ Generate new token → check <code>repo</code>\n\n"
                    f"✉️ Send <code>/cancel</code> to abort.\n"
                    f"━━━━━━━━━━━━━━━━━━━━",
                    chat_id, msg_id, reply_markup=back_btn("menu_deploy", "🔙 Back"))
            else:
                sess['step'] = 'url'; sess['repo_type'] = 'public'; sess['token'] = None
                safe_edit(
                    f"🌐 <b>PUBLIC REPO</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Send the GitHub repository URL.\n\n"
                    f"<b>Examples:</b>\n"
                    f"  <code>https://github.com/user/repo</code>\n"
                    f"  <code>https://github.com/user/repo/tree/dev</code>\n\n"
                    f"✉️ Send <code>/cancel</code> to abort.\n"
                    f"━━━━━━━━━━━━━━━━━━━━",
                    chat_id, msg_id, reply_markup=back_btn("menu_deploy", "🔙 Back"))
            safe_answer(call.id)

        elif data == "menu_sub":
            safe_answer(call.id)
            u = db.get_user(uid)
            role = get_role_label(uid)
            t = (
                f"💎 <b>SUBSCRIPTION</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 Current Plan: {role}\n"
                f"📅 Expires: {time_left(u.get('subscription_end') if u else None)}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Choose payment method below:")
            safe_edit(t, chat_id, msg_id, reply_markup=sub_choice_kb())

        elif data == "sub_tk":
            safe_answer(call.id)
            u = db.get_user(uid)
            role = get_role_label(uid)
            t = (f"💵 <b>TK PAYMENT</b>\n"
                 f"━━━━━━━━━━━━━━━━━━━━\n\n"
                 f"📦 Current Plan: {role}\n"
                 f"📅 Expires: {time_left(u.get('subscription_end') if u else None)}\n"
                 f"━━━━━━━━━━━━━━━━━━━━\n\n<b>Available Plans:</b>\n\n")
            for k, p in PLAN_LIMITS.items():
                if k == 'free': continue
                slots = '♾️' if p['max_bots'] == -1 else str(p['max_bots'])
                t += (f"{p['name']}\n"
                      f"  🤖 {slots} bots | 💾 {p['ram']}MB\n"
                      f"  💰 {p['price']} BDT/month\n\n")
            t += "━━━━━━━━━━━━━━━━━━━━\n👇 <b>Select a plan:</b>"
            safe_edit(t, chat_id, msg_id, reply_markup=plan_kb())

        elif data == "sub_star":
            safe_answer(call.id)
            u = db.get_user(uid)
            role = get_role_label(uid)
            t = (f"⭐ <b>STARS SUBSCRIPTION</b>\n"
                 f"━━━━━━━━━━━━━━━━━━━━\n\n"
                 f"📦 Current Plan: {role}\n"
                 f"⚡ Auto-approved — no waiting\n"
                 f"━━━━━━━━━━━━━━━━━━━━\n\n<b>Available Plans:</b>\n\n")
            for k, stars in STAR_PLAN_PRICES.items():
                p = PLAN_LIMITS.get(k, {})
                if not p: continue
                slots = '♾️' if p['max_bots'] == -1 else str(p['max_bots'])
                t += (f"{p['name']}\n"
                      f"  🤖 {slots} bots | 💾 {p['ram']}MB\n"
                      f"  ⭐ {stars} Stars/month\n\n")
            t += "━━━━━━━━━━━━━━━━━━━━\n👇 <b>Select a plan:</b>"
            safe_edit(t, chat_id, msg_id, reply_markup=star_plan_kb())

        elif data.startswith("star_buy:"):
            plan_key = data.split(":")[1]
            if plan_key not in STAR_PLAN_PRICES:
                return safe_answer(call.id, "❌ Unknown plan!", show_alert=True)
            p = PLAN_LIMITS.get(plan_key); stars = STAR_PLAN_PRICES[plan_key]
            if not p: return safe_answer(call.id, "❌ Unknown plan!", show_alert=True)
            safe_answer(call.id, "⭐ Opening payment...")
            try:
                bot.send_invoice(
                    chat_id,
                    title=f"{p['name']} Plan",
                    description=(f"Activate {p['name']} for 30 days\n"
                                 f"• {p['max_bots']} bots\n"
                                 f"• {p['ram']}MB RAM"),
                    invoice_payload=f"star:{plan_key}:{uid}",
                    provider_token="",
                    currency="XTR",
                    prices=[types.LabeledPrice(label=f"{p['name']} Plan", amount=stars)],
                    start_parameter="star-plan")
            except Exception as e:
                forward_error("STAR_INVOICE", e, uid)
                safe_send(chat_id, f"❌ Could not create invoice:\n<code>{str(e)[:150]}</code>")

        elif data == "menu_promo":
            safe_answer(call.id)
            safe_edit(
                f"🎟 <b>PROMO CODE</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Choose promo type:\n\n"
                f"💵 <b>Tk Wallet</b>\n"
                f"   Get balance added to your wallet\n\n"
                f"💰 <b>% Discount</b>\n"
                f"   Get a discount on your next plan\n\n"
                f"👇 Select type:",
                chat_id, msg_id, reply_markup=promo_choice_kb())

        elif data == "promo_tk":
            safe_answer(call.id)
            state.set_state(uid, {'action': 'promo_tk_code'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="go_home", style="danger"))
            safe_edit(
                f"💵 <b>TK WALLET PROMO</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📝 Send your promo code below.\n\n"
                f"💡 Valid code adds money to your wallet.\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=m)

        elif data == "promo_pct":
            safe_answer(call.id)
            state.set_state(uid, {'action': 'promo_pct_code'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="go_home", style="danger"))
            safe_edit(
                f"💰 <b>% DISCOUNT PROMO</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📝 Send your promo code below.\n\n"
                f"💡 Valid code gives you a discount on a plan.\n"
                f"⚠️ One-time use — expires after 1 purchase.\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=m)

        elif data.startswith("promo_plan:"):
            parts = data.split(":")
            code = parts[1]; plan = parts[2]
            p = PLAN_LIMITS.get(plan); promo = db.get_promo_by_type(code, 'percent')
            if not p or not promo:
                return safe_answer(call.id, "❌ Invalid promo or plan!", show_alert=True)
            if db.user_used_promo(uid, code):
                return safe_answer(call.id, "❌ You already used this promo code!", show_alert=True)
            discount = int(promo.get('discount_pct', 0))
            original = p['price']; discounted = int(original * (100 - discount) / 100)
            state.set_state(uid, {
                'action': 'promo_paying', 'promo_code': code,
                'promo_plan': plan, 'promo_amount': discounted, 'discount_pct': discount})
            safe_edit(
                f"💰 <b>{p['name']} — DISCOUNTED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎟 Code: <code>{code}</code>\n"
                f"💯 Discount: {discount}%\n\n"
                f"💵 Original: <s>{original} BDT</s>\n"
                f"💰 You pay: <b>{discounted} BDT</b>\n\n"
                f"👇 Choose payment method:",
                chat_id, msg_id,
                reply_markup=promo_pay_method_kb(code, plan, discounted))
            safe_answer(call.id)

        elif data.startswith("promo_pay:"):
            parts = data.split(":")
            code = parts[1]; plan = parts[2]; mk = parts[3]
            p = PLAN_LIMITS.get(plan); pm = PAYMENT_METHODS.get(mk)
            promo = db.get_promo_by_type(code, 'percent')
            if not p or not pm or not promo:
                return safe_answer(call.id, "❌ Invalid!", show_alert=True)
            if db.user_used_promo(uid, code):
                return safe_answer(call.id, "❌ Promo already used!", show_alert=True)
            discount = int(promo.get('discount_pct', 0))
            discounted = int(p['price'] * (100 - discount) / 100)
            state.set_pay_state(uid, {
                'step': 'wait_trx', 'plan': plan, 'method': mk,
                'amount': discounted, 'promo_code': code})
            safe_edit(
                f"{pm['icon']} <b>{pm['name']} Payment</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎟 Promo: <code>{code}</code> (-{discount}%)\n"
                f"📱 Send to: <code>{pm['number']}</code>\n"
                f"📝 Type: {pm['type']}\n"
                f"💰 Amount: <b>{discounted} BDT</b>\n"
                f"📦 Plan: {p['name']}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📤 <b>Now send the Transaction ID:</b>",
                chat_id, msg_id)
            safe_answer(call.id)

        elif data.startswith("promo_wallet:"):
            parts = data.split(":")
            code = parts[1]; plan = parts[2]
            p = PLAN_LIMITS.get(plan); promo = db.get_promo_by_type(code, 'percent')
            u = db.get_user(uid)
            if not p or not promo or not u:
                return safe_answer(call.id, "❌ Invalid!", show_alert=True)
            if db.user_used_promo(uid, code):
                return safe_answer(call.id, "❌ Promo already used!", show_alert=True)
            discount = int(promo.get('discount_pct', 0))
            discounted = int(p['price'] * (100 - discount) / 100)
            if u.get('wallet_balance', 0) < discounted:
                return safe_answer(call.id,
                    f"❌ Insufficient balance!\nNeed: {discounted} BDT\nHave: {u.get('wallet_balance', 0)} BDT",
                    show_alert=True)
            db.wallet_tx(uid, discounted, 'purchase', f"Plan: {plan} (-{discount}% promo {code})")
            db.set_sub(uid, plan, 0 if plan == 'lifetime' else 30)
            db.mark_user_promo_used(uid, code)
            db.use_promo(code)
            state.clear_state(uid)
            safe_answer(call.id, "✅ Plan activated!", show_alert=True)
            safe_edit(
                f"✅ <b>PLAN ACTIVATED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 Plan: {p['name']}\n"
                f"🎟 Promo: <code>{code}</code> (-{discount}%)\n"
                f"💰 Paid: {discounted} BDT\n"
                f"💡 Promo code used — no longer valid.\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=back_btn())

        elif data == "adm_promo":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            promos = db.all_promos()
            t = f"🎟 <b>Promo Codes ({len(promos)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for p in promos[:15]:
                st = "🟢" if p.get('is_active') else "🔴"
                ptype = p.get('promo_type', 'percent')
                if ptype == 'wallet': val = f"💵 {p.get('wallet_amount', 0)} Tk"
                else: val = f"💰 {p.get('discount_pct', 0)}%"
                t += (f"  {st} <code>{p.get('code','?')}</code> — {val} "
                      f"— {p.get('used_count', 0)}/{p.get('max_uses', 0)}\n")
            if not promos: t += "  No promo codes yet.\n"
            t += "\n━━━━━━━━━━━━━━━━━━━━\n👇 Choose type to create:"
            safe_edit(t, chat_id, msg_id, reply_markup=adm_promo_choice_kb())

        elif data == "adm_promo_tk":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'adm_promo_tk'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="adm_promo", style="danger"))
            safe_edit(
                f"💵 <b>Create TK Promo</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📝 Format: <code>CODE TK MAX_USES</code>\n\n"
                f"Example: <code>WELCOME100 100 50</code>\n"
                f"  → Code: WELCOME100\n"
                f"  → Wallet: 100 Tk\n"
                f"  → Max uses: 50\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=m)

        elif data == "adm_promo_pct":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'adm_promo_create'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="adm_promo", style="danger"))
            safe_edit(
                f"💰 <b>Create % Discount Promo</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📝 Format: <code>CODE DISCOUNT% MAX_USES</code>\n\n"
                f"Example: <code>SAVE50 50 100</code>\n"
                f"  → Code: SAVE50\n"
                f"  → Discount: 50%\n"
                f"  → Max uses: 100\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=m)

        elif data == "adm_toggle_approval":
            if not state.is_admin(uid): return
            new_val = db.toggle_setting("approval_required", "1")
            on = (new_val == "1")
            safe_answer(call.id, f"File Approval: {'🟢 ON' if on else '🔴 OFF'}", show_alert=True)
            db.admin_log(uid, 'toggle_approval', det=new_val)
            s_adm = db.stats()
            rn_adm = len([k for k in bot_scripts if is_running(k)])
            tickets_adm = len(db.open_tickets())
            safe_edit(
                f"👑 <b>ADMIN PANEL</b>\n{BRAND_TAG}\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total Users: {s_adm['users']} (+{s_adm['today']} today)\n"
                f"🤖 Running Bots: {rn_adm}\n💎 Active Subs: {s_adm['active_subs']}\n"
                f"🚫 Banned: {s_adm['banned']}\n💳 Pending Payments: {s_adm['pending']}\n"
                f"🎫 Open Tickets: {tickets_adm}\n💰 Total Revenue: {s_adm['revenue']} BDT\n\n"
                f"🔐 Force Sub: {'🟢 ON' if state.force_sub_enabled else '🔴 OFF'}\n"
                f"🔒 Bot Lock: {'🔒 LOCKED' if state.bot_locked else '🔓 OPEN'}\n"
                f"📥 File Approval: {'🟢 ON' if on else '🔴 OFF'}\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=admin_kb(on))

        elif data == "adm_pending_files":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            rows = db.pending_bots()
            t = f"📥 <b>Pending Files ({len(rows)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            if rows:
                for b in rows[:20]:
                    t += (f"⏳ #{b['bot_id']} — <code>{b['bot_name'][:22]}</code>\n"
                          f"   👤 <code>{b['user_id']}</code> | "
                          f"📅 {str(b.get('created_at',''))[:10]}\n\n")
            else: t += "📭 No pending files!\n"
            t += "━━━━━━━━━━━━━━━━━━━━"
            safe_edit(t, chat_id, msg_id, reply_markup=pending_files_kb())

        elif data.startswith("review_file:"):
            if not state.is_admin(uid): return
            bid = data.split(":")[1]
            bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌ Not found!", show_alert=True)
            safe_edit(
                f"📄 <b>Review File #{bid}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📁 Name: <code>{bd['bot_name'][:30]}</code>\n"
                f"👤 User: <code>{bd['user_id']}</code>\n"
                f"🔤 Type: {bd.get('file_type','?').upper()}\n"
                f"📄 Entry: <code>{bd.get('entry_file','?')}</code>\n"
                f"📊 Approval: ⏳ Pending\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=file_approval_kb(bid))
            safe_answer(call.id)

        elif data.startswith("approve_file:"):
            if not state.is_admin(uid): return
            bid = data.split(":")[1]
            bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌ Not found!", show_alert=True)

            db.set_approval_status(bid, 'approved')
            db.admin_log(uid, 'approve_file', bd['user_id'], f"#{bid}")
            safe_answer(call.id, "✅ File approved!")

            safe_delete(chat_id, msg_id)
            p_cid = bd.get('pending_chat_id'); p_mid = bd.get('pending_msg_id')
            if p_cid and p_mid:
                try: safe_delete(p_cid, p_mid)
                except Exception: pass

            mk_u = types.InlineKeyboardMarkup(row_width=1)
            mk_u.add(
                types.InlineKeyboardButton("▶️ Start Now",
                                           callback_data=f"bot_start:{bid}",
                                           style="success"),
                types.InlineKeyboardButton("🤖 My Bots",
                                           callback_data="menu_mybots",
                                           style="primary"))
            safe_send(bd['user_id'],
                f"✅ <b>FILE APPROVED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📁 <code>{bd['bot_name'][:25]}</code>\n🆔 Bot ID: #{bid}\n\n"
                f"▶️ You can now start your bot!\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                reply_markup=mk_u)

        elif data.startswith("reject_file:"):
            if not state.is_admin(uid): return
            bid = data.split(":")[1]
            bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌ Not found!", show_alert=True)

            db.set_approval_status(bid, 'rejected')
            db.admin_log(uid, 'reject_file', bd['user_id'], f"#{bid}")
            safe_answer(call.id, "❌ File rejected!")

            safe_delete(chat_id, msg_id)
            p_cid = bd.get('pending_chat_id'); p_mid = bd.get('pending_msg_id')
            if p_cid and p_mid:
                try: safe_delete(p_cid, p_mid)
                except Exception: pass

            safe_send(bd['user_id'],
                f"❌ <b>FILE REJECTED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📁 <code>{bd['bot_name'][:25]}</code>\n🆔 Bot ID: #{bid}\n\n"
                f"Your upload was rejected by admin.\n"
                f"📞 Contact: {YOUR_USERNAME}\n"
                f"━━━━━━━━━━━━━━━━━━━━")

        elif data.startswith("pay_approve:"):
            if not state.is_admin(uid): return
            pid = data.split(":")[1]
            p = db.approve_pay(pid, uid)
            safe_delete(chat_id, msg_id)
            if p:
                try:
                    msgs = db.get_payment_msgs(pid)
                    uc = msgs.get('user_chat_id'); um = msgs.get('user_msg_id')
                    if uc and um:
                        try: safe_delete(uc, um)
                        except Exception: pass
                    for ent in msgs.get('admin_msgs', []):
                        try:
                            if ent.get('cid') == chat_id and ent.get('mid') == msg_id: continue
                            safe_delete(ent.get('cid'), ent.get('mid'))
                        except Exception: pass
                except Exception: pass

                safe_answer(call.id, "✅ Payment approved!")
                safe_send(p['user_id'],
                    f"✅ <b>PAYMENT APPROVED!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🆔 #{pid}\n"
                    f"📦 Plan: {PLAN_LIMITS.get(p['plan'], {}).get('name', p['plan'])}\n"
                    f"💰 {p['amount']} BDT\n\n"
                    f"🎉 Your plan is now active!\n"
                    f"━━━━━━━━━━━━━━━━━━━━",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("📤 Deploy Bot", callback_data="menu_deploy", style="success"),
                        types.InlineKeyboardButton("💎 My Plan", callback_data="menu_sub", style="primary")))
                db.admin_log(uid, 'approve_pay', p['user_id'], f"#{pid}")
            else:
                safe_answer(call.id, "❌ Payment not found!", show_alert=True)

        elif data.startswith("pay_reject:"):
            if not state.is_admin(uid): return
            pid = data.split(":")[1]
            p_info = db.get_pay(pid)
            db.reject_pay(pid, uid)
            safe_delete(chat_id, msg_id)
            try:
                msgs = db.get_payment_msgs(pid)
                uc = msgs.get('user_chat_id'); um = msgs.get('user_msg_id')
                if uc and um:
                    try: safe_delete(uc, um)
                    except Exception: pass
                for ent in msgs.get('admin_msgs', []):
                    try:
                        if ent.get('cid') == chat_id and ent.get('mid') == msg_id: continue
                        safe_delete(ent.get('cid'), ent.get('mid'))
                    except Exception: pass
            except Exception: pass

            safe_answer(call.id, "❌ Payment rejected!")
            if p_info:
                safe_send(p_info['user_id'],
                    f"❌ <b>PAYMENT REJECTED</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🆔 #{pid}\n💰 {p_info['amount']} BDT\n\n"
                    f"💡 Possible reasons:\n"
                    f"  • Wrong Transaction ID\n"
                    f"  • Amount not received\n"
                    f"  • Duplicate submission\n\n"
                    f"📞 Contact: {YOUR_USERNAME}\n"
                    f"━━━━━━━━━━━━━━━━━━━━")
            db.admin_log(uid, 'reject_pay', det=f"#{pid}")

        elif data == "menu_help":
            safe_answer(call.id)
            safe_edit(
                f"📚 <b>HELP CENTER</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Welcome to {BRAND}!\n"
                f"Select a topic below.\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=help_menu_kb())

        elif data == "menu_admin":
            if not state.is_admin(uid): return safe_answer(call.id, "❌ Admins only!", show_alert=True)
            safe_answer(call.id)
            s = db.stats(); rn = len([k for k in bot_scripts if is_running(k)])
            tickets = len(db.open_tickets())
            safe_edit(
                f"👑 <b>ADMIN PANEL</b>\n{BRAND_TAG}\n━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total Users: {s['users']} (+{s['today']} today)\n"
                f"🤖 Running Bots: {rn}\n💎 Active Subs: {s['active_subs']}\n"
                f"🚫 Banned: {s['banned']}\n💳 Pending Payments: {s['pending']}\n"
                f"🎫 Open Tickets: {tickets}\n💰 Total Revenue: {s['revenue']} BDT\n\n"
                f"🔐 Force Sub: {'🟢 ON' if state.force_sub_enabled else '🔴 OFF'}\n"
                f"🔒 Bot Lock: {'🔒 LOCKED' if state.bot_locked else '🔓 OPEN'}\n"
                f"📥 File Approval: {'🟢 ON' if approval_is_on() else '🔴 OFF'}\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=admin_kb(approval_is_on()))

        elif data == "menu_wallet":
            safe_answer(call.id)
            u = db.get_user(uid); hist = db.wallet_hist(uid, 10)
            t = f"💰 <b>WALLET</b>\n━━━━━━━━━━━━━━━━━━━━\n\nBalance: <b>{u.get('wallet_balance', 0) if u else 0} BDT</b>\n\n📋 Recent Transactions:\n"
            for tx in hist[:8]:
                ic = "+" if tx.get('tx_type') in ('credit','referral','refund','bonus') else "-"
                t += f"  {ic}{tx.get('amount', 0)} BDT — {tx.get('tx_type', '?')} | {str(tx.get('created_at', ''))[:10]}\n"
            if not hist: t += "  No transactions yet."
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home", style="primary"))
            safe_edit(t + "\n━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id, reply_markup=m)

        elif data == "menu_ref":
            safe_answer(call.id)
            u = db.get_user(uid)
            rc = u.get('referral_code', gen_ref_code(uid)) if u else gen_ref_code(uid)
            lnk = f"https://t.me/{BOT_USERNAME}?start={rc}"
            t = (
                f"🎁 <b>REFERRAL PROGRAM</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔗 Your Link:\n<code>{lnk}</code>\n\n"
                f"💰 Earn per referral:\n"
                f"  • +{REF_COMMISSION} BDT wallet bonus\n"
                f"  • +{REF_BONUS_DAYS} days premium\n\n"
                f"📊 Your Stats:\n"
                f"  👥 Referrals: {u.get('referral_count', 0) if u else 0}\n"
                f"  💰 Earnings: {u.get('referral_earnings', 0) if u else 0} BDT\n"
                f"  🏆 Level: {u.get('referral_level', 'Bronze').title() if u else 'Bronze'}\n"
                f"━━━━━━━━━━━━━━━━━━━━")
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("📋 Copy Link",    callback_data=f"ref_copy:{rc}", style="primary"),
                types.InlineKeyboardButton("👥 My Referrals", callback_data="ref_list",        style="primary"))
            m.add(types.InlineKeyboardButton("🏆 Leaderboard", callback_data="ref_board", style="primary"))
            m.add(types.InlineKeyboardButton("🏠 Main Menu",   callback_data="go_home",   style="primary"))
            safe_edit(t, chat_id, msg_id, reply_markup=m)

        elif data == "menu_stats":
            safe_answer(call.id)
            ss = sys_stats(); rn = len([k for k in bot_scripts if is_running(k)])
            u = db.get_user(uid); bc = db.bot_count(uid)
            role = get_role_label(uid)
            t = (
                f"📊 <b>STATISTICS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🖥 <b>System</b>\n"
                f"  CPU: {ss['cpu']}% | RAM: {ss['mem']}%\n"
                f"  Disk: {ss['disk']}% | Uptime: {ss['up']}\n\n"
                f"🤖 <b>Your Stats</b>\n"
                f"  Bots: {bc} | Running: {rn}\n"
                f"  Plan: {role}\n"
                f"  Wallet: {u.get('wallet_balance', 0) if u else 0} BDT\n"
                f"━━━━━━━━━━━━━━━━━━━━")
            safe_edit(t, chat_id, msg_id, reply_markup=back_btn())

        elif data == "menu_running":
            safe_answer(call.id)
            bots_list = db.get_bots(uid)
            active = [(b, bot_running(uid, b['bot_name'])) for b in bots_list]
            act = [x for x in active if x[1]]
            t = f"🟢 <b>Running Bots ({len(act)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            m = types.InlineKeyboardMarkup(row_width=1)
            for b, _ in act:
                sk = f"{uid}_{b['bot_name']}"; ram, cpu = bot_res(sk)
                t += f"  🐍 <code>{b['bot_name'][:20]}</code>\n  💾 {ram}MB | ⚡ {cpu}%\n\n"
                m.add(types.InlineKeyboardButton(f"⚙️ {b['bot_name'][:15]}",
                        callback_data=f"bot_detail:{b['bot_id']}", style="primary"))
            if not act: t += "No bots running!"
            m.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home", style="primary"))
            safe_edit(t + "━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id, reply_markup=m)

        elif data == "menu_notif":
            safe_answer(call.id)
            db.mark_read(uid); notifs = db.get_notifs(uid, 10)
            t = f"🔔 <b>NOTIFICATIONS</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for n in notifs:
                t += f"📌 <b>{n.get('title', 'Notice')}</b>\n{n.get('message', '')}\n📅 {str(n.get('created_at', ''))[:16]}\n\n"
            if not notifs: t += "No notifications!"
            safe_edit(t + "━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id, reply_markup=back_btn())

        elif data == "menu_support":
            safe_answer(call.id)
            state.set_state(uid, {'action': 'ticket'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="go_home", style="danger"))
            safe_edit(f"🎫 <b>CREATE SUPPORT TICKET</b>\n"
                      f"━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Describe your issue below:\n"
                      f"━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "menu_settings":
            safe_answer(call.id)
            u = db.get_user(uid)
            role = get_role_label(uid)
            t = (f"⚙️ <b>SETTINGS</b>\n"
                 f"━━━━━━━━━━━━━━━━━━━━\n\n"
                 f"🆔 ID: <code>{uid}</code>\n"
                 f"📛 Name: {u.get('full_name', '?') if u else '?'}\n"
                 f"👤 @{u.get('username', 'N/A') if u else 'N/A'}\n"
                 f"💎 Role: {role}\n"
                 f"🔑 Ref Code: <code>{u.get('referral_code', '?') if u else '?'}</code>\n"
                 f"━━━━━━━━━━━━━━━━━━━━")
            safe_edit(t, chat_id, msg_id, reply_markup=back_btn())

        elif data == "menu_speed":
            safe_answer(call.id); ss = sys_stats()
            start_t = time.time()
            try:
                requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=5)
                latency = round((time.time() - start_t) * 1000, 2)
            except Exception: latency = round((time.time() - start_t) * 1000, 2)
            safe_edit(
                f"⚡ <b>SPEED TEST</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🏓 Telegram Latency: {latency}ms\n"
                f"⏱️ Uptime: {ss['up']}\n"
                f"💻 CPU: {ss['cpu']}% | RAM: {ss['mem']}%\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=back_btn())

        elif data.startswith("bot_detail:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌ Bot not found!", show_alert=True)
            sk = f"{bd['user_id']}_{bd['bot_name']}"
            rn = is_running(sk); ram, cpu = bot_res(sk) if rn else (0, 0)
            uptime_str = "—"
            if rn and sk in bot_scripts:
                st = bot_scripts[sk].get('start_time')
                if st: uptime_str = str(datetime.now() - st).split('.')[0]
            icon = "🐍" if bd['file_type'] == 'py' else "🟨"
            auto = bd.get('auto_restart_24h', 0)
            appr = bd.get('approval_status', 'approved')
            appr_line = {'pending': '⏳ Pending Approval',
                         'rejected': '❌ Rejected',
                         'approved': '✅ Approved'}.get(appr, '✅ Approved')
            t = (
                f"{icon} <b>{bd['bot_name'][:22]}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 Bot ID: #{bid}\n"
                f"📄 Entry: <code>{bd['entry_file']}</code>\n"
                f"🔤 Type: {bd['file_type'].upper()}\n"
                f"📊 Status: {'🟢 Running' if rn else '🔴 Stopped'}\n"
                f"📋 Approval: {appr_line}\n"
                f"💾 RAM: {ram}MB | ⚡ CPU: {cpu}%\n"
                f"⏱️ Uptime: {uptime_str}\n"
                f"🔄 Restarts: {bd.get('total_restarts', 0)}\n"
                f"📅 Created: {str(bd.get('created_at', '?'))[:10]}\n"
                f"━━━━━━━━━━━━━━━━━━━━")
            allow_ar = plan_allows_auto_restart(bd['user_id'])
            safe_edit(t, chat_id, msg_id, reply_markup=bot_action_kb(bid, rn, auto, appr, allow_ar))
            safe_answer(call.id)

        elif data.startswith("bot_start:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌ Not found!", show_alert=True)
            appr = bd.get('approval_status', 'approved')
            if appr == 'pending':
                return safe_answer(call.id, "⏳ File is waiting for admin approval.", show_alert=True)
            if appr == 'rejected':
                return safe_answer(call.id, "❌ File was rejected by admin.", show_alert=True)
            if not db.is_active(bd['user_id']):
                return safe_answer(call.id, "⚠️ Subscription expired!", show_alert=True)
            sk = f"{bd['user_id']}_{bd['bot_name']}"
            if is_running(sk):
                return safe_answer(call.id, "⚠️ Already running!", show_alert=True)
            safe_answer(call.id, "🚀 Starting...")
            threading.Thread(target=run_bot_script, args=(bid, chat_id), daemon=True).start()

        elif data.startswith("bot_stop:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌ Not found!", show_alert=True)
            sk = f"{bd['user_id']}_{bd['bot_name']}"
            if sk in bot_scripts:
                kill_tree(bot_scripts[sk]); cleanup_script(sk)
            db.update_bot(bid, status='stopped', last_stopped=datetime.now().isoformat())
            safe_answer(call.id, "✅ Stopped!")
            rn = False; icon = "🐍" if bd['file_type'] == 'py' else "🟨"
            auto = bd.get('auto_restart_24h', 0); appr = bd.get('approval_status', 'approved')
            t = (f"{icon} <b>{bd['bot_name'][:22]}</b>\n"
                 f"━━━━━━━━━━━━━━━━━━━━\n\n"
                 f"🆔 Bot ID: #{bid}\n"
                 f"📄 Entry: <code>{bd['entry_file']}</code>\n"
                 f"🔤 Type: {bd['file_type'].upper()}\n"
                 f"📊 Status: 🔴 Stopped\n"
                 f"💾 RAM: 0MB | ⚡ CPU: 0%\n"
                 f"⏱️ Uptime: —\n"
                 f"🔄 Restarts: {bd.get('total_restarts', 0)}\n"
                 f"📅 Created: {str(bd.get('created_at', '?'))[:10]}\n"
                 f"━━━━━━━━━━━━━━━━━━━━")
            allow_ar = plan_allows_auto_restart(bd['user_id'])
            safe_edit(t, chat_id, msg_id, reply_markup=bot_action_kb(bid, rn, auto, appr, allow_ar))

        elif data.startswith("bot_restart:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌ Not found!", show_alert=True)
            sk = f"{bd['user_id']}_{bd['bot_name']}"
            if sk in bot_scripts:
                kill_tree(bot_scripts[sk]); cleanup_script(sk)
            db.update_bot(bid, total_restarts=bd.get('total_restarts', 0) + 1)
            time.sleep(2)
            safe_answer(call.id, "🔄 Restarting...")
            threading.Thread(target=run_bot_script, args=(bid, chat_id), daemon=True).start()

        elif data.startswith("bot_logs:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌ Bot not found!", show_alert=True)
            if bd['user_id'] != uid and not state.is_admin(uid):
                return safe_answer(call.id, "❌ Access denied!", show_alert=True)
            sk = f"{bd['user_id']}_{bd['bot_name']}"
            lp = os.path.join(LOGS_DIR, f"{sk}.log")
            logs = "📭 No logs available."
            if os.path.exists(lp):
                try:
                    with open(lp, 'r', encoding='utf-8', errors='ignore') as f:
                        raw = f.read()
                    logs = raw[-3000:] if raw.strip() else "📭 Log file is empty."
                except Exception as log_err:
                    logs = f"❌ Error reading log: {str(log_err)[:100]}"
            import html as _html
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("🔄 Refresh",   callback_data=f"bot_logs:{bid}",      style="primary"),
                types.InlineKeyboardButton("🗑 Clear Logs", callback_data=f"bot_clearlogs:{bid}", style="danger"))
            m.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"bot_detail:{bid}", style="primary"))
            log_text = f"📋 <b>Logs — Bot #{bid}</b>\n<code>{bd['bot_name'][:20]}</code>\n"
            log_text += f"━━━━━━━━━━━━━━━━━━━━\n\n<code>{_html.escape(logs)}</code>"
            if len(log_text) > 4000: log_text = log_text[:3950] + "\n...</code>"
            safe_edit(log_text, chat_id, msg_id, reply_markup=m)
            safe_answer(call.id)

        elif data.startswith("bot_clearlogs:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if bd:
                sk = f"{bd['user_id']}_{bd['bot_name']}"
                lp = os.path.join(LOGS_DIR, f"{sk}.log")
                try:
                    with open(lp, 'w') as f: f.write("")
                except Exception: pass
            safe_answer(call.id, "🗑 Logs cleared!")
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("🔄 Refresh",   callback_data=f"bot_logs:{bid}",      style="primary"),
                types.InlineKeyboardButton("🗑 Clear Logs", callback_data=f"bot_clearlogs:{bid}", style="danger"))
            m.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"bot_detail:{bid}", style="primary"))
            safe_edit(f"📋 <b>Logs — Bot #{bid}</b>\n"
                      f"━━━━━━━━━━━━━━━━━━━━\n\n<code>📭 Logs cleared.</code>",
                      chat_id, msg_id, reply_markup=m)

        elif data.startswith("bot_del:"):
            bid = data.split(":")[1]
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("✅ Yes, Delete", callback_data=f"bot_confirm_del:{bid}", style="danger"),
                types.InlineKeyboardButton("❌ Cancel",      callback_data=f"bot_detail:{bid}",      style="primary"))
            safe_edit(f"🗑 <b>Delete Bot #{bid}?</b>\n\n⚠️ This cannot be undone!",
                      chat_id, msg_id, reply_markup=m)
            safe_answer(call.id)

        elif data.startswith("bot_confirm_del:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if bd:
                sk = f"{bd['user_id']}_{bd['bot_name']}"
                if sk in bot_scripts:
                    kill_tree(bot_scripts[sk]); cleanup_script(sk)
                if os.path.isdir(bd['file_path']):
                    shutil.rmtree(bd['file_path'], ignore_errors=True)
                db.del_bot(bid)
            safe_answer(call.id, "✅ Bot deleted!")
            bots_list = db.get_bots(uid); pl = db.get_plan(uid)
            mx = '♾️' if pl['max_bots'] == -1 else str(pl['max_bots'])
            if not bots_list:
                m2 = types.InlineKeyboardMarkup(row_width=2)
                m2.add(types.InlineKeyboardButton("📤 Deploy Bot", callback_data="menu_deploy", style="success"))
                m2.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home", style="primary"))
                safe_edit(f"📭 <b>No bots yet!</b>\n\nDeploy your first bot!\n📦 Slots: 0/{mx}\n"
                          f"━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id, reply_markup=m2)
            else:
                rn2 = sum(1 for b in bots_list if bot_running(uid, b['bot_name']))
                t2 = f"🤖 <b>My Bots</b> ({len(bots_list)})\n🟢 Running: {rn2} | 🔴 Stopped: {len(bots_list)-rn2}\n📦 Limit: {mx}\n━━━━━━━━━━━━━━━━━━━━\n\n"
                m2 = types.InlineKeyboardMarkup(row_width=1)
                for b in bots_list:
                    r2 = bot_running(uid, b['bot_name'])
                    ic2 = "🐍" if b['file_type'] == 'py' else "🟨"
                    appr2 = b.get('approval_status', 'approved')
                    if appr2 == 'pending': st_icon2 = "⏳"
                    elif appr2 == 'rejected': st_icon2 = "❌"
                    else: st_icon2 = "🟢" if r2 else "🔴"
                    t2 += f"{st_icon2} {ic2} <code>{b['bot_name'][:20]}</code> — #{b['bot_id']}\n"
                    m2.add(types.InlineKeyboardButton(
                        f"{st_icon2} {ic2} {b['bot_name'][:15]} — #{b['bot_id']}",
                        callback_data=f"bot_detail:{b['bot_id']}",
                        style="success" if (r2 and appr2 == 'approved') else "primary"))
                m2.add(types.InlineKeyboardButton("📤 Deploy New Bot", callback_data="menu_deploy", style="success"))
                m2.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home", style="primary"))
                safe_edit(t2, chat_id, msg_id, reply_markup=m2)

        elif data.startswith("bot_res:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌ Not found!", show_alert=True)
            sk = f"{bd['user_id']}_{bd['bot_name']}"
            rn = is_running(sk); ram, cpu = bot_res(sk) if rn else (0, 0)
            uptime_str = "—"
            if rn and sk in bot_scripts:
                st_t = bot_scripts[sk].get('start_time')
                if st_t: uptime_str = str(datetime.now() - st_t).split('.')[0]
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("🔄 Refresh", callback_data=f"bot_res:{bid}",    style="primary"),
                types.InlineKeyboardButton("🔙 Back",    callback_data=f"bot_detail:{bid}", style="primary"))
            safe_edit(
                f"📊 <b>Resources — Bot #{bid}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🟢 Status: {'Running' if rn else '🔴 Stopped'}\n"
                f"💾 RAM: {ram} MB\n"
                f"⚡ CPU: {cpu}%\n"
                f"⏱️ Uptime: {uptime_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=m)
            safe_answer(call.id)

        elif data.startswith("bot_redetect:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌!", show_alert=True)
            wd = bd['file_path'] if os.path.isdir(bd['file_path']) else user_folder(bd['user_id'])
            entry, ft, rp = det.report(wd)
            if entry:
                db.update_bot(bid, entry_file=entry, file_type=ft)
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(
                    types.InlineKeyboardButton("▶️ Start", callback_data=f"bot_start:{bid}",  style="success"),
                    types.InlineKeyboardButton("🔙 Back",  callback_data=f"bot_detail:{bid}", style="primary"))
                safe_edit(f"🔍 <b>Re-Detection Complete</b>\n\n{rp}\n\n✅ Entry file updated!",
                          chat_id, msg_id, reply_markup=m)
            else:
                safe_edit(f"❌ <b>Auto-detect failed!</b>\n\nNo runnable files found.",
                          chat_id, msg_id, reply_markup=back_btn(f"bot_detail:{bid}", "🔙 Back"))
            safe_answer(call.id)

        elif data.startswith("bot_dl:"):
            bid = data.split(":")[1]; bd = db.get_bot(bid)
            if not bd: return safe_answer(call.id, "❌!", show_alert=True)
            fp = os.path.join(bd['file_path'], bd['entry_file']) if os.path.isdir(bd['file_path']) \
                 else os.path.join(user_folder(bd['user_id']), bd['bot_name'])
            if os.path.exists(fp):
                try:
                    with open(fp, 'rb') as f:
                        bot.send_document(uid, f, caption=f"📄 {bd['bot_name']}")
                except: safe_send(uid, "❌ Could not send file.")
            else: safe_send(uid, "❌ File not found on server.")
            safe_answer(call.id, "📥 Sending...")

        elif data.startswith("bot_autorestart:"):
            bid = data.split(":")[1]
            bd = db.get_bot(bid)
            if not bd:
                return safe_answer(call.id, "❌ Bot not found!", show_alert=True)
            if not plan_allows_auto_restart(bd['user_id']):
                return safe_answer(call.id,
                    "🔒 Auto Restart is a premium feature.\n"
                    "Upgrade your plan to enable it!",
                    show_alert=True)
            new_val = db.toggle_auto_restart(bid)
            bd = db.get_bot(bid)
            if bd:
                sk = f"{bd['user_id']}_{bd['bot_name']}"
                rn = is_running(sk); ram, cpu = bot_res(sk) if rn else (0, 0)
                uptime_str = "—"
                if rn and sk in bot_scripts:
                    st = bot_scripts[sk].get('start_time')
                    if st: uptime_str = str(datetime.now() - st).split('.')[0]
                icon = "🐍" if bd['file_type'] == 'py' else "🟨"
                auto = bd.get('auto_restart_24h', 0)
                appr = bd.get('approval_status', 'approved')
                t = (f"{icon} <b>{bd['bot_name'][:22]}</b>\n"
                     f"━━━━━━━━━━━━━━━━━━━━\n\n"
                     f"🆔 Bot ID: #{bid}\n"
                     f"📄 Entry: <code>{bd['entry_file']}</code>\n"
                     f"🔤 Type: {bd['file_type'].upper()}\n"
                     f"📊 Status: {'🟢 Running' if rn else '🔴 Stopped'}\n"
                     f"💾 RAM: {ram}MB | ⚡ CPU: {cpu}%\n"
                     f"⏱️ Uptime: {uptime_str}\n"
                     f"🔄 Restarts: {bd.get('total_restarts', 0)}\n"
                     f"📅 Created: {str(bd.get('created_at', '?'))[:10]}\n"
                     f"━━━━━━━━━━━━━━━━━━━━")
                allow_ar = plan_allows_auto_restart(bd['user_id'])
                safe_edit(t, chat_id, msg_id, reply_markup=bot_action_kb(bid, rn, auto, appr, allow_ar))
            safe_answer(call.id, f"✅ Auto-restart {'enabled' if new_val else 'disabled'}!")

        elif data.startswith("ref_copy:"):
            rc = data.split(":", 1)[1]
            lnk = f"https://t.me/{BOT_USERNAME}?start={rc}"
            safe_answer(call.id)
            safe_send(uid, f"📋 <b>Your Referral Link:</b>\n\n<code>{lnk}</code>\n\n👆 Tap to copy!")

        elif data == "ref_list":
            refs = db.user_refs(uid)
            t = f"📋 <b>Your Referrals ({len(refs)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for r in refs[:20]:
                ru = db.get_user(r['referred_id'])
                name = ru.get('full_name', str(r['referred_id'])) if ru else str(r['referred_id'])
                t += f"  👤 {name} — +{r.get('commission', 0)} BDT\n    📅 {str(r.get('created_at', ''))[:10]}\n\n"
            if not refs: t += "No referrals yet!"
            safe_edit(t + "━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id,
                      reply_markup=back_btn("menu_ref", "🔙 Referral"))
            safe_answer(call.id)

        elif data == "ref_board":
            lb = db.ref_board(10)
            t = f"🏆 <b>Referral Leaderboard</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            medals = ['🥇', '🥈', '🥉']
            for i, l in enumerate(lb):
                icon = medals[i] if i < 3 else f"  #{i + 1}"
                t += f"{icon} {l.get('full_name', '?')} — {l.get('referral_count', 0)} refs ({l.get('referral_earnings', 0)} BDT)\n"
            if not lb: t += "No referrals yet!\n"
            safe_edit(t + "\n━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id,
                      reply_markup=back_btn("menu_ref", "🔙 Referral"))
            safe_answer(call.id)

        elif data.startswith("plan_select:"):
            pk = data.split(":")[1]; p = PLAN_LIMITS.get(pk)
            if not p: return safe_answer(call.id, "❌ Plan not found!", show_alert=True)
            slots = '♾️' if p['max_bots'] == -1 else str(p['max_bots'])
            safe_edit(
                f"{p['name']}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🤖 Bot Slots: {slots}\n"
                f"💾 RAM: {p['ram']}MB\n"
                f"🔄 Auto Restart: {'✅' if p['auto_restart'] else '❌'}\n"
                f"💰 Price: <b>{p['price']} BDT/month</b>\n\n"
                f"Select payment method:\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=pay_method_kb(pk))
            safe_answer(call.id)

        elif data.startswith("pay_method:"):
            parts = data.split(":")
            pk = parts[1]; mk = parts[2]
            p = PLAN_LIMITS.get(pk); pm_info = PAYMENT_METHODS.get(mk)
            if not p or not pm_info: return safe_answer(call.id, "❌ Error!", show_alert=True)
            state.set_pay_state(uid, {'step': 'wait_trx', 'plan': pk, 'method': mk, 'amount': p['price']})
            safe_edit(
                f"{pm_info['icon']} <b>{pm_info['name']} Payment</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📱 Send to: <code>{pm_info['number']}</code>\n"
                f"📝 Type: {pm_info['type']}\n"
                f"💰 Amount: <b>{p['price']} BDT</b>\n"
                f"📦 Plan: {p['name']}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📤 <b>Now send the Transaction ID below:</b>",
                chat_id, msg_id)
            safe_answer(call.id)

        elif data.startswith("pay_wallet:"):
            pk = data.split(":")[1]
            u = db.get_user(uid); p = PLAN_LIMITS.get(pk)
            if not u or not p: return safe_answer(call.id, "❌ Error!", show_alert=True)
            if u.get('wallet_balance', 0) < p['price']:
                return safe_answer(call.id,
                    f"❌ Insufficient balance!\nNeed: {p['price']} BDT | Have: {u.get('wallet_balance', 0)} BDT",
                    show_alert=True)
            db.wallet_tx(uid, p['price'], 'purchase', f"Plan: {pk}")
            db.set_sub(uid, pk, 0 if pk == 'lifetime' else 30)
            safe_answer(call.id, "✅ Plan activated!", show_alert=True)
            safe_edit(
                f"✅ <b>PLAN ACTIVATED!</b>\n\n"
                f"📦 {p['name']}\n"
                f"💰 {p['price']} BDT deducted\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=back_btn())

        elif data == "adm_stats":
            if not state.is_admin(uid): return
            safe_answer(call.id); s = db.stats(); ss = sys_stats()
            safe_edit(
                f"📊 <b>ADMIN STATISTICS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total Users: {s['users']} (+{s['today']} today)\n"
                f"🤖 Total Bots: {s['bots']}\n"
                f"💎 Active Subs: {s['active_subs']}\n"
                f"🚫 Banned: {s['banned']}\n"
                f"💳 Pending: {s['pending']}\n"
                f"💰 Revenue: {s['revenue']} BDT\n\n"
                f"🖥 System:\n"
                f"  CPU: {ss['cpu']}% | RAM: {ss['mem']}%\n"
                f"  Disk: {ss['disk']}%\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=back_btn("menu_admin", "🔙 Admin"))

        elif data == "adm_payments":
            if not state.is_admin(uid): return
            safe_answer(call.id); pays = db.pending_pay()
            t = f"💳 <b>Pending Payments ({len(pays)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            m = types.InlineKeyboardMarkup(row_width=2)
            for p in pays[:10]:
                pu = db.get_user(p['user_id'])
                t += f"  #{p['payment_id']} — {p['amount']} BDT | {p['plan']} | {p.get('method','?')}\n"
                t += f"  👤 {pu.get('full_name','?') if pu else '?'} (<code>{p['user_id']}</code>)\n\n"
                m.add(
                    types.InlineKeyboardButton(f"✅ #{p['payment_id']}", callback_data=f"pay_approve:{p['payment_id']}", style="success"),
                    types.InlineKeyboardButton(f"❌ #{p['payment_id']}", callback_data=f"pay_reject:{p['payment_id']}",  style="danger"))
            if not pays: t += "No pending payments!"
            m.add(types.InlineKeyboardButton("🔙 Admin", callback_data="menu_admin", style="primary"))
            safe_edit(t + "━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id, reply_markup=m)

        elif data == "adm_broadcast":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'broadcast'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
            safe_edit(f"📢 <b>BROADCAST</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send your message now:\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "adm_addsub":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'adm_addsub_uid'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
            safe_edit(f"➕ <b>ADD SUBSCRIPTION</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send the User ID:\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data.startswith("adm_setplan:"):
            if not state.is_admin(uid): return
            parts = data.split(":"); plan = parts[1]; target = int(parts[2])
            m = types.InlineKeyboardMarkup(row_width=3)
            m.add(
                types.InlineKeyboardButton("7 Days",   callback_data=f"adm_quicksub:{plan}:{target}:7",   style="success"),
                types.InlineKeyboardButton("30 Days",  callback_data=f"adm_quicksub:{plan}:{target}:30",  style="success"),
                types.InlineKeyboardButton("90 Days",  callback_data=f"adm_quicksub:{plan}:{target}:90",  style="success"))
            m.add(
                types.InlineKeyboardButton("180 Days", callback_data=f"adm_quicksub:{plan}:{target}:180", style="success"),
                types.InlineKeyboardButton("365 Days", callback_data=f"adm_quicksub:{plan}:{target}:365", style="success"),
                types.InlineKeyboardButton("♾ Lifetime", callback_data=f"adm_quicksub:lifetime:{target}:0", style="success"))
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
            safe_edit(f"📅 <b>Select Duration</b>\n\n"
                      f"👤 User: <code>{target}</code>\n"
                      f"📦 Plan: {PLAN_LIMITS.get(plan, {}).get('name', plan)}\n\n"
                      f"Choose below:",
                      chat_id, msg_id, reply_markup=m)
            safe_answer(call.id)

        elif data.startswith("adm_quicksub:"):
            if not state.is_admin(uid): return
            parts = data.split(":"); plan = parts[1]; target = int(parts[2]); days = int(parts[3])
            if days == 0 or plan == 'lifetime':
                db.set_sub(target, 'lifetime'); plan_name = "👑 Lifetime"; dur_text = "Lifetime"
            else:
                db.set_sub(target, plan, days)
                plan_name = PLAN_LIMITS.get(plan, {}).get('name', plan); dur_text = f"{days} days"
            safe_answer(call.id, "✅ Done!")
            safe_edit(f"✅ <b>Subscription Added!</b>\n\n"
                      f"👤 User: <code>{target}</code>\n"
                      f"📦 Plan: {plan_name}\n"
                      f"📅 Duration: {dur_text}",
                      chat_id, msg_id, reply_markup=back_btn("menu_admin", "🔙 Admin"))
            db.admin_log(uid, 'add_sub', target, f"{plan}/{dur_text}")
            safe_send(target, f"🎉 <b>Plan Upgraded!</b>\n📦 {plan_name}\n📅 {dur_text}\n{BRAND_FOOTER}")

        elif data == "adm_remsub":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'adm_remsub_uid'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
            safe_edit(f"➖ <b>REMOVE SUBSCRIPTION</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send the User ID:\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "adm_ban":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'adm_ban_uid'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
            safe_edit(f"🚫 <b>BAN USER</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send: USER_ID [REASON]\nExample: 123456789 Spam\n"
                      f"━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "adm_unban":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'adm_unban_uid'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
            safe_edit(f"✅ <b>UNBAN USER</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send the User ID:\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data.startswith("adm_ban_direct:"):
            if not state.is_admin(uid): return
            target = int(data.split(":")[1])
            db.ban(target, "Banned from admin panel"); db.admin_log(uid, 'ban', target)
            for b in db.get_bots(target):
                sk = f"{target}_{b['bot_name']}"
                if sk in bot_scripts:
                    kill_tree(bot_scripts[sk]); cleanup_script(sk)
                db.update_bot(b['bot_id'], status='stopped')
            safe_answer(call.id, "🚫 Banned!")
            safe_send(target, f"🚫 <b>You have been banned!</b>\nContact {YOUR_USERNAME}")

        elif data.startswith("adm_unban_direct:"):
            if not state.is_admin(uid): return
            target = int(data.split(":")[1])
            db.unban(target); db.admin_log(uid, 'unban', target)
            safe_answer(call.id, "✅ Unbanned!")
            safe_send(target, "✅ You have been unbanned!")

        elif data == "adm_channels":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            channels = db.get_all_channels()
            t = f"📢 <b>Force Subscribe Channels</b>\n"
            t += f"Status: {'🟢 ON' if state.force_sub_enabled else '🔴 OFF'}\n"
            t += f"━━━━━━━━━━━━━━━━━━━━\n\n"
            for ch in channels:
                t += f"  {'🟢' if ch['is_active'] else '🔴'} @{ch['channel_username']} — {ch['channel_name']}\n"
            if not channels: t += "  No custom channels. Default: @sb_aura\n"
            t += "\n━━━━━━━━━━━━━━━━━━━━"
            safe_edit(t, chat_id, msg_id, reply_markup=channels_manage_kb())

        elif data.startswith("ch_toggle:"):
            if not state.is_admin(uid): return
            try:
                raw = data.split(":", 1)[1]
                try: cid_ch = int(raw)
                except ValueError: cid_ch = raw
                ns = db.toggle_channel(cid_ch)
                if ns is not None: safe_answer(call.id, f"{'🟢 Enabled' if ns else '🔴 Disabled'}!")
                else: safe_answer(call.id, "❌ Channel not found!")
            except Exception: safe_answer(call.id, "❌ Error!")
            channels_r = db.get_all_channels()
            t_ch = f"📢 <b>Force Subscribe Channels</b>\n"
            t_ch += f"Status: {'🟢 ON' if state.force_sub_enabled else '🔴 OFF'}\n"
            t_ch += f"━━━━━━━━━━━━━━━━━━━━\n\n"
            for ch in channels_r:
                t_ch += f"  {'🟢' if ch['is_active'] else '🔴'} @{ch['channel_username']} — {ch['channel_name']}\n"
            if not channels_r: t_ch += "  No custom channels. Default: @sb_aura\n"
            t_ch += "\n━━━━━━━━━━━━━━━━━━━━"
            safe_edit(t_ch, chat_id, msg_id, reply_markup=channels_manage_kb())

        elif data == "ch_add":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'ch_add'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="adm_channels", style="danger"))
            safe_edit(f"➕ <b>Add Channel</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send: @username [Channel Name]\n"
                      f"⚠️ Bot must be admin!\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "ch_remove":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'ch_remove'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="adm_channels", style="danger"))
            safe_edit(f"🗑 <b>Remove Channel</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send the channel username:\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "adm_give":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'adm_give_balance'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
            safe_edit(f"💰 <b>GIVE BALANCE</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send: USER_ID AMOUNT\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "adm_userinfo":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'adm_userinfo_uid'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
            safe_edit(f"🔍 <b>User Info</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send the User ID:\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "adm_notify":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            state.set_state(uid, {'action': 'adm_notify_uid'})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_admin", style="danger"))
            safe_edit(f"🔔 <b>Send Notification</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Send: USER_ID MESSAGE\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "adm_fsub_toggle":
            if not state.is_admin(uid): return
            state.force_sub_enabled = not state.force_sub_enabled
            st = "🟢 ON" if state.force_sub_enabled else "🔴 OFF"
            safe_answer(call.id, f"Force Subscribe: {st}", show_alert=True)
            db.admin_log(uid, 'toggle_fsub', det=st)
            s_adm = db.stats()
            rn_adm = len([k for k in bot_scripts if is_running(k)])
            tickets_adm = len(db.open_tickets())
            safe_edit(
                f"👑 <b>ADMIN PANEL</b>\n{BRAND_TAG}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total Users: {s_adm['users']} (+{s_adm['today']} today)\n"
                f"🤖 Running Bots: {rn_adm}\n💎 Active Subs: {s_adm['active_subs']}\n"
                f"🚫 Banned: {s_adm['banned']}\n💳 Pending Payments: {s_adm['pending']}\n"
                f"🎫 Open Tickets: {tickets_adm}\n💰 Total Revenue: {s_adm['revenue']} BDT\n\n"
                f"🔐 Force Sub: {'🟢 ON' if state.force_sub_enabled else '🔴 OFF'}\n"
                f"🔒 Bot Lock: {'🔒 LOCKED' if state.bot_locked else '🔓 OPEN'}\n"
                f"📥 File Approval: {'🟢 ON' if approval_is_on() else '🔴 OFF'}\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=admin_kb(approval_is_on()))

        elif data == "adm_lock_toggle":
            if not state.is_admin(uid): return
            state.bot_locked = not state.bot_locked
            st = "🔒 LOCKED" if state.bot_locked else "🔓 OPEN"
            safe_answer(call.id, f"Bot: {st}", show_alert=True)
            db.admin_log(uid, 'toggle_lock', det=st)
            s_adm = db.stats()
            rn_adm = len([k for k in bot_scripts if is_running(k)])
            tickets_adm = len(db.open_tickets())
            safe_edit(
                f"👑 <b>ADMIN PANEL</b>\n{BRAND_TAG}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total Users: {s_adm['users']} (+{s_adm['today']} today)\n"
                f"🤖 Running Bots: {rn_adm}\n💎 Active Subs: {s_adm['active_subs']}\n"
                f"🚫 Banned: {s_adm['banned']}\n💳 Pending Payments: {s_adm['pending']}\n"
                f"🎫 Open Tickets: {tickets_adm}\n💰 Total Revenue: {s_adm['revenue']} BDT\n\n"
                f"🔐 Force Sub: {'🟢 ON' if state.force_sub_enabled else '🔴 OFF'}\n"
                f"🔒 Bot Lock: {'🔒 LOCKED' if state.bot_locked else '🔓 OPEN'}\n"
                f"📥 File Approval: {'🟢 ON' if approval_is_on() else '🔴 OFF'}\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=admin_kb(approval_is_on()))

        elif data == "adm_stopall":
            if not state.is_admin(uid): return
            stopped = 0
            for sk in list(bot_scripts.keys()):
                i = bot_scripts.get(sk)
                if i:
                    kill_tree(i)
                    bid_inner = i.get('bot_id')
                    if bid_inner: db.update_bot(bid_inner, status='stopped')
                    cleanup_script(sk); stopped += 1
            safe_answer(call.id, f"🛑 Stopped {stopped} bots!", show_alert=True)
            db.admin_log(uid, 'stop_all', det=f"stopped:{stopped}")
            s_adm = db.stats()
            rn_adm = len([k for k in bot_scripts if is_running(k)])
            tickets_adm = len(db.open_tickets())
            safe_edit(
                f"👑 <b>ADMIN PANEL</b>\n{BRAND_TAG}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total Users: {s_adm['users']} (+{s_adm['today']} today)\n"
                f"🤖 Running Bots: {rn_adm}\n💎 Active Subs: {s_adm['active_subs']}\n"
                f"🚫 Banned: {s_adm['banned']}\n💳 Pending Payments: {s_adm['pending']}\n"
                f"🎫 Open Tickets: {tickets_adm}\n💰 Total Revenue: {s_adm['revenue']} BDT\n\n"
                f"🔐 Force Sub: {'🟢 ON' if state.force_sub_enabled else '🔴 OFF'}\n"
                f"🔒 Bot Lock: {'🔒 LOCKED' if state.bot_locked else '🔓 OPEN'}\n"
                f"📥 File Approval: {'🟢 ON' if approval_is_on() else '🔴 OFF'}\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=admin_kb(approval_is_on()))

        elif data == "adm_system":
            if not state.is_admin(uid): return
            safe_answer(call.id); ss = sys_stats()
            rn = len([k for k in bot_scripts if is_running(k)])
            safe_edit(
                f"🖥 <b>SYSTEM INFO</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⚡ CPU: {ss['cpu']}%\n"
                f"💾 RAM: {ss['mem']}% ({ss['mem_used']}/{ss['mem_total']})\n"
                f"💿 Disk: {ss['disk']}% ({ss['disk_used']}/{ss['disk_total']})\n"
                f"⏱️ Uptime: {ss['up']}\n"
                f"🤖 Running Bots: {rn}\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=back_btn("menu_admin", "🔙 Admin"))

        elif data == "adm_backup":
            if not state.is_admin(uid): return
            try:
                from database import DB_PATH
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                bp = os.path.join(BACKUP_DIR, f"bk_{ts}.db")
                if os.path.exists(DB_PATH):
                    shutil.copy2(DB_PATH, bp)
                    with open(bp, 'rb') as f:
                        bot.send_document(uid, f, caption=f"💾 Backup {ts}")
                    safe_answer(call.id, "✅ Backup created!")
                else:
                    safe_answer(call.id, "ℹ️ Using MongoDB, no local backup needed.", show_alert=True)
                db.admin_log(uid, 'backup')
            except Exception as e:
                safe_answer(call.id, f"❌ Backup error: {str(e)[:50]}", show_alert=True)

        elif data == "adm_logs":
            if not state.is_admin(uid): return
            safe_answer(call.id); logs = db.get_admin_logs(15)
            t = f"📜 <b>Admin Logs</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            for l in logs:
                t += f"  🔹 {l.get('action', '?')} by <code>{l.get('admin_id', '?')}</code>\n"
                t += f"  📅 {str(l.get('created_at', ''))[:16]}\n\n"
            if not logs: t += "No logs."
            safe_edit(t + "━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id,
                      reply_markup=back_btn("menu_admin", "🔙 Admin"))

        elif data == "adm_tickets":
            if not state.is_admin(uid): return
            safe_answer(call.id); tickets = db.open_tickets()
            t = f"🎫 <b>Open Tickets ({len(tickets)})</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            m = types.InlineKeyboardMarkup(row_width=1)
            for ticket in tickets[:10]:
                tu = db.get_user(ticket['user_id'])
                t += f"  #{ticket['ticket_id']} — {ticket.get('subject', '?')}\n"
                t += f"  👤 {tu.get('full_name', '?') if tu else '?'} | 📅 {str(ticket.get('created_at', ''))[:10]}\n\n"
                m.add(types.InlineKeyboardButton(f"💬 Reply #{ticket['ticket_id']}",
                        callback_data=f"adm_ticket_reply:{ticket['ticket_id']}", style="primary"))
            if not tickets: t += "No open tickets!"
            m.add(types.InlineKeyboardButton("🔙 Admin", callback_data="menu_admin", style="primary"))
            safe_edit(t + "━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id, reply_markup=m)

        elif data.startswith("adm_ticket_reply:"):
            if not state.is_admin(uid): return
            tid = data.split(":")[1]
            safe_answer(call.id)
            state.set_state(uid, {'action': 'ticket_reply', 'ticket_id': tid})
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data="adm_tickets", style="danger"))
            safe_edit(f"💬 <b>Reply to Ticket #{tid}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📝 Type your reply now:\n━━━━━━━━━━━━━━━━━━━━",
                      chat_id, msg_id, reply_markup=m)

        elif data == "adm_users":
            if not state.is_admin(uid): return
            safe_answer(call.id); s = db.stats(); users = db.get_all_users()
            t = (f"👥 <b>ALL USERS ({s['users']})</b>\n"
                 f"━━━━━━━━━━━━━━━━━━━━\n\n"
                 f"💎 Active Subs: {s['active_subs']}\n"
                 f"🚫 Banned: {s['banned']}\n\n")
            for u in users[:20]:
                icon = "🚫" if u.get('is_banned') else ("💎" if u.get('plan') != 'free' else "👤")
                t += f"  {icon} <code>{u['user_id']}</code> — {u.get('full_name', '?')[:15]} | {u.get('plan', 'free')}\n"
            if s['users'] > 20: t += f"\n  ... and {s['users'] - 20} more users"
            safe_edit(t + "\n━━━━━━━━━━━━━━━━━━━━", chat_id, msg_id,
                      reply_markup=back_btn("menu_admin", "🔙 Admin"))

        elif data == "adm_cleanup":
            if not state.is_admin(uid): return
            safe_answer(call.id)
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(types.InlineKeyboardButton("🗑️ Delete Bot Files (disk)",       callback_data="adm_cleanup_files",    style="danger"))
            m.add(types.InlineKeyboardButton("📜 Delete Log Files (disk)",       callback_data="adm_cleanup_logs",     style="danger"))
            m.add(types.InlineKeyboardButton("💾 Delete Old Backups (keep 5)",   callback_data="adm_cleanup_backups",  style="danger"))
            m.add(types.InlineKeyboardButton("❌ Delete Error Logs (DB)",         callback_data="adm_cleanup_errlogs",  style="danger"))
            m.add(types.InlineKeyboardButton("🔔 Delete Old Notifications (30d)",callback_data="adm_cleanup_notifs",   style="danger"))
            m.add(types.InlineKeyboardButton("🔙 Admin Panel",                    callback_data="menu_admin",           style="primary"))
            safe_edit(
                f"🗑️ <b>CLEANUP STORAGE</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⚠️ Choose what to clean:\n\n"
                f"• <b>Bot Files</b> — deletes uploaded bot files from disk\n"
                f"• <b>Log Files</b> — clears all .log files\n"
                f"• <b>Old Backups</b> — keeps only last 5 backups\n"
                f"• <b>Error Logs</b> — clears error_logs from DB\n"
                f"• <b>Old Notifications</b> — deletes read notifs older than 30 days\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                chat_id, msg_id, reply_markup=m)

        elif data == "adm_cleanup_files":
            if not state.is_admin(uid): return
            safe_answer(call.id, "🗑️ Deleting bot files...")
            try:
                n = db.cleanup_user_files()
                db.admin_log(uid, 'cleanup_files', det=f"deleted:{n}")
                safe_edit(f"✅ <b>Bot Files Deleted!</b>\n\n🗑️ {n} items removed from disk.",
                          chat_id, msg_id, reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))
            except Exception as e:
                safe_edit(f"❌ Error: {str(e)[:200]}", chat_id, msg_id,
                          reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))

        elif data == "adm_cleanup_logs":
            if not state.is_admin(uid): return
            safe_answer(call.id, "📜 Clearing logs...")
            try:
                n = db.cleanup_old_logs()
                db.admin_log(uid, 'cleanup_logs', det=f"deleted:{n}")
                safe_edit(f"✅ <b>Log Files Cleared!</b>\n\n🗑️ {n} log files deleted.",
                          chat_id, msg_id, reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))
            except Exception as e:
                safe_edit(f"❌ Error: {str(e)[:200]}", chat_id, msg_id,
                          reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))

        elif data == "adm_cleanup_backups":
            if not state.is_admin(uid): return
            safe_answer(call.id, "💾 Cleaning backups...")
            try:
                n = db.cleanup_old_backups(keep=5)
                db.admin_log(uid, 'cleanup_backups', det=f"deleted:{n}")
                safe_edit(f"✅ <b>Old Backups Deleted!</b>\n\n🗑️ {n} old backups removed (kept last 5).",
                          chat_id, msg_id, reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))
            except Exception as e:
                safe_edit(f"❌ Error: {str(e)[:200]}", chat_id, msg_id,
                          reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))

        elif data == "adm_cleanup_errlogs":
            if not state.is_admin(uid): return
            safe_answer(call.id, "❌ Clearing error logs...")
            try:
                n = db.cleanup_error_logs_db()
                db.admin_log(uid, 'cleanup_errlogs', det=f"deleted:{n}")
                safe_edit(f"✅ <b>Error Logs Cleared!</b>\n\n🗑️ {n} error records removed from DB.",
                          chat_id, msg_id, reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))
            except Exception as e:
                safe_edit(f"❌ Error: {str(e)[:200]}", chat_id, msg_id,
                          reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))

        elif data == "adm_cleanup_notifs":
            if not state.is_admin(uid): return
            safe_answer(call.id, "🔔 Cleaning notifications...")
            try:
                n = db.cleanup_old_notifications(days=30)
                db.admin_log(uid, 'cleanup_notifs', det=f"deleted:{n}")
                safe_edit(f"✅ <b>Old Notifications Deleted!</b>\n\n🗑️ {n} old read notifications removed.",
                          chat_id, msg_id, reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))
            except Exception as e:
                safe_edit(f"❌ Error: {str(e)[:200]}", chat_id, msg_id,
                          reply_markup=back_btn("adm_cleanup", "🔙 Cleanup"))

        elif data.startswith("help_"):
            safe_answer(call.id)
            topic = data.replace("help_", "")
            help_texts = {
                "deploy": "📤 <b>HOW TO DEPLOY</b>\n\n1. Press 📤 Deploy Bot\n2. Choose source:\n   • 📤 Upload File\n   • 🐙 GitHub Repo\n3. Auto-detects entry\n4. Press ▶️ Start",
                "bots": "🤖 <b>MANAGING BOTS</b>\n\n• Start/Stop/Restart\n• Toggle Auto Restart (paid plans)\n• Logs & Resources\n• Re-detect entry",
                "plans": "💎 <b>PLANS & PRICING</b>\n\n• 🆓 Free — 1 bot\n• 🟢 Starter — 2 bots — 99 BDT / ⭐ 15\n• ⭐ Basic — 5 bots — 199 BDT / ⭐ 30\n• 💎 Pro — 15 bots — 499 BDT / ⭐ 75\n• 🏢 Enterprise — 50 bots — 999 BDT / ⭐ 150\n• 👑 Lifetime — ♾️ — 1999 BDT / ⭐ 400",
                "payment": f"💳 <b>PAYMENT GUIDE</b>\n\n• bKash/Nagad: 01306633616\n• Send Money → TRX ID\n• Submit in bot → Admin approves\n• ⭐ Stars: Auto-approved\n\n📞 {YOUR_USERNAME}",
                "referral": f"🎁 <b>REFERRAL</b>\n\n• Share your link\n• +{REF_COMMISSION} BDT per ref\n• +{REF_BONUS_DAYS} days premium",
                "wallet": "💰 <b>WALLET</b>\n\n• Earn via referral\n• Redeem Tk promos\n• Pay for plans",
                "detect": "🔍 <b>AUTO DETECTION</b>\n\n• main.py, app.py, bot.py, index.js\n• package.json, Procfile support\n• Manual override via Re-detect",
                "files": "📦 <b>SUPPORTED FILES</b>\n\n• Python .py\n• Node.js .js\n• ZIP archives\n• Config: .json .env .yml\n• Max: 100MB",
                "faq": f"❓ <b>FAQ</b>\n\nQ: Free plan?\nA: 1 bot (auto-stop 24h)\n\nQ: Stars?\nA: Yes! Auto-activated\n\nQ: Promo codes?\nA: Tk wallet or % discount\n\nQ: Contact: {YOUR_USERNAME}",
                "trouble": "🛠 <b>TROUBLESHOOT</b>\n\n• Bot crashes: Check logs\n• Entry not found: Re-detect\n• Module missing: Auto-installed\n• GitHub 404: Add token",
                "commands": "/start /help /cancel /id /ping\n\n<b>Admin:</b>\n/admin /ban /broadcast /give",
                "contact": f"📞 <b>CONTACT</b>\n\n👨‍💻 {YOUR_USERNAME}\n📢 {UPDATE_CHANNEL}\n🎫 Or create support ticket"
            }
            text = help_texts.get(topic, f"❓ Help topic: {topic}")
            safe_edit(text, chat_id, msg_id, reply_markup=back_help_btn())

        else:
            safe_answer(call.id, "⚠️ Unknown action!", show_alert=False)
            logger.warning(f"Unknown callback: {data} from {uid}")

    except Exception as e:
        logger.error(f"Callback error [{data}]: {e}", exc_info=True)
        forward_crash(f"callback:{data}", e, uid)
        safe_answer(call.id, "❌ An error occurred!", show_alert=True)
        try:
            safe_edit(f"❌ <b>Error occurred!</b>\n\nPlease try again.\n{BRAND_FOOTER}",
                      chat_id, msg_id, reply_markup=back_btn())
        except: pass


def cleanup():
    logger.info("🛑 Shutting down...")
    for sk in list(bot_scripts.keys()):
        i = bot_scripts.get(sk)
        if i:
            try: kill_tree(i)
            except: pass
            bid_inner = i.get('bot_id')
            if bid_inner:
                try: db.update_bot(bid_inner, status='stopped')
                except: pass
            cleanup_script(sk)
    logger.info("✅ Cleanup complete")

atexit.register(cleanup)

def signal_handler(sig, frame):
    cleanup(); sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main():
    from config import FREE_BOT_MAX_HOURS
    logger.info("=" * 50)
    logger.info(f"  {BRAND_TAG}")
    logger.info("  Starting up...")
    logger.info("=" * 50)

    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10)
        logger.info("✅ Webhook cleared")
        time.sleep(3)
    except Exception as e:
        logger.warning(f"Webhook clear failed: {e}")

    keep_alive(); logger.info(f"✅ Flask keep-alive started (port {FLASK_PORT})")

    threading.Thread(target=thread_monitor, daemon=True).start()
    logger.info("✅ Bot monitor started")

    threading.Thread(target=thread_backup, daemon=True).start()
    logger.info("✅ Auto-backup started")

    threading.Thread(target=thread_expiry, daemon=True).start()
    logger.info("✅ Expiry checker started")

    threading.Thread(target=thread_storage_monitor, daemon=True).start()
    logger.info("✅ Storage monitor started")

    threading.Thread(target=thread_daily_report, daemon=True).start()
    logger.info("✅ Daily report thread started")

    threading.Thread(target=thread_free_bot_limit, daemon=True).start()
    logger.info(f"✅ Free bot auto-stop started ({FREE_BOT_MAX_HOURS}h)")

    threading.Thread(target=thread_per_bot_auto_restart, daemon=True).start()
    logger.info("✅ Per-bot auto-restart (24h) thread started")

    try:
        from database import USE_MONGO, mongo_db
        if USE_MONGO and mongo_db is not None:
            all_bots = list(mongo_db['bots'].find({'status': 'running'}, {'_id': 0}))
        else:
            from database import DB_PATH
            import sqlite3 as _sqlite3
            _conn = _sqlite3.connect(DB_PATH)
            _conn.row_factory = _sqlite3.Row
            all_bots = [dict(r) for r in _conn.execute("SELECT * FROM bots WHERE status='running'").fetchall()]
            _conn.close()

        logger.info(f"🔄 Found {len(all_bots)} bots to auto-restart")
        for b in all_bots:
            logger.info(f"🔄 Auto-restarting bot #{b['bot_id']}: {b['bot_name']}")
            db.update_bot(b['bot_id'], status='starting')
            threading.Thread(target=run_bot_script,
                             args=(b['bot_id'], b['user_id']),
                             daemon=True, name=f"autostart_{b['bot_id']}").start()
            time.sleep(1)
    except Exception as e:
        logger.error(f"Auto-restart error: {e}")
        forward_error("AUTO_RESTART", e)

    safe_send(OWNER_ID,
        f"🚀 <b>{BRAND_TAG} STARTED!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ All systems online\n"
        f"📊 DB: {'MongoDB ✅' if __import__('database').USE_MONGO else 'SQLite ⚠️'}\n"
        f"🌐 Flask: OK (port {FLASK_PORT})\n"
        f"🔍 Monitor: OK\n"
        f"💾 Backup: OK\n"
        f"🐙 GitHub Deploy: OK\n"
        f"⭐ Stars Payment: OK\n"
        f"🎟 Promo Codes: OK\n"
        f"📥 File Approval: {'🟢 ON' if approval_is_on() else '🔴 OFF'}\n"
        f"🔄 Auto-restart: Per-bot toggle (paid only)\n"
        f"🆓 Free bot limit: {FREE_BOT_MAX_HOURS}h\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=main_menu_kb(OWNER_ID))

    logger.info("🚀 Bot polling started!")

    while True:
        try:
            bot.infinity_polling(
                timeout=60, long_polling_timeout=60,
                allowed_updates=['message', 'callback_query'],
                skip_pending=True)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt — shutting down"); break
        except Exception as e:
            logger.error(f"Polling error: {e}")
            forward_error("POLLING_CRASH", e)
            logger.info("🔄 Reconnecting in 10 seconds...")
            time.sleep(10)


if __name__ == '__main__':
    main()