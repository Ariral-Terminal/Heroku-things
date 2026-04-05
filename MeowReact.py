from telethon import types
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionCustomEmoji, ReactionEmoji, MessageEntityCustomEmoji
from .. import loader, utils
import logging

logger = logging.getLogger(__name__)
__version__ = (3, 7, 1)


@loader.tds
class MeowReactMod(loader.Module):
    strings = {
        "name": "MeowReact",
        "enabled": "✅ Реакции включены в этом чате",
        "disabled": "🚫 Реакции отключены в этом чате",
        "reaction_set": "✅ Установлена реакция для триггера <code>{}</code>: {}",
        "premium_set": "✅ Установлена Premium реакция для триггера <code>{}</code>: ID <code>{}</code>",
        "trigger_list": "📋 <b>Список триггеров:</b>\n\n{}",
        "trigger_removed": "🗑 Триггер удалён",
        "no_args": "⚠️ Укажите триггер и реакцию\nФормат: .setr триггер | реакция\nПример: .setr черихедер прикольный | 👋\nДля Premium: .setr привет | 5395371714332869687\nИли: .setr привет 💎 (с premium эмодзи)",
        "no_triggers": "⚠️ Нет активных триггеров",
        "settings": "⚙️ <b>Настройки MeowReact</b>\n\n📊 Активных чатов: <code>{}</code>\n🎯 Триггеров настроено: <code>{}</code>\n\n💡 Выберите действие:",
        "chat_enabled": "✅ Реакции включены",
        "chat_disabled": "🚫 Реакции выключены",
        "add_trigger_info": "➕ <b>Добавление триггера</b>\n\nОтправьте сообщение в формате:\n<code>триггер | реакция</code>\n\nПримеры:\n• <code>привет всем | 👋</code>\n• <code>спасибо большое | ❤️</code>\n• <code>это круто | 😂</code>\n\nДля premium эмодзи:\n• <code>черихедер прикольный | 5395371714332869687</code>\n• Или просто напиши триггер и добавь premium эмодзи: <code>привет 💎</code>\n• Или поставь реакцию на сообщение\n\n⚠️ Сообщение будет удалено",
        "edit_trigger_select": "✏️ <b>Редактирование триггера</b>\n\nВыберите триггер для изменения:",
        "edit_trigger_info": "✏️ <b>Изменение триггера:</b> <code>{}</code>\n\nОтправьте новую реакцию:\n• Обычный эмодзи: <code>👋</code>\n• Premium ID: <code>5395371714332869687</code>\n• Или поставьте реакцию на сообщение\n\n⚠️ Сообщение будет удалено",
        "trigger_updated": "✅ Триггер <code>{}</code> обновлён",
        "premium_detected": "✨ Обнаружена premium реакция!\nID: <code>{}</code>",
        "waiting_reaction": "⏳ Поставьте premium реакцию на любое сообщение...",
        "active_chats": "💬 <b>Активные чаты:</b>\n\n{}",
        "no_active_chats": "⚠️ Нет активных чатов",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            "default_reaction",
            "😸",
            "Реакция по умолчанию (если нет триггеров)",
            
            "default_is_premium",
            False,
            "Используется ли премиум-эмодзи по умолчанию"
        )
        self.waiting_for_trigger = {}
        self.waiting_for_edit = {}
        self.waiting_for_premium = {}

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self.active_chats = self.get("active_chats", {})
        self.triggers = self.get("triggers", {})
        
        migrated = False
        for trigger, data in list(self.triggers.items()):
            if isinstance(data, str):
                self.triggers[trigger] = {
                    "reaction": data,
                    "is_premium": data.isdigit()
                }
                migrated = True
            elif isinstance(data, dict) and "reaction" not in data:
                del self.triggers[trigger]
                migrated = True
        
        if migrated:
            self.save_data()

    def save_data(self):
        self.set("active_chats", self.active_chats)
        self.set("triggers", self.triggers)

    def _get_reaction_info(self, data):
        if isinstance(data, str):
            return f"ID: {data}" if data.isdigit() else data
        elif isinstance(data, dict):
            reaction = data.get("reaction", "❓")
            is_premium = data.get("is_premium", False)
            return f"ID: {reaction}" if is_premium else reaction
        return "❓"

    def _get_reaction_info_html(self, data):
        if isinstance(data, str):
            return f"ID: <code>{data}</code>" if data.isdigit() else data
        elif isinstance(data, dict):
            reaction = data.get("reaction", "❓")
            is_premium = data.get("is_premium", False)
            return f"ID: <code>{reaction}</code>" if is_premium else reaction
        return "❓"

    def _get_main_markup(self, chat_id):
        is_active = str(chat_id) in self.active_chats
        return [
            [
                {
                    "text": "🔴 Выключить" if is_active else "🟢 Включить",
                    "callback": self.toggle_callback,
                    "args": (str(chat_id),)
                }
            ],
            [
                {
                    "text": "➕ Добавить",
                    "callback": self.add_trigger_callback
                },
                {
                    "text": "✏️ Изменить",
                    "callback": self.edit_menu_callback
                }
            ],
            [
                {
                    "text": "📋 Список",
                    "callback": self.list_callback
                },
                {
                    "text": "🗑 Удалить",
                    "callback": self.remove_menu_callback
                }
            ],
            [
                {
                    "text": "💬 Активные чаты",
                    "callback": self.active_chats_callback
                }
            ],
            [{"text": "❌ Закрыть", "action": "close"}]
        ]

    @loader.command(ru_doc="Панель управления модулем")
    async def meow(self, message):
        await self.inline.form(
            text=self.strings["settings"].format(
                len(self.active_chats),
                len(self.triggers)
            ),
            message=message,
            reply_markup=self._get_main_markup(message.chat_id)
        )

    async def toggle_callback(self, call, chat_id):
        if chat_id in self.active_chats:
            del self.active_chats[chat_id]
            status_text = self.strings["chat_disabled"]
        else:
            self.active_chats[chat_id] = True
            status_text = self.strings["chat_enabled"]
        
        self.save_data()
        await call.edit(
            text=self.strings["settings"].format(
                len(self.active_chats),
                len(self.triggers)
            ),
            reply_markup=self._get_main_markup(chat_id)
        )
        await call.answer(status_text)

    async def add_trigger_callback(self, call):
        user_id = call.from_user.id
        self.waiting_for_trigger[user_id] = {"type": "add"}
        
        await call.edit(
            text=self.strings["add_trigger_info"],
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self.cancel_callback}]
            ]
        )

    async def edit_menu_callback(self, call):
        if not self.triggers:
            await call.answer("Нет триггеров для редактирования", show_alert=True)
            return
        
        buttons = []
        for trigger in list(self.triggers.keys()):
            reaction_data = self.triggers[trigger]
            reaction_info = self._get_reaction_info(reaction_data)
            buttons.append([{
                "text": f"✏️ {trigger} → {reaction_info}",
                "callback": self.edit_trigger_callback,
                "args": (trigger,)
            }])
        buttons.append([{"text": "« Назад", "callback": self.back_callback}])
        
        await call.edit(
            text=self.strings["edit_trigger_select"],
            reply_markup=buttons
        )

    async def edit_trigger_callback(self, call, trigger):
        user_id = call.from_user.id
        self.waiting_for_edit[user_id] = {"trigger": trigger}
        
        await call.edit(
            text=self.strings["edit_trigger_info"].format(trigger),
            reply_markup=[
                [
                    {
                        "text": "✨ Premium реакция",
                        "callback": self.wait_premium_callback,
                        "args": (trigger, "edit")
                    }
                ],
                [{"text": "❌ Отмена", "callback": self.cancel_callback}]
            ]
        )

    async def wait_premium_callback(self, call, trigger, mode):
        user_id = call.from_user.id
        self.waiting_for_premium[user_id] = {"trigger": trigger, "mode": mode}
        
        await call.edit(
            text=self.strings["waiting_reaction"],
            reply_markup=[
                [{"text": "❌ Отмена", "callback": self.cancel_callback}]
            ]
        )

    async def list_callback(self, call):
        if not self.triggers:
            text = self.strings["no_triggers"]
        else:
            trigger_list = []
            for trigger, data in self.triggers.items():
                reaction_info = self._get_reaction_info_html(data)
                trigger_list.append(f"• <code>{trigger}</code> → {reaction_info}")
            text = self.strings["trigger_list"].format("\n".join(trigger_list))
        
        await call.edit(
            text=text,
            reply_markup=[
                [{"text": "« Назад", "callback": self.back_callback}]
            ]
        )

    async def active_chats_callback(self, call):
        if not self.active_chats:
            text = self.strings["no_active_chats"]
        else:
            chat_list = []
            for chat_id in self.active_chats.keys():
                try:
                    chat_id_int = int(chat_id)
                    entity = await self._client.get_entity(chat_id_int)
                    chat_name = getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Unknown')
                    chat_list.append(f"• <a href='tg://chat?id={chat_id}'>{chat_name}</a> (<code>{chat_id}</code>)")
                except Exception as e:
                    logger.error(f"Ошибка при получении информации о чате {chat_id}: {str(e)}")
                    chat_list.append(f"• <a href='tg://chat?id={chat_id}'>Chat</a> (<code>{chat_id}</code>)")
            text = self.strings["active_chats"].format("\n".join(chat_list)) if chat_list else self.strings["no_active_chats"]
        
        await call.edit(
            text=text,
            reply_markup=[
                [{"text": "« Назад", "callback": self.back_callback}]
            ]
        )

    async def remove_menu_callback(self, call):
        if not self.triggers:
            await call.answer("Нет триггеров для удаления", show_alert=True)
            return
        
        buttons = []
        for trigger in list(self.triggers.keys()):
            buttons.append([{
                "text": f"🗑 {trigger}",
                "callback": self.remove_trigger_callback,
                "args": (trigger,)
            }])
        buttons.append([{"text": "« Назад", "callback": self.back_callback}])
        
        await call.edit(
            text="🗑 <b>Выберите триггер для удаления:</b>",
            reply_markup=buttons
        )

    async def remove_trigger_callback(self, call, trigger):
        if trigger in self.triggers:
            del self.triggers[trigger]
            self.save_data()
            await call.answer(self.strings["trigger_removed"], show_alert=True)
        await self.back_callback(call)

    async def cancel_callback(self, call):
        user_id = call.from_user.id
        if user_id in self.waiting_for_trigger:
            del self.waiting_for_trigger[user_id]
        if user_id in self.waiting_for_edit:
            del self.waiting_for_edit[user_id]
        if user_id in self.waiting_for_premium:
            del self.waiting_for_premium[user_id]
        await self.back_callback(call)

    async def back_callback(self, call):
        chat_id = str(getattr(call, 'chat_id', ''))
        if not chat_id and hasattr(call, 'message') and call.message:
            chat_id = str(call.message.chat_id)
        
        await call.edit(
            text=self.strings["settings"].format(
                len(self.active_chats),
                len(self.triggers)
            ),
            reply_markup=self._get_main_markup(chat_id)
        )

    @loader.command(ru_doc="Включить/выключить реакции в чате")
    async def toggle(self, message):
        chat_id = str(message.chat_id)
        if chat_id in self.active_chats:
            del self.active_chats[chat_id]
            status = False
        else:
            self.active_chats[chat_id] = True
            status = True
        self.save_data()
        await utils.answer(message, self.strings["enabled"] if status else self.strings["disabled"])

    @loader.command(ru_doc="Установить реакцию для триггера\nПример: .setr черихедер прикольный | 5395371714332869687\nИли отправь команду с premium эмодзи в конце")
    async def setr(self, message):
        args = utils.get_args_raw(message)
        
        entities = getattr(message, 'entities', None)
        premium_emoji_id = None
        
        if entities:
            for entity in entities:
                if hasattr(entity, 'document_id') and entity.document_id:
                    premium_emoji_id = str(entity.document_id)
                    break
        
        if premium_emoji_id:
            if "|" in args:
                trigger = args.split("|", 1)[0].strip().lower()
            else:
                parts = args.rsplit(None, 1)
                if len(parts) >= 1:
                    trigger = parts[0].strip().lower()
                else:
                    await utils.answer(message, self.strings["no_args"])
                    return
            
            self.triggers[trigger] = {
                "reaction": premium_emoji_id,
                "is_premium": True
            }
            self.save_data()
            
            await utils.answer(
                message,
                self.strings["premium_set"].format(trigger, premium_emoji_id)
            )
            return
        
        if not args or "|" not in args:
            await utils.answer(message, self.strings["no_args"])
            return
        
        parts = args.split("|", 1)
        trigger = parts[0].strip().lower()
        reaction = parts[1].strip()
        
        is_premium = reaction.isdigit()
        
        self.triggers[trigger] = {
            "reaction": reaction,
            "is_premium": is_premium
        }
        self.save_data()
        
        await utils.answer(
            message,
            self.strings["premium_set"].format(trigger, reaction) if is_premium 
            else self.strings["reaction_set"].format(trigger, reaction)
        )

    @loader.command(ru_doc="Показать список триггеров")
    async def listt(self, message):
        if not self.triggers:
            await utils.answer(message, self.strings["no_triggers"])
            return
        
        trigger_list = []
        for trigger, data in self.triggers.items():
            reaction_info = self._get_reaction_info(data)
            trigger_list.append(f"• {trigger} → {reaction_info}")
        
        await utils.answer(
            message,
            self.strings["trigger_list"].format("\n".join(trigger_list))
        )

    @loader.command(ru_doc="Удалить триггер\nПример: .remt черихедер прикольный")
    async def remt(self, message):
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, "⚠️ Укажите триггер для удаления")
            return
        
        trigger = args.lower()
        if trigger in self.triggers:
            del self.triggers[trigger]
            self.save_data()
            await utils.answer(message, self.strings["trigger_removed"])
        else:
            await utils.answer(message, f"⚠️ Триггер '{trigger}' не найден")

    @loader.watcher()
    async def watcher(self, message):
        try:
            if not isinstance(message, types.Message):
                return
            
            user_id = message.sender_id
            
            if hasattr(message, 'reactions') and message.reactions:
                if user_id in self.waiting_for_premium:
                    premium_data = self.waiting_for_premium[user_id]
                    trigger = premium_data.get("trigger", "")
                    
                    if not trigger:
                        return
                    
                    for reaction_count in message.reactions.results:
                        if hasattr(reaction_count.reaction, 'document_id'):
                            doc_id = reaction_count.reaction.document_id
                            
                            self.triggers[trigger] = {
                                "reaction": str(doc_id),
                                "is_premium": True
                            }
                            self.save_data()
                            
                            del self.waiting_for_premium[user_id]
                            
                            try:
                                await self._client.send_message(
                                    message.chat_id,
                                    self.strings["premium_detected"].format(doc_id) + "\n" +
                                    self.strings["trigger_updated"].format(trigger)
                                )
                            except Exception as e:
                                logger.error(f"Ошибка при отправке сообщения: {str(e)}")
                            return
            
            if user_id in self.waiting_for_trigger:
                text = getattr(message, "text", "") or ""
                entities = message.entities or []
                premium_emoji_id = None
                
                for entity in entities:
                    if isinstance(entity, MessageEntityCustomEmoji):
                        premium_emoji_id = str(entity.document_id)
                        break
                
                if premium_emoji_id:
                    if "|" in text:
                        trigger = text.split("|", 1)[0].strip().lower()
                    else:
                        text_clean = text
                        for entity in entities:
                            if isinstance(entity, MessageEntityCustomEmoji):
                                offset = entity.offset
                                length = entity.length
                                text_clean = text_clean[:offset] + text_clean[offset + length:]
                        
                        trigger = text_clean.strip().lower()
                        
                        if not trigger:
                            return
                    
                    self.triggers[trigger] = {
                        "reaction": premium_emoji_id,
                        "is_premium": True
                    }
                    self.save_data()
                    
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    
                    del self.waiting_for_trigger[user_id]
                    
                    try:
                        await self._client.send_message(
                            message.chat_id,
                            self.strings["premium_set"].format(trigger, premium_emoji_id)
                        )
                    except Exception as e:
                        logger.error(f"Ошибка при отправке сообщения: {str(e)}")
                    return
                
                if text and "|" in text:
                    parts = text.split("|", 1)
                    trigger = parts[0].strip().lower()
                    reaction = parts[1].strip()
                    
                    is_premium = reaction.isdigit()
                    
                    self.triggers[trigger] = {
                        "reaction": reaction,
                        "is_premium": is_premium
                    }
                    self.save_data()
                    
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    
                    del self.waiting_for_trigger[user_id]
                    
                    try:
                        await self._client.send_message(
                            message.chat_id,
                            self.strings["premium_set"].format(trigger, reaction) if is_premium 
                            else self.strings["reaction_set"].format(trigger, reaction)
                        )
                    except Exception as e:
                        logger.error(f"Ошибка при отправке сообщения: {str(e)}")
                return
            
            if user_id in self.waiting_for_edit:
                text = getattr(message, "text", "") or ""
                entities = message.entities or []
                premium_emoji_id = None
                
                for entity in entities:
                    if isinstance(entity, MessageEntityCustomEmoji):
                        premium_emoji_id = str(entity.document_id)
                        break
                
                if premium_emoji_id:
                    edit_data = self.waiting_for_edit[user_id]
                    trigger = edit_data.get("trigger", "")
                    
                    if not trigger:
                        return
                    
                    self.triggers[trigger] = {
                        "reaction": premium_emoji_id,
                        "is_premium": True
                    }
                    self.save_data()
                    
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    
                    del self.waiting_for_edit[user_id]
                    
                    try:
                        await self._client.send_message(
                            message.chat_id,
                            self.strings["trigger_updated"].format(trigger) + "\n" +
                            self.strings["premium_set"].format(trigger, premium_emoji_id)
                        )
                    except Exception as e:
                        logger.error(f"Ошибка при отправке сообщения: {str(e)}")
                    return
                
                if text:
                    edit_data = self.waiting_for_edit[user_id]
                    trigger = edit_data.get("trigger", "")
                    
                    if not trigger:
                        return
                    
                    reaction = text.strip()
                    is_premium = reaction.isdigit()
                    
                    self.triggers[trigger] = {
                        "reaction": reaction,
                        "is_premium": is_premium
                    }
                    self.save_data()
                    
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    
                    del self.waiting_for_edit[user_id]
                    
                    try:
                        await self._client.send_message(
                            message.chat_id,
                            self.strings["trigger_updated"].format(trigger) + "\n" +
                            (self.strings["premium_set"].format(trigger, reaction) if is_premium 
                            else self.strings["reaction_set"].format(trigger, reaction))
                        )
                    except Exception as e:
                        logger.error(f"Ошибка при отправке сообщения: {str(e)}")
                return
            
            chat_id = str(message.chat_id)
            if chat_id not in self.active_chats:
                return
            
            if hasattr(message, 'via_bot_id') and message.via_bot_id:
                return

            text = getattr(message, "text", "") or ""
            if not text:
                return
            
            text_lower = text.lower()
            
            matched_triggers = []
            for trigger in self.triggers:
                if trigger in text_lower:
                    matched_triggers.append(trigger)
            
            if not matched_triggers:
                if not self.triggers:
                    matched_triggers = ["_default"]
                else:
                    return
            
            reactions_to_send = []
            for matched_trigger in matched_triggers:
                if matched_trigger == "_default":
                    reaction_value = self.config["default_reaction"]
                    is_premium = self.config["default_is_premium"]
                else:
                    reaction_data = self.triggers[matched_trigger]
                    if isinstance(reaction_data, str):
                        reaction_value = reaction_data
                        is_premium = reaction_data.isdigit()
                    else:
                        reaction_value = reaction_data.get("reaction", "😸")
                        is_premium = reaction_data.get("is_premium", False)
                
                try:
                    if is_premium:
                        doc_id = int(reaction_value)
                        reaction = ReactionCustomEmoji(document_id=doc_id)
                    else:
                        reaction = ReactionEmoji(emoticon=reaction_value)
                    reactions_to_send.append(reaction)
                except Exception as e:
                    logger.error(f"Ошибка при создании реакции для '{matched_trigger}': {str(e)}")
            
            if reactions_to_send:
                try:
                    await self._client(SendReactionRequest(
                        peer=message.chat_id,
                        msg_id=message.id,
                        reaction=reactions_to_send
                    ))
                except Exception as e:
                    logger.error(f"Ошибка при установке реакций: {str(e)}")
        except Exception as e:
            logger.error(f"Ошибка в watcher: {str(e)}")