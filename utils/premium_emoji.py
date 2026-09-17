"""
PREMIUM EMOJI MODULE — Auto-converts plain emoji in outgoing HTML text
to Telegram custom (premium) emoji, so the bot "looks premium" everywhere.

Usage (already wired into handlers/bot_safe.py — no per-message changes
needed anywhere else in the codebase):

    from utils.premium_emoji import premiumize_emoji_html
    text = premiumize_emoji_html(text)

Notes:
  • Custom emoji only render inside message TEXT / CAPTIONS with
    parse_mode='HTML'. Telegram does NOT support them inside inline
    keyboard button labels (Bot API limitation) — buttons keep plain emoji.
  • <code>/<pre> blocks are left untouched on purpose, so IDs/tokens shown
    to admins stay tap-to-copy and don't get replaced.
  • These emoji-ids were not generated from this account — some may
    become invalid if the source pack is ever deleted. safe_send /
    safe_edit already retry with plain emoji automatically if Telegram
    rejects a message because of a bad custom-emoji id
    (see is_emoji_send_error / strip_custom_emoji below).
"""
import re as _re

# ═══════════════════════════════════════════════════
#  ANIMATED EMOJI IDS (used only for a handful of named entries in EMOJI)
# ═══════════════════════════════════════════════════
_ANIMATED = {
    "⚠️": "6098337704682984714",
    "🛑": "6325507973896472524",
    "👋": "6026306335715365949",
    "🤕": "6325636152900453913",
    "❤️": "5287446418909328171",
    "💙": "5285528007342058142",
    "💚": "5287724290408477329",
    "💛": "5287501467505161665",
    "💜": "5287590605256418477",
    "🧡": "5287614480979618146",
    "🖤": "5287447767529055897",
    "🤍": "5287767360340519834",
    "🤎": "5285242409196741959",
    "💕": "5284987172175246592",
    "💖": "5287448931465194557",
    "💗": "5287503091002794719",
    "💘": "5287249000737564644",
    "💔": "5285051678289063571",
    "💓": "5285273758163038115",
    "💎": "6026031174340579961",
    "⭐️": "5285074982781610729",
    "🦋": "5287474383441390368",
    "☹️": "5287450700991720181",
    "🍬": "5287389347383897591",
}

# ═══════════════════════════════════════════════════
#  PLAIN-EMOJI -> CUSTOM-EMOJI-ID MAP
#  Used by premiumize_emoji_html() to auto-replace any of these
#  characters wherever they show up in outgoing message text.
# ═══════════════════════════════════════════════════
PREMIUM_EMOJI_IDS = {
    "✅": "5444987348334965906", "❌": "5447647474984449520", "🔥": "5116414868357907335",
    "⚡": "5219943216781995020", "💳": "5447453226498552490", "💠": "5870498447068502918",
    "📝": "5444860552310457690", "🌐": "5447602197439218445", "📊": "5445146408153806223",
    "📦": "5303102515301083665", "📋": "5444931419270839381", "⏳": "5258113901106580375",
    "🚀": "4904936030232117798", "⚠️": "4915853119839011973", "💎": "5343636681473935403",
    "👋": "5134476056241112076", "💡": "5301275719681190738", "📈": "5134457377428341766",
    "🔢": "5305652587708572354", "🔌": "5364052602357044385", "⭐": "5343636681473935403",
    "🆓": "5406756500108501710", "👑": "5303547611351902889", "🔍": "5258396243666681152",
    "⏱️": "5303243514782443814", "💥": "5122933683820430249", "🆔": "5447311106030726740",
    "👤": "5445174334031166029", "📅": "5116575178012235794", "🔄": "5454245266305604993",
    "🏦": "5303159080020372094", "🥰": "5881784744949062058", "😱": "5868517294618975202",
    "🔷": "5258024802010026053", "🔑": "5454386656628991407", "📆": "5454074580010295588",
    "👥": "5454371323595744068", "🥕": "5116599934203724812", "🌳": "5305346287820895195",
    "🦉": "5123344136665039833", "🍑": "5258121851091043775", "💪": "5305622454218024328",
    "🌝": "5404494035891023578", "📁": "5447408120752013199", "ℹ️": "5289930378885214069",
    "💀": "5231338559587257737", "📢": "5116445341150872576", "💰": "5283232570660634549",
    "🔘": "5219901967916084166", "🔗": "5447479640547428304", "👇": "5305618829265628111",
    "📌": "5447187153274567373", "💸": "5447579253723918909", "🎉": "5172632227871196306",
    "🎁": "5283031441637148958", "🚫": "5116151848855667552", "🛒": "5447319442562251569",
    "⛔️": "5275969776668134187", "🥲": "4904468402782864209", "☠️": "5231338559587257737",
    "📸": "5445344161333015312", "💬": "5447510826304959724", "😺": "5118590136149345664",
    "🌍": "5303440357428586778", "🔹": "5429436388447655367", "📹": "5445158077579952110",
    "📡": "5447448489149625830", "📍": "5447187153274567373", "🔐": "5258476306152038031",
    "🎯": "5444987348334965906", "🤖": "5219943216781995020", "🤵": "5445174334031166029",
    "⏸️": "5258113901106580375", "▶️": "5219943216781995020",
    "✉️": "5444860552310457690", "🛰️": "5447602197439218445", "🩺": "5444931419270839381",
    "🎚️": "5219943216781995020", "📐": "5444931419270839381", "🏓": "5219943216781995020",
    "🔎": "5258396243666681152", "📭": "5444860552310457690", "📩": "5444860552310457690",
    "⛔": "5275969776668134187", "🔻": "5447647474984449520", "🏛": "5303159080020372094",
    "🏪": "5447453226498552490", "📖": "5444860552310457690", "🗂": "5447408120752013199",
    "🔁": "5454245266305604993", "🧭": "5447602197439218445",
}

# ═══════════════════════════════════════════════════
#  NAMED EMOJI (optional — use EMOJI['check'] etc. directly in new code
#  if you want a specific animated/premium emoji rather than the
#  auto-replacement above)
# ═══════════════════════════════════════════════════
_CUSTOM_EMOJI_RE = _re.compile(r'<tg-emoji\s+emoji-id="\d+">([^<]*)</tg-emoji>')
_HTML_TAG_RE = _re.compile(
    r'(<tg-emoji\s+emoji-id="\d+">[^<]*</tg-emoji>|<[^>]+>)', _re.IGNORECASE
)


def _ce(eid: str, fallback: str) -> str:
    """Build a custom-emoji HTML tag. `fallback` is shown to clients that
    can't render custom emoji (older clients / no premium support)."""
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


def strip_custom_emoji(text: str) -> str:
    """Remove <tg-emoji> tags but KEEP the fallback emoji inside them.
    Used as an automatic retry when Telegram rejects a message because a
    custom-emoji id is invalid/deleted, so the message still sends with
    a normal emoji instead of failing outright."""
    return _CUSTOM_EMOJI_RE.sub(lambda m: m.group(1), str(text or ""))


def is_emoji_send_error(err_text: str) -> bool:
    """Return True if a Telegram API error looks like it was caused by a
    bad/expired custom-emoji id (so callers know it's safe to retry with
    strip_custom_emoji() rather than treating it as a fatal error)."""
    err = str(err_text or "").lower()
    return any(p in err for p in (
        "document_invalid",
        "document invalid",
        "wrong custom emoji",
        "custom emoji identifier",
        "invalid custom emoji",
        "emoji_invalid",
    ))


# NOTE on this dict: every id below was supplied by the bot owner from a
# source other than their own account (borrowed custom-emoji document ids,
# not generated from messages the owner sent). That's fine for display
# purposes, but it does mean some ids may go stale if the original source
# pack is ever deleted — that's exactly what the safe_send/safe_edit retry
# logic (is_emoji_send_error + strip_custom_emoji) above is there to handle,
# so a bad id degrades gracefully to a plain emoji instead of failing the
# whole message.
EMOJI = {
    "activity": _ce("5454245266305604993", "🔄"),
    "admin": _ce("5472308992514464048", "🛡"),
    "alarm": _ce("5852753450382659113", "🚨"),
    "alert": _ce(PREMIUM_EMOJI_IDS["⚠️"], "⚠️"),
    "angel": _ce("5438577831200178997", "🧿"),
    "angry": _ce("6136392768487954831", "😠"),
    "antenna": _ce("6097926401434851083", "📶"),
    "approved": _ce(PREMIUM_EMOJI_IDS["✅"], "✅"),
    "apprv": _ce(PREMIUM_EMOJI_IDS["✅"], "✅"),
    "arrow_curve": _ce("5253997076169115797", "↪️"),
    "arrow_left": _ce("5253997076169115797", "⬅️"),
    "arrow_right": _ce("5253997076169115797", "➡️"),
    "arrow_up": _ce("6098076497656944429", "⚡️"),
    "badge": _ce("6100448805663020296", "📛"),
    "bag": _ce("6136159783692017451", "⟐"),
    "bank": _ce(PREMIUM_EMOJI_IDS["🏦"], "🏦"),
    "bank_raw": _ce("6098365012085053396", "🏦"),
    "bat1": _ce("6138798143447244059", "🦇"),
    "bat2": _ce("6136246765369694911", "🦇"),
    "bat3": _ce("6138944241054783305", "🦇"),
    "bat4": _ce("6138477872030947849", "🦇"),
    "bat5": _ce("6136363339372043522", "🦇"),
    "bell": _ce(PREMIUM_EMOJI_IDS["📢"], "📢"),
    "bin": _ce("5472250091332993630", "🗃"),
    "black_dot": _ce("5316858509571144216", "⚫"),
    "blue_dot": _ce("5472308992514464048", "🔵"),
    "boom": _ce("6147565374289220368", "💥"),
    "braintree": _ce("5472250091332993630", "🌳"),
    "bronze": _ce("6100586674113222901", "🥉"),
    "bulb": _ce("6098387861311068868", "💡"),
    "calendar": _ce(PREMIUM_EMOJI_IDS["📅"], "📅"),
    "calendar_raw": _ce("5082628525303792441", "📅"),
    "cart": _ce(PREMIUM_EMOJI_IDS["🛒"], "🛒"),
    "cat1": _ce("6136480866857130917", "🐱"),
    "cat2": _ce("6138551474885499690", "🐱"),
    "champion": _ce("5467406098367521267", "🏆"),
    "chart": _ce(PREMIUM_EMOJI_IDS["📊"], "📊"),
    "chart_down": _ce("6098257904190624738", "📉"),
    "chart_up": _ce("6098257904190624738", "📈"),
    "chart_up_raw": _ce("6098163741327629439", "📈"),
    "chat": _ce("6100672624998750369", "💬"),
    "check": _ce(PREMIUM_EMOJI_IDS["✅"], "✅"),
    "check2": _ce("6253414379442670769", "✅"),
    "check3": _ce("6253754970349243649", "✅"),
    "checkmark": _ce(PREMIUM_EMOJI_IDS["✅"], "✅"),
    "checkout": _ce(PREMIUM_EMOJI_IDS["🛒"], "🛒"),
    "clipboard": _ce(PREMIUM_EMOJI_IDS["📋"], "📋"),
    "clock": _ce(PREMIUM_EMOJI_IDS["⏱️"], "⏱️"),
    "code": _ce("6098076497656944429", "🖋"),
    "coin": _ce("6100448805663020296", "🪙"),
    "collapse": _ce("6097926401434851083", "🔼"),
    "comet": _ce("6100586674113222901", "🔥"),
    "confetti": _ce("5424818078833715060", "📣"),
    "cop": _ce("5472308992514464048", "👮"),
    "copy": _ce("6100672624998750369", "📋"),
    "cross": _ce(PREMIUM_EMOJI_IDS["❌"], "❌"),
    "crown": _ce(PREMIUM_EMOJI_IDS["👑"], "👑"),
    "crown_raw": _ce("5319149831673887746", "👑"),
    "crystal": _ce("6100448805663020296", "🔮"),
    "cycle": _ce(PREMIUM_EMOJI_IDS["🔄"], "🔄"),
    "database": _ce("5316858509571144216", "🗄"),
    "dead": _ce(PREMIUM_EMOJI_IDS["❌"], "❌"),
    "decl": _ce(PREMIUM_EMOJI_IDS["❌"], "❌"),
    "diamond": _ce(PREMIUM_EMOJI_IDS["💎"], "💎"),
    "dice": _ce("5436113877181941026", "🎲"),
    "dizzy": _ce("6136389654636665179", "⟐"),
    "dollar": _ce("5472250091332993630", "💵"),
    "downgrade": _ce("5852753450382659113", "⬇️"),
    "elite": _ce(_ANIMATED.get("💎", "6100448805663020296"), "💎"),
    "expand": _ce("6097926401434851083", "🔽"),
    "export": _ce("5424818078833715060", "📤"),
    "eye": _ce("5188217332748527444", "👁"),
    "file": _ce("6100672624998750369", "📄"),
    "filter": _ce("5188217332748527444", "🔬"),
    "fingerprint": _ce("5316858509571144216", "🔏"),
    "fire": _ce(PREMIUM_EMOJI_IDS["🔥"], "🔥"),
    "firewall": _ce("5472308992514464048", "🧱"),
    "flag": _ce("6097926401434851083", "🚩"),
    "flag1": _ce("6136165822416033423", "⟐"),
    "flag2": _ce("6136330925253860126", "⟐"),
    "flame": _ce(PREMIUM_EMOJI_IDS["🔥"], "🔥"),
    "fleur": _ce("6136165822416033423", "⟐"),
    "folder": _ce(PREMIUM_EMOJI_IDS["📁"], "📁"),
    "forward": _ce("5253997076169115797", "▶️"),
    "gear": _ce("4904936030232117798", "🔧"),
    "gem": _ce(PREMIUM_EMOJI_IDS["💎"], "💎"),
    "generate": _ce(PREMIUM_EMOJI_IDS["🔢"], "🔢"),
    "ghost": _ce("5240241223632954241", "👻"),
    "gift": _ce(PREMIUM_EMOJI_IDS["🎁"], "🎁"),
    "globe": _ce(PREMIUM_EMOJI_IDS["🌐"], "🌐"),
    "glow": _ce("6136204644625423818", "⚡"),
    "gold": _ce("5467406098367521267", "🥇"),
    "graph": _ce("6098257904190624738", "📊"),
    "green_dot": _ce("6100395724162210221", "🟢"),
    "hammer": _ce("6098076497656944429", "🔨"),
    "hand": _ce("6136205108481890460", "⟐"),
    "handshake": _ce("6136198451282581752", "⟐"),
    "hash": _ce(PREMIUM_EMOJI_IDS["🔢"], "🔢"),
    "heart": _ce(_ANIMATED["❤️"], "❤️"),
    "heart2": _ce("6136585445015821278", "❤️"),
    "heart3": _ce("6136470835319351236", "❤️"),
    "heart_blue": _ce(_ANIMATED["💙"], "💙"),
    "heart_fire": _ce("6100586674113222901", "❤️‍🔥"),
    "heart_gold": _ce(_ANIMATED["💛"], "💛"),
    "heart_purple": _ce(_ANIMATED["💜"], "💜"),
    "home": _ce("6100448805663020296", "🏠"),
    "hourglass": _ce(PREMIUM_EMOJI_IDS["⏳"], "⏳"),
    "hundred": _ce("6100395724162210221", "💯"),
    "id": _ce("5197593250650680436", "🆔"),
    "id_card": _ce(PREMIUM_EMOJI_IDS["🆔"], "🆔"),
    "import_data": _ce("6100672624998750369", "📥"),
    "inbox": _ce("6100672624998750369", "📥"),
    "info": _ce(PREMIUM_EMOJI_IDS["ℹ️"], "ℹ️"),
    "invoice": _ce("6100672624998750369", "🧾"),
    "joystick": _ce("6098076497656944429", "🕹"),
    "key": _ce(PREMIUM_EMOJI_IDS["🔑"], "🔑"),
    "laptop": _ce("6136618494789163433", "💻"),
    "laugh": _ce("6138950679210760878", "⟐"),
    "leaf": _ce("6136525109315245846", "⟐"),
    "legend": _ce("5467406098367521267", "⚜️"),
    "lightning": _ce("6098076497656944429", "🌩"),
    "link": _ce(PREMIUM_EMOJI_IDS["🔗"], "🔗"),
    "load": _ce("5303382628773161521", "📂"),
    "lock": _ce(PREMIUM_EMOJI_IDS["🔐"], "🔐"),
    "love": _ce("6138851255012826209", "❤️"),
    "love2": _ce("6138851255012826209", "❤️"),
    "love_face": _ce("6100144816467744473", "🥰"),
    "magic": _ce(PREMIUM_EMOJI_IDS["🔥"], "🔥"),
    "mail": _ce("6100672624998750369", "📧"),
    "medal": _ce("5467406098367521267", "🏅"),
    "megaphone": _ce(PREMIUM_EMOJI_IDS["📢"], "📢"),
    "meter": _ce("6098076497656944429", "📏"),
    "midnight": _ce("5316858509571144216", "🌙"),
    "money": _ce(PREMIUM_EMOJI_IDS["💰"], "💰"),
    "mute": _ce("5240241223632954241", "🔕"),
    "network": _ce("6097926401434851083", "🕸"),
    "neutral": _ce("6253319739838303271", "⟐"),
    "news": _ce("6136389654636665179", "⟐"),
    "newuser": _ce(_ANIMATED["👋"], "🆕"),
    "numbers": _ce("6098132224857610496", "🔢"),
    "orange_dot": _ce("6100586674113222901", "🟠"),
    "outbox": _ce("5424818078833715060", "📤"),
    "owner": _ce(PREMIUM_EMOJI_IDS["👑"], "👑"),
    "party": _ce(PREMIUM_EMOJI_IDS["🎉"], "🎉"),
    "pass_card": _ce("5472250091332993630", "🎟"),
    "paste": _ce("6100672624998750369", "📎"),
    "pause": _ce("5303382628773161521", "⏸"),
    "payment": _ce("5472250091332993630", "💲"),
    "paypal": _ce("5472250091332993630", "🅿️"),
    "pending": _ce(PREMIUM_EMOJI_IDS["⏳"], "⏳"),
    "pin": _ce(PREMIUM_EMOJI_IDS["📌"], "📌"),
    "play": _ce("6098076497656944429", "▶️"),
    "premium": _ce(PREMIUM_EMOJI_IDS["💎"], "💎"),
    "premium_alert": _ce(PREMIUM_EMOJI_IDS["⚠️"], "⚠️"),
    "premium_badge": _ce(PREMIUM_EMOJI_IDS["💎"], "💎"),
    "premium_doc": _ce("6100672624998750369", "✍️"),
    "premium_fast": _ce("6098076497656944429", "⚡️"),
    "premium_hot": _ce(PREMIUM_EMOJI_IDS["🔥"], "🔥"),
    "premium_lock": _ce(PREMIUM_EMOJI_IDS["🔐"], "🔐"),
    "premium_ok": _ce(PREMIUM_EMOJI_IDS["✅"], "✅"),
    "premium_stop": _ce(PREMIUM_EMOJI_IDS["⛔️"], "⛔️"),
    "premium_wave": _ce(_ANIMATED["👋"], "👋"),
    "pro_badge": _ce(PREMIUM_EMOJI_IDS["👑"], "👑"),
    "processing": _ce(PREMIUM_EMOJI_IDS["⏳"], "⏳"),
    "proxy": _ce(PREMIUM_EMOJI_IDS["🌐"], "🌐"),
    "pulse": _ce(_ANIMATED.get("💓", "6098076497656944429"), "💓"),
    "purple_dot": _ce("6100448805663020296", "🟣"),
    "pushpin": _ce(PREMIUM_EMOJI_IDS["📍"], "📍"),
    "rainbow": _ce("6100448805663020296", "🌈"),
    "random": _ce("5436113877181941026", "🎲"),
    "receipt": _ce("6100672624998750369", "🧾"),
    "red_dot": _ce("5852753450382659113", "🔴"),
    "rocket": _ce(PREMIUM_EMOJI_IDS["🚀"], "🚀"),
    "robot": _ce(PREMIUM_EMOJI_IDS["🤖"], "🤖"),
    "star": _ce(PREMIUM_EMOJI_IDS["⭐"], "⭐"),
    "wallet_bill": _ce(PREMIUM_EMOJI_IDS["💸"], "💸"),
    "wave": _ce(_ANIMATED["👋"], "👋"),
}


_TOKEN_RE = _re.compile(r'(<[^>]+>|&[a-zA-Z][a-zA-Z0-9]*;|&#\d+;)')


def bold(text: str) -> str:
    """Convert ASCII letters/digits to Unicode 'sans-serif bold' code
    points, so text can be visually bold without needing <b> tags
    (useful inside <code> spans, where <b> is not rendered by Telegram)."""
    out = []
    for ch in str(text or ""):
        o = ord(ch)
        if 0x41 <= o <= 0x5A:      # A-Z
            out.append(chr(o - 0x41 + 0x1D5D4))
        elif 0x61 <= o <= 0x7A:    # a-z
            out.append(chr(o - 0x61 + 0x1D5EE))
        elif 0x30 <= o <= 0x39:    # 0-9
            out.append(chr(o - 0x30 + 0x1D7EC))
        else:
            out.append(ch)
    return "".join(out)


def boldify_b_tags(text: str) -> str:
    """Render <b>/<strong> content as Unicode sans-serif bold, then drop
    the tags. Content inside <code>/<pre> is never bolded (stays
    tap-to-copy) and HTML entities (&amp; etc.) are preserved intact."""
    text = str(text or "")
    if "<b>" not in text and "<strong>" not in text:
        return text
    out = []
    skip_depth = 0
    b_depth = 0
    pos = 0
    for m in _TOKEN_RE.finditer(text):
        if m.start() > pos:
            chunk = text[pos:m.start()]
            out.append(bold(chunk) if (b_depth and not skip_depth) else chunk)
        tok = m.group(0)
        low = tok.lower()
        if low in ("<b>", "<strong>"):
            b_depth += 1
        elif low in ("</b>", "</strong>"):
            b_depth = max(0, b_depth - 1)
        elif low.startswith("<code") or low.startswith("<pre"):
            skip_depth += 1
            out.append(tok)
        elif low.startswith("</code") or low.startswith("</pre"):
            skip_depth = max(0, skip_depth - 1)
            out.append(tok)
        else:
            out.append(tok)
        pos = m.end()
    if pos < len(text):
        chunk = text[pos:]
        out.append(bold(chunk) if (b_depth and not skip_depth) else chunk)
    return "".join(out)


# Sort once at import time (longest emoji first, so multi-codepoint emoji
# like "⚠️" match before their shorter prefix "⚠" would).
_SORTED_EMOJI = sorted(PREMIUM_EMOJI_IDS.items(), key=lambda kv: len(kv[0]), reverse=True)


def _premiumize_simple(text: str) -> str:
    """Replace plain emoji with premium <tg-emoji> tags using a
    placeholder pass (avoids double-replacing inside emoji we just
    inserted, e.g. an emoji-id fallback char matching another key)."""
    if not text:
        return text
    placeholders = []
    result = text
    for i, (emoji, doc_id) in enumerate(_SORTED_EMOJI):
        if emoji not in result:
            continue
        placeholder = f"\x00PE{i:03d}\x00"
        placeholders.append((placeholder, doc_id, emoji))
        result = result.replace(emoji, placeholder)
    for placeholder, doc_id, emoji in placeholders:
        result = result.replace(placeholder, f'<tg-emoji emoji-id="{doc_id}">{emoji}</tg-emoji>')
    return result


def premiumize_emoji_html(text: str) -> str:
    """Convert plain emoji in HTML bot text to Telegram premium custom
    emoji tags. Existing <tg-emoji> tags and <code>/<pre> content are
    left untouched so card/ID/log lines stay copy-friendly and nothing
    gets double-wrapped."""
    text = str(text or "")
    if not text:
        return text
    out: list = []
    skip_depth = 0
    pos = 0
    for match in _HTML_TAG_RE.finditer(text):
        if match.start() > pos:
            chunk = text[pos:match.start()]
            out.append(chunk if skip_depth else _premiumize_simple(chunk))
        tag = match.group(0)
        out.append(tag)
        tag_lower = tag.lower()
        if tag_lower.startswith("<code") or tag_lower.startswith("<pre"):
            skip_depth += 1
        elif tag_lower.startswith("</code") or tag_lower.startswith("</pre"):
            skip_depth = max(0, skip_depth - 1)
        pos = match.end()
    if pos < len(text):
        chunk = text[pos:]
        out.append(chunk if skip_depth else _premiumize_simple(chunk))
    return "".join(out)
