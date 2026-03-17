# meta developer: @Mr4epTuk
# meta version: 1.1.0
# meta name: MultiFC
# requires: aiohttp

from herokutl.types import Message
from herokutl.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from herokutl.tl.functions.messages import GetDialogFiltersRequest, GetDiscussionMessageRequest
from .. import loader, utils
import logging
import asyncio
import re
import random
import aiohttp
import time
from typing import Optional, List, Dict, Set

logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# PRIZE KEYWORDS
# ═════════════════════════════════════════════════════════════════════════════
_PRIZE_KW = (
    r"нфт|nft|мишк|мишек|медвед|розочк|звезд|star|прем|prem|gift|гифт|алмаз|"
    r"сердечк|сердец|ракет|rocket|ton|usdt|rub|крист|crystal|цветоч|букет|"
    r"подар|приз|награ|выигр|выдад|получ|раздад|разыгр|жетон|токен|coin|монет|"
    r"\U0001F9F8|\U0001F5BC|\U0001F339|\u2B50|\U0001F48E|\U0001F381|\U0001F940"
    r"|\U0001F49D|\U0001F380|\U0001F680|\U0001F4AB|\U0001F3C6|\U0001FA99"
    r"|\U0001F338|\U0001F33A|\U0001F33B|\U0001F33C|\U0001F490|\U0001F38A|\U0001F389"
    r"|\U0001F388|\U0001F3C5|\U0001F947|\U0001F948|\U0001F949|\U0001F4B0"
    r"|\U0001F4B5|\U0001F4B4|\U0001F4B6|\U0001F4B7|\U0001FA85|\U0001F9FF"
    r"|\U0001F52E|\u26A1|\U0001F31F|\u2728|\U0001F4A5"
)
_PRIZE_RE = re.compile(_PRIZE_KW, re.IGNORECASE)

# Слово «комментарий» в любой форме
_KOM = r"комм?ент(?:арий|ариев|арию|ариям|ария|ов|у|е|ом|ах|ами|а|ы|атор\w*)?\b|ком\b"

# Разделители "число = приз" / "число: приз" / "число — приз"
_SEP = r"(?:[\s=:—–\-\u2013\u2014\u2192>|,.]+|(?:\s*и\s*))"

# ═════════════════════════════════════════════════════════════════════════════
# DEFAULT TRIGGERS
# ═════════════════════════════════════════════════════════════════════════════
DEFAULT_TRIGGERS = [

    # 1. "21 коментарий = нфт" / "25 Комментарий = НФТ" / "5 ком: подарок"
    (r"\b\d+" + _SEP + r"(?:" + _KOM + r")" + _SEP + r"(?:" + _PRIZE_KW + r")"),

    # 2. "нфт 21 коментарий" / "мишка = 5 ком"
    (r"(?:" + _PRIZE_KW + r")" + _SEP + r"\b\d+" + _SEP + r"(?:" + _KOM + r")"),

    # 3. "5му нфт" / "10-му мишка" / "3й алмаз"
    (r"\b\d+\s*[-–—]?\s*(?:го|му|ому|ему|й|ый|ий|ой)\b.{0,60}(?:" + _PRIZE_KW + r")"),

    # 4. "пятому нфт" / "первому мишка" / "третьему алмаз"
    (r"(?:перв\w+|втор\w+|трет\w+|четв\w+|пят\w+|шест\w+|седьм\w+|восьм\w+"
     r"|девят\w+|десят\w+).{0,60}(?:" + _PRIZE_KW + r")"),

    # 5. Список чисел + приз: "13 19 и 34 нфт" / "1, 8, 15 мишка" / "10 20 30 нфт"
    (r"\d+(?:" + _SEP + r"\d+){2,}.{0,30}(?:" + _PRIZE_KW + r")"),

    # 6. Большой арифм. список: "10 20 30 40 50 коментарий"
    (r"\b\d{1,4}(?:\s+\d{1,4}){4,}.{0,80}(?:" + _KOM + r"|" + _PRIZE_KW + r")"),

    # 7. "первые N + приз" / "N первых + приз"
    (r"первы[ехми]+\s+\d+.{0,80}(?:" + _PRIZE_KW + r")"),
    (r"\d+\s+первы[ехми]+.{0,80}(?:" + _PRIZE_KW + r")"),

    # 8. "первым N коментам" (с призом или без)
    (r"первы[ехми]+\s+\d+\s*(?:" + _KOM + r")"),
    (r"первым\s+\d+\s*(?:" + _KOM + r")"),

    # 9. "N комментов получат/получит"
    (r"\b\d+\s*(?:" + _KOM + r")\s*(?:получ|выигр|достан)\w*"),

    # 10. "напиши «слово»" / 'напиши "слово"'
    (r'(?:напиш[иеёт]+|написавш\w+|написать|пишем|пишите)\s+(?:слово\s+)?[«"]'),

    # 11. "кто первый напишет"
    (r"кто\s+(?:будет\s+)?первы[йм]\s+(?:кто\s+)?напиш\w+"),
    (r"первому\s+(?:кто\s+)?напиш\w+"),

    # 12. Emoji приз после числа: "5 🧸" / "10 💎"
    (r"\b\d+\s*(?:\U0001F9F8|\U0001F48E|\U0001F381|\U0001F339|\U0001F940|\U0001F680"
     r"|\U0001F4AB|\U0001F3C6|\U0001F389|\U0001F338|\U0001F31F|\u2728|\u2B50)"),

    # 13. "разыгрываем/раздаём/отдадим + приз"
    (r"(?:разыгрыва\w+|раздаём|раздаем|раздадим|отдад\w+|дарим|дарю)\s.{0,60}"
     r"(?:" + _PRIZE_KW + r")"),

    # 14. "первый комментарий" в любом контексте
    (r"перв\w+\s+(?:" + _KOM + r")"),
    (r"(?:" + _KOM + r")\s*[#№]?\s*1\b"),
]

# ═════════════════════════════════════════════════════════════════════════════
# ANALYZERS
# ═════════════════════════════════════════════════════════════════════════════

# "напиши «слово»"
_REQ_WORD_RE = re.compile(
    r'(?:напиш[иеёт]+|написавш\w+|написать|пишем|пишите|написавшему)\s+'
    r'(?:в\s+)?(?:комм?ент(?:арий)?\s+)?(?:слово\s+)?'
    r'(?:[«"\'"]([^»"\'"\n]{1,120})[»"\'"\n]'
    r'|([а-яёА-ЯЁa-zA-Z]{2,30}(?<![её]т)(?<!ит)(?<!ут)(?<!ают)))',
    re.IGNORECASE,
)

# "первые N" / "N первых" / "первым N коментам" / "получат первые N"
_FIRST_N_RE = re.compile(
    r"первы[ехми]+\s+(\d+)"             # "первые 30"
    r"|(\d+)\s+первы[ехми]+"            # "30 первых"
    r"|первым\s+(\d+)\s*(?:" + _KOM + r")"  # "первым 30 коментам"
    r"|получ\w*\s+первы[ехми]+\s+(\d+)" # "получат первые 15"
    r"|первы[ехми]+\s+(\d+)\s*(?:человек|участник|комментатор)\w*",  # "первые 10 человек"
    re.IGNORECASE,
)

# "N коментов получит" → одиночная цель
_NTH_RECV_RE = re.compile(
    r"\b(\d+)\s*(?:" + _KOM + r")\s*(?:получ|выигр|достан)\w+",
    re.IGNORECASE,
)

# "N коменту/комментарию" (с разделителями)
_NTH_KOM_RE = re.compile(
    r"\b(\d+)\s*[-–—=:]*\s*(?:" + _KOM + r")",
    re.IGNORECASE,
)

# "Nму/N-го/Nй"
_NTH_ORD_RE = re.compile(
    r"\b(\d+)\s*[-–—]?\s*(?:го|му|ому|ему|й|ый|ий|ой|им)\b",
    re.IGNORECASE,
)

_ORDINALS = [
    (re.compile(r"\bперв(?!ые|ым|ых|ого|ому|ой|ую|ое)\w*", re.I), 1),
    (re.compile(r"\bвтор\w*", re.I), 2),
    (re.compile(r"\bтрет[ьейиму]\w*", re.I), 3),
    (re.compile(r"\bчетв[её]р\w*", re.I), 4),
    (re.compile(r"\bпят(?!н)\w*", re.I), 5),
    (re.compile(r"\bшест\w*", re.I), 6),
    (re.compile(r"\bседьм\w*", re.I), 7),
    (re.compile(r"\bвосьм\w*", re.I), 8),
    (re.compile(r"\bдевят\w*", re.I), 9),
    (re.compile(r"\bдесят\w*", re.I), 10),
    (re.compile(r"\bдвадцат\w*", re.I), 20),
    (re.compile(r"\bтридцат\w*", re.I), 30),
    (re.compile(r"\bсорок\w*", re.I), 40),
    (re.compile(r"\bпятьдесят\w*|\bпятидесят\w*", re.I), 50),
    (re.compile(r"\bсот\w+|\bсотому\b", re.I), 100),
]

_CARDINALS = {
    r"\bодин\b|\bодного\b": 1,
    r"\bдва\b|\bдвух\b|\bдвое\b": 2,
    r"\bтри\b|\bтрёх\b|\bтрех\b": 3,
    r"\bчетыр\w+": 4,
    r"\bпять\b|\bпяти\b": 5,
    r"\bшесть\b|\bшести\b": 6,
    r"\bсемь\b|\bсеми\b": 7,
    r"\bвосемь\b|\bвосьми\b": 8,
    r"\bдевять\b|\bдевяти\b": 9,
    r"\bдесять\b|\bдесяти\b": 10,
    r"\bдвадцать\b": 20,
    r"\bтридцать\b": 30,
    r"\bсорок\b": 40,
    r"\bпятьдесят\b": 50,
    r"\bсто\b|\bсотн\w+": 100,
}

_BAD_REQ_RE = re.compile(
    r"^(?:получ|выигр|достан|написат?|написа|раздад|первому|первый|первые|первым"
    r"|нфт|nft|мишк|алмаз|gift|звезд|прем|ракет|монет|приз)\w*$",
    re.I,
)



# Паттерны "результаты розыгрыша" — такие посты ПРОПУСКАЕМ (это не будущий розыгрыш)
_RESULTS_RE = re.compile(
    r"результат[ыи]\s+розыгрыш|победител[иь]|🏆\s*\d+\.\s+\w|призёр|winners\b"
    r"|итог[ии]\s+розыгрыш|конкурс\s+завершён|розыгрыш\s+завершён",
    re.IGNORECASE,
)

# Числа у которых есть "комментарий/ком" рядом — это реальные таргеты
# Числа у которых нет — может быть что угодно (кол-во призов, минут, и т.д.)
_NUM_WITH_CONTEXT_RE = re.compile(
    r"\b(\d{1,5})\s*[-–—=:]*\s*(?:комм?ент\w*|ком)\b"   # "25 коментов", "3 коменту"
    r"|\b(\d{1,5})\s*[-–—]?\s*(?:го|му|ому|ему|й|ый|ий|ой|им)\b"  # "10му", "3-ий"
    r"|\b(?:перв|втор|трет|четв|пят|шест|седьм|восьм|девят|десят)\w*\s+(\d{1,5})\b"
    r"|\b(\d{1,5})\s+(?:перв|втор|трет)\w+\b",           # "30 первых"
    re.IGNORECASE,
)


def _is_results_post(text: str) -> bool:
    """True если пост — это объявление результатов (не будущий розыгрыш)."""
    return bool(_RESULTS_RE.search(text))


def _nums_have_comment_context(text: str, nums: list) -> bool:
    """
    True если хотя бы одно число стоит рядом с словом комментарий/ком/порядковым суффиксом.
    Это отличает "25 коменту нфт" (цель = 25) от "3 ПЕЧЕНЬКИ 🎁" (цель != 3).
    """
    for m in _NUM_WITH_CONTEXT_RE.finditer(text):
        n = int(next(g for g in m.groups() if g is not None))
        if n in nums:
            return True
    return False


def _extract_nums(text: str) -> list:
    """Extract comment-target numbers. Three passes."""
    cleaned = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text)   # strip HH:MM times
    cleaned = re.sub(r"[=:\u2192>|]", " ", cleaned)
    result = set()
    # Pass 1: ordinal suffix "5му", "10-й"
    for m in re.finditer(
        r"\b(\d{1,5})\s*[-\u2013\u2014]?\s*"
        r"(?:\u0433\u043e|\u043c\u0443|\u043e\u043c\u0443|\u0435\u043c\u0443"
        r"|\u0439|\u044b\u0439|\u0438\u0439|\u043e\u0439|\u0438\u043c)\b",
        cleaned, re.I
    ):
        n = int(m.group(1))
        if 1 <= n <= 5000:
            result.add(n)
    # Pass 2: "N ком/комент"
    for m in re.finditer(
        r"\b(\d{1,5})\s*[-\u2013\u2014=:]*\s*"
        r"(?:\u043a\u043e\u043c\u043c?\u0435\u043d\u0442\w*|\u043a\u043e\u043c)\b",
        cleaned, re.I
    ):
        n = int(m.group(1))
        if 1 <= n <= 5000:
            result.add(n)
    # Pass 3: standalone digits (only if context check passes later)
    for m in re.finditer(r"(?<!\d)(\d{1,5})(?!\d)", cleaned):
        n = int(m.group(1))
        if 1 <= n <= 5000:
            result.add(n)
    return sorted(result)


def _analyze(text: str) -> dict:
    """Parse giveaway post. Returns {targets, required_text, is_first_n, first_n}."""
    # Skip results posts
    if _is_results_post(text):
        return {"required_text": None, "is_first_n": True, "first_n": 1,
                "targets": [1], "_skip_reason": "results_post"}

    clean = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text)
    clean = re.sub(r"[=:\u2192>|]", " ", clean)
    has_prize = bool(_PRIZE_RE.search(clean))

    # "напиши «слово»"
    req = None
    rm = _REQ_WORD_RE.search(text)
    if rm:
        quoted = (rm.group(1) or "").strip()
        bare   = (rm.group(2) or "").strip()
        if quoted:
            req = quoted
        elif bare and not _BAD_REQ_RE.match(bare) and not _PRIZE_RE.search(bare):
            req = bare

    base = {"required_text": req, "is_first_n": False, "first_n": 1}

    # ── FIRST_N check first ───────────────────────────────────────────────────
    fn = _FIRST_N_RE.search(clean)
    if fn:
        raw = fn.group(1) or fn.group(2) or fn.group(3) or fn.group(4) or fn.group(5)
        n = int(raw) if raw else 1
        if req:
            return {**base, "required_text": req, "is_first_n": False, "targets": [1]}
        return {**base, "targets": [1], "is_first_n": True, "first_n": n}

    # ── "первые + cardinal word" ──────────────────────────────────────────────
    if re.search(r"первы[ехми]+|первым\b", clean, re.I):
        for pat_str, num in _CARDINALS.items():
            if re.search(pat_str, clean, re.I):
                if req:
                    return {**base, "required_text": req, "is_first_n": False, "targets": [num]}
                return {**base, "targets": [1], "is_first_n": True, "first_n": num}

    if not has_prize and not req:
        return {**base, "targets": [1], "is_first_n": True}

    # ── Explicit ordinal/comment-context numbers ──────────────────────────────
    # Collect ALL numbers near "ком/комент/ordinal-suffix"
    context_nums = []
    for m in _NUM_WITH_CONTEXT_RE.finditer(clean):
        n = int(next(g for g in m.groups() if g is not None))
        if 1 <= n <= 5000:
            context_nums.append(n)
    context_nums = sorted(set(context_nums))

    # All numbers in text (for list detection)
    all_nums = _extract_nums(clean)
    plausible = [n for n in all_nums if n <= 2000]

    # If ≥2 plausible and at least one has comment context → all are targets
    if len(plausible) >= 2 and _nums_have_comment_context(clean, set(plausible)):
        diffs = [plausible[i+1] - plausible[i] for i in range(len(plausible)-1)]
        if len(set(diffs)) == 1 and diffs[0] > 0:
            return {**base, "targets": plausible}
        return {**base, "targets": plausible}

    # Single context number
    if len(context_nums) >= 2:
        return {**base, "targets": context_nums}
    if len(context_nums) == 1:
        n = context_nums[0]
        return {**base, "targets": [n], "is_first_n": n == 1}

    # ── "N коментов получит" ─────────────────────────────────────────────────
    nr = _NTH_RECV_RE.search(clean)
    if nr:
        n = int(nr.group(1))
        if 1 <= n <= 5000:
            return {**base, "targets": [n], "is_first_n": False}

    # ── "N коменту/комментарию" ───────────────────────────────────────────────
    nk = _NTH_KOM_RE.search(clean)
    if nk:
        n = int(nk.group(1))
        if 1 <= n <= 5000:
            return {**base, "targets": [n], "is_first_n": n == 1}

    # ── Russian ordinal word ──────────────────────────────────────────────────
    for pat, num in _ORDINALS:
        if pat.search(clean):
            is_fn = (num == 1) and not req
            return {**base, "targets": [num], "is_first_n": is_fn}

    # ── Digit ordinal "5му", "10-й" ───────────────────────────────────────────
    no = _NTH_ORD_RE.search(clean)
    if no:
        n = int(no.group(1))
        if 1 <= n <= 5000:
            return {**base, "targets": [n], "is_first_n": n == 1}

    # (list with context already handled above)

    # ── Fallback ──────────────────────────────────────────────────────────────
    if req:
        return {**base, "required_text": req, "is_first_n": False, "targets": [1]}
    return {**base, "targets": [1], "is_first_n": True}


@loader.tds
class MultiFCMod(loader.Module):
    """
    MultiFC — Smart Gift Hunter для Heroku Userbot.
    Анализирует посты в каналах, вычисляет нужный номер комментария и пишет
    в правильный момент чтобы выигрывать призы, NFT, мишки и другие подарки.
    Поддерживает AI (Gemini/Groq), папки каналов, индивидуальные настройки
    и уведомления через inline-бота Heroku.
    """

    strings = {
        "name": "MultiFC",
        "status": (
            "🎯 <b>MultiFC</b>\n\n"
            "⚡️ <b>Статус:</b> {status}\n"
            "📢 <b>Каналов:</b> {channels}\n"
            "🎪 <b>Охот активно:</b> {hunting}\n"
            "📁 <b>Папка:</b> <code>{folder}</code>\n"
            "🤖 <b>AI:</b> <code>{ai}</code>\n"
            "🎯 <b>Глобал триггеров:</b> {trigs}"
        ),
        "paused": "⏸ <b>MultiFC приостановлен</b>",
        "resumed": "▶️ <b>MultiFC возобновлён</b>",
        "ch_added": "✅ <b>Добавлен:</b> {title}\n<code>{id}</code>",
        "ch_exists": "ℹ️ Канал уже в списке",
        "ch_removed": "❌ <b>Удалён:</b> {title}",
        "ch_not_found": "⚠️ Канал не в списке. Сначала <code>.mfcadd</code>",
        "no_channels": "📂 Список каналов пуст. Добавь через <code>.mfcadd</code>",
        "no_folder": "📁 Укажи <code>folder_name</code> в <code>.cfg MultiFC</code>",
        "folder_not_found": "⚠️ Папка <b>{name}</b> не найдена. Создай папку в Telegram.",
        "log_empty": "📋 Логов пока нет",
        "hunt_sent": (
            "🎯 <b>MultiFC</b>\n\n"
            "📢 <b>Канал:</b> {channel}\n"
            "📝 <b>Пост:</b> <i>{post}</i>\n\n"
            "💬 <b>Отправлено:</b> {count} сообщ. {links}\n"
            "📊 <b>Статус:</b> ⚡️ Предварительная победа"
        ),
        "trig_help": (
            "<b>🎯 Управление глобал триггерами</b>\n\n"
            "<code>.mfctrig list</code> — список\n"
            "<code>.mfctrig add текст/regex</code> — добавить\n"
            "<code>.mfctrig del N</code> — удалить по номеру\n"
            "<code>.mfctrig reset</code> — сбросить к дефолтным\n"
            "<code>.mfctrig clear</code> — очистить все (реагировать на всё)"
        ),
        "chan_help": (
            "<b>⚙️ Настройка канала</b>\n\n"
            "<code>.mfcchan [id/@] info</code>\n"
            "<code>.mfcchan [id/@] enabled true/false</code>\n"
            "<code>.mfcchan [id/@] delay 0.5</code>\n"
            "<code>.mfcchan [id/@] spam_count 5</code>\n"
            "<code>.mfcchan [id/@] use_ai true/false</code>\n"
            "<code>.mfcchan [id/@] add_trigger текст</code>\n"
            "<code>.mfcchan [id/@] del_trigger текст</code>\n"
            "<code>.mfcchan [id/@] add_msg текст</code>\n"
            "<code>.mfcchan [id/@] del_msg текст</code>\n"
            "<code>.mfcchan [id/@] only_triggers true/false</code>\n"
            "<code>.mfcchan [id/@] only_msgs true/false</code>\n"
            "<code>.mfcchan [id/@] lock_global true/false</code>"
        ),
        "panel_main": (
            "🎯 <b>MultiFC Panel</b>\n\n"
            "⚡️ {status} | 🤖 AI: <code>{ai}</code>\n"
            "📢 Каналов: <b>{channels}</b> | 🎪 Охот: <b>{hunting}</b>\n"
            "📁 Папка: <code>{folder}</code>\n"
            "🎯 Триггеров: <b>{trigs}</b>"
        ),
        "panel_channels": "📋 <b>Каналы MultiFC</b> ({count} шт.)",
        "panel_chan_detail": (
            "⚙️ <b>{title}</b>\n"
            "<code>{id}</code>\n\n"
            "Статус: {enabled}\n"
            "Задержка: <code>{delay}s</code>\n"
            "Спам: <code>{spam}x</code>\n"
            "AI: <code>{ai}</code>\n"
            "Триггеров: <b>{trigs}</b>\n"
            "Сообщений: <b>{msgs}</b>"
        ),
    }

    strings_ru = {"name": "MultiFC"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "status", True,
                "Глобальный переключатель модуля",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "folder_name", "",
                "Название папки Telegram с каналами (пусто = не использовать)",
                validator=loader.validators.String(min_len=0),
            ),
            loader.ConfigValue(
                "global_messages", ["а", "ну", ".", "г", "о", "р", "э", "в", "с", "п"],
                "Сообщения для комментариев — рандомно",
                validator=loader.validators.Series(validator=loader.validators.String()),
            ),
            loader.ConfigValue(
                "global_delay", 0.0,
                "Задержка перед первым комментарием (секунды)",
                validator=loader.validators.Float(),
            ),
            loader.ConfigValue(
                "spam_count", 3,
                "Кол-во сообщений при атаке",
                validator=loader.validators.Integer(minimum=1, maximum=10),
            ),
            loader.ConfigValue(
                "spam_interval", 0.3,
                "Интервал между спам-сообщениями (сек)",
                validator=loader.validators.Float(),
            ),
            loader.ConfigValue(
                "ai_provider", "none",
                "AI провайдер: none / gemini / groq",
                validator=loader.validators.Choice(["none", "gemini", "groq"]),
            ),
            loader.ConfigValue(
                "ai_api_key", "",
                "API ключ AI провайдера",
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "auto_join", True,
                "Авто-вступление в чаты обсуждений",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "disc_folder", "archive",
                "Папка для вступленных дискуссий: archive / none / <название папки>",
                validator=loader.validators.String(min_len=0),
            ),
            loader.ConfigValue(
                "dlog_file", "",
                "Путь к файлу для debug-лога (пусто = только память)",
                validator=loader.validators.String(min_len=0),
            ),
        )
        self._hunting: Dict[int, dict] = {}
        self._ch_to_disc: Dict[int, int] = {}
        self._monitored: Set[int] = set()
        self._paused: bool = False
        self._logs: List[dict] = []         # hunt summary log
        self._dlogs: List[str] = []          # detailed debug log (last 500 lines)
        self._me = None
        self._dlog_path: str = None   # optional file log path
        # (ch_pid, post_id) → timestamp — prevent duplicate fires
        self._fired: Dict[tuple, float] = {}

    async def client_ready(self, client, db):
        self._client = client
        self.db = db
        self._me = await client.get_me()
        if not self.db.get("MultiFC", "triggers", None):
            self.db.set("MultiFC", "triggers", DEFAULT_TRIGGERS)
        await self._reload_channels()

    # ── Utils ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _pid(raw_id: int) -> int:
        return abs(raw_id)

    def _get_triggers(self) -> List[str]:
        t = self.db.get("MultiFC", "triggers", None)
        return t if t is not None else DEFAULT_TRIGGERS

    async def _reload_channels(self):
        self._monitored = set()
        for cid in self.db.get("MultiFC", "channels", {}):
            try:
                self._monitored.add(self._pid(int(cid)))
            except ValueError:
                pass
        if self.config["folder_name"]:
            chs = await self._folder_channels(self.config["folder_name"])
            if chs:
                for ch in chs:
                    self._monitored.add(self._pid(ch.id))

    async def _folder_channels(self, name: str):
        try:
            res = await self._client(GetDialogFiltersRequest())
            for f in res.filters:
                if not hasattr(f, "title"):
                    continue
                raw_title = f.title
                # TextWithEntities fix
                if hasattr(raw_title, "text"):
                    raw_title = raw_title.text
                if not isinstance(raw_title, str):
                    raw_title = str(raw_title)
                if raw_title.strip().lower() != name.strip().lower():
                    continue
                out = []
                seen = set()
                # include_peers + pinned_peers (pinned chats in folder are stored separately)
                all_peers = list(getattr(f, "include_peers", [])) + list(getattr(f, "pinned_peers", []))
                for peer in all_peers:
                    try:
                        e = await self._client.get_entity(peer)
                        if e.id in seen:
                            continue
                        seen.add(e.id)
                        # Only broadcast channels, skip discussion megagroups
                        if getattr(e, "broadcast", False) and not getattr(e, "megagroup", False):
                            out.append(e)
                    except Exception:
                        pass
                return out
        except Exception as e:
            logger.error(f"[MultiFC] folder_channels: {e}")
        return None

    def _chan_cfg(self, channel_pid: int) -> dict:
        ch = self.db.get("MultiFC", "channels", {}).get(str(channel_pid), {})
        lock = ch.get("lock_global", False)
        g_trigs = self._get_triggers()
        c_trigs = ch.get("custom_triggers", [])
        excluded = set(ch.get("excluded_triggers", []))
        triggers = c_trigs if (ch.get("only_triggers") or lock) else (
            [t for t in g_trigs if t not in excluded] + c_trigs
        )
        g_msgs = self.config["global_messages"]
        c_msgs = ch.get("custom_messages", [])
        messages = (c_msgs or g_msgs) if (ch.get("only_msgs") or lock) else (g_msgs + c_msgs)
        return {
            "enabled": ch.get("enabled", True),
            "delay": ch.get("delay", self.config["global_delay"]),
            "spam_count": ch.get("spam_count", self.config["spam_count"]),
            "spam_interval": ch.get("spam_interval", self.config["spam_interval"]),
            "use_ai": ch.get("use_ai", False),
            "triggers": triggers,
            "messages": messages or ["а"],
        }

    def _match_triggers(self, text: str, cfg: dict) -> bool:
        triggers = cfg["triggers"]
        if not triggers:
            return True
        for t in triggers:
            try:
                if re.search(t, text, re.IGNORECASE):
                    return True
            except re.error:
                if t.lower() in text.lower():
                    return True
        return False

    async def _get_discussion(self, channel_pid: int) -> Optional[int]:
        if channel_pid in self._ch_to_disc:
            return self._ch_to_disc[channel_pid]
        try:
            entity = await self._client.get_entity(channel_pid)
            full = await self._client(GetFullChannelRequest(entity))
            disc = full.full_chat.linked_chat_id
            if disc:
                dpid = self._pid(disc)
                self._ch_to_disc[channel_pid] = dpid
                return dpid
        except Exception as e:
            logger.error(f"[MultiFC] get_discussion({channel_pid}): {e}")
        return None

    async def _ensure_joined(self, disc_pid: int):
        try:
            await self._client(JoinChannelRequest(disc_pid))
        except Exception:
            pass
        # Move to configured folder
        disc_folder = self.config.get("disc_folder", "archive").strip().lower()
        if disc_folder == "none" or not disc_folder:
            return
        try:
            from herokutl.tl.functions.folders import EditPeerFoldersRequest
            from herokutl.tl.types import InputFolderPeer
            entity = await self._client.get_entity(disc_pid)
            if disc_folder == "archive":
                folder_id = 1
            else:
                # Find folder by name
                folder_id = 1  # fallback
                try:
                    res = await self._client(GetDialogFiltersRequest())
                    for f in res.filters:
                        raw = getattr(f, "title", "")
                        if hasattr(raw, "text"):
                            raw = raw.text
                        if str(raw).strip().lower() == disc_folder:
                            folder_id = f.id
                            break
                except Exception:
                    pass
            await self._client(EditPeerFoldersRequest(
                folder_peers=[InputFolderPeer(peer=entity, folder_id=folder_id)]
            ))
        except Exception as e:
            logger.debug(f"[MultiFC] ensure_joined folder: {e}")

    async def _get_title(self, entity_id: int) -> str:
        try:
            e = await self._client.get_entity(entity_id)
            return getattr(e, "title", str(entity_id))
        except Exception:
            return str(entity_id)

    @staticmethod
    def _msg_link(disc_pid: int, msg_id: int) -> str:
        return f"https://t.me/c/{disc_pid}/{msg_id}"

    # ── AI ────────────────────────────────────────────────────────────────────

    async def _ai_text(self, post_text: str) -> Optional[str]:
        provider = self.config["ai_provider"]
        key = self.config["ai_api_key"]
        if provider == "none" or not key:
            return None
        prompt = (
            f'Напиши один короткий (1-5 слов) нейтральный комментарий к посту: '
            f'"{post_text[:200]}". Только текст, без кавычек и пояснений.'
        )
        try:
            async with aiohttp.ClientSession() as s:
                if provider == "gemini":
                    url = (
                        "https://generativelanguage.googleapis.com/v1beta/"
                        f"models/gemini-2.0-flash:generateContent?key={key}"
                    )
                    async with s.post(
                        url,
                        json={"contents": [{"parts": [{"text": prompt}]}]},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        d = await r.json()
                        return d["candidates"][0]["content"]["parts"][0]["text"].strip()
                elif provider == "groq":
                    async with s.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        json={
                            "model": "llama3-8b-8192",
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 20,
                        },
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"[MultiFC] AI error: {e}")
        return None

    # ── Core spam ─────────────────────────────────────────────────────────────

    async def _spam(self, hunt: dict, override_n: int = 0) -> list:
        sent = []
        req = hunt.get("required_text")
        cfg = hunt["cfg"]
        pool = [req] if req else list(cfg["messages"])
        if cfg["use_ai"] and self.config["ai_provider"] != "none":
            ai = await self._ai_text(hunt["post_text"])
            if ai:
                pool = [ai] + pool

        n = override_n if override_n > 0 else cfg["spam_count"]
        interval = cfg["spam_interval"]

        for i in range(n):
            try:
                msg = await self._client.send_message(
                    hunt["ch_peer"],
                    random.choice(pool),
                    comment_to=hunt["post_id"],
                )
                sent.append(msg)
                if i < n - 1:
                    await asyncio.sleep(interval)
            except Exception as e:
                err = str(e).lower()
                if "slow" in err or "slowmode" in err:
                    logger.info("[MultiFC] Slow mode — stopping spam")
                    break
                elif "flood" in err:
                    await asyncio.sleep(3)
                    break
                else:
                    logger.error(f"[MultiFC] send: {e}")
                    break
        return sent

    # ── Notify ────────────────────────────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════════════════════
    # NOTIFY
    # ═══════════════════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════════════════
    # ADAPTIVE ENGINE
    # ═══════════════════════════════════════════════════════════════════════════
    #
    # Firing window: target N → fire 3 msgs starting at real_count == N - offset
    # offset adapts per-channel based on where our msgs actually landed.
    # Small targets (1/2/3): fire immediately with full spam.
    #
    # Anti-duplicate: lock + done set + notify_sent flag.
    # Single exit: _finish_hunt() → _do_final_notify() called exactly once.
    # ───────────────────────────────────────────────────────────────────────────

    # ── Per-channel adaptive state (in-memory, survives per-session) ──────────
    # disc_pid → {"offset": int, "comment_ts": deque, "last_latency": float}
    _ch_stats: Dict[int, dict] = {}

    def _get_offset(self, disc_pid: int) -> int:
        """Pre-fire offset for this channel (how many comments before target to fire)."""
        s = self._ch_stats.get(disc_pid)
        if not s:
            return 2  # default
        # If chat is fast (>2 comments/sec) add +1 to offset automatically
        ts = s.get("comment_ts")
        if ts and len(ts) >= 4:
            recent = list(ts)[-4:]
            span = recent[-1] - recent[0]
            if span > 0:
                rate = 3 / span  # comments/sec
                extra = 1 if rate > 2 else 0
                return min(5, s.get("offset", 2) + extra)
        return s.get("offset", 2)

    def _update_offset(self, disc_pid: int, target: int, actual_pos: int):
        """Adjust offset based on where our message actually landed."""
        if not disc_pid or not target or not actual_pos:
            return
        s = self._ch_stats.setdefault(disc_pid, {"offset": 2, "comment_ts": __import__('collections').deque(maxlen=60)})
        error = actual_pos - target  # >0 we were late, <0 we were early
        old = s.get("offset", 2)
        # Clamp adjustment to ±1 per hunt
        adj = max(-1, min(1, error))
        s["offset"] = max(1, min(5, old + adj))
        logger.info(f"[MultiFC] offset {disc_pid}: {old} → {s['offset']} (target={target} landed={actual_pos})")

    def _record_comment_ts(self, disc_pid: int):
        """Record timestamp of a comment for speed calculation."""
        import collections
        s = self._ch_stats.setdefault(disc_pid, {"offset": 2, "comment_ts": collections.deque(maxlen=60)})
        s["comment_ts"].append(time.time())

    # ── Notification ──────────────────────────────────────────────────────────

    async def _do_final_notify(self, hunt: dict):
        """Send exactly ONE final notification per hunt."""
        # Guard: only one caller wins
        if hunt.get("notify_sent"):
            return
        hunt["notify_sent"] = True
        self._dlog(hunt, "do_final_notify: starting (waiting 3s for msgs to appear)")

        sent = [m for m in hunt.get("sent_msgs", []) if m]
        disc_pid = hunt["disc_pid"]
        targets = set(hunt.get("targets", []))

        # Wait for our messages to appear in history
        await asyncio.sleep(3)
        self._dlog(hunt, f"resolving positions: sent_ids={[m.id for m in sent]} disc_thread_id={hunt.get('disc_thread_id')}")

        positions: Dict[int, int] = {}
        try:
            disc_entity = await self._client.get_entity(disc_pid)
            our_ids = {m.id for m in sent}

            # Get the discussion thread root message id via API
            thread_id = hunt.get("disc_thread_id")
            if not thread_id:
                try:
                    ch_entity = await self._client.get_entity(hunt["ch_pid"])
                    disc_info = await self._client(GetDiscussionMessageRequest(
                        peer=ch_entity,
                        msg_id=hunt["post_id"],
                    ))
                    if disc_info and disc_info.messages:
                        thread_id = disc_info.messages[0].id
                        hunt["disc_thread_id"] = thread_id
                except Exception:
                    thread_id = None

            # Fetch discussion messages
            fetch_kwargs = {"limit": 300}
            if thread_id:
                fetch_kwargs["reply_to"] = thread_id
            history = await self._client.get_messages(disc_entity, **fetch_kwargs)
            msgs_sorted = sorted(list(history), key=lambda m: m.id)

            pos = 0
            for msg in msgs_sorted:
                if getattr(msg, "action", None):
                    continue
                sender = getattr(msg, "sender_id", None) or 0
                if abs(sender) == hunt["ch_pid"]:
                    continue
                pos += 1
                if msg.id in our_ids:
                    positions[msg.id] = pos

            # Debug log positions
            self._dlog(hunt, f"resolve: thread_id={thread_id} total_msgs={len(msgs_sorted)} "
                       f"our_ids={our_ids} positions={positions}")
        except Exception as e:
            logger.error(f"[MultiFC] resolve_positions: {e}")
            self._dlog(hunt, f"resolve ERROR: {e}")

        # Adapt offset using the best (earliest) position we achieved
        if positions and targets:
            best_pos = min(positions.values())
            closest_target = min(targets, key=lambda t: abs(t - best_pos))
            self._dlog(hunt, f"best_pos={best_pos} closest_target={closest_target} → update_offset")
            self._update_offset(disc_pid, closest_target, best_pos)
        else:
            self._dlog(hunt, f"no positions resolved — cannot adapt offset")

        if not sent:
            return

        lines = []
        won_any = False
        for m in sent:
            p = positions.get(m.id)
            link = f"<a href='{self._msg_link(disc_pid, m.id)}'>#{p if p else '?'}</a>"
            won = (p in targets) if p else False
            if won:
                won_any = True
            lines.append(("🏆" if won else "❌") + " " + link)

        close_enough = any(
            abs(p - min(targets, key=lambda t: abs(t - p))) <= 2
            for p in positions.values() if p
        )
        if won_any:
            result = "🏆 Победа!"
        elif close_enough:
            result = "🎯 Почти! (±2 от цели)"
        else:
            result = "😔 Не попал"
        self._dlog(hunt, f"result={result} positions={positions} targets={targets}", "OK" if won_any else "WARN")

        post_safe = hunt["post_text"][:100].replace("<", "&lt;").replace(">", "&gt;")
        text = (
            "🎯 <b>MultiFC — Итог</b>\n\n"
            f"📢 <b>Канал:</b> "
            + (f"<a href='https://t.me/c/{hunt['ch_pid']}/1'>{hunt['ch_title']}</a>" if hunt.get('ch_username') else hunt['ch_title'])
            + "\n"
            f"📝 <b>Пост:</b> <i>{post_safe}</i>\n\n"
            f"🎯 <b>Цели:</b> {', '.join(map(str, sorted(targets)))}\n"
            f"📍 <b>Offset:</b> {self._get_offset(disc_pid)}\n"
            "💬 <b>Сообщения:</b>\n" + "\n".join(lines) + "\n\n"
            f"📊 {result}"
        )
        msg_ids_str = ",".join(str(m.id) for m in sent)
        markup = [[{
            "text": "🗑 Удалить мои",
            "callback": self._cb_del_my_msgs,
            "args": (disc_pid, msg_ids_str),
        }]]
        try:
            await self.inline.bot.send_message(
                self._me.id, text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=self.inline.generate_markup(markup),
            )
            self._dlog(hunt, "final notify sent OK via inline bot")
        except Exception as e:
            logger.error(f"[MultiFC] notify send failed: {e}")
            self._dlog(hunt, f"notify FAIL inline: {e} — trying userbot fallback")
            # Fallback: send via userbot itself (no inline buttons)
            try:
                await self._client.send_message(self._me.id, text, parse_mode="html",
                                                link_preview=False)
            except Exception as e2:
                logger.error(f"[MultiFC] notify fallback failed: {e2}")
                self._dlog(hunt, f"notify fallback FAIL: {e2}")

    def _finish_hunt(self, hunt: dict):
        """Single exit point. Schedules ONE final notification."""
        if hunt.get("finished"):
            return
        hunt["finished"] = True
        self._hunting.pop(hunt["disc_pid"], None)
        elapsed = round(time.time() - hunt.get("started", time.time()), 1)
        self._dlog(hunt, f"hunt finished: sent={len(hunt.get('sent_msgs',[]))} "
                   f"targets={hunt['targets']} done={sorted(hunt['done'])} elapsed={elapsed}s", "OK")
        asyncio.create_task(self._do_final_notify(hunt))

    async def _cb_del_my_msgs(self, call, disc_pid: int, ids_str: str):
        try:
            ids = [int(x) for x in ids_str.split(",") if x.strip().isdigit()]
            entity = await self._client.get_entity(disc_pid)
            await self._client.delete_messages(entity, ids)
            await call.answer("✅ Удалено")
            await call.edit(text=call.message.text + "\n\n<i>🗑 Сообщения удалены</i>")
        except Exception as e:
            await call.answer(f"❌ {e}")

    def _log(self, hunt: dict, ok: bool):
        self._logs.append({
            "ts": time.time(),
            "channel": hunt["ch_title"],
            "ok": ok,
            "count": len(hunt.get("sent_msgs", [])),
            "post": hunt["post_text"][:60],
        })
        self._logs = self._logs[-50:]

    def _dlog(self, hunt_or_label, msg: str, level: str = "INFO"):
        """Rich debug log. Writes to memory + optional file via config dlog_file."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S.") + f"{int((time.time() % 1) * 1000):03d}"
        if isinstance(hunt_or_label, dict):
            ch = hunt_or_label.get("ch_title", "?")[:20]
            pid = hunt_or_label.get("post_id", "?")
            disc = hunt_or_label.get("disc_pid", "?")
            post_snip = hunt_or_label.get("post_text", "")[:50].replace("\n", " ").strip()
            label = f"[{ch}|post={pid}|disc={disc}|text='{post_snip}']"
        else:
            label = f"[{hunt_or_label}]"
        lvl_str = {"INFO": "INF", "FIRE": "FIR", "OK": " OK", "ERR": "ERR", "WARN": "WRN"}.get(level, level[:3])
        line = f"{ts} [{lvl_str}] {label} {msg}"
        if level == "ERR":
            logger.error(f"[MultiFC] {label} {msg}")
        else:
            logger.debug(f"[MultiFC] {line}")
        self._dlogs.append(line)
        if len(self._dlogs) > 1000:
            self._dlogs = self._dlogs[-1000:]
        # File output
        dlog_file = self.config.get("dlog_file", "").strip() if hasattr(self, "config") else ""
        if dlog_file:
            try:
                with open(dlog_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    @loader.watcher()
    async def watcher(self, message: Message):
        if self._paused or not self.config["status"]:
            return

        cid = self._pid(utils.get_chat_id(message))

        # Channel post → start hunt
        if getattr(message, "post", False) and not getattr(message, "is_group", False):
            if cid in self._monitored:
                asyncio.create_task(self._on_post(message))
            return

        # Discussion comment → real-time trigger
        hunt = self._hunting.get(cid)
        if not hunt or hunt.get("finished"):
            return
        sender = getattr(message, "sender_id", None) or 0
        if sender == self._me.id:
            return
        if abs(sender) == hunt["ch_pid"]:
            return
        if getattr(message, "action", None):
            return

        # Record timestamp for speed tracking
        self._record_comment_ts(cid)
        # Immediately check if we should fire (using real API count)
        asyncio.create_task(self._check_and_fire(hunt))

    # ── Core firing logic ─────────────────────────────────────────────────────

    async def _get_real_count(self, ch_entity, post_id: int) -> int:
        """Get authoritative comment count."""
        try:
            msg = await self._client.get_messages(ch_entity, ids=post_id)
            if msg and getattr(msg, "replies", None):
                return msg.replies.replies or 0
        except Exception:
            pass
        return 0

    async def _check_and_fire(self, hunt: dict):
        """
        Get real comment count → fire if we've entered the firing window.
        Firing window: target - offset  (adaptive per channel)
        Sends cfg["spam_count"] messages.
        Called by both watcher (per comment) and poll_sync (periodic).
        """
        if hunt.get("finished"):
            return
        # Retry up to 3 times on network error
        real_count = -1
        latency = 0.0
        for attempt in range(3):
            try:
                ch_entity = await self._client.get_entity(hunt["ch_pid"])
                t0 = time.time()
                real_count = await self._get_real_count(ch_entity, hunt["post_id"])
                latency = time.time() - t0
                break
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(0.3 * (attempt + 1))
                else:
                    self._dlog(hunt, f"_check_and_fire: get_count failed after 3 attempts: {e}", "ERR")
                    return
        import collections as _col
        s = self._ch_stats.setdefault(hunt["disc_pid"], {"offset": 2, "comment_ts": _col.deque(maxlen=60)})
        s["last_latency"] = latency

        async with hunt["lock"]:
            if hunt.get("finished"):
                return
            remaining = [t for t in hunt["targets"] if t not in hunt["done"]]
            if not remaining:
                self._finish_hunt(hunt)
                return

            next_t = remaining[0]
            offset = self._get_offset(hunt["disc_pid"])
            fire_at = max(0, next_t - offset)

            self._dlog(hunt, f"check: real={real_count} target={next_t} fire_at={fire_at} offset={offset}")

            if real_count < fire_at:
                return  # not yet in window

            # Claim this target — inside lock so only one caller fires
            hunt["done"].add(next_t)
            self._dlog(hunt, f"FIRE target={next_t} real_count={real_count}")

        # Fire outside lock
        msgs = await self._spam(hunt)
        if msgs:
            hunt["sent_msgs"].extend(msgs)
            self._dlog(hunt, f"sent {len(msgs)} msgs: ids={[m.id for m in msgs]}")
            self._log(hunt, True)

        async with hunt["lock"]:
            if not [t for t in hunt["targets"] if t not in hunt["done"]]:
                self._finish_hunt(hunt)

    async def _poll_sync(self, hunt: dict):
        """
        Periodic backup + speed-adaptive polling.
        Calls _check_and_fire. Adapts interval by proximity to next target.
        """
        import collections
        try:
            ch_entity = await self._client.get_entity(hunt["ch_pid"])
        except Exception as e:
            logger.error(f"[MultiFC] poll entity: {e}")
            return

        timeout = 600
        interval = 2.0

        while not hunt.get("finished"):
            if time.time() - hunt["started"] > timeout:
                self._finish_hunt(hunt)
                break

            if self._paused or not self.config["status"]:
                await asyncio.sleep(2)
                continue

            await asyncio.sleep(interval)
            if hunt.get("finished"):
                break

            # Get count for interval adaptation
            try:
                real_count = await self._get_real_count(ch_entity, hunt["post_id"])
            except Exception:
                continue

            remaining = [t for t in hunt["targets"] if t not in hunt["done"]]
            if not remaining:
                self._finish_hunt(hunt)
                break

            next_t = remaining[0]
            offset = self._get_offset(hunt["disc_pid"])
            fire_at = max(0, next_t - offset)
            dist = fire_at - real_count

            # Adaptive interval: closer to target → poll faster
            if dist > 50:
                interval = 4.0
            elif dist > 20:
                interval = 2.0
            elif dist > 10:
                interval = 1.0
            elif dist > 3:
                interval = 0.5
            else:
                interval = 0.2

            await self._check_and_fire(hunt)

    async def _on_post(self, message: Message):
        try:
            if hasattr(message, "media") and message.media:
                if "paid" in type(message.media).__name__.lower():
                    return

            ch_pid = self._pid(utils.get_chat_id(message))
            cfg = self._chan_cfg(ch_pid)
            if not cfg["enabled"]:
                return

            text = message.raw_text or ""

            # Skip results/winner announcement posts
            # Skip results/winner posts
            _skip = re.search(
                r"(?:результат|итоги|победители|завершён|поздравляем)[^\S\r\n]{0,20}(?:розыгрыш|победител|конкурс)",
                text, re.IGNORECASE
            )
            if _skip:
                self._dlog(f"post:{message.id}", "SKIP: results/winners post")
                return
            if not self._match_triggers(text, cfg):
                return

            # Deduplicate per post
            post_key = (ch_pid, message.id)
            now = time.time()
            if self._fired.get(post_key, 0) > now - 120:
                return
            self._fired[post_key] = now
            if len(self._fired) > 500:
                for k, _ in sorted(self._fired.items(), key=lambda x: x[1])[:200]:
                    del self._fired[k]

            info = _analyze(text)
            self._dlog(f"post:{message.id}", f"trigger matched | ch={ch_title!r}")
            self._dlog(f"post:{message.id}", f"POST TEXT: {text[:200]!r}")
            skip = info.get('_skip_reason')
            if skip:
                self._dlog(f"post:{message.id}", f"SKIP: {skip}", "WARN")
                return
            self._dlog(f"post:{message.id}", f"analyze → targets={info['targets']} first_n={info['is_first_n']} fn_count={info['first_n']} req={info.get('required_text')!r}")

            disc_pid = await self._get_discussion(ch_pid)
            if disc_pid is None:
                self._dlog(f"post:{message.id}", "no discussion group found — skip")
                return

            if self.config["auto_join"]:
                await self._ensure_joined(disc_pid)

            if cfg["delay"] > 0:
                await asyncio.sleep(cfg["delay"])

            ch_title = await self._get_title(ch_pid)
            try:
                _ch_ent = await self._client.get_entity(ch_pid)
                ch_username = getattr(_ch_ent, "username", None)
            except Exception:
                ch_username = None

            # Resolve disc_thread_id now so notify works later
            disc_thread_id = None
            try:
                ch_entity_tmp = await self._client.get_entity(ch_pid)
                disc_info = await self._client(GetDiscussionMessageRequest(
                    peer=ch_entity_tmp,
                    msg_id=message.id,
                ))
                if disc_info and disc_info.messages:
                    disc_thread_id = disc_info.messages[0].id
            except Exception:
                pass

            hunt = {
                "ch_pid": ch_pid,
                "ch_title": ch_title,
                "ch_username": ch_username,
                "ch_peer": message.peer_id,
                "post_id": message.id,
                "post_text": text[:400],
                "disc_pid": disc_pid,
                "disc_thread_id": disc_thread_id,
                "targets": sorted(info["targets"]),
                "required_text": info.get("required_text"),
                "is_first_n": info.get("is_first_n", False),
                "first_n": info.get("first_n", 1),
                "cfg": cfg,
                "sent_msgs": [],
                "done": set(),
                "started": time.time(),
                "finished": False,
                "notify_sent": False,
                "lock": asyncio.Lock(),
            }

            # Kill any previous hunt on this discussion
            old = self._hunting.get(disc_pid)
            if old:
                self._finish_hunt(old)
            self._hunting[disc_pid] = hunt

            first_target = hunt["targets"][0] if hunt["targets"] else 1

            # ── Target == 1 or first-N: fire immediately ─────────────────────
            if hunt["is_first_n"] or first_target == 1:
                self._dlog(hunt, f"IMMEDIATE FIRE: is_first_n={hunt['is_first_n']} target={first_target} fn_count={hunt['first_n']}", "FIRE")
                hunt["done"].add(first_target)
                msgs = await self._spam(hunt)
                if msgs:
                    hunt["sent_msgs"].extend(msgs)
                    self._log(hunt, True)
                    self._dlog(hunt, f"sent {len(msgs)} msgs immediately ids={[m.id for m in msgs]}", "OK")
                else:
                    self._dlog(hunt, "spam() returned 0 messages", "WARN")

                remaining = [t for t in hunt["targets"] if t not in hunt["done"]]
                if not remaining:
                    self._finish_hunt(hunt)
                    return
                self._dlog(hunt, f"remaining after immediate fire: {remaining}")
                asyncio.create_task(self._poll_sync(hunt))

            else:
                self._dlog(hunt, f"starting poll for target={first_target} offset={self._get_offset(hunt['disc_pid'])}")
                asyncio.create_task(self._poll_sync(hunt))

                asyncio.create_task(self._poll_sync(hunt))

        except Exception as e:
            logger.error(f"[MultiFC] _on_post: {e}", exc_info=True)


    # ── Commands ──────────────────────────────────────────────────────────────

    @loader.command(ru_doc="Статус модуля")
    async def mfc(self, message: Message):
        """MultiFC status"""
        await self._reload_channels()
        if not self.config["status"]:
            s = "🔴 Выключен"
        elif self._paused:
            s = "⏸ Пауза"
        else:
            s = "🟢 Активен"
        await utils.answer(
            message,
            self.strings["status"].format(
                status=s,
                channels=len(self._monitored),
                hunting=len(self._hunting),
                folder=self.config["folder_name"] or "не задана",
                ai=self.config["ai_provider"],
                trigs=len(self._get_triggers()),
            ),
        )

    @loader.command(ru_doc="Приостановить")
    async def mfcpause(self, message: Message):
        """Pause MultiFC"""
        self._paused = True
        await utils.answer(message, self.strings["paused"])

    @loader.command(ru_doc="Возобновить")
    async def mfcresume(self, message: Message):
        """Resume MultiFC"""
        self._paused = False
        await utils.answer(message, self.strings["resumed"])

    @loader.command(ru_doc="[username/ID] Добавить канал")
    async def mfcadd(self, message: Message):
        """[username/ID] Add channel"""
        args = utils.get_args_raw(message).strip()
        try:
            if args:
                ref = int(args) if args.lstrip("-").isdigit() else args
                entity = await self._client.get_entity(ref)
            else:
                entity = await message.get_chat()
            if not getattr(entity, "broadcast", False):
                await utils.answer(message, "<b>❌ Это не канал</b>")
                return
            title = getattr(entity, "title", str(entity.id))
            cid_str = str(entity.id)
        except Exception as e:
            await utils.answer(message, f"<b>❌ Ошибка:</b> <code>{e}</code>")
            return

        chs = self.db.get("MultiFC", "channels", {})
        if cid_str in chs:
            await utils.answer(message, self.strings["ch_exists"])
            return
        username = getattr(entity, "username", None)
        chs[cid_str] = {"title": title, "enabled": True, "username": username or ""}
        self.db.set("MultiFC", "channels", chs)
        self._monitored.add(self._pid(entity.id))
        await utils.answer(message, self.strings["ch_added"].format(title=title, id=entity.id))

    @loader.command(ru_doc="[username/ID] Удалить канал")
    async def mfcdel(self, message: Message):
        """[username/ID] Remove channel"""
        args = utils.get_args_raw(message).strip()
        try:
            if args:
                ref = int(args) if args.lstrip("-").isdigit() else args
                entity = await self._client.get_entity(ref)
            else:
                entity = await message.get_chat()
            title = getattr(entity, "title", str(entity.id))
            cid_str = str(entity.id)
        except Exception as e:
            await utils.answer(message, f"<b>❌ Ошибка:</b> <code>{e}</code>")
            return

        chs = self.db.get("MultiFC", "channels", {})
        if cid_str not in chs:
            await utils.answer(message, self.strings["ch_not_found"])
            return
        del chs[cid_str]
        self.db.set("MultiFC", "channels", chs)
        self._monitored.discard(self._pid(entity.id))
        await utils.answer(message, self.strings["ch_removed"].format(title=title))

    async def _all_channels(self):
        """Return combined list of (cid_str, title, enabled, from_folder) for all channels."""
        result = []
        chs = self.db.get("MultiFC", "channels", {})
        for cid, data in chs.items():
            result.append({
                "id": cid,
                "title": data.get("title", cid),
                "enabled": data.get("enabled", True),
                "folder": False,
                "username": data.get("username", ""),
            })
        folder = self.config["folder_name"]
        if folder:
            fch = await self._folder_channels(folder)
            if fch:
                manual_ids = set(chs.keys())
                for ch in fch:
                    cid = str(ch.id)
                    if cid not in manual_ids:
                        result.append({
                            "id": cid,
                            "title": getattr(ch, "title", cid),
                            "enabled": True,
                            "folder": True,
                            "username": getattr(ch, "username", "") or "",
                        })
        return result

    @loader.command(ru_doc="Список каналов")
    async def mfclist(self, message: Message):
        """Show monitored channels"""
        await self._reload_channels()
        channels = await self._all_channels()
        if not channels:
            await utils.answer(message, self.strings["no_channels"])
            return
        text = f"<b>🎯 MultiFC — Каналы</b> ({len(channels)} шт.)\n\n"
        for ch in channels:
            icon = "🟢" if ch["enabled"] else "🔴"
            src = "📁" if ch["folder"] else "📌"
            uname = f" @{ch['username']}" if ch.get("username") else ""
            text += f"{src}{icon} <b>{ch['title']}</b>{uname}\n  <code>{ch['id']}</code>\n"
        await utils.answer(message, text)

    @loader.command(ru_doc="Обновить каналы из папки")
    async def mfcfolder(self, message: Message):
        """Reload folder channels"""
        folder = self.config["folder_name"]
        if not folder:
            await utils.answer(message, self.strings["no_folder"])
            return
        chs = await self._folder_channels(folder)
        if chs is None:
            await utils.answer(message, self.strings["folder_not_found"].format(name=folder))
            return
        await self._reload_channels()
        text = f"<b>📁 Папка «{folder}»</b> — {len(chs)} канал(ов)\n\n"
        for ch in chs:
            text += f"  📢 <b>{getattr(ch, 'title', '?')}</b> <code>{ch.id}</code>\n"
        await utils.answer(message, text)

    @loader.command(ru_doc="Управление глобал триггерами")
    async def mfctrig(self, message: Message):
        """Manage global triggers. .mfctrig help"""
        args = utils.get_args_raw(message).strip()
        if not args or args == "help":
            await utils.answer(message, self.strings["trig_help"])
            return

        parts = args.split(maxsplit=1)
        cmd = parts[0].lower()
        val = parts[1].strip() if len(parts) > 1 else ""
        trigs = list(self._get_triggers())

        if cmd == "list":
            if not trigs:
                await utils.answer(message, "📋 Триггеров нет (реагирую на все посты)")
                return
            text = f"<b>🎯 Триггеры ({len(trigs)}):</b>\n\n"
            for i, t in enumerate(trigs, 1):
                text += f"<b>{i}.</b> <code>{t[:120]}</code>\n"
            await utils.answer(message, text)

        elif cmd == "add":
            if not val:
                await utils.answer(message, "<b>❌ Укажи триггер(ы) — по одному на строку</b>")
                return
            # Support multiline: each non-empty line is a separate trigger
            # Support both real newlines and literal \\n in args
            raw_lines = val.replace("\\n", "\n").splitlines()
            new_trigs = [line.strip() for line in raw_lines if line.strip()]
            if not new_trigs:
                await utils.answer(message, "<b>❌ Пустой ввод</b>")
                return
            # Validate regex patterns
            added, bad = [], []
            for t in new_trigs:
                try:
                    re.compile(t, re.IGNORECASE)
                    trigs.append(t)
                    added.append(t)
                except re.error as e:
                    bad.append(f"<code>{t[:60]}</code> — {e}")
            if added:
                self.db.set("MultiFC", "triggers", trigs)
            lines_out = []
            if added:
                lines_out.append(f"✅ Добавлено {len(added)} триггер(ов):")
                for t in added:
                    lines_out.append(f"  • <code>{t[:80]}</code>")
            if bad:
                lines_out.append(f"❌ Ошибки ({len(bad)}):")
                lines_out.extend(bad)
            await utils.answer(message, "\n".join(lines_out))

        elif cmd == "del":
            try:
                idx = int(val) - 1
                removed = trigs.pop(idx)
                self.db.set("MultiFC", "triggers", trigs)
                await utils.answer(message, f"✅ Удалён: <code>{removed[:80]}</code>")
            except (ValueError, IndexError):
                await utils.answer(message, "<b>❌ Укажи правильный номер из списка</b>")

        elif cmd == "reset":
            self.db.set("MultiFC", "triggers", DEFAULT_TRIGGERS)
            await utils.answer(message, f"✅ Сброшено к дефолтным ({len(DEFAULT_TRIGGERS)} триггеров)")

        elif cmd == "clear":
            self.db.set("MultiFC", "triggers", [])
            await utils.answer(message, "✅ Очищено — реагирую на все посты в каналах")

        else:
            await utils.answer(message, self.strings["trig_help"])

    @loader.command(ru_doc="[id/@] <param> <value> — настройки канала")
    async def mfcchan(self, message: Message):
        """Per-channel settings. .mfcchan help"""
        raw = utils.get_args_raw(message).strip()
        if not raw or raw == "help":
            await utils.answer(message, self.strings["chan_help"])
            return

        parts = raw.split(maxsplit=2)
        cid_str = None
        pi = 0

        first = parts[0]
        if first.lstrip("-").isdigit() or first.startswith("@"):
            try:
                ref = int(first) if first.lstrip("-").isdigit() else first
                e = await self._client.get_entity(ref)
                cid_str = str(e.id)
                pi = 1
            except Exception:
                pass

        if cid_str is None:
            try:
                chat = await message.get_chat()
                cid_str = str(chat.id)
            except Exception:
                await utils.answer(message, "<b>❌ Не могу определить канал</b>")
                return

        rest = parts[pi:]
        if not rest:
            await utils.answer(message, self.strings["chan_help"])
            return

        param = rest[0]
        value = rest[1] if len(rest) > 1 else ""
        chs = self.db.get("MultiFC", "channels", {})

        if param == "info":
            ch = chs.get(cid_str, {})
            t = ch.get("title", cid_str)
            text = (
                f"<b>⚙️ {t}</b> <code>{cid_str}</code>\n\n"
                f"enabled: <code>{ch.get('enabled', True)}</code>\n"
                f"delay: <code>{ch.get('delay', self.config['global_delay'])}</code>\n"
                f"spam_count: <code>{ch.get('spam_count', self.config['spam_count'])}</code>\n"
                f"use_ai: <code>{ch.get('use_ai', False)}</code>\n"
                f"lock_global: <code>{ch.get('lock_global', False)}</code>\n"
                f"only_triggers: <code>{ch.get('only_triggers', False)}</code>\n"
                f"only_msgs: <code>{ch.get('only_msgs', False)}</code>\n"
                f"custom_triggers: <code>{ch.get('custom_triggers', [])}</code>\n"
                f"custom_messages: <code>{ch.get('custom_messages', [])}</code>"
            )
            await utils.answer(message, text)
            return

        if cid_str not in chs:
            await utils.answer(message, self.strings["ch_not_found"])
            return

        ch = chs[cid_str]
        BOOL = {"enabled", "use_ai", "only_triggers", "only_msgs", "lock_global"}
        FLOAT = {"delay", "spam_interval"}
        INT = {"spam_count"}

        if param in BOOL:
            ch[param] = value.lower() in ("true", "1", "yes", "да")
            await utils.answer(message, f"✅ <b>{param}</b> = <code>{ch[param]}</code>")
        elif param in FLOAT:
            try:
                ch[param] = float(value)
                await utils.answer(message, f"✅ <b>{param}</b> = <code>{ch[param]}</code>")
            except ValueError:
                await utils.answer(message, "<b>❌ Нужно число</b>")
                return
        elif param in INT:
            try:
                ch[param] = int(value)
                await utils.answer(message, f"✅ <b>{param}</b> = <code>{ch[param]}</code>")
            except ValueError:
                await utils.answer(message, "<b>❌ Нужно целое число</b>")
                return
        elif param == "add_trigger":
            ch.setdefault("custom_triggers", []).append(value)
            await utils.answer(message, f"✅ Триггер добавлен: <code>{value}</code>")
        elif param == "del_trigger":
            lst = ch.get("custom_triggers", [])
            if value in lst:
                lst.remove(value)
                ch["custom_triggers"] = lst
                await utils.answer(message, "✅ Триггер удалён")
            else:
                await utils.answer(message, "<b>❌ Триггер не найден</b>")
                return
        elif param == "add_msg":
            ch.setdefault("custom_messages", []).append(value)
            await utils.answer(message, f"✅ Сообщение добавлено: <code>{value}</code>")
        elif param == "del_msg":
            lst = ch.get("custom_messages", [])
            if value in lst:
                lst.remove(value)
                ch["custom_messages"] = lst
                await utils.answer(message, "✅ Сообщение удалено")
            else:
                await utils.answer(message, "<b>❌ Сообщение не найдено</b>")
                return
        else:
            await utils.answer(message, f"<b>❌ Неизвестный параметр:</b> <code>{param}</code>")
            return

        chs[cid_str] = ch
        self.db.set("MultiFC", "channels", chs)

    @loader.command(ru_doc="Последние события")
    async def mfclogs(self, message: Message):
        """Last hunt events"""
        if not self._logs:
            await utils.answer(message, self.strings["log_empty"])
            return
        text = "<b>📋 MultiFC — Логи</b>\n\n"
        for e in reversed(self._logs[-20:]):
            t = time.strftime("%H:%M", time.localtime(e["ts"]))
            icon = "✅" if e["ok"] else "❌"
            text += (
                f"{icon} <code>{t}</code> <b>{e['channel']}</b>\n"
                f"   {e['count']} сообщ. | <i>{e['post'][:50]}</i>\n\n"
            )
        await utils.answer(message, text)

    @loader.command(ru_doc="Детальный лог. .mfcdlog [N] [clear] [hunt]")
    async def mfcdlog(self, message: Message):
        """Detailed debug log. .mfcdlog [N=60] | .mfcdlog clear | .mfcdlog hunt"""
        args = utils.get_args_raw(message).strip().lower()

        if args == "clear":
            n_before = len(self._dlogs)
            self._dlogs.clear()
            await utils.answer(message, f"🗑 Debug-лог очищен ({n_before} записей удалено)")
            return

        if args == "hunt" or args == "hunts":
            # Show only hunt-related lines
            hunt_lines = [l for l in self._dlogs if "FIRE" in l or "targets=" in l
                         or "sent" in l and "msgs" in l or "result=" in l
                         or "hunt finished" in l or "analyze" in l]
            if not hunt_lines:
                await utils.answer(message, "📋 Нет hunt-событий в логе")
                return
            body = "\n".join(f"<code>{l}</code>" for l in hunt_lines[-40:])
            await utils.answer(message, f"<b>🎯 Hunt-события ({len(hunt_lines)} шт.):</b>\n\n{body}")
            return

        try:
            n = int(args) if args else 60
        except ValueError:
            n = 60
        n = max(10, min(n, 300))

        if not self._dlogs:
            await utils.answer(message, "📋 Debug-лог пуст — ещё ни одного события")
            return

        selected = self._dlogs[-n:]
        header = (
            f"<b>🔍 MultiFC Debug-лог</b>\n"
            f"Показано: {len(selected)}/{len(self._dlogs)} • "
            f"Активных охот: {len(self._hunting)}\n"
            f"<i>.mfcdlog N</i> | <i>.mfcdlog hunt</i> | <i>.mfcdlog clear</i>\n"
        )

        # Split into Telegram-safe chunks (4096 chars max)
        chunks = []
        cur = []
        cur_len = 0
        for line in selected:
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            entry = f"<code>{safe}</code>\n"
            if cur_len + len(entry) > 3600:
                chunks.append(cur)
                cur = [entry]
                cur_len = len(entry)
            else:
                cur.append(entry)
                cur_len += len(entry)
        if cur:
            chunks.append(cur)

        for idx, ch in enumerate(chunks):
            text = (header if idx == 0 else "") + "".join(ch)
            if idx == 0:
                await utils.answer(message, text.strip())
            else:
                await message.respond(text.strip())

    @loader.command(ru_doc="Лог в файл. .mfcdlogfile [путь] | .mfcdlogfile off")
    async def mfcdlogfile(self, message: Message):
        """Toggle debug log to file. .mfcdlogfile /path/log.txt | off"""
        args = utils.get_args_raw(message).strip()
        if not args or args.lower() == "off":
            self._dlog_path = None
            await utils.answer(message, "🔕 Лог в файл выключен")
            return
        self._set_dlog_file(args)
        await utils.answer(message, f"📄 Лог пишется в <code>{args}</code>\n"
                           f"<i>.mfcdlogfile off</i> — выключить")

    # ── Inline Panel ──────────────────────────────────────────────────────────

    def _panel_main_markup(self):
        s = "⏸ Пауза" if self._paused else ("🟢 Вкл" if self.config["status"] else "🔴 Выкл")
        return [
            [
                {"text": f"{'▶️ Продолжить' if self._paused else '⏸ Пауза'}", "callback": self._cb_toggle_pause},
                {"text": "🔄 Обновить", "callback": self._cb_refresh_main},
            ],
            [
                {"text": "📋 Каналы", "callback": self._cb_channels_page},
                {"text": "🎯 Триггеры", "callback": self._cb_triggers_page},
            ],
            [
                {"text": "📊 Логи", "callback": self._cb_logs_page},
            ],
        ]

    def _panel_main_text(self):
        if not self.config["status"]:
            s = "🔴 Выключен"
        elif self._paused:
            s = "⏸ Пауза"
        else:
            s = "🟢 Активен"
        return self.strings["panel_main"].format(
            status=s,
            ai=self.config["ai_provider"],
            channels=len(self._monitored),
            hunting=len(self._hunting),
            folder=self.config["folder_name"] or "не задана",
            trigs=len(self._get_triggers()),
        )

    @loader.command(ru_doc="Открыть панель управления")
    async def mfcp(self, message: Message):
        """Open MultiFC inline panel"""
        await self._reload_channels()
        await self.inline.form(
            message=message,
            text=self._panel_main_text(),
            reply_markup=self._panel_main_markup(),
        )

    async def _cb_refresh_main(self, call):
        await self._reload_channels()
        await call.edit(
            text=self._panel_main_text(),
            reply_markup=self._panel_main_markup(),
        )

    async def _cb_toggle_pause(self, call):
        self._paused = not self._paused
        await call.answer("⏸ Пауза" if self._paused else "▶️ Продолжил")
        await call.edit(
            text=self._panel_main_text(),
            reply_markup=self._panel_main_markup(),
        )

    async def _cb_channels_page(self, call, page: int = 0):
        channels = await self._all_channels()
        per = 5
        total = len(channels)
        pages = max(1, (total + per - 1) // per)
        page = max(0, min(page, pages - 1))
        chunk = channels[page * per: page * per + per]

        if not chunk:
            await call.answer("Каналов нет")
            return

        text = self.strings["panel_channels"].format(count=total)
        text += f" — стр. {page + 1}/{pages}\n\n"
        for ch in chunk:
            icon = "🟢" if ch["enabled"] else "🔴"
            src = "📁" if ch["folder"] else "📌"
            uname = f" @{ch['username']}" if ch.get("username") else ""
            text += f"{src}{icon} <b>{ch['title']}</b>{uname}\n<code>{ch['id']}</code>\n\n"

        btns = []
        # Per-channel buttons
        for ch in chunk:
            btns.append([{
                "text": f"⚙️ {ch['title'][:20]}",
                "callback": self._cb_chan_detail,
                "args": (ch["id"],),
            }])

        nav = []
        if page > 0:
            nav.append({"text": "◀️", "callback": self._cb_channels_page, "args": (page - 1,)})
        if page < pages - 1:
            nav.append({"text": "▶️", "callback": self._cb_channels_page, "args": (page + 1,)})
        if nav:
            btns.append(nav)
        btns.append([{"text": "🔙 Назад", "callback": self._cb_refresh_main}])

        await call.edit(text=text, reply_markup=btns)

    async def _cb_chan_detail(self, call, cid: str):
        chs = self.db.get("MultiFC", "channels", {})
        ch = chs.get(cid, {})
        in_db = bool(ch)

        title = ch.get("title", cid) if in_db else cid
        enabled = ch.get("enabled", True)
        delay = ch.get("delay", self.config["global_delay"])
        spam = ch.get("spam_count", self.config["spam_count"])
        use_ai = ch.get("use_ai", False)
        only_t = ch.get("only_triggers", False)
        only_m = ch.get("only_msgs", False)
        lock_g = ch.get("lock_global", False)
        c_trigs = ch.get("custom_triggers", [])
        c_msgs = ch.get("custom_messages", [])

        text = (
            f"⚙️ <b>{title}</b>\n<code>{cid}</code>\n\n"
            f"Статус: {'🟢 Вкл' if enabled else '🔴 Выкл'}\n"
            f"Задержка: <code>{delay}s</code>\n"
            f"Спам: <code>{spam}x</code>\n"
            f"AI: {'✅' if use_ai else '❌'}\n"
            f"Только свои тригеры: {'✅' if only_t else '❌'}\n"
            f"Только свои сообщения: {'✅' if only_m else '❌'}\n"
            f"Заморозить глобальные: {'✅' if lock_g else '❌'}\n"
            f"Своих триггеров: <b>{len(c_trigs)}</b>\n"
            f"Своих сообщений: <b>{len(c_msgs)}</b>"
        )

        btns = []
        if in_db:
            # Row 1: toggle + AI
            toggle_txt = "🔴 Выкл" if enabled else "🟢 Вкл"
            ai_txt = "🤖 AI: выкл" if use_ai else "🤖 AI: вкл"
            btns.append([
                {"text": toggle_txt, "callback": self._cb_chan_toggle, "args": (cid,)},
                {"text": ai_txt, "callback": self._cb_chan_ai, "args": (cid,)},
            ])
            # Row 2: flags
            btns.append([
                {"text": f"{'✅' if only_t else '☑️'} Свои тригеры", "callback": self._cb_chan_flag, "args": (cid, "only_triggers")},
                {"text": f"{'✅' if only_m else '☑️'} Свои сообщения", "callback": self._cb_chan_flag, "args": (cid, "only_msgs")},
            ])
            btns.append([
                {"text": f"{'✅' if lock_g else '☑️'} Заморозить глобал", "callback": self._cb_chan_flag, "args": (cid, "lock_global")},
            ])
            # Row 3: spam count
            btns.append([
                {"text": f"📨 Спам: {spam}x  ➖", "callback": self._cb_chan_spam, "args": (cid, -1)},
                {"text": "➕", "callback": self._cb_chan_spam, "args": (cid, 1)},
            ])
            # Row 4: delay
            btns.append([
                {"text": f"⏱ Задержка: {delay}s  ➖", "callback": self._cb_chan_delay, "args": (cid, -0.5)},
                {"text": "➕", "callback": self._cb_chan_delay, "args": (cid, 0.5)},
            ])
            # Row 5: custom triggers list
            if c_trigs:
                btns.append([{"text": f"🎯 Свои триггеры ({len(c_trigs)})", "callback": self._cb_chan_trigs, "args": (cid,)}])
            # Row 6: custom messages list
            if c_msgs:
                btns.append([{"text": f"💬 Свои сообщения ({len(c_msgs)})", "callback": self._cb_chan_msgs, "args": (cid,)}])
            # Row 7: delete
            btns.append([{"text": "🗑 Удалить канал", "callback": self._cb_chan_remove, "args": (cid,)}])
        btns.append([{"text": "🔙 Каналы", "callback": self._cb_channels_page}])

        await call.edit(text=text, reply_markup=btns)

    async def _cb_chan_ai(self, call, cid: str):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            chs[cid]["use_ai"] = not chs[cid].get("use_ai", False)
            self.db.set("MultiFC", "channels", chs)
            await call.answer("🤖 AI " + ("вкл" if chs[cid]["use_ai"] else "выкл"))
        await self._cb_chan_detail(call, cid)

    async def _cb_chan_flag(self, call, cid: str, flag: str):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            chs[cid][flag] = not chs[cid].get(flag, False)
            self.db.set("MultiFC", "channels", chs)
            await call.answer("✅ " + flag + " = " + str(chs[cid][flag]))
        await self._cb_chan_detail(call, cid)

    async def _cb_chan_spam(self, call, cid: str, delta: int):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            cur = chs[cid].get("spam_count", self.config["spam_count"])
            new = max(1, min(10, cur + delta))
            chs[cid]["spam_count"] = new
            self.db.set("MultiFC", "channels", chs)
            await call.answer(f"📨 Спам: {new}x")
        await self._cb_chan_detail(call, cid)

    async def _cb_chan_delay(self, call, cid: str, delta: float):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            cur = chs[cid].get("delay", self.config["global_delay"])
            new = round(max(0.0, cur + delta), 1)
            chs[cid]["delay"] = new
            self.db.set("MultiFC", "channels", chs)
            await call.answer(f"⏱ Задержка: {new}s")
        await self._cb_chan_detail(call, cid)

    async def _cb_chan_trigs(self, call, cid: str, page: int = 0):
        chs = self.db.get("MultiFC", "channels", {})
        ch = chs.get(cid, {})
        trigs = ch.get("custom_triggers", [])
        per = 4
        pages = max(1, (len(trigs) + per - 1) // per)
        page = max(0, min(page, pages - 1))
        chunk = trigs[page * per: page * per + per]
        start = page * per

        text = f"<b>🎯 Свои триггеры — {ch.get('title', cid)}</b> ({len(trigs)})\n\n"
        for i, t in enumerate(chunk, start + 1):
            text += f"<b>{i}.</b> <code>{t[:80]}</code>\n\n"

        btns = []
        for i, _ in enumerate(chunk):
            btns.append([{"text": f"🗑 #{start+i+1}", "callback": self._cb_chan_trig_del, "args": (cid, start+i)}])
        nav = []
        if page > 0:
            nav.append({"text": "◀️", "callback": self._cb_chan_trigs, "args": (cid, page-1)})
        if page < pages - 1:
            nav.append({"text": "▶️", "callback": self._cb_chan_trigs, "args": (cid, page+1)})
        if nav:
            btns.append(nav)
        btns.append([{"text": "🔙 Назад", "callback": self._cb_chan_detail, "args": (cid,)}])
        await call.edit(text=text, reply_markup=btns)

    async def _cb_chan_trig_del(self, call, cid: str, idx: int):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            lst = chs[cid].get("custom_triggers", [])
            if 0 <= idx < len(lst):
                lst.pop(idx)
                chs[cid]["custom_triggers"] = lst
                self.db.set("MultiFC", "channels", chs)
                await call.answer(f"✅ Удалён #{idx+1}")
        await self._cb_chan_trigs(call, cid)

    async def _cb_chan_msgs(self, call, cid: str, page: int = 0):
        chs = self.db.get("MultiFC", "channels", {})
        ch = chs.get(cid, {})
        msgs = ch.get("custom_messages", [])
        per = 5
        pages = max(1, (len(msgs) + per - 1) // per)
        page = max(0, min(page, pages - 1))
        chunk = msgs[page * per: page * per + per]
        start = page * per

        text = f"<b>💬 Свои сообщения — {ch.get('title', cid)}</b> ({len(msgs)})\n\n"
        for i, m in enumerate(chunk, start + 1):
            text += f"<b>{i}.</b> <code>{m[:60]}</code>\n"

        btns = []
        for i, _ in enumerate(chunk):
            btns.append([{"text": f"🗑 #{start+i+1}", "callback": self._cb_chan_msg_del, "args": (cid, start+i)}])
        nav = []
        if page > 0:
            nav.append({"text": "◀️", "callback": self._cb_chan_msgs, "args": (cid, page-1)})
        if page < pages - 1:
            nav.append({"text": "▶️", "callback": self._cb_chan_msgs, "args": (cid, page+1)})
        if nav:
            btns.append(nav)
        btns.append([{"text": "🔙 Назад", "callback": self._cb_chan_detail, "args": (cid,)}])
        await call.edit(text=text, reply_markup=btns)

    async def _cb_chan_msg_del(self, call, cid: str, idx: int):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            lst = chs[cid].get("custom_messages", [])
            if 0 <= idx < len(lst):
                lst.pop(idx)
                chs[cid]["custom_messages"] = lst
                self.db.set("MultiFC", "channels", chs)
                await call.answer(f"✅ Удалено #{idx+1}")
        await self._cb_chan_msgs(call, cid)

    async def _cb_chan_toggle(self, call, cid: str):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            chs[cid]["enabled"] = not chs[cid].get("enabled", True)
            self.db.set("MultiFC", "channels", chs)
            state = "🟢 Включён" if chs[cid]["enabled"] else "🔴 Выключен"
            await call.answer(state)
        await self._cb_chan_detail(call, cid)

    async def _cb_chan_remove(self, call, cid: str):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            title = chs[cid].get("title", cid)
            del chs[cid]
            self.db.set("MultiFC", "channels", chs)
            self._monitored.discard(self._pid(int(cid)))
            await call.answer(f"❌ {title} удалён")
        await self._cb_channels_page(call)

    async def _cb_triggers_page(self, call, page: int = 0):
        trigs = self._get_triggers()
        per = 5
        total = len(trigs)
        pages = max(1, (total + per - 1) // per)
        page = max(0, min(page, pages - 1))
        chunk = trigs[page * per: page * per + per]
        start_idx = page * per

        text = f"<b>🎯 Триггеры</b> ({total} шт.) — стр. {page + 1}/{pages}\n\n"
        for i, t in enumerate(chunk, start_idx + 1):
            text += f"<b>{i}.</b> <code>{t[:80]}</code>\n\n"

        btns = []
        for i, _ in enumerate(chunk):
            real_i = start_idx + i
            btns.append([{
                "text": f"🗑 Удалить #{real_i + 1}",
                "callback": self._cb_trig_del,
                "args": (real_i,),
            }])

        nav = []
        if page > 0:
            nav.append({"text": "◀️", "callback": self._cb_triggers_page, "args": (page - 1,)})
        if page < pages - 1:
            nav.append({"text": "▶️", "callback": self._cb_triggers_page, "args": (page + 1,)})
        if nav:
            btns.append(nav)

        btns.append([
            {"text": "🔄 Сбросить к дефолт", "callback": self._cb_trig_reset},
            {"text": "🗑 Очистить всё", "callback": self._cb_trig_clear},
        ])
        btns.append([{"text": "🔙 Назад", "callback": self._cb_refresh_main}])

        await call.edit(text=text, reply_markup=btns)

    async def _cb_trig_del(self, call, idx: int):
        trigs = list(self._get_triggers())
        if 0 <= idx < len(trigs):
            removed = trigs.pop(idx)
            self.db.set("MultiFC", "triggers", trigs)
            await call.answer(f"✅ Удалён #{idx + 1}")
        await self._cb_triggers_page(call)

    async def _cb_trig_reset(self, call):
        self.db.set("MultiFC", "triggers", DEFAULT_TRIGGERS)
        await call.answer(f"✅ Сброшено ({len(DEFAULT_TRIGGERS)} триггеров)")
        await self._cb_triggers_page(call)

    async def _cb_trig_clear(self, call):
        self.db.set("MultiFC", "triggers", [])
        await call.answer("✅ Очищено")
        await self._cb_triggers_page(call)

    async def _cb_logs_page(self, call):
        if not self._logs:
            await call.answer("Логов нет")
            return
        text = "<b>📋 MultiFC — Логи</b>\n\n"
        for e in reversed(self._logs[-15:]):
            t = time.strftime("%H:%M", time.localtime(e["ts"]))
            icon = "✅" if e["ok"] else "❌"
            text += (
                f"{icon} <code>{t}</code> <b>{e['channel']}</b>\n"
                f"   {e['count']} сообщ. | <i>{e['post'][:40]}</i>\n\n"
            )
        await call.edit(
            text=text,
            reply_markup=[[{"text": "🔙 Назад", "callback": self._cb_refresh_main}]],
        )

    # ── Quick settings command ────────────────────────────────────────────────
    # .mfcs <param> [+|-]value   — глобальные настройки
    # .mfcs <id/@> <param> [+|-]value — настройки канала
    #
    # Params: delay / spam / ai / msgs / trigs / enabled / folder
    # Syntax:
    #   +текст   → добавить в список
    #   -текст   → убрать из списка
    #   =значение или просто значение → заменить / установить

    @loader.command(ru_doc="Быстрые настройки. .mfcs help")
    async def mfcs(self, message: Message):
        """Quick settings. .mfcs help"""
        raw = utils.get_args_raw(message).strip()
        if not raw or raw == "help":
            await utils.answer(message, (
                "<b>⚙️ .mfcs — Быстрые настройки</b>\n\n"
                "<b>Глобальные:</b>\n"
                "<code>.mfcs delay 0.5</code> — задержка\n"
                "<code>.mfcs spam 5</code> — кол-во спам сообщений\n"
                "<code>.mfcs ai gemini|groq|none</code> — AI провайдер\n"
                "<code>.mfcs folder Название</code> — папка\n"
                "<code>.mfcs msgs +текст</code> — добавить сообщение\n"
                "<code>.mfcs msgs -текст</code> — убрать сообщение\n"
                "<code>.mfcs msgs текст1|текст2</code> — заменить всё\n"
                "<code>.mfcs trigs +regex</code> — добавить триггер\n"
                "<code>.mfcs trigs -N</code> — удалить триггер #N\n"
                "<code>.mfcs trigs reset</code> — сбросить к дефолту\n\n"
                "<b>На канал:</b>\n"
                "<code>.mfcs @channel delay 1</code>\n"
                "<code>.mfcs @channel spam 3</code>\n"
                "<code>.mfcs @channel ai true/false</code>\n"
                "<code>.mfcs @channel enabled true/false</code>\n"
                "<code>.mfcs @channel msgs +текст</code>\n"
                "<code>.mfcs @channel trigs +regex</code>\n"
                "<code>.mfcs @channel only_triggers true/false</code>\n"
                "<code>.mfcs @channel only_msgs true/false</code>\n"
                "<code>.mfcs @channel lock_global true/false</code>"
            ))
            return

        parts = raw.split(maxsplit=2)

        # Detect if first arg is channel reference
        cid_str = None
        pi = 0
        first = parts[0]
        if first.startswith("@") or (first.lstrip("-").isdigit() and len(first) > 6):
            try:
                ref = int(first) if first.lstrip("-").isdigit() else first
                e = await self._client.get_entity(ref)
                cid_str = str(e.id)
                pi = 1
            except Exception:
                pass

        if len(parts) <= pi:
            await utils.answer(message, "<b>❌ Укажи параметр</b>")
            return

        param = parts[pi].lower() if len(parts) > pi else ""
        value = parts[pi + 1].strip() if len(parts) > pi + 1 else ""

        # ── Channel-level settings ────────────────────────────────────────────
        if cid_str:
            chs = self.db.get("MultiFC", "channels", {})
            if cid_str not in chs:
                await utils.answer(message, self.strings["ch_not_found"])
                return
            ch = chs[cid_str]

            if param == "delay":
                ch["delay"] = float(value)
                await utils.answer(message, f"✅ delay = <code>{ch['delay']}</code>")

            elif param == "spam":
                ch["spam_count"] = max(1, min(10, int(value)))
                await utils.answer(message, f"✅ spam = <code>{ch['spam_count']}</code>")

            elif param == "ai":
                ch["use_ai"] = value.lower() in ("true", "1", "yes", "да")
                await utils.answer(message, f"✅ use_ai = <code>{ch['use_ai']}</code>")

            elif param == "enabled":
                ch["enabled"] = value.lower() in ("true", "1", "yes", "да")
                await utils.answer(message, f"✅ enabled = <code>{ch['enabled']}</code>")

            elif param in ("only_triggers", "only_msgs", "lock_global"):
                ch[param] = value.lower() in ("true", "1", "yes", "да")
                await utils.answer(message, f"✅ {param} = <code>{ch[param]}</code>")

            elif param == "msgs":
                lst = ch.setdefault("custom_messages", [])
                if value.startswith("+"):
                    v = value[1:].strip()
                    lst.append(v)
                    await utils.answer(message, f"✅ Сообщение добавлено: <code>{v}</code>")
                elif value.startswith("-"):
                    v = value[1:].strip()
                    if v in lst:
                        lst.remove(v)
                        await utils.answer(message, f"✅ Удалено: <code>{v}</code>")
                    else:
                        await utils.answer(message, "<b>❌ Сообщение не найдено</b>")
                        return
                else:
                    ch["custom_messages"] = [x.strip() for x in value.split("|") if x.strip()]
                    await utils.answer(message, f"✅ Сообщений: {len(ch['custom_messages'])}")

            elif param == "trigs":
                lst = ch.setdefault("custom_triggers", [])
                if value.startswith("+"):
                    v = value[1:].strip()
                    lst.append(v)
                    await utils.answer(message, f"✅ Триггер добавлен: <code>{v}</code>")
                elif value.startswith("-"):
                    v = value[1:].strip()
                    if v in lst:
                        lst.remove(v)
                        await utils.answer(message, f"✅ Удалён")
                    else:
                        await utils.answer(message, "<b>❌ Не найден</b>")
                        return
                else:
                    ch["custom_triggers"] = [x.strip() for x in value.split("|") if x.strip()]
                    await utils.answer(message, f"✅ Триггеров: {len(ch['custom_triggers'])}")
            else:
                await utils.answer(message, f"<b>❌ Неизвестный параметр:</b> <code>{param}</code>")
                return

            chs[cid_str] = ch
            self.db.set("MultiFC", "channels", chs)

        # ── Global settings ───────────────────────────────────────────────────
        else:
            if param == "delay":
                self.config["global_delay"] = float(value)
                await utils.answer(message, f"✅ global_delay = <code>{value}</code>")

            elif param == "spam":
                self.config["spam_count"] = max(1, min(10, int(value)))
                await utils.answer(message, f"✅ spam_count = <code>{self.config['spam_count']}</code>")

            elif param == "ai":
                if value not in ("gemini", "groq", "none"):
                    await utils.answer(message, "<b>❌ Только: gemini / groq / none</b>")
                    return
                self.config["ai_provider"] = value
                await utils.answer(message, f"✅ ai_provider = <code>{value}</code>")

            elif param == "folder":
                self.config["folder_name"] = value
                await self._reload_channels()
                await utils.answer(message, f"✅ folder = <code>{value}</code>")

            elif param == "msgs":
                lst = list(self.config["global_messages"])
                if value.startswith("+"):
                    v = value[1:].strip()
                    lst.append(v)
                    self.config["global_messages"] = lst
                    await utils.answer(message, f"✅ Добавлено: <code>{v}</code> ({len(lst)} шт.)")
                elif value.startswith("-"):
                    v = value[1:].strip()
                    if v in lst:
                        lst.remove(v)
                        self.config["global_messages"] = lst
                        await utils.answer(message, f"✅ Удалено: <code>{v}</code>")
                    else:
                        await utils.answer(message, "<b>❌ Не найдено</b>")
                        return
                else:
                    new = [x.strip() for x in value.split("|") if x.strip()]
                    self.config["global_messages"] = new
                    await utils.answer(message, f"✅ Сообщений: {len(new)}")

            elif param == "trigs":
                trigs = list(self._get_triggers())
                if value.startswith("+"):
                    v = value[1:].strip()
                    trigs.append(v)
                    self.db.set("MultiFC", "triggers", trigs)
                    await utils.answer(message, f"✅ Триггер добавлен: <code>{v}</code>")
                elif value.startswith("-"):
                    v = value[1:].strip()
                    # support -N (number) or -text
                    if v.isdigit():
                        idx = int(v) - 1
                        if 0 <= idx < len(trigs):
                            removed = trigs.pop(idx)
                            self.db.set("MultiFC", "triggers", trigs)
                            await utils.answer(message, f"✅ Удалён #{idx+1}: <code>{removed[:60]}</code>")
                        else:
                            await utils.answer(message, "<b>❌ Неверный номер</b>")
                            return
                    else:
                        if v in trigs:
                            trigs.remove(v)
                            self.db.set("MultiFC", "triggers", trigs)
                            await utils.answer(message, f"✅ Удалён")
                        else:
                            await utils.answer(message, "<b>❌ Не найден</b>")
                            return
                elif value == "reset":
                    self.db.set("MultiFC", "triggers", DEFAULT_TRIGGERS)
                    await utils.answer(message, f"✅ Сброшено ({len(DEFAULT_TRIGGERS)} триггеров)")
                elif value == "clear":
                    self.db.set("MultiFC", "triggers", [])
                    await utils.answer(message, "✅ Очищено")
                else:
                    new = [x.strip() for x in value.split("|") if x.strip()]
                    self.db.set("MultiFC", "triggers", new)
                    await utils.answer(message, f"✅ Триггеров: {len(new)}")
            else:
                await utils.answer(message, f"<b>❌ Неизвестный параметр:</b> <code>{param}</code>")