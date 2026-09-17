"""
SAFE BOT FUNCTIONS v6.0
─────────────────────────────────────────────────────────
Changes:
  • forward_error / forward_crash now notify BOTH the
    affected user AND admin — no one else
  • Error text is capped at 10 lines for user messages
  • User gets a friendly plain-language description
  • Admin gets the full technical traceback
─────────────────────────────────────────────────────────
"""

import telebot, logging, traceback, threading, time, html as _html
from datetime import datetime
from config import ERROR_BOT_TOKEN, BRAND_TAG, YOUR_USERNAME
from utils.premium_emoji import premiumize_emoji_html, strip_custom_emoji, is_emoji_send_error

logger = logging.getLogger('APON.safe')

_bot           = None
_error_bot     = None
_error_chat_id = None   # owner/admin ID

import requests as _requests
_session = _requests.Session()
_session.headers.update({'Connection': 'keep-alive'})

_send_lock = threading.Semaphore(25)


def init_safe(bot_instance, owner_id):
    global _bot, _error_bot, _error_chat_id
    _bot           = bot_instance
    _error_chat_id = owner_id
    try:
        _error_bot = telebot.TeleBot(ERROR_BOT_TOKEN, parse_mode='HTML', threaded=False)
        logger.info("✅ Error forwarding bot initialized")
    except Exception as e:
        logger.error(f"❌ Error bot init failed: {e}")


def _trim_error_for_user(error_msg: str, max_lines: int = 10) -> str:
    """Return at most max_lines lines of the error, stripped of stack trace noise."""
    lines = [l for l in str(error_msg).splitlines() if l.strip()]
    # Remove internal Python traceback lines (File "...", line N, in ...) from user view
    clean = [l for l in lines if not l.startswith('  File "') and not l.strip().startswith('self.')]
    trimmed = clean[:max_lines]
    result = '\n'.join(trimmed)
    if len(clean) > max_lines:
        result += f'\n... (+{len(clean) - max_lines} more lines)'
    return result or str(error_msg)[:300]


def forward_error(error_type: str, error_msg, user_id=None, extra: str = ""):
    """
    Send error notification:
      • Admin  → full technical report
      • User   → friendly message with trimmed error (max 10 lines)
    Only these two recipients — nobody else.
    """
    def _send():
        try:
            timestamp  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            err_full   = _html.escape(str(error_msg)[:1500])
            err_user   = _html.escape(_trim_error_for_user(str(error_msg)))
            extra_text = _html.escape(str(extra)[:500]) if extra else ''
            etype_esc  = _html.escape(str(error_type))

            # ── Admin message (full technical detail) ──
            admin_text = (
                f"🚨 <b>ERROR REPORT</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ Time: <code>{timestamp}</code>\n"
                f"🔴 Type: <code>{etype_esc}</code>\n"
                f"👤 User: <code>{user_id or 'System'}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 Error:\n<code>{err_full}</code>\n"
            )
            if extra_text:
                admin_text += f"\n📎 Traceback:\n<code>{extra_text}</code>\n"
            admin_text += f"\n━━━━━━━━━━━━━━━━━━━━\n🤖 {BRAND_TAG}"

            # Send to admin via error bot
            if _error_bot and _error_chat_id:
                try:
                    _error_bot.send_message(_error_chat_id, admin_text)
                except Exception as e:
                    logger.error(f"Admin error-forward failed: {e}")

            # ── User message (friendly, trimmed) ──
            # Only send if user_id is a real Telegram user (not 'System' / None)
            if user_id and str(user_id).lstrip('-').isdigit():
                uid_int = int(user_id)
                # Don't double-notify admin
                if uid_int != _error_chat_id:
                    user_text = (
                        f"⚠️ <b>আপনার বটে একটি সমস্যা হয়েছে</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🔴 Error Type: <code>{etype_esc}</code>\n"
                        f"⏰ Time: {timestamp}\n\n"
                        f"📋 Details (max 10 lines):\n"
                        f"<code>{err_user}</code>\n\n"
                        f"💡 Fix the error in your bot code and restart.\n"
                        f"🆘 Need help? Contact {YOUR_USERNAME}\n"
                        f"━━━━━━━━━━━━━━━━━━━━"
                    )
                    if _bot:
                        try:
                            _bot.send_message(uid_int, user_text)
                        except Exception as e:
                            logger.warning(f"User error-notify failed for {uid_int}: {e}")

        except Exception as e:
            logger.error(f"forward_error itself failed: {e}")

    threading.Thread(target=_send, daemon=True).start()


def forward_crash(func_name: str, exception, user_id=None):
    """Convenience wrapper — captures traceback and forwards."""
    tb = traceback.format_exc()
    forward_error(f"CRASH in {func_name}", str(exception), user_id, tb[-800:])


# ═══════════════════════════════════════════════════
#  SAFE SEND / EDIT / DELETE / REPLY
# ═══════════════════════════════════════════════════

def safe_send(chat_id, text, **kwargs):
    kwargs.setdefault('parse_mode', 'HTML')
    if kwargs.get('parse_mode') == 'HTML':
        text = premiumize_emoji_html(text)
    with _send_lock:
        for attempt in range(2):
            try:
                return _bot.send_message(chat_id, text, **kwargs)
            except telebot.apihelper.ApiTelegramException as e:
                err = str(e).lower()
                if is_emoji_send_error(err):
                    # One of the borrowed custom-emoji ids is invalid/expired —
                    # retry once with plain emoji instead of failing outright.
                    text = strip_custom_emoji(text)
                    continue
                if "can't parse" in err or 'bad request' in err:
                    try:
                        kw2 = {k: v for k, v in kwargs.items() if k != 'parse_mode'}
                        return _bot.send_message(chat_id, strip_custom_emoji(text), **kw2)
                    except Exception as e2:
                        if attempt == 1:
                            forward_error("SEND_MSG_FALLBACK", e2, chat_id)
                        return None
                elif 'bot was blocked' in err or 'user is deactivated' in err:
                    return None
                elif 'too many requests' in err:
                    try:
                        retry_after = int(str(e).split('Retry after ')[1].split(' ')[0])
                    except Exception:
                        retry_after = 2
                    time.sleep(min(retry_after, 5))
                    continue
                else:
                    if attempt == 1:
                        forward_error("SEND_MSG_API", e, chat_id)
                    return None
            except Exception as e:
                if attempt == 1:
                    forward_error("SEND_MSG", e, chat_id)
                return None
    return None


def safe_edit(text, chat_id, msg_id, **kwargs):
    kwargs.setdefault('parse_mode', 'HTML')
    if kwargs.get('parse_mode') == 'HTML':
        text = premiumize_emoji_html(text)
    for attempt in range(2):
        try:
            return _bot.edit_message_text(text, chat_id, msg_id, **kwargs)
        except telebot.apihelper.ApiTelegramException as e:
            err = str(e).lower()
            if 'message is not modified' in err:
                return None
            if is_emoji_send_error(err):
                text = strip_custom_emoji(text)
                continue
            if "can't parse" in err or 'bad request' in err:
                try:
                    kw2 = {k: v for k, v in kwargs.items() if k != 'parse_mode'}
                    return _bot.edit_message_text(strip_custom_emoji(text), chat_id, msg_id, **kw2)
                except Exception as e2:
                    if attempt == 1:
                        forward_error("EDIT_MSG_FALLBACK", e2, chat_id)
                    return None
            if 'message to edit not found' in err:
                return safe_send(chat_id, text, **kwargs)
            if 'too many requests' in err:
                try:
                    retry_after = int(str(e).split('Retry after ')[1].split(' ')[0])
                except Exception:
                    retry_after = 2
                time.sleep(min(retry_after, 5))
                continue
            if attempt == 1:
                forward_error("EDIT_MSG_API", e, chat_id)
            return None
        except Exception as e:
            if attempt == 1:
                forward_error("EDIT_MSG", e, chat_id)
            return None
    return None


def safe_delete(chat_id, msg_id):
    try:
        _bot.delete_message(chat_id, msg_id)
        return True
    except Exception:
        return False


def safe_answer(call_id, text="", **kwargs):
    try:
        _bot.answer_callback_query(call_id, text, **kwargs)
    except Exception:
        pass


def safe_reply(msg, text, **kwargs):
    try:
        kwargs.setdefault('parse_mode', 'HTML')
        if kwargs.get('parse_mode') == 'HTML':
            text = premiumize_emoji_html(text)
        return _bot.reply_to(msg, text, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        if is_emoji_send_error(str(e)):
            try:
                return _bot.reply_to(msg, strip_custom_emoji(text), **kwargs)
            except Exception:
                return safe_send(msg.chat.id, strip_custom_emoji(text), **kwargs)
        return safe_send(msg.chat.id, text, **kwargs)
    except Exception:
        return safe_send(msg.chat.id, text, **kwargs)
