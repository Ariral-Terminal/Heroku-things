# Name: ReactionWatcher
# Description: Informs when someone reacts to your messages in chats
# Author: @desertedowl
# ---------------------------------------------------------------------------------
# meta developer: @desertedowl
# meta banner: https://raw.githubusercontent.com/Ariral-Terminal/Heroku-things/main/reactionwatcher.png
# scope: heroku_min 2.0.0
# ---------------------------------------------------------------------------------

import logging
import time
from typing import NamedTuple, Optional

from telethon.tl.functions.messages import (
    GetCustomEmojiDocumentsRequest,
    GetStickerSetRequest,
    ReadReactionsRequest,
)
from telethon.tl.types import PeerUser, UpdateMessageReactions

from .. import loader, main, utils

logger = logging.getLogger("ReactionWatcher")


class Entry(NamedTuple):
    """Entry for delayed read-reactions queue."""

    peer: object
    schedule: float
    top_msg_id: Optional[int] = None


@loader.tds
class ReactionWatcher(loader.Module):
    """Informs when someone reacts to your messages in chats."""

    strings = {
        "name": "ReactionWatcher",
        "_cmd_doc_reactionwatcher": "(<code>{prefix}tw</code>)Enable/Disable ReactionWatcher.",
        "_cfg_doc_custom_notif_text": (
            "Custom notification text. Available variables: {title}, {chat_id}, {name},"
            " {user_id}, {reaction}, {msg_content}, {link}."
        ),
        "_cfg_doc_ignore_bots": "Ignore reactions from bots.",
        "_cfg_doc_ignore_chats": "List of chat IDs to ignore reactions from.",
        "_cfg_doc_ignore_users": "List of user IDs to ignore reactions from.",
        "_cfg_doc_blacklist_chats": "List of chat IDs to ignore notifications from.",
        "_cfg_doc_blacklist_users": "List of user IDs to ignore notifications from.",
        "_cfg_doc_autoread_reactions": "Automatically mark unread reactions as read.",
        "enabled": "<emoji document_id=5208808350858364013>✅</emoji> <b>ReactionWatcher enabled.</b>",
        "disabled": "<emoji document_id=5219776129669276751>❌</emoji> <b>ReactionWatcher disabled.</b>",
        "reacted": (
            "<b>{name}</b> reacted with {reaction}\n"
            "<b>Chat:</b> <code>{title}</code> [<code>{chat_id}</code>]\n"
            "<b>User ID:</b> <code>{user_id}</code>\n"
            "<b>Message:</b> {msg_content}\n\n"
            "<a href='{link}'>Open message</a>"
        ),
        "no_message_content": "❓ Empty message text",
    }

    strings_ru = {
        "_cls_doc": "Сообщает, когда кто-то реагирует на ваши сообщения в чатах.",
        "_cmd_doc_reactionwatcher": "Вкл/выкл ReactionWatcher (алиас: rw).",
        "_cfg_doc_custom_notif_text": (
            "Пользовательский текст уведомления. Доступные переменные: {title}, "
            "{chat_id}, {name}, {user_id}, {reaction}, {msg_content}, {link}."
        ),
        "_cfg_doc_ignore_bots": "Игнорировать реакции от ботов.",
        "_cfg_doc_ignore_chats": "Список ID чатов, от которых реакции будут игнорироваться.",
        "_cfg_doc_ignore_users": "Список ID пользователей, от которых реакции будут игнорироваться.",
        "_cfg_doc_blacklist_chats": "Список ID чатов, от которых уведомления не будут приходить.",
        "_cfg_doc_blacklist_users": "Список ID пользователей, от которых уведомления не будут приходить.",
        "_cfg_doc_autoread_reactions": "Автоматически отмечать непрочитанные реакции как прочитанные.",
        "enabled": "<emoji document_id=5208808350858364013>✅</emoji> <b>ReactionWatcher включен.</b>",
        "disabled": "<emoji document_id=5219776129669276751>❌</emoji> <b>ReactionWatcher выключен.</b>",
        "reacted": (
            "<b>{name}</b> отреагировал(а): {reaction}\n"
            "<b>Чат:</b> <code>{title}</code> [<code>{chat_id}</code>]\n"
            "<b>ID пользователя:</b> <code>{user_id}</code>\n"
            "<b>Сообщение:</b> {msg_content}\n\n"
            "<a href='{link}'>Перейти к сообщению</a>"
        ),
        "no_message_content": "❓ Пустой текст сообщения",
    }

    def __init__(self):
        self._queue = []
        self._flood_protect = []
        self._flood_protect_sample = 60
        self._threshold = 10
        self._me_id = 0
        self._custom_emoji_cache = {}
        self._emoji_pack_cache = {}

        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "custom_notif_text",
                None,
                doc=lambda: self.strings["_cfg_doc_custom_notif_text"],
                validator=loader.validators.Union(
                    loader.validators.String(), loader.validators.NoneType()
                ),
            ),
            loader.ConfigValue(
                "ignore_bots",
                True,
                doc=lambda: self.strings["_cfg_doc_ignore_bots"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "ignore_chats",
                [],
                doc=lambda: self.strings["_cfg_doc_ignore_chats"],
                validator=loader.validators.Series(
                    validator=loader.validators.TelegramID()
                ),
            ),
            loader.ConfigValue(
                "blacklist_chats",
                [],
                doc=lambda: self.strings["_cfg_doc_blacklist_chats"],
                validator=loader.validators.Series(
                    validator=loader.validators.TelegramID()
                ),
            ),
            loader.ConfigValue(
                "ignore_users",
                [],
                doc=lambda: self.strings["_cfg_doc_ignore_users"],
                validator=loader.validators.Series(
                    validator=loader.validators.TelegramID()
                ),
            ),
            loader.ConfigValue(
                "blacklist_users",
                [],
                doc=lambda: self.strings["_cfg_doc_blacklist_users"],
                validator=loader.validators.Series(
                    validator=loader.validators.TelegramID()
                ),
            ),
            loader.ConfigValue(
                "autoread_reactions",
                True,
                doc=lambda: self.strings["_cfg_doc_autoread_reactions"],
                validator=loader.validators.Boolean(),
            ),
        )

    async def client_ready(self):
        me = await self._client.get_me()
        self._me_id = me.id if me else 0
        self.asset_channel = self._db.get("heroku.forums", "channel_id", 0)
        try:
            self._notif_topic = await utils.asset_forum_topic(
                self._client,
                self._db,
                self.asset_channel,
                "ReactionWatcher",
                description="Here will be notifications about reactions in chats.",
                icon_emoji_id=5954175920506933873,
            )
        except Exception:
            self._notif_topic = await utils.asset_forum_topic(
                self._client,
                self._db,
                self.asset_channel,
                "ReactionWatcher",
                description="Here will be notifications about reactions in chats.",
            )

    def _is_enabled(self) -> bool:
        disabled = self._db.pointer(main.__name__, "disabled_watchers", {})
        return self.strings["name"] not in disabled

    @staticmethod
    def _peer_to_id(peer) -> int:
        if not peer:
            return 0
        if isinstance(peer, int):
            return peer
        for attr in ("user_id", "chat_id", "channel_id", "id"):
            if hasattr(peer, attr):
                value = getattr(peer, attr)
                if isinstance(value, int):
                    return value
        return 0

    async def _reaction_to_text(self, reaction) -> str:
        if not reaction:
            return "unknown"

        if hasattr(reaction, "emoticon"):
            return reaction.emoticon

        if hasattr(reaction, "document_id"):
            document_id = reaction.document_id
            if document_id in self._custom_emoji_cache:
                return self._custom_emoji_cache[document_id]

            fallback_emoji = "✨"
            pack_short_name = None
            pack_id = None
            try:
                documents = await self._client(
                    GetCustomEmojiDocumentsRequest(document_id=[document_id])
                )
                if documents:
                    for attr in getattr(documents[0], "attributes", []):
                        if hasattr(attr, "stickerset") and attr.stickerset:
                            stickerset = attr.stickerset
                            cache_key = self._stickerset_cache_key(stickerset)
                            if cache_key in self._emoji_pack_cache:
                                pack_short_name, pack_id = self._emoji_pack_cache[cache_key]
                            else:
                                pack_short_name, pack_id = await self._resolve_pack_info(
                                    stickerset
                                )
                                self._emoji_pack_cache[cache_key] = (
                                    pack_short_name,
                                    pack_id,
                                )
                        if hasattr(attr, "alt") and attr.alt:
                            fallback_emoji = attr.alt
                            break
            except Exception:
                pass

            pack_suffix = ""
            if pack_short_name:
                pack_suffix = (
                    f" <a href='https://t.me/addemoji/{pack_short_name}'>"
                    f"pack:{pack_short_name}</a>"
                )
                if pack_id:
                    pack_suffix += f" <code>({pack_id})</code>"
            elif pack_id:
                pack_suffix = f" <code>pack_id:{pack_id}</code>"

            rendered = (
                f"<tg-emoji emoji-id=\"{document_id}\">"
                f"{utils.escape_html(fallback_emoji)}</tg-emoji>{pack_suffix}"
            )
            self._custom_emoji_cache[document_id] = rendered
            return rendered

        if reaction.__class__.__name__ == "ReactionPaid":
            return "⭐"

        return reaction.__class__.__name__

    @staticmethod
    def _stickerset_cache_key(stickerset) -> str:
        short_name = getattr(stickerset, "short_name", None)
        if short_name:
            return f"sn:{short_name}"
        set_id = getattr(stickerset, "id", None)
        access_hash = getattr(stickerset, "access_hash", None)
        return f"id:{set_id}:{access_hash}"

    async def _resolve_pack_info(self, stickerset):
        short_name = getattr(stickerset, "short_name", None)
        set_id = getattr(stickerset, "id", None)

        if short_name and set_id:
            return short_name, set_id

        try:
            result = await self._client(
                GetStickerSetRequest(stickerset=stickerset, hash=0)
            )
            set_obj = getattr(result, "set", None)
            if set_obj:
                short_name = short_name or getattr(set_obj, "short_name", None)
                set_id = set_id or getattr(set_obj, "id", None)
        except Exception:
            pass

        return short_name, set_id

    async def _build_link(self, message, chat, chat_id: int, peer) -> str:
        try:
            return await message.link()
        except Exception:
            pass

        username = getattr(chat, "username", None)
        if username:
            return f"https://t.me/{username}/{message.id}"

        if isinstance(peer, PeerUser):
            return f"tg://openmessage?user_id={chat_id}&message_id={message.id}"

        return f"https://t.me/c/{chat_id}/{message.id}"

    async def _safe_get_entity(self, peer):
        try:
            return await self._client.get_entity(peer)
        except Exception:
            return None

    async def _safe_get_message(self, peer, msg_id: int):
        try:
            return await self._client.get_messages(peer, ids=msg_id)
        except Exception:
            return None

    async def _read_reactions(self, peer, top_msg_id: Optional[int]):
        if not self.config["autoread_reactions"]:
            return

        self._flood_protect = list(
            filter(lambda x: x > time.time(), self._flood_protect)
        )

        if len(self._flood_protect) > self._threshold:
            self._queue.append(
                Entry(
                    peer=peer,
                    schedule=self._flood_protect[0],
                    top_msg_id=top_msg_id,
                )
            )
            return

        self._flood_protect += [int(time.time()) + self._flood_protect_sample]
        await self._client(ReadReactionsRequest(peer=peer, top_msg_id=top_msg_id))

    async def render_text(self, message, chat, reactor, reactor_peer, reaction_item, chat_id):
        text = self.config["custom_notif_text"] or self.strings["reacted"]

        title_raw = (
            chat.title
            if hasattr(chat, "title") and chat.title
            else getattr(chat, "first_name", None) or "Unknown"
        )
        title = utils.escape_html(title_raw)

        reactor_id = self._peer_to_id(reactor_peer)
        reactor_name_raw = (
            reactor.first_name
            if reactor and hasattr(reactor, "first_name") and reactor.first_name
            else reactor.title
            if reactor and hasattr(reactor, "title") and reactor.title
            else "Unknown"
        )
        reactor_name_escaped = utils.escape_html(reactor_name_raw)

        if isinstance(reactor_peer, PeerUser) and reactor_id:
            reactor_name = f"<a href='tg://user?id={reactor_id}'>{reactor_name_escaped}</a>"
        else:
            reactor_name = reactor_name_escaped

        msg_content = (
            utils.escape_html(message.message)
            if message and message.message
            else self.strings["no_message_content"]
        )

        reaction = await self._reaction_to_text(reaction_item.reaction)
        link = await self._build_link(message, chat, chat_id, message.peer_id)

        return text.format(
            title=title,
            chat_id=chat_id,
            name=reactor_name,
            user_id=reactor_id,
            reaction=reaction,
            msg_content=msg_content,
            link=link,
        )

    @loader.command(
        ru_doc="Вкл/выкл ReactionWatcher.",
        alias="rw",
    )
    async def reactionwatcher(self, m):
        """Enable/Disable ReactionWatcher."""
        try:
            disabled = self._db.pointer(main.__name__, "disabled_watchers", {})
            if self.strings["name"] in list(disabled.keys()):
                del disabled[self.strings["name"]]
                await utils.answer(m, self.strings["enabled"])
            else:
                disabled[self.strings["name"]] = ["*"]
                await utils.answer(m, self.strings["disabled"])
        except Exception as e:
            logger.error(e)

    @loader.loop(interval=3, autostart=True)
    async def _queue_handler(self):
        if not self._queue:
            return

        peer, schedule, top_msg_id = self._queue[0]
        if schedule > time.time():
            return

        self._queue.pop(0)
        try:
            await self._client(ReadReactionsRequest(peer=peer, top_msg_id=top_msg_id))
        except Exception as e:
            logger.error(e)

    @loader.raw_handler(UpdateMessageReactions)
    async def inform_reactions(self, update: UpdateMessageReactions):
        """Inform when someone reacts to your messages."""
        try:
            if not self._is_enabled() or not hasattr(update, "reactions"):
                return

            reactions = getattr(update.reactions, "recent_reactions", None)
            if not isinstance(reactions, (list, tuple, set)):
                return

            unread_reactions = [i for i in reactions if getattr(i, "unread", False)]
            if not unread_reactions:
                return

            chat_id = self._peer_to_id(update.peer)
            if (
                not chat_id
                or chat_id == self.asset_channel
                or chat_id in self.config["ignore_chats"]
                or chat_id in self.config["blacklist_chats"]
            ):
                return

            message = await self._safe_get_message(update.peer, update.msg_id)
            if not message:
                await self._read_reactions(update.peer, getattr(update, "top_msg_id", None))
                return

            chat = await message.get_chat()
            if not chat:
                await self._read_reactions(update.peer, getattr(update, "top_msg_id", None))
                return

            for reaction_item in unread_reactions:
                if getattr(reaction_item, "my", False):
                    continue

                reactor_peer = getattr(reaction_item, "peer_id", None)
                reactor_id = self._peer_to_id(reactor_peer)
                if (
                    not reactor_id
                    or reactor_id == self._me_id
                    or reactor_id in self.config["ignore_users"]
                    or reactor_id in self.config["blacklist_users"]
                ):
                    continue

                reactor = await self._safe_get_entity(reactor_peer)
                if (
                    self.config["ignore_bots"]
                    and reactor
                    and hasattr(reactor, "bot")
                    and reactor.bot
                ):
                    continue

                await self.inline.bot.send_message(
                    int(f"-100{self.asset_channel}"),
                    await self.render_text(
                        message,
                        chat,
                        reactor,
                        reactor_peer,
                        reaction_item,
                        chat_id,
                    ),
                    disable_web_page_preview=True,
                    message_thread_id=self._notif_topic.id,
                )

            await self._read_reactions(update.peer, getattr(update, "top_msg_id", None))
        except Exception as e:
            logger.error(e)
