# meta developer: @xdesai /@desertedowl / @klaucc
import logging
from ..inline.types import InlineCall, InlineQuery
from .. import loader

@loader.tds
class SecretMessageMod(loader.Module):
    strings = {
        "name": "SecretMessage",
        "for_user_message": "🔐 Secret message for <b><a href='tg://user?id={id}'>{name}</a></b>",
        "open": "👀 Open",
        "no_user_or_message": "Specify the user and the message",
        "secret_message": "Secret message",
        "send_message": "Send secret message for {name}",
        "help_message": "<b>Usage:</b>\n<code>@{bot} whisper (id/username) (text)</code>",
        "not_for_you": "❌ Not for you",
        "eaten": "😽 The message was eaten by cats"
    }

    strings_ru = {
        "name": "SecretMessage",
        "for_user_message": "🔐 Секретное сообщение для <b><a href='tg://user?id={id}'>{name}</a></b>",
        "open": "👀 Открыть",
        "no_user_or_message": "Укажите пользователя и сообщение",
        "secret_message": "Секретное сообщение",
        "send_message": "Отправить секретное сообщение для {name}",
        "help_message": "<b>Использование:</b>\n<code>@{bot} whisper (id/username) (текст)</code>",
        "not_for_you": "❌ Не для тебя",
        "eaten": "😽 Ты попытался прочитать второй раз, котик съел это сообщение."
    }

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self._oppened_messages = []

    @loader.inline_handler(ru_doc="Секретное сообщение для пользователя")
    async def whisper(self, query: InlineQuery):
        if len(query.args.split()) > 1:
            try:
                args = query.args.split()
                user_input = args[0]
                text = " ".join(args[1:])
                
                if user_input.isdigit():
                    for_user = await self._client.get_entity(int(user_input))
                else:
                    for_user = await self._client.get_entity(user_input)
                    
                return {
                    "title": self.strings("secret_message"),
                    "description": self.strings("send_message").format(name=for_user.first_name),
                    "message": self.strings("for_user_message").format(id=for_user.id, name=for_user.first_name),
                    "thumb": "https://img.icons8.com/?size=100&id=kDMAGBvpqAyW&format=png&color=000000",
                    "reply_markup": {
                        "text": self.strings("open"),
                        "callback": self._handler,
                        "args": (text, for_user),
                        "disable_security": True
                    },
                }
            except Exception as e:
                logging.error(f"Error getting user: {e}")
                return {
                    "title": self.strings("secret_message"),
                    "description": self.strings("no_user_or_message"),
                    "message": self.strings("help_message").format(bot=(await self.inline.bot.get_me()).username),
                    "thumb": "https://img.icons8.com/?size=100&id=T9nkeADgD3z6&format=png&color=000000",
                }
        else:
            return {
                "title": self.strings("secret_message"),
                "description": self.strings("no_user_or_message"),
                "message": self.strings("help_message").format(bot=(await self.inline.bot.get_me()).username),
                "thumb": "https://img.icons8.com/?size=100&id=T9nkeADgD3z6&format=png&color=000000",
            }

    async def _handler(self, call: InlineCall, text: str, for_user):
        if call.from_user.id == self._tg_id:
            await call.answer(f"{text}", show_alert=True)
            return
        if call.from_user.id != for_user.id:
            await call.answer(self.strings("not_for_you"), show_alert=True)
            return
        if call.inline_message_id in self._oppened_messages:
            await call.answer(self.strings("eaten"), show_alert=True)
            return
        
        await call.answer(f"{text}", show_alert=True)
        self._oppened_messages.append(call.inline_message_id)