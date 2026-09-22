"""BOT RUNNER — uses security.sandbox"""
import os, sys, re, json, subprocess, time, threading, logging
from datetime import datetime, timedelta
from telebot import types

from config import (
    LOGS_DIR, PLAN_LIMITS, MODULES_MAP, BRAND_FOOTER,
    DAILY_REPORT_HOUR, DAILY_REPORT_MINUTE,
    FREE_BOT_MAX_HOURS, OWNER_ID
)
from core.state import state, bot_scripts
from utils.helpers import user_folder, cleanup_script, kill_tree, is_running

# ═══ SECURITY PACKAGE ═══
try:
    from security import (
        run_sandboxed, sandbox_status,
        scan_directory_recursive, scan_file_path,
    )
    _SECURITY_OK = True
except Exception as _sec_err:
    print(f"[security] load failed: {_sec_err}", file=sys.stderr)
    _SECURITY_OK = False

logger = logging.getLogger('APON.runner')
_bot = _db = _forward_error = _safe_send = None


def init_runner(bot_instance, db_instance, forward_error_fn, safe_send_fn):
    global _bot, _db, _forward_error, _safe_send
    _bot = bot_instance
    _db = db_instance
    _forward_error = forward_error_fn
    _safe_send = safe_send_fn
    if _SECURITY_OK:
        st = sandbox_status()
        logger.info(f"🛡 Sandbox: mode={st['mode']}")


def _is_admin_or_owner(check_uid):
    try:
        if check_uid == OWNER_ID: return True
        if state.is_admin(check_uid): return True
    except Exception: pass
    return False


class Detector:
    PY = ['main.py', 'app.py', 'bot.py', 'run.py', 'start.py',
          'server.py', 'index.py', '__main__.py']
    JS = ['index.js', 'app.js', 'bot.js', 'main.js',
          'server.js', 'start.js', 'run.js']

    @staticmethod
    def detect(d):
        if not os.path.isdir(d):
            if os.path.isfile(d):
                return os.path.basename(d), d.rsplit('.', 1)[-1].lower(), 'exact'
            return None, None, None
        top = os.listdir(d)
        for e in Detector.PY:
            if e in top and os.path.isfile(os.path.join(d, e)):
                return e, 'py', 'high'
        for e in Detector.JS:
            if e in top and os.path.isfile(os.path.join(d, e)):
                return e, 'js', 'high'

        pj = os.path.join(d, 'package.json')
        if os.path.exists(pj):
            try:
                with open(pj) as f: pkg = json.load(f)
                if 'main' in pkg and os.path.exists(os.path.join(d, pkg['main'])):
                    return pkg['main'], pkg['main'].rsplit('.', 1)[-1].lower(), 'high'
                if 'scripts' in pkg and 'start' in pkg['scripts']:
                    cmd = pkg['scripts']['start']
                    m = re.search(r'node\s+(\S+\.js)', cmd)
                    if m and os.path.exists(os.path.join(d, m.group(1))):
                        return m.group(1), 'js', 'high'
                    m = re.search(r'python[3]?\s+(\S+\.py)', cmd)
                    if m and os.path.exists(os.path.join(d, m.group(1))):
                        return m.group(1), 'py', 'high'
            except Exception: pass

        pf = os.path.join(d, 'Procfile')
        if os.path.exists(pf):
            try:
                with open(pf) as f: c = f.read()
                m = re.search(r'(?:worker|web):\s*python[3]?\s+(\S+\.py)', c)
                if m and os.path.exists(os.path.join(d, m.group(1))):
                    return m.group(1), 'py', 'high'
                m = re.search(r'(?:worker|web):\s*node\s+(\S+\.js)', c)
                if m and os.path.exists(os.path.join(d, m.group(1))):
                    return m.group(1), 'js', 'high'
            except Exception: pass

        for root, dirs, files in os.walk(d):
            depth = os.path.relpath(root, d).count(os.sep)
            if depth > 2: continue
            if root == d: continue
            for e in Detector.PY:
                if e in files:
                    return os.path.relpath(os.path.join(root, e), d), 'py', 'medium'
            for e in Detector.JS:
                if e in files:
                    return os.path.relpath(os.path.join(root, e), d), 'js', 'medium'

        pyf, jsf = [], []
        for root, dirs, files in os.walk(d):
            depth = os.path.relpath(root, d).count(os.sep)
            if depth > 2: continue
            for f in files:
                fp = os.path.join(root, f)
                rp = os.path.relpath(fp, d)
                if f.endswith('.py'): pyf.append((rp, fp))
                elif f.endswith('.js'): jsf.append((rp, fp))

        indicators_py = ['infinity_polling', 'polling()', 'bot.polling',
                         'app.run(', 'if __name__', 'telebot.TeleBot', 'Bot(token']
        for rp, fp in pyf:
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    c = f.read(5000)
                if sum(1 for x in indicators_py if x in c) >= 2:
                    return rp, 'py', 'medium'
            except Exception: pass
        indicators_js = ['require(', 'app.listen', 'bot.launch',
                         'client.login', 'express()']
        for rp, fp in jsf:
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    c = f.read(5000)
                if sum(1 for x in indicators_js if x in c) >= 2:
                    return rp, 'js', 'medium'
            except Exception: pass

        if pyf: return pyf[0][0], 'py', 'low'
        if jsf: return jsf[0][0], 'js', 'low'
        return None, None, None

    @staticmethod
    def install_req(d, cid=None):
        r = os.path.join(d, 'requirements.txt')
        if not os.path.exists(r): return True
        if cid and _safe_send:
            _safe_send(cid, "📦 Installing <b>requirements.txt</b>... Please wait.")
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-r', r,
                 '--quiet', '--no-warn-script-location',
                 '--disable-pip-version-check', '--break-system-packages'],
                capture_output=True, text=True, timeout=300, cwd=d)
            if result.returncode != 0 and cid and _safe_send:
                err_out = (result.stderr or result.stdout or '')[-500:]
                import html as _html
                _safe_send(cid, f"⚠️ <b>Requirements warning:</b>\n<code>{_html.escape(err_out)}</code>")
        except subprocess.TimeoutExpired:
            if cid and _safe_send:
                _safe_send(cid, "⚠️ Requirements timed out.")
        except Exception as e:
            if _forward_error: _forward_error("INSTALL_REQ", e)
        return True

    @staticmethod
    def install_npm(d, cid=None):
        if os.path.exists(os.path.join(d, 'package.json')) and \
           not os.path.exists(os.path.join(d, 'node_modules')):
            if cid and _safe_send:
                _safe_send(cid, "📦 Running npm install...")
            try:
                subprocess.run(['npm', 'install', '--production'],
                               capture_output=True, text=True, timeout=300, cwd=d)
            except Exception as e:
                if _forward_error: _forward_error("INSTALL_NPM", e)
        return True

    @staticmethod
    def report(d):
        e, ft, cf = Detector.detect(d)
        if not e: return None, None, "❌ No runnable file detected!"
        ci = {'exact': '🎯 Exact', 'high': '✅ High', 'medium': '🟡 Medium', 'low': '⚠️ Low'}
        ti = {'py': '🐍 Python', 'js': '🟨 Node.js'}
        return e, ft, (f"📄 Entry: <code>{e}</code>\n"
                       f"🔤 Type: {ti.get(ft, ft)}\n"
                       f"🎯 Confidence: {ci.get(cf, cf)}")


det = Detector()


def pip_install(mod, cid=None):
    pkg = MODULES_MAP.get(mod, mod)
    if cid and _safe_send:
        _safe_send(cid, f"📦 Auto-installing: <code>{pkg}</code>...")
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', pkg, '--quiet',
             '--break-system-packages', '--disable-pip-version-check'],
            capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception as e:
        logger.error(f"pip_install error: {e}")
        return False


def _make_sandbox_alert(uid, cid, bid):
    def _on_alert(bot_id_str, message):
        try:
            if _forward_error:
                _forward_error("SANDBOX_ALERT", f"bot=#{bot_id_str} user={uid}: {message}", uid)
            if _safe_send:
                _safe_send(cid, f"⚠️ <b>Sandbox Alert</b>\nBot #{bot_id_str}: <code>{message[:200]}</code>")
        except Exception: pass
    return _on_alert


def _pre_scan_or_block(wd, cid, bid, uid, lf=None):
    """
    Run-time security gate.

    Rules (per admin setting):
      • File Approval ON  + bot already admin-approved → NO scan (trust admin)
      • File Approval OFF → full scan; if malware → block start + tell user to delete
    """
    if not _SECURITY_OK:
        return True, ""

    # Trust admin-approved bots when approval system is enabled
    try:
        bd = _db.get_bot(bid) if _db else None
        appr = (bd or {}).get('approval_status', 'approved')
        approval_on = True
        try:
            # Prefer live setting from DB
            if _db and hasattr(_db, 'get_setting'):
                approval_on = str(_db.get_setting('approval_required', '1')) == '1'
        except Exception:
            pass
        if approval_on and appr == 'approved':
            logger.info(f"[pre-scan] skip bot #{bid} — admin-approved (approval ON)")
            return True, "skipped-admin-approved"
        if appr == 'pending':
            if _safe_send:
                _safe_send(cid, "⏳ File is waiting for admin approval.")
            return False, "pending"
        if appr == 'rejected':
            if _safe_send:
                _safe_send(cid, "❌ File was rejected by admin.")
            return False, "rejected"
    except Exception as e:
        logger.warning(f"pre-scan approval check: {e}")

    # Approval OFF (or unknown) → full scan before every start
    try:
        pre = scan_directory_recursive(wd, reject_threshold=70)
        if pre.get("ok"):
            return True, ""
        w = pre.get("worst") or {}
        score = w.get("risk_score", 0)
        path = w.get("path", "?")
        threats = w.get("all_threats", [])[:5]
        threats_text = "\n".join(f"  • <code>{t[:70]}</code>" for t in threats)
        if lf:
            try:
                lf.close()
            except Exception:
                pass
        if _safe_send:
            _safe_send(cid,
                f"🚫 <b>Your bot virus detected</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Please <b>delete</b> this file and upload a new clean one.\n\n"
                f"📊 Score: <b>{score}/100</b>\n"
                f"📄 File: <code>{path}</code>\n\n"
                f"⚠️ Threats:\n{threats_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━")
        if _forward_error:
            _forward_error("SECGUARD_PRERUN", f"Bot #{bid} blocked: score={score}", uid)
        return False, f"score={score}"
    except Exception as e:
        logger.warning(f"pre-scan error: {e}")
        return True, ""


def run_bot_script(bid, cid, att=1):
    if not _db or not _safe_send:
        logger.error("Runner not initialized!"); return
    bd = _db.get_bot(bid)
    if not bd: return

    uid = bd['user_id']; bn = bd['bot_name']; fp = bd['file_path']
    ef = bd['entry_file']; ft = bd['file_type']
    sk = f"{uid}_{bn}"
    wd = fp if os.path.isdir(fp) else user_folder(uid)

    try:
        de, dt, dr = det.report(wd)
        if de:
            ef = de; ft = dt or 'py'
            _db.update_bot(bid, entry_file=ef, file_type=ft)

        fsp = os.path.join(wd, ef)
        if not os.path.exists(fsp):
            found = False
            for root, dirs, files in os.walk(wd):
                if os.path.basename(ef) in files:
                    fsp = os.path.join(root, os.path.basename(ef))
                    ef = os.path.relpath(fsp, wd)
                    _db.update_bot(bid, entry_file=ef)
                    found = True; break
            if not found:
                af = [os.path.relpath(os.path.join(r, f), wd)
                      for r, d_, fs in os.walk(wd) for f in fs
                      if f.endswith(('.py', '.js'))]
                err = f"❌ <b>Entry file not found:</b> <code>{ef}</code>\n\n📁 Available:\n"
                for f in af[:10]: err += f"  • <code>{f}</code>\n"
                if not af: err += "  (No .py or .js files found)\n"
                err += "\n💡 Try uploading again or use Re-detect."
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("🔍 Re-detect", callback_data=f"bot_redetect:{bid}", style="primary"))
                m.add(types.InlineKeyboardButton("🔙 My Bots", callback_data="menu_mybots", style="primary"))
                _safe_send(cid, err, reply_markup=m)
                return

        if att == 1:
            if ft == 'py': det.install_req(wd, cid)
            else: det.install_npm(wd, cid)

        type_icon = '🐍 Python' if ft == 'py' else '🟨 Node.js'
        _safe_send(cid, f"🚀 <b>Starting Bot...</b>\n\n"
                        f"📄 <code>{ef}</code>\n🔤 {type_icon}\n🔄 Attempt: {att}/3")

        lp = os.path.join(LOGS_DIR, f"{sk}.log")
        lf = open(lp, 'w', encoding='utf-8', errors='ignore')

        allowed, _ = _pre_scan_or_block(wd, cid, bid, uid, lf=lf)
        if not allowed:
            _db.update_bot(bid, status='crashed', last_crash=datetime.now().isoformat())
            return
        if lf.closed:
            lf = open(lp, 'w', encoding='utf-8', errors='ignore')

        cmd = ['node', fsp] if ft == 'js' else [sys.executable, '-u', fsp]
        env_user = {}
        if bd.get('bot_token'): env_user['BOT_TOKEN'] = bd['bot_token']

        if _SECURITY_OK:
            try:
                proc = run_sandboxed(
                    bot_dir=wd, cmd=cmd, user_env=env_user,
                    log_file=lf, bot_id=str(bid),
                    on_scan_alert=_make_sandbox_alert(uid, cid, bid))
                logger.info(f"[run] bot #{bid} SANDBOXED")
            except Exception as sb_err:
                logger.error(f"Sandbox failed: {sb_err} — clean fallback")
                from security.sandbox import _build_clean_env, _apply_rlimits
                from pathlib import Path as _P
                env = _build_clean_env(dict(os.environ), _P(wd), env_user)
                proc = subprocess.Popen(
                    cmd, cwd=wd, stdout=lf, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='ignore', env=env,
                    preexec_fn=_apply_rlimits if os.name != 'nt' else None)
        else:
            env = os.environ.copy()
            for k in list(env.keys()):
                if any(frag in k.upper() for frag in (
                    'MONGO', 'REDIS', 'ERROR_BOT', 'SECRET',
                    'PASSWORD', 'API_KEY', 'OWNER_ID', 'DB_NAME',
                    'UPSTASH')) and k != 'BOT_TOKEN':
                    env.pop(k, None)
            if bd.get('bot_token'): env['BOT_TOKEN'] = bd['bot_token']
            env['PYTHONUNBUFFERED'] = '1'
            proc = subprocess.Popen(
                cmd, cwd=wd, stdout=lf, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='ignore', env=env,
                preexec_fn=os.setsid if os.name != 'nt' else None)

        bot_scripts[sk] = {
            'process': proc, 'file_name': bn, 'bot_id': bid,
            'user_id': uid, 'start_time': datetime.now(),
            'log_file': lf, 'log_path': lp, 'entry_file': ef,
            'work_dir': wd, 'type': ft, 'attempt': att,
            'sandboxed': _SECURITY_OK,
        }

        time.sleep(3)
        if proc.poll() is None:
            time.sleep(2)
            if proc.poll() is None:
                _db.update_bot(bid, status='running',
                               last_started=datetime.now().isoformat(),
                               entry_file=ef, file_type=ft)
                mk = types.InlineKeyboardMarkup(row_width=2)
                mk.add(
                    types.InlineKeyboardButton("🛑 Stop", callback_data=f"bot_stop:{bid}", style="danger"),
                    types.InlineKeyboardButton("📋 Logs", callback_data=f"bot_logs:{bid}", style="primary"))
                mk.add(types.InlineKeyboardButton("🔙 My Bots", callback_data="menu_mybots", style="primary"))
                sb_line = "🛡 Sandbox: <b>Active</b>" if _SECURITY_OK else "🛡 Sandbox: <i>rlimits only</i>"
                _safe_send(uid,
                    f"✅ <b>আপনার বট চালু হয়েছে!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🤖 Bot: <code>{bn[:20]}</code>\n"
                    f"📄 Entry: <code>{ef}</code>\n"
                    f"🆔 PID: <code>{proc.pid}</code>\n"
                    f"{sb_line}\n"
                    f"⏱️ {datetime.now().strftime('%H:%M:%S')}\n"
                    f"📊 Status: 🟢 Running\n"
                    f"━━━━━━━━━━━━━━━━━━━━",
                    reply_markup=mk)
                if int(cid) != int(uid):
                    _safe_send(cid,
                        f"✅ <b>BOT IS RUNNING!</b>\n\n"
                        f"📄 <code>{ef}</code>\n🆔 PID: <code>{proc.pid}</code>\n"
                        f"🔤 {type_icon}\n{sb_line}\n📊 Status: 🟢 Running", reply_markup=mk)
                return

        lf.flush()
        try: lf.close()
        except Exception: pass
        err = ""
        try:
            with open(lp, 'r', encoding='utf-8', errors='ignore') as f:
                err = f.read()[-2000:]
        except Exception: pass

        match = re.search(r"ModuleNotFoundError: No module named '([^']+)'", err)
        if match and att < 3:
            cleanup_script(sk)
            if pip_install(match.group(1).split('.')[0], cid):
                time.sleep(0.5)
                run_bot_script(bid, cid, att + 1); return

        match = re.search(r"Cannot find module '([^']+)'", err)
        if match and not match.group(1).startswith('.') and att < 3:
            cleanup_script(sk)
            try:
                subprocess.run(['npm', 'install', match.group(1)],
                               cwd=wd, capture_output=True, timeout=60)
                time.sleep(1)
                run_bot_script(bid, cid, att + 1); return
            except Exception: pass

        if att == 1:
            for alt in ['app.py', 'main.py', 'bot.py', 'run.py', 'index.js', 'app.js']:
                if os.path.exists(os.path.join(wd, alt)) and alt != ef:
                    cleanup_script(sk)
                    _db.update_bot(bid, entry_file=alt,
                                   file_type='js' if alt.endswith('.js') else 'py')
                    run_bot_script(bid, cid, att + 1); return

        err_display = err[-500:] if err.strip() else 'No output captured'
        mk2 = types.InlineKeyboardMarkup(row_width=2)
        mk2.add(
            types.InlineKeyboardButton("🔄 Retry", callback_data=f"bot_start:{bid}", style="success"),
            types.InlineKeyboardButton("📋 Full Logs", callback_data=f"bot_logs:{bid}", style="primary"))
        mk2.add(types.InlineKeyboardButton("🔙 My Bots", callback_data="menu_mybots", style="primary"))
        _safe_send(cid,
            f"❌ <b>BOT CRASHED!</b>\n\n"
            f"📄 <code>{ef}</code>\n"
            f"🔢 Exit: {proc.returncode} | Attempt: {att}/3\n\n"
            f"📋 Error:\n<code>{err_display}</code>",
            reply_markup=mk2)
        _db.update_bot(bid, status='crashed', last_crash=datetime.now().isoformat())
        cleanup_script(sk)
        if _forward_error:
            _forward_error("BOT_CRASH", f"Bot #{bid} ({bn}) crashed\n\n{err[-800:]}", uid)

    except Exception as e:
        logger.error(f"Run error: {e}", exc_info=True)
        if _forward_error: _forward_error("run_bot_script", str(e), uid)
        if _safe_send: _safe_send(cid, f"❌ Fatal error: {str(e)[:200]}")
        cleanup_script(sk)


# ═══════════════════════════════════════════════════
#  MONITOR / BACKUP / EXPIRY / REPORT THREADS
#  (identical to previous version — kept intact)
# ═══════════════════════════════════════════════════
def thread_monitor():
    while True:
        try:
            for sk in list(bot_scripts.keys()):
                i = bot_scripts.get(sk)
                if not i: continue
                proc = i.get('process')
                if not proc or proc.poll() is None: continue
                bid = i.get('bot_id'); uid = i.get('user_id')
                if bid and _db:
                    _db.update_bot(bid, status='crashed', last_crash=datetime.now().isoformat())
                if uid and bid and _db:
                    u = _db.get_user(uid)
                    if u and _db.is_active(uid):
                        pl = PLAN_LIMITS.get(u.get('plan', 'free'), PLAN_LIMITS['free'])
                        att = i.get('attempt', 1)
                        if pl.get('auto_restart') and att < 3:
                            cleanup_script(sk); time.sleep(3)
                            threading.Thread(target=run_bot_script, args=(bid, uid, att + 1),
                                             daemon=True, name=f"restart_{bid}").start()
                            continue
                cleanup_script(sk)
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            if _forward_error: _forward_error("MONITOR_THREAD", e)
        time.sleep(15)


def thread_storage_monitor():
    time.sleep(60)
    while True:
        try:
            if _db and _safe_send:
                from database import storage_monitor
                storage_monitor.check(_safe_send, state.admin_ids)
        except Exception as e:
            logger.error(f"Storage monitor error: {e}")
        time.sleep(3600)


def thread_daily_report():
    while True:
        try:
            now = datetime.now()
            nr = now.replace(hour=DAILY_REPORT_HOUR, minute=DAILY_REPORT_MINUTE,
                             second=0, microsecond=0)
            if nr <= now: nr += timedelta(days=1)
            time.sleep((nr - now).total_seconds())
            if not _db or not _safe_send: continue
            s = _db.stats()
            rn = len([k for k in bot_scripts if is_running(k)])
            try:
                from database import storage_monitor, USE_MONGO, MONGO_IS_BACKUP
                if USE_MONGO:
                    size_mb = storage_monitor.get_mongo_size_mb() or '?'
                    db_type = f"MongoDB {'(Backup)' if MONGO_IS_BACKUP else '(Primary)'}"
                else:
                    size_mb = storage_monitor.get_sqlite_size_mb(); db_type = "SQLite"
            except Exception:
                size_mb = '?'; db_type = 'DB'
            report = (f"📊 <b>DAILY REPORT</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
                      f"📅 {datetime.now().strftime('%Y-%m-%d')}\n\n"
                      f"👥 Users: {s['users']} (+{s['today']})\n"
                      f"🤖 Bots: {s['bots']} (🟢 {rn})\n"
                      f"💎 Subs: {s['active_subs']}\n"
                      f"💳 Pending: {s['pending']}\n"
                      f"💰 Revenue: {s['revenue']} BDT\n\n"
                      f"🗄 {db_type}: {size_mb} MB\n"
                      f"🛡 Sandbox: {'ACTIVE' if _SECURITY_OK else 'DISABLED'}\n"
                      f"━━━━━━━━━━━━━━━━━━━━")
            for aid in state.admin_ids: _safe_send(aid, report)
        except Exception as e:
            if _forward_error: _forward_error("DAILY_REPORT", e)
        time.sleep(60)


def thread_backup():
    import shutil
    from config import BACKUP_DIR
    while True:
        try:
            time.sleep(86400)
            from database import DB_PATH
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            bp = os.path.join(BACKUP_DIR, f"bk_{ts}.db")
            if os.path.exists(DB_PATH):
                shutil.copy2(DB_PATH, bp)
                bks = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('bk_')], reverse=True)
                for old in bks[10:]:
                    try: os.remove(os.path.join(BACKUP_DIR, old))
                    except Exception: pass
        except Exception as e:
            if _forward_error: _forward_error("BACKUP_THREAD", e)


def thread_free_bot_limit():
    if FREE_BOT_MAX_HOURS <= 0: return
    while True:
        try:
            time.sleep(1800)
            if not _db or not _safe_send: continue
            for sk in list(bot_scripts.keys()):
                i = bot_scripts.get(sk)
                if not i: continue
                uid = i.get('user_id'); bid = i.get('bot_id'); st = i.get('start_time')
                if not (uid and bid and st): continue
                if _is_admin_or_owner(uid): continue
                u = _db.get_user(uid)
                if not u or u.get('is_lifetime') or u.get('plan', 'free') != 'free': continue
                hrs = (datetime.now() - st).total_seconds() / 3600
                if hrs >= FREE_BOT_MAX_HOURS:
                    bd = _db.get_bot(bid)
                    bn = bd['bot_name'] if bd else sk
                    kill_tree(i); cleanup_script(sk)
                    _db.update_bot(bid, status='stopped', last_stopped=datetime.now().isoformat())
                    mk = types.InlineKeyboardMarkup(row_width=2)
                    mk.add(
                        types.InlineKeyboardButton("▶️ Restart", callback_data=f"bot_start:{bid}", style="success"),
                        types.InlineKeyboardButton("💎 Upgrade", callback_data="menu_sub", style="primary"))
                    _safe_send(uid,
                        f"⏰ <b>Free Plan Bot Auto-Stopped</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🤖 <code>{bn[:20]}</code>\n"
                        f"⏱️ Ran for: {FREE_BOT_MAX_HOURS}h\n\n"
                        f"💎 Upgrade for 24/7!\n"
                        f"━━━━━━━━━━━━━━━━━━━━", reply_markup=mk)
        except Exception as e:
            if _forward_error: _forward_error("FREE_BOT_LIMIT_THREAD", e)


def thread_per_bot_auto_restart():
    while True:
        try:
            time.sleep(1800)
            if not _db or not _safe_send: continue
            now = datetime.now()
            for sk, info in list(bot_scripts.items()):
                if not info.get('process') or info['process'].poll() is not None: continue
                bid = info.get('bot_id')
                if not bid: continue
                bd = _db.get_bot(bid)
                if not bd or not bd.get('auto_restart_24h', 0): continue
                owner_uid = bd.get('user_id')
                if owner_uid and not _is_admin_or_owner(owner_uid):
                    u_o = _db.get_user(owner_uid)
                    if u_o and not PLAN_LIMITS.get(u_o.get('plan', 'free'),
                                                  PLAN_LIMITS['free']).get('auto_restart'):
                        continue
                st = info.get('start_time')
                if not st: continue
                hrs = (now - st).total_seconds() / 3600
                if hrs >= 24:
                    uid = bd['user_id']
                    kill_tree(info); cleanup_script(sk)
                    _db.update_bot(bid, status='running')
                    threading.Thread(target=run_bot_script, args=(bid, uid),
                                     daemon=True, name=f"autorestart_{bid}").start()
                    _safe_send(uid,
                        f"🔄 <b>Bot Auto-Restarted</b>\n"
                        f"🤖 <code>{bd['bot_name'][:20]}</code>\n"
                        f"⏱️ After 24h\n━━━━━━━━━━━━━━━━━━━━")
        except Exception as e:
            if _forward_error: _forward_error("PER_BOT_AUTO_RESTART", e)


def thread_expiry():
    while True:
        try:
            time.sleep(3600)
            if not _db or not _safe_send: continue
            now = datetime.now().isoformat()
            for u in _db.get_all_users():
                if u.get('plan') == 'free' or u.get('is_lifetime'): continue
                se = u.get('subscription_end')
                if se and se <= now:
                    uid = u['user_id']
                    if _is_admin_or_owner(uid): continue
                    _db.rem_sub(uid)
                    for b in _db.get_bots(uid):
                        sk = f"{uid}_{b['bot_name']}"
                        if sk in bot_scripts:
                            kill_tree(bot_scripts[sk]); cleanup_script(sk)
                        _db.update_bot(b['bot_id'], status='stopped')
                    _safe_send(uid, f"⚠️ <b>Subscription Expired!</b>\nBots stopped.",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("💎 Renew", callback_data="menu_sub", style="success"),
                            types.InlineKeyboardButton("🏠 Menu", callback_data="go_home", style="primary")))
        except Exception as e:
            if _forward_error: _forward_error("EXPIRY_THREAD", e)