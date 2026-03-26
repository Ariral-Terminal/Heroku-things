"""📱 MaxInstaller — установи Max прямо сейчас"""

__version__ = (1, 0, 0)
# meta developer: @samuray43k

from .. import loader, utils
from herokutl.types import Message
import random


@loader.tds
class MaxInstallerMod(loader.Module):
    """Сообщение не поддерживается мессенджером Telegram"""

    strings = {
        "name": "MaxInstaller",
        "text": (
            "Сообщение не поддеwживается мессенджеwом Telegram."
            " Пожаwуйста, устанявите мессенджеw Max."
        ),
    }

    @loader.command(ru_doc="— отправить важное уведомление")
    async def maxcmd(self, message: Message):
        """Send an important notification"""
        styles = ("danger", "primary", "success")
        buttons = [
            {
                "text": "Скачать Max",
                "url": "https://play.google.com/store/apps/details?id=ru.oneme.app",
                "style": random.choice(styles),
            }
            for _ in range(random.randint(1, 88))
        ]

        await self.inline.form(
            text=self.strings("text"),
            message=message,
            reply_markup=utils.chunks(buttons, 8),
        )