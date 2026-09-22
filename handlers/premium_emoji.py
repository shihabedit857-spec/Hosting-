"""
Button + text helpers — NORMAL unicode emoji only.
No premium custom emoji IDs. No icon_custom_emoji_id. No tg-emoji tags.
"""
from __future__ import annotations
import logging
import re as _re
from telebot import types

logger = logging.getLogger('APON.emoji')

# ── Normal unicode emoji for buttons ──────────────────────────
BTN_FALLBACK = {
    "robot": "🤖", "rocket": "🚀", "send": "📤", "gem": "💎",
    "money": "💰", "gift": "🎁", "promo": "🎟", "chart": "📊",
    "green": "🟢", "flash": "⚡", "book": "📚", "gear": "⚙️",
    "bell": "🔔", "crown": "👑", "check": "✅", "cross": "❌",
    "back": "🔙", "refresh": "🔄", "stop": "🛑", "play": "▶️",
    "logs": "📋", "download": "📥", "trash": "🗑", "search": "🔍",
    "monitor": "🖥️", "ban": "🚫", "user": "👤", "users": "👥",
    "clock": "⏱️", "card": "💳", "plus": "➕", "minus": "➖",
    "lock": "🔐", "key": "🔑", "star": "⭐", "home": "🏠",
    "contact": "📞", "siren": "🚨", "megaphone": "📢", "party": "🎉",
    "trophy": "🏆", "speech": "💬", "planet": "🌐", "link": "🔗",
    "bulb": "💡", "box": "📦", "target": "🎯", "shield": "🛡",
    "fire": "🔥", "sparkle": "✨", "pip": "📦", "pkg": "📦",
}

# Empty — no premium IDs
BTN_E = {}

# ── Style support only (Bot API 9.4) — no custom emoji icons ──
_ICON_EMOJI_SUPPORTED = False

try:
    _orig_init = types.InlineKeyboardButton.__init__
    _orig_to_dict = types.InlineKeyboardButton.to_dict

    def _patched_init(self, *args, **kwargs):
        style = kwargs.pop('style', None)
        kwargs.pop('icon_custom_emoji_id', None)  # always drop
        _orig_init(self, *args, **kwargs)
        self._style = style
        self._icon_custom_emoji_id = None

    def _patched_to_dict(self):
        d = _orig_to_dict(self)
        s = getattr(self, '_style', None)
        if s:
            d['style'] = s
        # never attach icon_custom_emoji_id
        d.pop('icon_custom_emoji_id', None)
        return d

    types.InlineKeyboardButton.__init__ = _patched_init
    types.InlineKeyboardButton.to_dict = _patched_to_dict
except Exception as e:
    logger.error(f"Monkey-patch failed: {e}")


def set_viewer_premium(is_premium: bool = False) -> None:
    """Compatibility no-op."""
    pass


def get_viewer_premium() -> bool:
    return False


def btn(text, style=None, emoji_key=None, emoji_id=None, plain=None,
        premium=None, **kwargs):
    """
    Normal button only — unicode emoji in text, never custom emoji ID.
    """
    has_action = (
        kwargs.get('callback_data') or kwargs.get('url') or
        kwargs.get('web_app') or kwargs.get('switch_inline_query') or
        kwargs.get('switch_inline_query_current_chat') or
        kwargs.get('login_url') or kwargs.get('callback_game') or
        kwargs.get('pay')
    )
    if not has_action:
        logger.warning(f"btn() called without action — text: {text}")
        kwargs['callback_data'] = 'noop'

    # Drop any accidental premium icon kwargs
    kwargs.pop('icon_custom_emoji_id', None)

    fb = plain or (BTN_FALLBACK.get(emoji_key, "") if emoji_key else "")
    if fb and not str(text).startswith(fb):
        text = f"{fb} {text}"
    return types.InlineKeyboardButton(text, style=style, **kwargs)


# ── Text helpers: strip custom tags, never inject them ─────────
_CUSTOM_EMOJI_RE = _re.compile(r'<tg-emoji\s+emoji-id="\d+">([^<]*)</tg-emoji>')


def strip_custom_emoji(text: str) -> str:
    """Replace any tg-emoji tags with their inner fallback unicode."""
    return _CUSTOM_EMOJI_RE.sub(lambda m: m.group(1), str(text or ""))


def is_emoji_send_error(err_text: str) -> bool:
    err = str(err_text or "").lower()
    return any(p in err for p in (
        'custom emoji', 'emoji_id', 'can\'t parse entities',
        'unsupported start tag "tg-emoji"',
    ))


def premiumize_emoji_html(text: str) -> str:
    """No-op: keep normal unicode only (strip any premium tags)."""
    return strip_custom_emoji(text or "")
