# meta developer: @crow

__version__ = (1, 4, 3)

import re
from datetime import datetime, timezone, timedelta

from telethon.tl.functions.help import GetPremiumPromoRequest

from .. import loader, utils


@loader.tds
class PremiumStatusMod(loader.Module):
    """Shows Telegram Premium status and expiration date if available."""

    strings = {
        "name": "PremiumStatus",
        "_cls_doc": "Shows Telegram Premium status and expiration date if available.",
        "_cmd_doc_ot": "Show Telegram Premium subscription status.",
        "no_premium": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>You do not have Telegram Premium.</b>",
        "unknown": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Failed to determine Premium expiration date.</b>",
        "active_days": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium expires in: </b><code>{days}</code><b> day(s).</b>",
        "active_today": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium expires today.</b>",
        "active_expired": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium has already expired.</b>",
        "active_date": "<tg-emoji emoji-id=5202083316836088030>❄️</tg-emoji> <b>Premium is active until: </b><code>{date}</code>",
        "error": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Error while getting Premium status:</b> <code>{}</code>",
    }

    strings_ru = {
        "_cls_doc": "Показывает статус Telegram Premium и дату окончания, если доступна.",
        "_cmd_doc_ot": "Показать статус подписки Telegram Premium.",
        "no_premium": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>У вас нет Telegram Premium.</b>",
        "unknown": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Не удалось определить дату окончания Premium.</b>",
        "active_days": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium закончится через: </b><code>{days}</code><b> дн.</b>",
        "active_today": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium истекает сегодня.</b>",
        "active_expired": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Срок действия Premium уже истёк.</b>",
        "active_date": "<tg-emoji emoji-id=5202083316836088030>❄️</tg-emoji> <b>Premium активен до: </b><code>{date}</code>",
        "error": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Ошибка при получении статуса Premium:</b> <code>{}</code>",
    }

    strings_kz = {
        "_cls_doc": "Telegram Premium мәртебесін және мүмкін болса аяқталу күнін көрсетеді.",
        "_cmd_doc_ot": "Telegram Premium жазылым мәртебесін көрсету.",
        "no_premium": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Сізде Telegram Premium жоқ.</b>",
        "unknown": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium аяқталу күнін анықтау мүмкін болмады.</b>",
        "active_days": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium аяқталуына: </b><code>{days}</code><b> күн қалды.</b>",
        "active_today": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium бүгін аяқталады.</b>",
        "active_expired": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium мерзімі өтіп кеткен.</b>",
        "active_date": "<tg-emoji emoji-id=5202083316836088030>❄️</tg-emoji> <b>Premium келесі күнге дейін белсенді: </b><code>{date}</code>",
        "error": "<tg-emoji emoji-id=5226780705933007535>☠️</tg-emoji> <b>Premium мәртебесін алу қатесі:</b> <code>{}</code>",
    }

    async def client_ready(self, client, db):
        self._client = client

    async def otcmd(self, message):
        """Show Telegram Premium subscription status."""
        try:
            prem = await self._client(GetPremiumPromoRequest())
        except Exception as e:
            await utils.answer(message, self.strings("error").format(utils.escape_html(str(e))))
            return

        status_text = getattr(prem, "status_text", "") or ""

        if self._is_no_premium(status_text):
            await utils.answer(message, self.strings("no_premium"))
            return

        date = self._extract_date(status_text)
        if not date:
            await utils.answer(message, self.strings("unknown"))
            return

        try:
            expiry_date = datetime.strptime(date, "%d.%m.%Y").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            end_of_day = expiry_date + timedelta(days=1)
            remaining_days = max((end_of_day - now).days, 0)
        except Exception:
            await utils.answer(message, self.strings("active_date").format(date=utils.escape_html(date)))
            return

        if end_of_day <= now:
            await utils.answer(
                message,
                self.strings("active_expired") + "\n" + self.strings("active_date").format(date=utils.escape_html(date)),
            )
            return

        if expiry_date.date() == now.date():
            await utils.answer(
                message,
                self.strings("active_today") + "\n" + self.strings("active_date").format(date=utils.escape_html(date)),
            )
            return

        await utils.answer(
            message,
            self.strings("active_days").format(days=remaining_days)
            + "\n"
            + self.strings("active_date").format(date=utils.escape_html(date)),
        )

    def _is_no_premium(self, text: str) -> bool:
        text = (text or "").lower()
        markers = [
            "by subscribing to telegram premium",
            "no premium",
            "subscribe to telegram premium",
            "telegram premium to unlock",
            "unlock with telegram premium",
            "get telegram premium",
        ]
        return any(marker in text for marker in markers)

    def _extract_date(self, text: str):
        patterns = [
            (r"(\d{1,2}\.\d{1,2}\.\d{4})", "%d.%m.%Y"),
            (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
            (r"(\d{1,2}/\d{1,2}/\d{4})", "%d/%m/%Y"),
        ]

        for pattern, fmt in patterns:
            match = re.search(pattern, text or "")
            if not match:
                continue

            raw = match.group(1)
            try:
                return datetime.strptime(raw, fmt).strftime("%d.%m.%Y")
            except Exception:
                continue

        return None