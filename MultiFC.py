# meta developer: @Mr4epTuk
# meta version: 2.0.0
# meta name: MultiFC
# requires: aiohttp

"""
MultiFC v2.0 — Smart Gift/NFT Hunter for Heroku Userbot
Fully rewritten for reliability and accuracy.
"""

from herokutl.types import Message
from herokutl.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from herokutl.tl.functions.messages import GetDialogFiltersRequest, GetDiscussionMessageRequest
from herokutl.tl.functions.folders import EditPeerFoldersRequest
from herokutl.tl.types import InputFolderPeer
from .. import loader, utils
import logging
import asyncio
import re
import random
import aiohttp
import time
import collections
import os
from typing import Optional, List, Dict, Set, Deque

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# PRIZE KEYWORDS
# ═══════════════════════════════════════════════════════════════════════════════

_PRIZE_KW = (
    r"нфт|nft|мишк|мишек|медвед|розочк|звезд|star|прем|prem|gift|гифт|алмаз|"
    r"сердечк|сердец|ракет|rocket|ton|usdt|rub|крист|crystal|цветоч|букет|"
    r"подар|приз|награ|выигр|выдад|раздад|разыгр|жетон|токен|coin|монет|"
    r"🧸|🖼|🌹|⭐|💎|🎁|🥀|💝|🎀|🚀|💫|🏆|🪙|🌸|🌺|🌻|🌼|💐|🎊|🎉|"
    r"🎈|🏅|🥇|🥈|🥉|💰|💵|💴|💶|💷|🪅|🧿|🔮|⚡|🌟|✨|💥|😇"
)
_PRIZE_RE = re.compile(_PRIZE_KW, re.IGNORECASE)

# Слово «комментарий» во всех формах
_KOM = r"комм?ент(?:арий|ариев|арию|ариям|ария|ов|у|е|ом|ах|ами|а|ы|атор\w*)?\b|ком\b"

# Разделители между числом и призом
_SEP = r"(?:[\s=:—–\-\u2013\u2014\u2192>|,.]+|\s*и\s*)"

# Посты-результаты розыгрыша (пропускаем)
_RESULTS_RE = re.compile(
    r"результат[ыи]\s+розыгрыш|🏆\s*победител|победители\s*:|итоги\s+розыгрыш"
    r"|конкурс\s+завершён|розыгрыш\s+завершён|поздравляем\s+победител"
    r"|winners\s*:|congratulations",
    re.IGNORECASE,
)

# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT TRIGGERS
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_TRIGGERS: List[str] = [
    # 1. "21 коментарий = нфт" / "25 Комментарий = НФТ" / "5 ком: подарок"
    r"\b\d+" + _SEP + r"(?:" + _KOM + r")" + _SEP + r"(?:" + _PRIZE_KW + r")",

    # 2. "нфт = 21 коментарий"
    r"(?:" + _PRIZE_KW + r")" + _SEP + r"\b\d+" + _SEP + r"(?:" + _KOM + r")",

    # 3. "5му нфт" / "10-му мишка" / "3й алмаз"
    r"\b\d+\s*[-–—]?\s*(?:го|му|ому|ему|й|ый|ий|ой)\b.{0,60}(?:" + _PRIZE_KW + r")",

    # 4. "пятому нфт" / "первому мишка" / "третьему алмаз"
    (r"(?:перв\w+|втор\w+|трет\w+|четв\w+|пят\w+|шест\w+|седьм\w+|восьм\w+"
     r"|девят\w+|десят\w+).{0,60}(?:" + _PRIZE_KW + r")"),

    # 5. Список чисел + приз: "13 19 и 34 нфт" / "1, 8, 15 мишка" / "5 9 8 по мишке"
    r"\d+(?:" + _SEP + r"\d+){2,}.{0,40}(?:" + _PRIZE_KW + r")",

    # 6. Большой арифм. список: "10 20 30 40 50 ... коментарий"
    r"\b\d{1,4}(?:\s+\d{1,4}){4,}.{0,80}(?:" + _KOM + r"|" + _PRIZE_KW + r")",

    # 7. "первые N + приз" / "N первых + приз"
    r"первы[ехми]+\s+\d+.{0,80}(?:" + _PRIZE_KW + r")",
    r"\d+\s+первы[ехми]+.{0,80}(?:" + _PRIZE_KW + r")",

    # 8. "первым N коментам" / "первые N комментариев"
    r"первы[ехми]+\s+\d+\s*(?:" + _KOM + r")",
    r"первым\s+\d+\s*(?:" + _KOM + r")",

    # 9. "N комментов получат/получит"
    r"\b\d+\s*(?:" + _KOM + r")\s*(?:получ|выигр|достан)\w*",

    # 10. "напиши «слово»"
    r'(?:напиш[иеёт]+|написавш\w+|написать|пишем|пишите)\s+(?:слово\s+)?[«"\'"]',

    # 11. "кто первый напишет"
    r"кто\s+(?:будет\s+)?первы[йм]\s+(?:кто\s+)?напиш\w+",
    r"первому\s+(?:кто\s+)?напиш\w+",

    # 12. Emoji приз после числа
    r"\b\d+\s*(?:🧸|💎|🎁|🌹|🥀|🚀|💝|⭐|🏆|🎉|🌸|🌟|✨)",

    # 13. "разыгрываем/раздаём/дарим + приз"
    (r"(?:разыгрыва\w+|раздаём|раздаем|раздадим|отдад\w+|дарим|дарю)\s.{0,60}"
     r"(?:" + _PRIZE_KW + r")"),

    # 14. "первый комментарий"
    r"перв\w+\s+(?:" + _KOM + r")",
    r"(?:" + _KOM + r")\s*[#№]?\s*1\b",
]

# ═══════════════════════════════════════════════════════════════════════════════
# ANALYZERS
# ═══════════════════════════════════════════════════════════════════════════════

_REQ_WORD_RE = re.compile(
    r'(?:напиш[иеёт]+|написавш\w+|написать|пишем|пишите|написавшему)\s+'
    r'(?:в\s+)?(?:комм?ент(?:арий)?\s+)?(?:слово\s+)?'
    r'(?:[«"\'"]([^»"\'"\n]{1,120})[»"\'"\n]'
    r'|([а-яёА-ЯЁa-zA-Z]{2,30}(?<![её]т)(?<!ит)(?<!ут)(?<!ают)))',
    re.IGNORECASE,
)

_FIRST_N_RE = re.compile(
    r"первы[ехми]+\s+(\d+)"
    r"|(\d+)\s+первы[ехми]+"
    r"|первым\s+(\d+)\s*(?:" + _KOM + r")"
    r"|получ\w*\s+первы[ехми]+\s+(\d+)"
    r"|первы[ехми]+\s+(\d+)\s*(?:человек|участник|комментатор)\w*",
    re.IGNORECASE,
)

_NTH_RECV_RE = re.compile(
    r"\b(\d+)\s*(?:" + _KOM + r")\s*(?:получ|выигр|достан)\w+",
    re.IGNORECASE,
)

_NTH_KOM_RE = re.compile(
    r"\b(\d+)\s*[-–—=:]*\s*(?:" + _KOM + r")",
    re.IGNORECASE,
)

_NTH_ORD_RE = re.compile(
    r"\b(\d+)\s*[-–—]?\s*(?:го|му|ому|ему|й|ый|ий|ой|им)\b",
    re.IGNORECASE,
)

# Числа рядом с "ком" или порядковым суффиксом — это реальные таргеты
_CTX_NUM_RE = re.compile(
    r"\b(\d{1,5})\s*[-–—=:]*\s*(?:" + _KOM + r")"
    r"|\b(\d{1,5})\s*[-–—]?\s*(?:го|му|ому|ему|й|ый|ий|ой|им)\b"
    r"|\b(?:перв|втор|трет|четв|пят|шест|седьм|восьм|девят|десят)\w*\s+(\d{1,5})\b"
    r"|\b(\d{1,5})\s+(?:перв|втор|трет)\w+\b",
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
    r"\bдвадцать\b": 20, r"\bтридцать\b": 30,
    r"\bсорок\b": 40, r"\bпятьдесят\b": 50, r"\bсто\b|\bсотн\w+": 100,
}

_BAD_REQ_RE = re.compile(
    r"^(?:получ|выигр|достан|написат?|написа|раздад|первому|первый|первые|первым"
    r"|нфт|nft|мишк|алмаз|gift|звезд|прем|ракет|монет|приз)\w*$",
    re.I,
)


def _strip_noise(text: str) -> str:
    """Strip times (15:40) and separators."""
    t = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text)
    t = re.sub(r"[=:\u2192>|]", " ", t)
    return t


def _extract_context_nums(text: str) -> List[int]:
    """Numbers that have comment/ordinal context — these are real targets."""
    result = []
    for m in _CTX_NUM_RE.finditer(text):
        n = int(next(g for g in m.groups() if g is not None))
        if 1 <= n <= 5000:
            result.append(n)
    return sorted(set(result))


def _extract_all_nums(text: str) -> List[int]:
    """All standalone numbers 1-5000."""
    result = set()
    for m in re.finditer(r"\b(\d{1,5})\b", text):
        n = int(m.group(1))
        if 1 <= n <= 5000:
            result.add(n)
    return sorted(result)


def _analyze(text: str) -> dict:
    """
    Analyze giveaway post. Returns:
    {targets, required_text, is_first_n, first_n, _reason}
    """
    base = {"required_text": None, "is_first_n": False, "first_n": 1, "_reason": "?"}

    # Skip results/winner announcement posts
    if _RESULTS_RE.search(text):
        return {**base, "targets": [1], "is_first_n": True, "_reason": "results_post_skip"}

    clean = _strip_noise(text)
    has_prize = bool(_PRIZE_RE.search(clean))

    # Required word ("напиши «слово»")
    req = None
    rm = _REQ_WORD_RE.search(text)
    if rm:
        quoted = (rm.group(1) or "").strip()
        bare   = (rm.group(2) or "").strip()
        if quoted:
            req = quoted
        elif bare and not _BAD_REQ_RE.match(bare) and not _PRIZE_RE.search(bare):
            req = bare

    # ── First-N ("первым N коментам") — highest priority ─────────────────────
    fn = _FIRST_N_RE.search(clean)
    if fn:
        raw = next((g for g in fn.groups() if g), None)
        n = int(raw) if raw else 1
        if req:
            return {**base, "required_text": req, "targets": [1],
                    "_reason": f"req_word+first_n"}
        return {**base, "targets": [1], "is_first_n": True, "first_n": n,
                "_reason": f"first_n={n}"}

    # ── "первые + cardinal" ("первые три") ───────────────────────────────────
    if re.search(r"первы[ехми]+|первым\b", clean, re.I):
        for pat_str, num in _CARDINALS.items():
            if re.search(pat_str, clean, re.I):
                if req:
                    return {**base, "required_text": req, "targets": [num],
                            "_reason": f"req_word, cardinal={num}"}
                return {**base, "targets": [1], "is_first_n": True, "first_n": num,
                        "_reason": f"cardinal_first_n={num}"}

    # No prize and no req → first-come
    if not has_prize and not req:
        return {**base, "targets": [1], "is_first_n": True, "_reason": "no_prize_fallback"}

    # ── Numbers with explicit comment context — always valid targets ──────────
    ctx = _extract_context_nums(clean)
    all_nums = _extract_all_nums(clean)
    plausible = [n for n in all_nums if n <= 2000]

    # If context nums form a list together with all plausible → return all
    if len(ctx) >= 1 and len(plausible) >= 2:
        # Check if context num is part of the plausible group
        if any(c in plausible for c in ctx):
            diffs = [plausible[i+1]-plausible[i] for i in range(len(plausible)-1)]
            if len(set(diffs)) == 1 and diffs[0] > 0:
                return {**base, "targets": plausible, "_reason": f"arith_seq ctx"}
            return {**base, "targets": plausible, "_reason": f"list+ctx"}

    if len(ctx) >= 2:
        return {**base, "targets": ctx, "_reason": "ctx_list"}
    if len(ctx) == 1:
        n = ctx[0]
        return {**base, "targets": [n], "is_first_n": n == 1,
                "_reason": f"ctx_single={n}"}

    # ── "N коментов получит" ─────────────────────────────────────────────────
    nr = _NTH_RECV_RE.search(clean)
    if nr:
        n = int(nr.group(1))
        if 1 <= n <= 5000:
            return {**base, "targets": [n], "_reason": f"nth_recv={n}"}

    # ── "N коменту/комментарию" ───────────────────────────────────────────────
    nk = _NTH_KOM_RE.search(clean)
    if nk:
        n = int(nk.group(1))
        if 1 <= n <= 5000:
            return {**base, "targets": [n], "is_first_n": n == 1,
                    "_reason": f"nth_kom={n}"}

    # ── Russian ordinal word ──────────────────────────────────────────────────
    for pat, num in _ORDINALS:
        if pat.search(clean):
            is_fn = (num == 1) and not req
            return {**base, "targets": [num], "is_first_n": is_fn,
                    "_reason": f"ordinal={num}"}

    # ── Digit ordinal "5му", "10-й" ───────────────────────────────────────────
    no = _NTH_ORD_RE.search(clean)
    if no:
        n = int(no.group(1))
        if 1 <= n <= 5000:
            return {**base, "targets": [n], "is_first_n": n == 1,
                    "_reason": f"digit_ord={n}"}

    # ── Fallback ──────────────────────────────────────────────────────────────
    if req:
        return {**base, "required_text": req, "targets": [1],
                "_reason": "req_word_fallback"}
    return {**base, "targets": [1], "is_first_n": True, "_reason": "ultimate_fallback"}


@loader.tds
class MultiFCMod(loader.Module):
    """MultiFC v2 — Smart Gift/NFT Hunter. @Mr4epTuk"""

    strings = {
        "name": "MultiFC",
        "status": (
            "🎯 <b>MultiFC v2</b>\n\n"
            "⚡ <b>Статус:</b> {status}\n"
            "📢 <b>Каналов:</b> {channels}\n"
            "🎪 <b>Охот активно:</b> {hunting}\n"
            "📁 <b>Папка:</b> <code>{folder}</code>\n"
            "🤖 <b>AI:</b> <code>{ai}</code>\n"
            "🎯 <b>Триггеров:</b> {trigs}"
        ),
        "trig_help": (
            "<b>🎯 Триггеры</b>\n\n"
            "<code>.mfctrig list</code>\n"
            "<code>.mfctrig add</code> — следующие строки = триггеры\n"
            "<code>.mfctrig del N</code>\n"
            "<code>.mfctrig reset</code> — к дефолтным\n"
            "<code>.mfctrig clear</code> — реагировать на все посты"
        ),
        "chan_help": (
            "<b>⚙️ Настройка канала</b>\n\n"
            "<code>.mfcchan [id/@] info|enabled|delay|spam_count|use_ai</code>\n"
            "<code>.mfcchan [id/@] add_trigger|del_trigger|add_msg|del_msg текст</code>\n"
            "<code>.mfcchan [id/@] only_triggers|only_msgs|lock_global true/false</code>"
        ),
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("status", True, "Включить модуль",
                               validator=loader.validators.Boolean()),
            loader.ConfigValue("folder_name", "",
                               "Папка Telegram с каналами (пусто = не использовать)",
                               validator=loader.validators.String(min_len=0)),
            loader.ConfigValue("global_messages",
                               ["а", "ну", ".", "г", "о", "р", "э", "в", "с", "п"],
                               "Сообщения для комментариев",
                               validator=loader.validators.Series(
                                   validator=loader.validators.String())),
            loader.ConfigValue("global_delay", 0.0,
                               "Задержка перед первым комментарием (сек)",
                               validator=loader.validators.Float()),
            loader.ConfigValue("spam_count", 3, "Сообщений при атаке",
                               validator=loader.validators.Integer(minimum=1, maximum=10)),
            loader.ConfigValue("spam_interval", 0.15, "Интервал между спам-сообщениями (сек)",
                               validator=loader.validators.Float()),
            loader.ConfigValue("ai_provider", "none", "AI: none/gemini/groq",
                               validator=loader.validators.Choice(["none", "gemini", "groq"])),
            loader.ConfigValue("ai_api_key", "", "API ключ AI",
                               validator=loader.validators.Hidden()),
            loader.ConfigValue("auto_join", True, "Авто-вступление в чаты обсуждений",
                               validator=loader.validators.Boolean()),
            loader.ConfigValue("disc_folder", "archive",
                               "Папка для дискуссий: archive / none / <название>",
                               validator=loader.validators.String(min_len=0)),
            loader.ConfigValue("dlog_file", "",
                               "Путь к файлу дебаг-лога (пусто = выключено)",
                               validator=loader.validators.String(min_len=0)),
        )
        self._hunting:   Dict[int, dict] = {}      # disc_pid → hunt
        self._ch_to_disc: Dict[int, int] = {}       # ch_pid → disc_pid cache
        self._monitored: Set[int] = set()
        self._paused:    bool = False
        self._logs:      List[dict] = []            # hunt summary log
        self._dlogs:     List[str] = []             # detailed debug log
        self._ch_stats:  Dict[int, dict] = {}       # disc_pid → {offset, comment_ts}
        self._fired:     Dict[tuple, float] = {}    # (ch_pid, post_id) → ts
        self._me = None

    # ── Init ──────────────────────────────────────────────────────────────────

    async def client_ready(self, client, db):
        self._client = client
        self.db = db
        self._me = await client.get_me()
        if not self.db.get("MultiFC", "triggers", None):
            self.db.set("MultiFC", "triggers", DEFAULT_TRIGGERS)
        await self._reload_channels()

    # ── Helpers ───────────────────────────────────────────────────────────────

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
                if hasattr(raw_title, "text"):
                    raw_title = raw_title.text
                if not isinstance(raw_title, str):
                    raw_title = str(raw_title)
                if raw_title.strip().lower() != name.strip().lower():
                    continue
                out, seen = [], set()
                # include_peers + pinned_peers
                all_peers = (list(getattr(f, "include_peers", []))
                             + list(getattr(f, "pinned_peers", [])))
                for peer in all_peers:
                    try:
                        e = await self._client.get_entity(peer)
                        if e.id in seen:
                            continue
                        seen.add(e.id)
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
            "enabled":       ch.get("enabled", True),
            "delay":         ch.get("delay", self.config["global_delay"]),
            "spam_count":    ch.get("spam_count", self.config["spam_count"]),
            "spam_interval": ch.get("spam_interval", self.config["spam_interval"]),
            "use_ai":        ch.get("use_ai", False),
            "triggers":      triggers,
            "messages":      messages or ["а"],
        }

    def _match_triggers(self, text: str, cfg: dict) -> bool:
        trigs = cfg.get("triggers", [])
        if not trigs:
            return True
        for t in trigs:
            try:
                if re.search(t, text, re.IGNORECASE):
                    return True
            except re.error:
                pass
        return False

    async def _get_discussion(self, channel_pid: int) -> Optional[int]:
        if channel_pid in self._ch_to_disc:
            return self._ch_to_disc[channel_pid]
        try:
            full = await self._client(GetFullChannelRequest(channel_pid))
            linked = getattr(full.full_chat, "linked_chat_id", None)
            if linked:
                self._ch_to_disc[channel_pid] = abs(linked)
                return abs(linked)
        except Exception:
            pass
        return None

    async def _ensure_joined(self, disc_pid: int):
        try:
            await self._client(JoinChannelRequest(disc_pid))
        except Exception:
            pass
        disc_folder = self.config.get("disc_folder", "archive").strip().lower()
        if disc_folder == "none":
            return
        try:
            entity = await self._client.get_entity(disc_pid)
            folder_id = 1  # archive by default
            if disc_folder not in ("archive", "1"):
                try:
                    res = await self._client(GetDialogFiltersRequest())
                    for f in res.filters:
                        if not hasattr(f, "title"):
                            continue
                        t = f.title
                        if hasattr(t, "text"):
                            t = t.text
                        if isinstance(t, str) and t.strip().lower() == disc_folder:
                            folder_id = f.id
                            break
                except Exception:
                    pass
            await self._client(EditPeerFoldersRequest(
                folder_peers=[InputFolderPeer(peer=entity, folder_id=folder_id)]
            ))
        except Exception:
            pass

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
        prompt = (f'Напиши один короткий (1-5 слов) нейтральный комментарий к посту: '
                  f'"{post_text[:200]}". Только текст, без кавычек.')
        try:
            async with aiohttp.ClientSession() as s:
                if provider == "gemini":
                    url = ("https://generativelanguage.googleapis.com/v1beta/"
                           f"models/gemini-2.0-flash:generateContent?key={key}")
                    async with s.post(url,
                                      json={"contents": [{"parts": [{"text": prompt}]}]},
                                      timeout=aiohttp.ClientTimeout(total=8)) as r:
                        d = await r.json()
                        return d["candidates"][0]["content"]["parts"][0]["text"].strip()
                elif provider == "groq":
                    async with s.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        json={"model": "llama3-8b-8192",
                              "messages": [{"role": "user", "content": prompt}],
                              "max_tokens": 20},
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=aiohttp.ClientTimeout(total=8),
                    ) as r:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"[MultiFC] AI error: {e}")
        return None

    # ── Spam ─────────────────────────────────────────────────────────────────

    async def _spam(self, hunt: dict, override_n: int = 0) -> list:
        req = hunt.get("required_text")
        cfg = hunt["cfg"]
        pool = [req] if req else list(cfg["messages"])
        if cfg["use_ai"] and self.config["ai_provider"] != "none":
            ai = await self._ai_text(hunt["post_text"])
            if ai:
                pool = [ai] + pool

        n = override_n if override_n > 0 else cfg["spam_count"]
        interval = cfg["spam_interval"]
        sent = []

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
                    self._dlog(hunt, "slowmode — stop spam", "WARN")
                    break
                elif "flood" in err:
                    self._dlog(hunt, f"flood wait — stop: {e}", "WARN")
                    await asyncio.sleep(3)
                    break
                else:
                    self._dlog(hunt, f"send error: {e}", "ERR")
                    break
        return sent

    # ── Adaptive offset ───────────────────────────────────────────────────────

    def _get_offset(self, disc_pid: int) -> int:
        s = self._ch_stats.get(disc_pid, {})
        base = s.get("offset", 2)
        ts = s.get("comment_ts")
        if ts and len(ts) >= 4:
            recent = list(ts)[-4:]
            span = recent[-1] - recent[0]
            if span > 0 and (3 / span) > 2:   # >2 comments/sec → fast chat
                return min(5, base + 1)
        return max(1, base)

    def _update_offset(self, disc_pid: int, target: int, actual: int):
        if not disc_pid or not target or not actual:
            return
        s = self._ch_stats.setdefault(disc_pid, {"offset": 2,
                                                   "comment_ts": collections.deque(maxlen=60)})
        error = actual - target
        adj = max(-1, min(1, error))
        old = s.get("offset", 2)
        s["offset"] = max(1, min(5, old + adj))
        self._dlog(disc_pid, f"offset update: {old}→{s['offset']} (target={target} landed={actual} error={error:+d})")

    def _record_comment_ts(self, disc_pid: int):
        s = self._ch_stats.setdefault(disc_pid, {"offset": 2,
                                                   "comment_ts": collections.deque(maxlen=60)})
        s["comment_ts"].append(time.time())

    # ── Logging ───────────────────────────────────────────────────────────────

    def _dlog(self, hunt_or_label, msg: str, level: str = "INFO"):
        """Structured debug log with ms timestamp, hunt context, optional file."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S.") + f"{int((time.time() % 1)*1000):03d}"
        if isinstance(hunt_or_label, dict):
            ch  = hunt_or_label.get("ch_title", "?")[:20]
            pid = hunt_or_label.get("post_id", "?")
            disc= hunt_or_label.get("disc_pid", "?")
            snippet = hunt_or_label.get("post_text", "")[:60].replace("\n", " ").strip()
            label = f"[{ch}|p={pid}|d={disc}|'{snippet}']"
        elif isinstance(hunt_or_label, int):
            label = f"[disc={hunt_or_label}]"
        else:
            label = f"[{hunt_or_label}]"

        lvl = {"INFO": "INF", "FIRE": "FIR", "OK": " OK",
               "ERR": "ERR", "WARN": "WRN"}.get(level, level[:3].upper())
        line = f"{ts} [{lvl}] {label} {msg}"

        if level == "ERR":
            logger.error(f"[MultiFC] {label} {msg}")
        else:
            logger.debug(f"[MultiFC] {line}")

        self._dlogs.append(line)
        if len(self._dlogs) > 1000:
            self._dlogs = self._dlogs[-1000:]

        path = self.config.get("dlog_file", "").strip() if hasattr(self, "config") else ""
        if path:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    def _log(self, hunt: dict, ok: bool):
        self._logs.append({
            "ts": time.time(),
            "channel": hunt["ch_title"],
            "ok": ok,
            "count": len(hunt.get("sent_msgs", [])),
            "post": hunt["post_text"][:80],
            "targets": hunt.get("targets", []),
        })
        self._logs = self._logs[-100:]

    # ── Notification ──────────────────────────────────────────────────────────

    async def _do_final_notify(self, hunt: dict):
        """Send ONE final notification. Protected by notify_sent flag."""
        if hunt.get("notify_sent"):
            return
        hunt["notify_sent"] = True
        self._dlog(hunt, "do_final_notify: start (waiting 3s)")

        sent = [m for m in hunt.get("sent_msgs", []) if m]
        disc_pid = hunt["disc_pid"]
        targets  = set(hunt.get("targets", []))

        await asyncio.sleep(3)

        positions: Dict[int, int] = {}
        our_ids = {m.id for m in sent}

        try:
            disc_entity = await self._client.get_entity(disc_pid)
            # Get the discussion thread root message
            thread_id = hunt.get("disc_thread_id")
            if not thread_id:
                try:
                    ch_ent = await self._client.get_entity(hunt["ch_pid"])
                    di = await self._client(GetDiscussionMessageRequest(
                        peer=ch_ent, msg_id=hunt["post_id"],
                    ))
                    if di and di.messages:
                        thread_id = di.messages[0].id
                        hunt["disc_thread_id"] = thread_id
                except Exception as e:
                    self._dlog(hunt, f"disc_thread_id fetch failed: {e}", "WARN")

            fetch_kw = {"limit": 300}
            if thread_id:
                fetch_kw["reply_to"] = thread_id
            history = await self._client.get_messages(disc_entity, **fetch_kw)
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

            self._dlog(hunt, f"positions: {positions} (thread={thread_id} total={len(msgs_sorted)})")
        except Exception as e:
            logger.error(f"[MultiFC] resolve_positions: {e}")
            self._dlog(hunt, f"resolve_positions ERROR: {e}", "ERR")

        # Update adaptive offset
        if positions and targets:
            best = min(positions.values())
            closest = min(targets, key=lambda t: abs(t - best))
            self._update_offset(disc_pid, closest, best)

        if not sent:
            return

        lines, won_any = [], False
        for m in sent:
            p = positions.get(m.id)
            link = f"<a href='{self._msg_link(disc_pid, m.id)}'>#{p if p else '?'}</a>"
            won = bool(p and p in targets)
            if won:
                won_any = True
            lines.append(("🏆" if won else "❌") + " " + link)

        close = any(abs(p - min(targets, key=lambda t: abs(t-p))) <= 2
                    for p in positions.values() if p)
        result = "🏆 Победа!" if won_any else ("🎯 Почти (±2)" if close else "😔 Не попал")
        self._dlog(hunt, f"result={result} positions={positions}", "OK" if won_any else "WARN")

        ch_link = hunt["ch_title"]
        if hunt.get("ch_username"):
            ch_link = f"<a href='https://t.me/{hunt['ch_username']}'>{hunt['ch_title']}</a>"

        post_safe = hunt["post_text"][:100].replace("<", "&lt;").replace(">", "&gt;")
        text = (
            "🎯 <b>MultiFC — Итог</b>\n\n"
            f"📢 <b>Канал:</b> {ch_link}\n"
            f"📝 <b>Пост:</b> <i>{post_safe}</i>\n\n"
            f"🎯 <b>Цели:</b> {', '.join(map(str, sorted(targets)))}\n"
            f"📍 <b>Offset:</b> {self._get_offset(disc_pid)}\n"
            "💬 <b>Сообщения:</b>\n" + "\n".join(lines) + "\n\n"
            f"📊 {result}"
        )
        ids_str = ",".join(str(m.id) for m in sent)
        markup = [[{"text": "🗑 Удалить мои", "callback": self._cb_del_my_msgs,
                    "args": (disc_pid, ids_str)}]]

        try:
            await self.inline.bot.send_message(
                self._me.id, text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=self.inline.generate_markup(markup),
            )
            self._dlog(hunt, "notify sent via inline bot", "OK")
        except Exception as e:
            self._dlog(hunt, f"inline bot notify failed: {e} — trying userbot fallback", "ERR")
            try:
                await self._client.send_message(self._me.id, text,
                                                parse_mode="html", link_preview=False)
                self._dlog(hunt, "notify sent via userbot fallback", "OK")
            except Exception as e2:
                self._dlog(hunt, f"notify fallback FAILED: {e2}", "ERR")

    def _finish_hunt(self, hunt: dict):
        """Single exit point — mark finished, schedule ONE notification."""
        if hunt.get("finished"):
            return
        hunt["finished"] = True
        self._hunting.pop(hunt["disc_pid"], None)
        elapsed = round(time.time() - hunt.get("started", time.time()), 1)
        self._dlog(hunt,
                   f"HUNT FINISHED: sent={len(hunt.get('sent_msgs',[]))} "
                   f"targets={hunt['targets']} done={sorted(hunt['done'])} elapsed={elapsed}s",
                   "OK")
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

    # ── Watcher + Core Engine ─────────────────────────────────────────────────

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

        # Discussion comment → trigger immediate real-count check
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

        self._record_comment_ts(cid)
        asyncio.create_task(self._check_and_fire(hunt))

    async def _get_real_count(self, ch_entity, post_id: int) -> int:
        try:
            msg = await self._client.get_messages(ch_entity, ids=post_id)
            if msg and getattr(msg, "replies", None):
                return msg.replies.replies or 0
        except Exception:
            pass
        return 0

    async def _check_and_fire(self, hunt: dict):
        """
        Get real comment count → fire if in window.
        Window = [target - offset, target + offset].
        Lock prevents double-firing same target.
        """
        if hunt.get("finished"):
            return

        # Retry up to 3 times on network error
        real_count = -1
        for attempt in range(3):
            try:
                ch_entity = await self._client.get_entity(hunt["ch_pid"])
                real_count = await self._get_real_count(ch_entity, hunt["post_id"])
                break
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(0.3 * (attempt + 1))
                else:
                    self._dlog(hunt, f"get_count failed (3 attempts): {e}", "ERR")
                    return

        async with hunt["lock"]:
            if hunt.get("finished"):
                return

            remaining = [t for t in hunt["targets"] if t not in hunt["done"]]
            if not remaining:
                self._finish_hunt(hunt)
                return

            next_t   = remaining[0]
            offset   = self._get_offset(hunt["disc_pid"])
            fire_at  = max(0, next_t - offset)

            self._dlog(hunt, f"check: real={real_count} next_t={next_t} fire_at={fire_at} offset={offset}")

            if real_count < fire_at:
                return

            # Claim this target inside lock
            hunt["done"].add(next_t)
            self._dlog(hunt, f"FIRE: target={next_t} real_count={real_count}", "FIRE")

        # Send outside lock
        msgs = await self._spam(hunt)
        if msgs:
            hunt["sent_msgs"].extend(msgs)
            self._log(hunt, True)
            self._dlog(hunt, f"sent {len(msgs)} msgs, ids={[m.id for m in msgs]}", "OK")

        async with hunt["lock"]:
            if not [t for t in hunt["targets"] if t not in hunt["done"]]:
                self._finish_hunt(hunt)

    async def _poll_sync(self, hunt: dict):
        """Periodic backup poller. Adapts interval by proximity to target."""
        try:
            ch_entity = await self._client.get_entity(hunt["ch_pid"])
        except Exception as e:
            self._dlog(hunt, f"poll_sync get_entity failed: {e}", "ERR")
            return

        timeout  = 600
        interval = 2.0

        while not hunt.get("finished"):
            if time.time() - hunt["started"] > timeout:
                self._dlog(hunt, f"poll_sync TIMEOUT ({timeout}s)", "WARN")
                self._finish_hunt(hunt)
                break

            if self._paused or not self.config["status"]:
                await asyncio.sleep(2)
                continue

            await asyncio.sleep(interval)
            if hunt.get("finished"):
                break

            try:
                real_count = await self._get_real_count(ch_entity, hunt["post_id"])
            except Exception:
                continue

            remaining = [t for t in hunt["targets"] if t not in hunt["done"]]
            if not remaining:
                self._finish_hunt(hunt)
                break

            next_t  = remaining[0]
            offset  = self._get_offset(hunt["disc_pid"])
            fire_at = max(0, next_t - offset)
            dist    = fire_at - real_count

            # Adaptive interval
            if dist > 50:     interval = 4.0
            elif dist > 20:   interval = 2.0
            elif dist > 10:   interval = 1.0
            elif dist > 3:    interval = 0.5
            else:             interval = 0.2

            await self._check_and_fire(hunt)

    async def _on_post(self, message: Message):
        try:
            # Skip paid media
            if hasattr(message, "media") and message.media:
                if "paid" in type(message.media).__name__.lower():
                    return

            ch_pid = self._pid(utils.get_chat_id(message))
            cfg    = self._chan_cfg(ch_pid)
            if not cfg["enabled"]:
                return

            text = message.raw_text or ""

            # Deduplicate
            post_key = (ch_pid, message.id)
            now      = time.time()
            if self._fired.get(post_key, 0) > now - 120:
                return
            self._fired[post_key] = now
            if len(self._fired) > 500:
                for k, _ in sorted(self._fired.items(), key=lambda x: x[1])[:200]:
                    del self._fired[k]

            if not self._match_triggers(text, cfg):
                return

            # Analyze
            info = _analyze(text)
            if info.get("_reason", "").endswith("_skip"):
                self._dlog(f"ch={ch_pid}|post={message.id}",
                           f"SKIP: {info['_reason']}", "WARN")
                return

            # Log trigger + analysis BEFORE any async calls
            self._dlog(f"ch={ch_pid}|post={message.id}",
                       f"TRIGGER MATCHED | text={text[:120]!r}")
            self._dlog(f"ch={ch_pid}|post={message.id}",
                       f"ANALYZE → targets={info['targets']} first_n={info['is_first_n']} "
                       f"fn={info['first_n']} req={info.get('required_text')!r} "
                       f"reason={info['_reason']}")

            disc_pid = await self._get_discussion(ch_pid)
            if disc_pid is None:
                self._dlog(f"ch={ch_pid}|post={message.id}",
                           "no discussion group — skip", "WARN")
                return

            if self.config["auto_join"]:
                await self._ensure_joined(disc_pid)

            if cfg["delay"] > 0:
                await asyncio.sleep(cfg["delay"])

            # Gather channel info
            ch_title   = await self._get_title(ch_pid)
            ch_username = None
            try:
                ch_ent = await self._client.get_entity(ch_pid)
                ch_username = getattr(ch_ent, "username", None)
            except Exception:
                pass

            # Get discussion thread ID for correct history fetch
            disc_thread_id = None
            try:
                di = await self._client(GetDiscussionMessageRequest(
                    peer=ch_ent if 'ch_ent' in dir() else await self._client.get_entity(ch_pid),
                    msg_id=message.id,
                ))
                if di and di.messages:
                    disc_thread_id = di.messages[0].id
            except Exception:
                pass

            hunt = {
                "ch_pid":        ch_pid,
                "ch_title":      ch_title,
                "ch_username":   ch_username,
                "ch_peer":       message.peer_id,
                "post_id":       message.id,
                "post_text":     text[:400],
                "disc_pid":      disc_pid,
                "disc_thread_id": disc_thread_id,
                "targets":       sorted(info["targets"]),
                "required_text": info.get("required_text"),
                "is_first_n":    info.get("is_first_n", False),
                "first_n":       info.get("first_n", 1),
                "cfg":           cfg,
                "sent_msgs":     [],
                "done":          set(),
                "started":       time.time(),
                "finished":      False,
                "notify_sent":   False,
                "lock":          asyncio.Lock(),
            }

            self._dlog(hunt, f"hunt created: targets={hunt['targets']} "
                             f"disc_thread_id={disc_thread_id}")

            # Kill previous hunt on this discussion
            old = self._hunting.get(disc_pid)
            if old:
                self._finish_hunt(old)
            self._hunting[disc_pid] = hunt

            first_target = hunt["targets"][0] if hunt["targets"] else 1

            if hunt["is_first_n"] or first_target == 1:
                self._dlog(hunt,
                           f"IMMEDIATE FIRE: is_first_n={hunt['is_first_n']} "
                           f"target={first_target} fn_count={hunt['first_n']}", "FIRE")
                hunt["done"].add(first_target)
                msgs = await self._spam(hunt)
                if msgs:
                    hunt["sent_msgs"].extend(msgs)
                    self._log(hunt, True)
                    self._dlog(hunt,
                               f"immediate sent {len(msgs)}: ids={[m.id for m in msgs]}", "OK")
                else:
                    self._dlog(hunt, "immediate spam returned 0 messages", "WARN")

                remaining = [t for t in hunt["targets"] if t not in hunt["done"]]
                if not remaining:
                    self._finish_hunt(hunt)
                    return
                self._dlog(hunt, f"remaining after immediate: {remaining}")
                asyncio.create_task(self._poll_sync(hunt))
            else:
                self._dlog(hunt,
                           f"poll mode: target={first_target} "
                           f"offset={self._get_offset(disc_pid)}")
                asyncio.create_task(self._poll_sync(hunt))

        except Exception as e:
            logger.error(f"[MultiFC] _on_post: {e}", exc_info=True)
            self._dlog(f"post:{message.id}", f"_on_post EXCEPTION: {e}", "ERR")

    # ── Commands ──────────────────────────────────────────────────────────────

    @loader.command(ru_doc="Статус MultiFC")
    async def mfc(self, message: Message):
        """Status"""
        await self._reload_channels()
        s = ("🔴 Выключен" if not self.config["status"]
             else ("⏸ Пауза" if self._paused else "🟢 Активен"))
        await utils.answer(message, self.strings["status"].format(
            status=s,
            channels=len(self._monitored),
            hunting=len(self._hunting),
            folder=self.config["folder_name"] or "не задана",
            ai=self.config["ai_provider"],
            trigs=len(self._get_triggers()),
        ))

    @loader.command(ru_doc="Пауза MultiFC")
    async def mfcpause(self, message: Message):
        """Pause"""
        self._paused = True
        await utils.answer(message, "⏸ <b>MultiFC приостановлен</b>")

    @loader.command(ru_doc="Возобновить MultiFC")
    async def mfcresume(self, message: Message):
        """Resume"""
        self._paused = False
        await utils.answer(message, "▶️ <b>MultiFC возобновлён</b>")

    @loader.command(ru_doc="Добавить канал. .mfcadd [id/@]")
    async def mfcadd(self, message: Message):
        """Add channel. .mfcadd [id/@ or reply]"""
        args = utils.get_args_raw(message).strip()
        entity = None
        if args:
            try:
                ref = int(args) if args.lstrip("-").isdigit() else args
                entity = await self._client.get_entity(ref)
            except Exception:
                pass
        if entity is None and message.is_reply:
            try:
                reply = await message.get_reply_message()
                entity = await self._client.get_entity(
                    self._pid(utils.get_chat_id(reply)))
            except Exception:
                pass
        if entity is None:
            await utils.answer(message, "❌ Укажи id/@username канала или ответь на пост")
            return

        cid  = str(entity.id)
        chs  = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            await utils.answer(message, "ℹ️ Уже в списке")
            return

        chs[cid] = {
            "title":    getattr(entity, "title", str(entity.id)),
            "username": getattr(entity, "username", None),
            "enabled":  True,
        }
        self.db.set("MultiFC", "channels", chs)
        self._monitored.add(self._pid(entity.id))
        await utils.answer(message,
                           f"✅ Добавлен: <b>{chs[cid]['title']}</b>\n<code>{cid}</code>")

    @loader.command(ru_doc="Удалить канал. .mfcdel [id/@]")
    async def mfcdel(self, message: Message):
        """Remove channel"""
        args = utils.get_args_raw(message).strip()
        if not args:
            await utils.answer(message, "❌ Укажи id или @username")
            return
        try:
            ref = int(args) if args.lstrip("-").isdigit() else args
            e = await self._client.get_entity(ref)
            cid = str(e.id)
        except Exception:
            await utils.answer(message, "❌ Канал не найден")
            return
        chs = self.db.get("MultiFC", "channels", {})
        if cid not in chs:
            await utils.answer(message, "⚠️ Канала нет в списке")
            return
        title = chs[cid].get("title", cid)
        del chs[cid]
        self.db.set("MultiFC", "channels", chs)
        self._monitored.discard(self._pid(int(cid)))
        await utils.answer(message, f"❌ Удалён: <b>{title}</b>")

    async def _all_channels(self) -> list:
        """All channels: manual + folder, deduped."""
        chs = self.db.get("MultiFC", "channels", {})
        result = {}
        for cid, info in chs.items():
            result[cid] = {**info, "_source": "manual"}
        if self.config["folder_name"]:
            folder_chs = await self._folder_channels(self.config["folder_name"])
            if folder_chs:
                for ch in folder_chs:
                    cid = str(ch.id)
                    if cid not in result:
                        result[cid] = {
                            "title": getattr(ch, "title", cid),
                            "username": getattr(ch, "username", None),
                            "enabled": True,
                            "_source": "folder",
                        }
        return [(cid, info) for cid, info in result.items()]

    @loader.command(ru_doc="Список каналов")
    async def mfclist(self, message: Message):
        """List all channels"""
        await self._reload_channels()
        all_ch = await self._all_channels()
        if not all_ch:
            await utils.answer(message, "📂 Список пуст. Добавь через <code>.mfcadd</code>")
            return
        text = f"<b>📋 Каналы MultiFC ({len(all_ch)} шт.)</b>\n\n"
        for cid, info in all_ch:
            src  = "📌" if info.get("_source") == "manual" else "📁"
            enbl = "🟢" if info.get("enabled", True) else "🔴"
            text += f"{src}{enbl} <b>{info.get('title', cid)}</b> <code>{cid}</code>\n"
        await utils.answer(message, text)

    @loader.command(ru_doc="Показать/перезагрузить папку")
    async def mfcfolder(self, message: Message):
        """Show folder channels"""
        fname = self.config["folder_name"]
        if not fname:
            await utils.answer(message, self.strings["no_folder"])
            return
        chs = await self._folder_channels(fname)
        if chs is None:
            await utils.answer(message, self.strings["folder_not_found"].format(name=fname))
            return
        await self._reload_channels()
        text = f"<b>📁 Папка: {fname} ({len(chs)} каналов)</b>\n\n"
        for ch in chs:
            text += f"• <b>{getattr(ch, 'title', ch.id)}</b> <code>{ch.id}</code>\n"
        await utils.answer(message, text)

    @loader.command(ru_doc="Управление триггерами. .mfctrig help")
    async def mfctrig(self, message: Message):
        """Manage triggers. .mfctrig help"""
        # Get FULL message text to support multiline add
        full_text = message.raw_text or ""
        # Remove the command prefix
        for prefix in [".mfctrig", "!mfctrig"]:
            if full_text.lower().startswith(prefix):
                after_cmd = full_text[len(prefix):].strip()
                break
        else:
            after_cmd = utils.get_args_raw(message).strip()

        if not after_cmd or after_cmd == "help":
            await utils.answer(message, self.strings["trig_help"])
            return

        # Split command from value (first line or first word)
        lines = after_cmd.splitlines()
        cmd   = lines[0].split()[0].lower() if lines else ""
        # For multiline add: everything after first line, OR rest of first line
        first_line_rest = " ".join(lines[0].split()[1:]).strip() if lines else ""
        extra_lines     = [l.strip() for l in lines[1:] if l.strip()]
        # Combined value
        if extra_lines:
            val_lines = ([first_line_rest] if first_line_rest else []) + extra_lines
        else:
            val_lines = [first_line_rest] if first_line_rest else []

        trigs = list(self._get_triggers())

        if cmd == "list":
            if not trigs:
                await utils.answer(message, "📋 Триггеров нет (реагирую на все посты)")
                return
            text = f"<b>🎯 Триггеры ({len(trigs)} шт.)</b>\n\n"
            for i, t in enumerate(trigs, 1):
                text += f"<b>{i}.</b> <code>{t[:100]}</code>\n"
            await utils.answer(message, text)

        elif cmd == "add":
            if not val_lines:
                await utils.answer(message,
                    "<b>❌ Укажи триггеры — каждый на новой строке:\n</b>"
                    "<code>.mfctrig add\nregex1\nregex2</code>")
                return
            added, bad = [], []
            for t in val_lines:
                try:
                    re.compile(t, re.IGNORECASE)
                    trigs.append(t)
                    added.append(t)
                except re.error as e:
                    bad.append(f"<code>{t[:60]}</code> — {e}")
            if added:
                self.db.set("MultiFC", "triggers", trigs)
            out = []
            if added:
                out.append(f"✅ Добавлено {len(added)} триггер(ов):")
                for t in added:
                    out.append(f"  • <code>{t[:80]}</code>")
            if bad:
                out.append(f"❌ Ошибки ({len(bad)}):")
                out.extend(bad)
            await utils.answer(message, "\n".join(out))

        elif cmd == "del":
            val = first_line_rest or (extra_lines[0] if extra_lines else "")
            try:
                idx = int(val) - 1
                removed = trigs.pop(idx)
                self.db.set("MultiFC", "triggers", trigs)
                await utils.answer(message,
                                   f"✅ Удалён #{idx+1}:\n<code>{removed[:80]}</code>")
            except (ValueError, IndexError):
                await utils.answer(message, "❌ Укажи правильный номер из <code>.mfctrig list</code>")

        elif cmd == "reset":
            self.db.set("MultiFC", "triggers", DEFAULT_TRIGGERS)
            await utils.answer(message,
                               f"✅ Сброшено к дефолтным ({len(DEFAULT_TRIGGERS)} триггеров)")

        elif cmd == "clear":
            self.db.set("MultiFC", "triggers", [])
            await utils.answer(message, "✅ Очищено — реагирую на все посты")

        else:
            await utils.answer(message, self.strings["trig_help"])

    @loader.command(ru_doc="Настройка канала. .mfcchan help")
    async def mfcchan(self, message: Message):
        """Per-channel settings. .mfcchan help"""
        raw = utils.get_args_raw(message).strip()
        if not raw or raw == "help":
            await utils.answer(message, self.strings["chan_help"])
            return

        parts = raw.split(maxsplit=2)
        cid_str, pi = None, 0

        first = parts[0]
        if first.lstrip("-").isdigit() or first.startswith("@"):
            try:
                ref = int(first) if first.lstrip("-").isdigit() else first
                e   = await self._client.get_entity(ref)
                cid_str = str(e.id)
                pi = 1
            except Exception:
                pass
        if cid_str is None:
            try:
                e = await self._client.get_entity(self._pid(utils.get_chat_id(message)))
                cid_str = str(e.id)
            except Exception:
                pass

        if cid_str is None or len(parts) <= pi:
            await utils.answer(message, self.strings["chan_help"])
            return

        param = parts[pi].lower() if len(parts) > pi else ""
        value = parts[pi + 1].strip() if len(parts) > pi + 1 else ""

        chs = self.db.get("MultiFC", "channels", {})
        if cid_str not in chs:
            await utils.answer(message, self.strings["ch_not_found"])
            return
        ch = chs[cid_str]

        bool_val = value.lower() in ("true", "1", "yes", "да")

        if param == "info":
            text = (f"⚙️ <b>{ch.get('title', cid_str)}</b> <code>{cid_str}</code>\n\n"
                    f"enabled: {ch.get('enabled', True)}\n"
                    f"delay: {ch.get('delay', self.config['global_delay'])}\n"
                    f"spam_count: {ch.get('spam_count', self.config['spam_count'])}\n"
                    f"use_ai: {ch.get('use_ai', False)}\n"
                    f"only_triggers: {ch.get('only_triggers', False)}\n"
                    f"only_msgs: {ch.get('only_msgs', False)}\n"
                    f"lock_global: {ch.get('lock_global', False)}\n"
                    f"custom_triggers: {len(ch.get('custom_triggers', []))}\n"
                    f"custom_messages: {len(ch.get('custom_messages', []))}")
            await utils.answer(message, text)
            return

        if param in ("enabled", "use_ai", "only_triggers", "only_msgs", "lock_global"):
            ch[param] = bool_val
        elif param == "delay":
            ch["delay"] = float(value)
        elif param == "spam_count":
            ch["spam_count"] = max(1, min(10, int(value)))
        elif param == "add_trigger":
            try:
                re.compile(value, re.I)
                ch.setdefault("custom_triggers", []).append(value)
            except re.error as e:
                await utils.answer(message, f"❌ Невалидный regex: {e}")
                return
        elif param == "del_trigger":
            lst = ch.get("custom_triggers", [])
            if value in lst:
                lst.remove(value)
            ch["custom_triggers"] = lst
        elif param == "add_msg":
            ch.setdefault("custom_messages", []).append(value)
        elif param == "del_msg":
            lst = ch.get("custom_messages", [])
            if value in lst:
                lst.remove(value)
            ch["custom_messages"] = lst
        else:
            await utils.answer(message, f"❌ Неизвестный параметр: <code>{param}</code>")
            return

        chs[cid_str] = ch
        self.db.set("MultiFC", "channels", chs)
        await utils.answer(message, f"✅ <code>{param}</code> обновлён")

    @loader.command(ru_doc="История охот")
    async def mfclogs(self, message: Message):
        """Hunt history log"""
        if not self._logs:
            await utils.answer(message, "📋 Логов пока нет")
            return
        text = "<b>📋 MultiFC — История</b>\n\n"
        for e in reversed(self._logs[-25:]):
            t    = time.strftime("%d.%m %H:%M", time.localtime(e["ts"]))
            icon = "🏆" if e["ok"] else "❌"
            text += (f"{icon} <code>{t}</code> <b>{e['channel']}</b> "
                     f"[{', '.join(map(str, e.get('targets', [])))}]\n"
                     f"   {e['count']} сообщ. • <i>{e['post'][:50]}</i>\n\n")
        await utils.answer(message, text)

    @loader.command(ru_doc="Детальный дебаг лог. .mfcdlog [N] [hunt] [clear]")
    async def mfcdlog(self, message: Message):
        """Debug log. .mfcdlog [N=60] | hunt | clear"""
        args = utils.get_args_raw(message).strip().lower()

        if args == "clear":
            n = len(self._dlogs)
            self._dlogs.clear()
            await utils.answer(message, f"🗑 Лог очищен ({n} записей)")
            return

        if args in ("hunt", "hunts", "fire"):
            keywords = ("FIRE", "HUNT FINISHED", "ANALYZE", "TRIGGER", "sent", "result=", "SKIP")
            lines = [l for l in self._dlogs if any(k in l for k in keywords)]
            if not lines:
                await utils.answer(message, "📋 Нет hunt-событий")
                return
            body = "\n".join(f"<code>{l.replace('<','&lt;').replace('>','&gt;')}</code>"
                             for l in lines[-50:])
            await utils.answer(message,
                f"<b>🎯 Hunt-события ({len(lines)} шт.):</b>\n\n{body}")
            return

        try:
            n = max(10, min(300, int(args))) if args else 60
        except ValueError:
            n = 60

        if not self._dlogs:
            await utils.answer(message, "📋 Debug-лог пуст")
            return

        selected = self._dlogs[-n:]
        header = (f"<b>🔍 MultiFC Debug-лог</b> ({len(selected)}/{len(self._dlogs)})\n"
                  f"Охот активно: {len(self._hunting)} • "
                  f"<i>.mfcdlog N | hunt | clear</i>\n\n")

        chunks, cur, cur_len = [], [], 0
        for line in selected:
            safe  = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            entry = f"<code>{safe}</code>\n"
            if cur_len + len(entry) > 3500:
                chunks.append(cur)
                cur, cur_len = [entry], len(entry)
            else:
                cur.append(entry)
                cur_len += len(entry)
        if cur:
            chunks.append(cur)

        for i, chunk in enumerate(chunks):
            txt = (header if i == 0 else "") + "".join(chunk)
            if i == 0:
                await utils.answer(message, txt.strip())
            else:
                await message.respond(txt.strip())

    @loader.command(ru_doc="Быстрые настройки. .mfcs help")
    async def mfcs(self, message: Message):
        """Quick settings. .mfcs help"""
        raw = utils.get_args_raw(message).strip()
        if not raw or raw == "help":
            await utils.answer(message, (
                "<b>⚙️ .mfcs — Быстрые настройки</b>\n\n"
                "<b>Глобальные:</b>\n"
                "<code>.mfcs delay 0.5</code>\n"
                "<code>.mfcs spam 5</code>\n"
                "<code>.mfcs ai gemini|groq|none</code>\n"
                "<code>.mfcs folder Название</code>\n"
                "<code>.mfcs msgs +текст</code> / <code>-текст</code> / <code>т1|т2</code>\n"
                "<code>.mfcs trigs +regex</code> / <code>-N</code> / <code>reset</code>\n\n"
                "<b>На канал:</b>\n"
                "<code>.mfcs @channel delay 1</code>\n"
                "<code>.mfcs @channel spam 3</code>\n"
                "<code>.mfcs @channel ai true/false</code>\n"
                "<code>.mfcs @channel enabled true/false</code>\n"
                "<code>.mfcs @channel msgs +текст</code>\n"
                "<code>.mfcs @channel trigs +regex</code>"
            ))
            return

        parts = raw.split(maxsplit=2)
        cid_str, pi = None, 0
        first = parts[0]
        if first.startswith("@") or (first.lstrip("-").isdigit() and len(first) > 5):
            try:
                ref = int(first) if first.lstrip("-").isdigit() else first
                e   = await self._client.get_entity(ref)
                cid_str = str(e.id)
                pi = 1
            except Exception:
                pass

        if len(parts) <= pi:
            await utils.answer(message, "❌ Укажи параметр")
            return

        param = parts[pi].lower() if len(parts) > pi else ""
        value = parts[pi+1].strip() if len(parts) > pi+1 else ""

        # Channel-level
        if cid_str:
            chs = self.db.get("MultiFC", "channels", {})
            if cid_str not in chs:
                await utils.answer(message, self.strings["ch_not_found"])
                return
            ch = chs[cid_str]
            if param == "delay":
                ch["delay"] = float(value)
            elif param == "spam":
                ch["spam_count"] = max(1, min(10, int(value)))
            elif param == "ai":
                ch["use_ai"] = value.lower() in ("true","1","yes","да")
            elif param == "enabled":
                ch["enabled"] = value.lower() in ("true","1","yes","да")
            elif param in ("only_triggers","only_msgs","lock_global"):
                ch[param] = value.lower() in ("true","1","yes","да")
            elif param == "msgs":
                lst = ch.setdefault("custom_messages", [])
                if value.startswith("+"):
                    lst.append(value[1:].strip())
                elif value.startswith("-"):
                    v = value[1:].strip()
                    if v in lst: lst.remove(v)
                else:
                    ch["custom_messages"] = [x.strip() for x in value.split("|") if x.strip()]
            elif param == "trigs":
                lst = ch.setdefault("custom_triggers", [])
                if value.startswith("+"):
                    v = value[1:].strip()
                    try:
                        re.compile(v, re.I)
                        lst.append(v)
                    except re.error as e:
                        await utils.answer(message, f"❌ Невалидный regex: {e}")
                        return
                elif value.startswith("-"):
                    v = value[1:].strip()
                    if v in lst: lst.remove(v)
                else:
                    ch["custom_triggers"] = [x.strip() for x in value.split("|") if x.strip()]
            else:
                await utils.answer(message, f"❌ Неизвестный параметр: {param}")
                return
            chs[cid_str] = ch
            self.db.set("MultiFC", "channels", chs)
            await utils.answer(message, f"✅ {param} обновлён")

        # Global
        else:
            if param == "delay":
                self.config["global_delay"] = float(value)
                await utils.answer(message, f"✅ global_delay = <code>{value}</code>")
            elif param == "spam":
                self.config["spam_count"] = max(1, min(10, int(value)))
                await utils.answer(message, f"✅ spam_count = <code>{self.config['spam_count']}</code>")
            elif param == "ai":
                if value not in ("gemini","groq","none"):
                    await utils.answer(message, "❌ Только: gemini / groq / none")
                    return
                self.config["ai_provider"] = value
                await utils.answer(message, f"✅ ai = <code>{value}</code>")
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
                    await utils.answer(message, f"✅ Добавлено: <code>{v}</code>")
                elif value.startswith("-"):
                    v = value[1:].strip()
                    if v in lst:
                        lst.remove(v)
                        self.config["global_messages"] = lst
                        await utils.answer(message, f"✅ Удалено: <code>{v}</code>")
                    else:
                        await utils.answer(message, "❌ Не найдено")
                else:
                    self.config["global_messages"] = [x.strip() for x in value.split("|") if x.strip()]
                    await utils.answer(message, f"✅ Сообщений: {len(self.config['global_messages'])}")
            elif param == "trigs":
                trigs = list(self._get_triggers())
                if value.startswith("+"):
                    v = value[1:].strip()
                    try:
                        re.compile(v, re.I)
                        trigs.append(v)
                        self.db.set("MultiFC", "triggers", trigs)
                        await utils.answer(message, f"✅ Добавлен: <code>{v}</code>")
                    except re.error as e:
                        await utils.answer(message, f"❌ Невалидный regex: {e}")
                elif value.startswith("-"):
                    v = value[1:].strip()
                    if v.isdigit():
                        idx = int(v) - 1
                        if 0 <= idx < len(trigs):
                            removed = trigs.pop(idx)
                            self.db.set("MultiFC", "triggers", trigs)
                            await utils.answer(message, f"✅ Удалён: <code>{removed[:60]}</code>")
                        else:
                            await utils.answer(message, "❌ Неверный номер")
                    elif v in trigs:
                        trigs.remove(v)
                        self.db.set("MultiFC", "triggers", trigs)
                        await utils.answer(message, "✅ Удалён")
                    else:
                        await utils.answer(message, "❌ Не найден")
                elif value == "reset":
                    self.db.set("MultiFC", "triggers", DEFAULT_TRIGGERS)
                    await utils.answer(message, f"✅ Сброшено ({len(DEFAULT_TRIGGERS)} триггеров)")
                elif value == "clear":
                    self.db.set("MultiFC", "triggers", [])
                    await utils.answer(message, "✅ Очищено")
                else:
                    await utils.answer(message, "❌ Используй +regex / -N / reset / clear")
            else:
                await utils.answer(message, f"❌ Неизвестный параметр: {param}")

    # ── Inline panel ──────────────────────────────────────────────────────────

    def _panel_main_markup(self):
        return [
            [
                {"text": "▶️ Продолжить" if self._paused else "⏸ Пауза",
                 "callback": self._cb_toggle_pause},
                {"text": "🔄 Обновить", "callback": self._cb_refresh_main},
            ],
            [
                {"text": "📋 Каналы", "callback": self._cb_channels_page},
                {"text": "🎯 Триггеры", "callback": self._cb_triggers_page},
            ],
            [{"text": "📊 Логи", "callback": self._cb_logs_page}],
        ]

    def _panel_main_text(self):
        s = ("🔴 Выключен" if not self.config["status"]
             else ("⏸ Пауза" if self._paused else "🟢 Активен"))
        return self.strings["status"].format(
            status=s,
            channels=len(self._monitored),
            hunting=len(self._hunting),
            folder=self.config["folder_name"] or "не задана",
            ai=self.config["ai_provider"],
            trigs=len(self._get_triggers()),
        )

    @loader.command(ru_doc="Открыть панель управления")
    async def mfcp(self, message: Message):
        """Open inline panel"""
        await self._reload_channels()
        await self.inline.form(
            message=message,
            text=self._panel_main_text(),
            reply_markup=self._panel_main_markup(),
        )

    async def _cb_refresh_main(self, call):
        await self._reload_channels()
        await call.edit(text=self._panel_main_text(), reply_markup=self._panel_main_markup())

    async def _cb_toggle_pause(self, call):
        self._paused = not self._paused
        await call.answer("⏸ Пауза" if self._paused else "▶️ Продолжен")
        await self._cb_refresh_main(call)

    async def _cb_channels_page(self, call, page: int = 0):
        all_ch = await self._all_channels()
        per = 5
        pages = max(1, (len(all_ch) + per - 1) // per)
        page  = max(0, min(page, pages - 1))
        chunk = all_ch[page * per:(page + 1) * per]
        chs_db = self.db.get("MultiFC", "channels", {})

        text  = f"<b>📋 Каналы ({len(all_ch)} шт.) — стр. {page+1}/{pages}</b>\n\n"
        for cid, info in chunk:
            src  = "📌" if info.get("_source") == "manual" else "📁"
            enbl = "🟢" if info.get("enabled", True) else "🔴"
            text += f"{src}{enbl} {info.get('title', cid)}\n"

        btns = []
        for cid, info in chunk:
            btns.append([{
                "text": f"⚙️ {info.get('title', cid)[:25]}",
                "callback": self._cb_chan_detail,
                "args": (cid,),
            }])
        nav = []
        if page > 0:
            nav.append({"text": "◀️", "callback": self._cb_channels_page, "args": (page-1,)})
        if page < pages - 1:
            nav.append({"text": "▶️", "callback": self._cb_channels_page, "args": (page+1,)})
        if nav:
            btns.append(nav)
        btns.append([{"text": "🔙 Назад", "callback": self._cb_refresh_main}])
        await call.edit(text=text, reply_markup=btns)

    async def _cb_chan_detail(self, call, cid: str):
        chs = self.db.get("MultiFC", "channels", {})
        ch  = chs.get(cid, {})
        in_db = bool(ch)

        title   = ch.get("title", cid) if in_db else cid
        enabled = ch.get("enabled", True)
        delay   = ch.get("delay", self.config["global_delay"])
        spam    = ch.get("spam_count", self.config["spam_count"])
        use_ai  = ch.get("use_ai", False)
        only_t  = ch.get("only_triggers", False)
        only_m  = ch.get("only_msgs", False)
        lock_g  = ch.get("lock_global", False)
        c_trigs = ch.get("custom_triggers", [])
        c_msgs  = ch.get("custom_messages", [])

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
            btns.append([
                {"text": "🔴 Выкл" if enabled else "🟢 Вкл",
                 "callback": self._cb_chan_toggle, "args": (cid,)},
                {"text": "🤖 AI: выкл" if use_ai else "🤖 AI: вкл",
                 "callback": self._cb_chan_ai, "args": (cid,)},
            ])
            btns.append([
                {"text": f"{'✅' if only_t else '☑️'} Свои тригеры",
                 "callback": self._cb_chan_flag, "args": (cid, "only_triggers")},
                {"text": f"{'✅' if only_m else '☑️'} Свои сообщения",
                 "callback": self._cb_chan_flag, "args": (cid, "only_msgs")},
            ])
            btns.append([
                {"text": f"{'✅' if lock_g else '☑️'} Заморозить глобал",
                 "callback": self._cb_chan_flag, "args": (cid, "lock_global")},
            ])
            btns.append([
                {"text": f"📨 Спам {spam}x  ➖",
                 "callback": self._cb_chan_spam, "args": (cid, -1)},
                {"text": "➕", "callback": self._cb_chan_spam, "args": (cid, 1)},
            ])
            btns.append([
                {"text": f"⏱ {delay}s  ➖",
                 "callback": self._cb_chan_delay, "args": (cid, -0.5)},
                {"text": "➕", "callback": self._cb_chan_delay, "args": (cid, 0.5)},
            ])
            btns.append([{"text": "🗑 Удалить канал",
                          "callback": self._cb_chan_remove, "args": (cid,)}])
        btns.append([{"text": "🔙 Каналы", "callback": self._cb_channels_page}])
        await call.edit(text=text, reply_markup=btns)

    async def _cb_chan_toggle(self, call, cid: str):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            chs[cid]["enabled"] = not chs[cid].get("enabled", True)
            self.db.set("MultiFC", "channels", chs)
            await call.answer("🟢 Включён" if chs[cid]["enabled"] else "🔴 Выключен")
        await self._cb_chan_detail(call, cid)

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
            await call.answer(f"{flag} = {chs[cid][flag]}")
        await self._cb_chan_detail(call, cid)

    async def _cb_chan_spam(self, call, cid: str, delta: int):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            cur = chs[cid].get("spam_count", self.config["spam_count"])
            chs[cid]["spam_count"] = max(1, min(10, cur + delta))
            self.db.set("MultiFC", "channels", chs)
            await call.answer(f"📨 {chs[cid]['spam_count']}x")
        await self._cb_chan_detail(call, cid)

    async def _cb_chan_delay(self, call, cid: str, delta: float):
        chs = self.db.get("MultiFC", "channels", {})
        if cid in chs:
            cur = chs[cid].get("delay", self.config["global_delay"])
            chs[cid]["delay"] = round(max(0.0, cur + delta), 1)
            self.db.set("MultiFC", "channels", chs)
            await call.answer(f"⏱ {chs[cid]['delay']}s")
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
        per   = 5
        pages = max(1, (len(trigs) + per - 1) // per)
        page  = max(0, min(page, pages - 1))
        chunk = trigs[page * per:(page + 1) * per]
        start = page * per

        text = f"<b>🎯 Триггеры ({len(trigs)} шт.) — стр. {page+1}/{pages}</b>\n\n"
        for i, t in enumerate(chunk, start + 1):
            text += f"<b>{i}.</b> <code>{t[:80]}</code>\n\n"

        btns = []
        for i, _ in enumerate(chunk):
            btns.append([{"text": f"🗑 Удалить #{start+i+1}",
                          "callback": self._cb_trig_del, "args": (start+i,)}])
        nav = []
        if page > 0:
            nav.append({"text": "◀️", "callback": self._cb_triggers_page, "args": (page-1,)})
        if page < pages - 1:
            nav.append({"text": "▶️", "callback": self._cb_triggers_page, "args": (page+1,)})
        if nav:
            btns.append(nav)
        btns.append([
            {"text": "🔄 Дефолт", "callback": self._cb_trig_reset},
            {"text": "🗑 Очистить", "callback": self._cb_trig_clear},
        ])
        btns.append([{"text": "🔙 Назад", "callback": self._cb_refresh_main}])
        await call.edit(text=text, reply_markup=btns)

    async def _cb_trig_del(self, call, idx: int):
        trigs = list(self._get_triggers())
        if 0 <= idx < len(trigs):
            trigs.pop(idx)
            self.db.set("MultiFC", "triggers", trigs)
            await call.answer(f"✅ Удалён #{idx+1}")
        await self._cb_triggers_page(call)

    async def _cb_trig_reset(self, call):
        self.db.set("MultiFC", "triggers", DEFAULT_TRIGGERS)
        await call.answer(f"✅ Сброшено ({len(DEFAULT_TRIGGERS)})")
        await self._cb_triggers_page(call)

    async def _cb_trig_clear(self, call):
        self.db.set("MultiFC", "triggers", [])
        await call.answer("✅ Очищено")
        await self._cb_triggers_page(call)

    async def _cb_logs_page(self, call):
        if not self._logs:
            await call.answer("📋 Нет логов")
            return
        text = "<b>📋 История (последние 15)</b>\n\n"
        for e in reversed(self._logs[-15:]):
            t    = time.strftime("%H:%M", time.localtime(e["ts"]))
            icon = "🏆" if e["ok"] else "❌"
            text += (f"{icon} <code>{t}</code> <b>{e['channel']}</b> "
                     f"[{','.join(map(str,e.get('targets',[])))}]\n"
                     f"   {e['count']} сообщ. • {e['post'][:40]}\n\n")
        btns = [[{"text": "🔙 Назад", "callback": self._cb_refresh_main}]]
        await call.edit(text=text, reply_markup=btns)