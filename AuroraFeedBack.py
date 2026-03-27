# *      _                             __  __           _       _
# *     / \  _   _ _ __ ___  _ __ __ _|  \/  | ___   __| |_   _| | ___  ___ 
# *    / _ \| | | | '__/ _ \| '__/ _` | |\/| |/ _ \ / _` | | | | |/ _ \/ __|
# *   / ___ \ |_| | | | (_) | | | (_| | |  | | (_) | (_| | |_| | |  __/\__ \
# *  /_/   \_\__,_|_|  \___/|_|  \__,_|_|  |_|\___/ \__,_|\__,_|_|\___||___/
# *
# *                          © Copyright 2024
# *
# *                      https://t.me/AuroraModules
# *
# * 🔒 Code is licensed under GNU AGPLv3
# * 🌐 https://www.gnu.org/licenses/agpl-3.0.html
# * ⛔️ You CANNOT edit this file without direct permission from the author.
# * ⛔️ You CANNOT distribute this file if you have modified it without the direct permission of the author.

# Name: AuroraFeedBack
# Author: Felix? || n3rcy
# Commands:
# .flink | .banfeedback | .unbanfeedback
# scope: hikka_only
# meta developer: @AuroraModules & @nercymods

# meta pic: https://i.postimg.cc/Hx3Zm8rB/logo.png
# meta banner: https://te.legra.ph/file/05a519da50f993b950260.jpg

__version__ = (1, 0, 2)

from aiogram.types import Message as AiogramMessage
from aiogram.types import CallbackQuery as AiogramCallbackQuery
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telethon import functions
from telethon.tl.types import PeerUser
from ..inline.types import InlineCall # type: ignore
from html import escape
from .. import loader, utils

@loader.tds
class AuroraFeedBackMod(loader.Module):
    """Multifunctional feedback bot."""

    strings = {
        "name": "AuroraFeedBack",
        "new_m": "🗣 New message from",
        "not_text": "🔎 The text was not found.",
        "waiting_answer": "⏳ Waiting for answer to user",
        "flink": "Here is my link to the feedback bot",
        "owner_answer": "🗣 Owner's Response",
        "successfully_send": "💬 Message successfully sent",
        "not_arg": "❌ No UserID argument provided",
        "successfully_ban": "✅ User successfully banned",
        "successfully_unban": "✅ User successfully unbanned",
        "already_banned": "🚫 User is already banned",
        "not_in_ban": "✅ User is not in the ban list",
        "cfg_mode": "Enable/Disable feedback bot functionality",
        "cfg_custom_text": "Enter custom greeting text",
        "cfg_no_meta": "Enter custom text for /nometa",
        "cfg_no_meta_baner": "Enter custom link for meta-banner",
    }

    strings_ru = {
        "new_m": "🗣 Новое сообщение от",
        "not_text": "🔎 Текст не найден.",
        "waiting_answer": "⏳ Ожидание ответа пользователя",
        "flink": "Вот моя ссылка на feedback бота",
        "owner_answer": "🗣 Ответ владельца",
        "successfully_send": "💬 Сообщение успешно отправлено",
        "not_arg": "❌ Не указан UserID",
        "successfully_ban": "✅ Пользователь успешно заблокирован",
        "successfully_unban": "✅ Пользователь успешно разблокирован",
        "already_banned": "🚫 Пользователь уже заблокирован",
        "not_in_ban": "✅ Пользователь не находится в списке заблокированных",
        "cfg_mode": "Включить/выключить функционал feedback бота",
        "cfg_custom_text": "Введите кастомный текст для приветствия",
        "cfg_no_meta": "Введите кастомный текст для команды /nometa",
        "cfg_no_meta_baner": "Введите кастомную ссылку на мета-баннер",
    }

    strings_uz = {
        "new_m": "🗣 Yangi xabar",
        "not_text": "🔎 Matn topilmadi.",
        "waiting_answer": "⏳ Foydalanuvchidan javob kutilmoqda",
        "flink": "Bu mening feedback botim havolam",
        "owner_answer": "🗣 Egasi javobi",
        "successfully_send": "💬 Xabar muvaffaqiyatli yuborildi",
        "not_arg": "❌ UserID argument kiritilmagan",
        "successfully_ban": "✅ Foydalanuvchi muvaffaqiyatli bloklandi",
        "successfully_unban": "✅ Foydalanuvchi muvaffaqiyatli ochib tashlandi",
        "already_banned": "🚫 Foydalanuvchi allaqachon bloklangan",
        "not_in_ban": "✅ Foydalanuvchi blok ro'yxatida yo'q",
        "cfg_mode": "Feedback bot funktsiyasini yoqish/yopish",
        "cfg_custom_text": "Xush kelibsiz matnini kiriting",
        "cfg_no_meta": "/nometa uchun maxsus matnni kiriting",
        "cfg_no_meta_baner": "Meta-banner uchun maxsus havolani kiriting",
    }

    strings_de = {
        "new_m": "🗣 Neue Nachricht von",
        "not_text": "🔎 Der Text wurde nicht gefunden.",
        "waiting_answer": "⏳ Warten auf die Antwort des Benutzers",
        "flink": "Hier ist mein Link zum Feedback-Bot",
        "owner_answer": "🗣 Antwort des Eigentümers",
        "successfully_send": "💬 Nachricht erfolgreich gesendet",
        "not_arg": "❌ Kein UserID-Argument angegeben",
        "successfully_ban": "✅ Benutzer erfolgreich gesperrt",
        "successfully_unban": "✅ Benutzer erfolgreich entsperrt",
        "already_banned": "🚫 Benutzer ist bereits gesperrt",
        "not_in_ban": "✅ Benutzer befindet sich nicht in der Sperrliste",
        "cfg_mode": "Feedback-Bot-Funktionalität aktivieren/deaktivieren",
        "cfg_custom_text": "Geben Sie benutzerdefinierten Begrüßungstext ein",
        "cfg_no_meta": "Geben Sie benutzerdefinierten Text für /nometa ein",
        "cfg_no_meta_baner": "Geben Sie einen benutzerdefinierten Link für den Meta-Banner ein",
    }   

    strings_es = {
        "new_m": "🗣 Nuevo mensaje de",
        "not_text": "🔎 No se encontró el texto.",
        "waiting_answer": "⏳ Esperando la respuesta del usuario",
        "flink": "Aquí está mi enlace al bot de retroalimentación",
        "owner_answer": "🗣 Respuesta del propietario",
        "successfully_send": "💬 Mensaje enviado con éxito",
        "not_arg": "❌ No se proporcionó el argumento UserID",
        "successfully_ban": "✅ Usuario bloqueado correctamente",
        "successfully_unban": "✅ Usuario desbloqueado correctamente",
        "already_banned": "🚫 El usuario ya está bloqueado",
        "not_in_ban": "✅ El usuario no está en la lista de bloqueados",
        "cfg_mode": "Activar/Desactivar la funcionalidad del bot de retroalimentación",
        "cfg_custom_text": "Ingrese texto de saludo personalizado",
        "cfg_no_meta": "Ingrese texto personalizado para /nometa",
        "cfg_no_meta_baner": "Ingrese el enlace personalizado para el meta-banner",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "mode",
                True,
                lambda: self.strings["cfg_mode"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "start_custom_text",
                None,
                lambda: self.strings["cfg_custom_text"],
            ),
            loader.ConfigValue(
                "no_meta",
                None,
                lambda: self.strings["cfg_no_meta"],
            ),
            loader.ConfigValue(
                "no_meta_baner",
                "https://te.legra.ph/file/91a54dee84cf1ec5990fd.jpg",
                lambda: self.strings["cfg_no_meta_baner"],
                validator=loader.validators.Link(),
            ),
        )

    async def on_dlmod(self, client, db):
        self.db.set("AuroraFeedBackMod", "ban_list", [])
        self.db.set("AuroraFeedBackMod", "known_users", {})

    async def client_ready(self, client, db):
        self._client = client
        self.forwarding_enabled = {}
        self._ban_list = self.db.get("AuroraFeedBackMod", "ban_list")
        self._known_users = self.db.get("AuroraFeedBackMod", "known_users", {}) or {}
        self._name = utils.escape_html((await client.get_me()).first_name)
        self.db.set("AuroraFeedBackMod", "state", "done")

    def _remember_user(self, user_id, username=None):
        if not username:
            return

        user_key = str(user_id)
        username = username.lstrip("@")
        cached = self._known_users.get(user_key, {})

        if cached.get("username") == username:
            return

        self._known_users[user_key] = {"username": username}
        self.db.set("AuroraFeedBackMod", "known_users", self._known_users)

    def _add_feedback_ban(self, user_id):
        if user_id in self._ban_list:
            return False

        self._ban_list.append(user_id)
        self.db.set("AuroraFeedBackMod", "ban_list", self._ban_list)
        return True

    def _remove_feedback_ban(self, user_id):
        if user_id not in self._ban_list:
            return False

        self._ban_list.remove(user_id)
        self.db.set("AuroraFeedBackMod", "ban_list", self._ban_list)
        return True

    async def _set_account_block(self, user_id, block=True):
        candidates = []
        user_data = self._known_users.get(str(user_id), {})
        username = user_data.get("username")

        if username:
            candidates.append(f"@{username}")

        candidates.extend([user_id, PeerUser(user_id)])

        peer = None
        for candidate in candidates:
            try:
                peer = await self._client.get_input_entity(candidate)
                break
            except Exception:
                continue

        if peer is None:
            return False

        try:
            request = (
                functions.contacts.BlockRequest(id=peer)
                if block
                else functions.contacts.UnblockRequest(id=peer)
            )
            await self._client(request)
            return True
        except Exception:
            return False

    @loader.command(
        ru_doc="- Получить ссылку на feedback бота",
        uz_doc="- Feedback botga havolani olish",
        de_doc="- Erhalten Sie einen Link zum Feedback-Bot",
        es_doc="- Obtener un enlace al bot de retroalimentación",
    )
    async def flink(self, message):
        """- Get a link to the feedback bot"""
        slinkbot = f"{self.strings['flink']}: https://t.me/{self.inline.bot_username}?start=AuroraFeedBack"
        await utils.answer(message, slinkbot)

    @loader.command(
        ru_doc="[UserID] - Заблокировать пользователю feedback бота",
        uz_doc="[UserID] - Feedback botga foydalanuvchi kirishini bloklang",
        de_doc="[UserID] - Blockiere den Zugriff des Benutzers auf den Feedback-Bot",
        es_doc="[UserID] - Bloquear el acceso del usuario al bot de retroalimentación",
    )
    async def banfeedback(self, message):
        """[UserID] - Block the feedback bot user"""
        user_id = utils.get_args_raw(message)
        # чот новое
        if not user_id and message.is_reply:
            reply = await message.get_reply_message()
            user_id = reply.from_id.user_id
            self._remember_user(
                user_id,
                getattr(getattr(reply, "sender", None), "username", None),
            )
        # чот старое
        if not user_id:
            await utils.answer(message, self.strings["not_arg"])
        else:
            user_id = int(user_id) 
            if self._add_feedback_ban(user_id):
                await self._set_account_block(user_id, block=True)
                await utils.answer(message, self.strings["successfully_ban"])
            else:
                await self._set_account_block(user_id, block=True)
                await utils.answer(message, self.strings["already_banned"])

    @loader.command(
        ru_doc="[UserID] - Разблокировать пользователю feedback бота",
        uz_doc="[UserID] - Feedback bot foydalanuvchisini ochib tashlash",
        de_doc="[UserID] - Feedback-Bot-Benutzer entsperren",
        es_doc="[UserID] - Desbloquear al usuario del bot de retroalimentación",
    )
    async def unbanfeedback(self, message):
        """[UserID] - Unblock the feedback bot user"""

        user_id = utils.get_args_raw(message)
        # чот новое
        if not user_id and message.is_reply:
            reply = await message.get_reply_message()
            user_id = reply.from_id.user_id
            self._remember_user(
                user_id,
                getattr(getattr(reply, "sender", None), "username", None),
            )
         # чот старое
        if not user_id:
            await utils.answer(message, self.strings["not_arg"])
        else:
            user_id = int(user_id)
            if self._remove_feedback_ban(user_id):
                await self._set_account_block(user_id, block=False)
                await utils.answer(message, self.strings["successfully_unban"])
            else:
                await self._set_account_block(user_id, block=False)
                await utils.answer(message, self.strings["not_in_ban"]) 

    async def aiogram_watcher(self, message: AiogramMessage):
        if self.config["mode"] is False:
            return

        self._remember_user(message.from_user.id, message.from_user.username)
    
        if message.from_user.id in list(self.db.get("AuroraFeedBackMod", "ban_list")):
            return
        
        if message.text == "/start AuroraFeedBack": 
            if self.config["start_custom_text"] == None:
                text = "Добро пожаловать в Aurora Feedback Bot!\nПожалуйста, ознакомтесь с /nometa"
            else:
                text = self.config["start_custom_text"]
            await message.answer(text)
            return

        elif message.text == "/nometa": 
            if self.config["no_meta"] == None:
                meta_text = "<b>🫦 Уважаемый пользователь!</b>\nПожалуйста, не задавайте мне вопросы такие, как:\n\n«Привет» , «Какие дела?» , «Что делаешь?» , «Чем занимаешься?» и т.д.\n\nЕсли вы хотите у меня что-то спросить, спрашивайте по делу, а также всю суть вопроса опишите в одном сообщении."
            else: 
                meta_text = self.config["no_meta"]
            if self.config["no_meta_baner"] == None:
                await self.inline.bot.send_message(message.from_user.id, meta_text)
            else: 
                await self.inline.bot.send_photo(
                    message.from_user.id,
                    self.config["no_meta_baner"],
                    caption=meta_text,
                )
            return 
        
        if message.from_user.id == self.tg_id:
            state = self.db.get("AuroraFeedBackMod", "state")
            if state.startswith('waiting_'):
                to_id = int(state.split('_')[1])
                waiting_message_id = int(state.split('_')[2])
                custom_text = f'{self.strings["owner_answer"]}:\n\n{message.text}'
                await self.inline.bot.send_message(to_id, custom_text)
                await self.inline.bot.delete_message(message.chat.id, waiting_message_id)
                await self.inline.bot.send_message(self.tg_id, f'{self.strings["successfully_send"]}')
                self.db.set("AuroraFeedBackMod", "state", "done")
                return
        
        original_text = message.caption if message.caption else message.text
        user_id = message.from_user.id
        WriteInPM =f'<b><a href="tg://user?id={user_id}">✏️Write in PM</a></b>'
        custom_text = f"{self.strings['new_m']} {escape(message.from_user.first_name)}:\n\n{escape(original_text) if original_text is not None else {self.strings['not_text']}}\n\nUserID: {message.from_user.id}\n{WriteInPM}"

        buttons = []
        if message.from_user.id != self._tg_id:
            buttons.append(
                [InlineKeyboardButton(text="📃 Reply", callback_data=f"reply_{user_id}")]
            )
        buttons.extend(
            [
                [InlineKeyboardButton(text="🔐 Ban", callback_data=f"ban_{user_id}")],
                [InlineKeyboardButton(text="🗑️ Delete", callback_data="MessageDelete")],
            ]
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    
        await self.inline.bot.send_message(self.tg_id, custom_text, reply_markup=reply_markup)
        await self.inline.bot.send_message(message.from_user.id, f'{self.strings["successfully_send"]}')

    async def feedback_callback_handler(self, call: InlineCall):
        if call.data == "MessageDelete":
            self.inline.ss(call.from_user.id, False)
            await self.inline.bot.delete_message(
                call.message.chat.id,
                call.message.message_id,
            )
            return
        if call.data.startswith('ban_'):
            user_id = int(call.data.split('_')[1])
            self._add_feedback_ban(user_id)
            await self._set_account_block(user_id, block=True)
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔓 Unban", callback_data=f"unban_{user_id}"
                        )
                    ]
                ]
            )
            await self.inline.bot.send_message(self.tg_id, f'{self.strings["successfully_ban"]} ({user_id})', reply_markup=reply_markup)
            return
        if call.data.startswith('unban_'):
            user_id = int(call.data.split('_')[1])
            self._remove_feedback_ban(user_id)
            await self._set_account_block(user_id, block=False)
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔐 Ban", callback_data=f"ban_{user_id}"
                        )
                    ]
                ]
            )
            await self.inline.bot.send_message(self.tg_id, f'{self.strings["successfully_unban"]} ({user_id})', reply_markup=reply_markup)
            return
        if call.data.startswith("reply"):
            user_id = int(call.data.split('_')[1])
            self.db.set("AuroraFeedBackMod", "state", f"waiting_{user_id}_{call.message.message_id}")
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❌ Cancel", callback_data="cancel_reply"
                        )
                    ]
                ]
            )
            await self.inline.bot.send_message(self.tg_id, f'{self.strings["waiting_answer"]}', reply_markup=reply_markup)   
        if call.data == "cancel_reply":
            self.db.set("AuroraFeedBackMod", "state", "done")
            await self.inline.bot.delete_message(call.message.chat.id, call.message.message_id)
