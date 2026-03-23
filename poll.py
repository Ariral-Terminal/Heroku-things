# modules/poll.py
"""
<manifest>
version: 3.2.2
source: https://t.me/KoteModulesMint
author: Kote
</manifest>

Мощный модуль для работы с опросами.
Позволяет создавать опросы по шаблонам с индивидуальными настройками (анонимность, закреп и т.д.).
"""

import asyncio
import html
import random
from telethon import functions, types
from telethon.tl.types import (
    MessageEntityBold, MessageEntityCode, MessageEntityBlockquote,
    MessageEntityTextUrl, MessageEntityCustomEmoji, MessageEntityItalic,
    MessageEntityMentionName, MessageEntityPre, MessageEntityUnderline,
    MessageEntityStrike, InputMediaPoll, Poll, PollAnswer, TextWithEntities
)
from telethon.tl.custom import Button
from telethon.errors.rpcerrorlist import MessageNotModifiedError, FloodWaitError, ChatAdminRequiredError
from telethon.utils import get_display_name

from core import register, Module, inline_handler, callback_handler, watcher
from utils import database as db
from utils.message_builder import build_and_edit, build_message
from utils.security import check_permission
from handlers.user_commands import _call_inline_bot

# --- Эмодзи ---
POLL_EMOJI_ID = 5956561916573782596
VOTE_EMOJI_ID = 5774022692642492953
NO_VOTE_EMOJI_ID = 5431449001532594346
TAG_EMOJI_ID = 5890727932011223292

MODULE_NAME = "poll"

DEFAULT_TEMPLATES_SIMPLE = {
    "данет": ["Да", "Нет"],
    "оценка": ["1", "2", "3", "4", "5"],
    "время": ["Сейчас", "Через 5 мин", "Через 15 мин", "Позже"]
}

# --- Утилиты для Entities ---
ENTITY_MAP = {
    'MessageEntityBold': MessageEntityBold, 'MessageEntityItalic': MessageEntityItalic,
    'MessageEntityCode': MessageEntityCode, 'MessageEntityPre': MessageEntityPre,
    'MessageEntityUnderline': MessageEntityUnderline, 'MessageEntityStrike': MessageEntityStrike,
    'MessageEntityCustomEmoji': MessageEntityCustomEmoji, 'MessageEntityTextUrl': MessageEntityTextUrl,
    'MessageEntityBlockquote': MessageEntityBlockquote, 'MessageEntityMentionName': MessageEntityMentionName
}

def deserialize_entities(entities_list):
    if not entities_list: return []
    reconstructed = []
    for e_dict in entities_list:
        class_name = e_dict.get('_')
        if class_name in ENTITY_MAP:
            params = {k: v for k, v in e_dict.items() if k != '_'}
            if 'document_id' in params: params['document_id'] = int(params['document_id'])
            if 'user_id' in params: params['user_id'] = int(params['user_id'])
            reconstructed.append(ENTITY_MAP[class_name](**params))
    return reconstructed

class PollModule(Module):
    def __init__(self):
        self.waiting_input = {} 

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        
        # Загружаем шаблоны
        raw_templates = self.db.get_module_data(MODULE_NAME, "templates", default=DEFAULT_TEMPLATES_SIMPLE)
        
        # --- МИГРАЦИЯ ДАННЫХ ---
        self.templates = {}
        for name, data in raw_templates.items():
            # Если старый формат (список) или неполный dict
            if isinstance(data, list):
                # Конвертируем список строк в новую структуру
                opts = []
                for opt in data:
                    if isinstance(opt, str): opts.append({"text": opt, "entities": []})
                    else: opts.append(opt) # Уже dict
                
                self.templates[name] = {
                    "options": opts,
                    "flags": {"public": True, "multi": False, "quiz": False, "pin": False}
                }
            elif isinstance(data, dict) and "options" in data:
                # Уже новый формат, проверяем наличие всех флагов
                if "flags" not in data:
                    data["flags"] = {"public": True, "multi": False, "quiz": False, "pin": False}
                else:
                    if "pin" not in data["flags"]: data["flags"]["pin"] = False
                    if "public" not in data["flags"]: data["flags"]["public"] = True
                self.templates[name] = data
            
        self.save_data()

    def save_data(self):
        self.db.set_module_data(MODULE_NAME, "templates", self.templates)

    @register("poll", incoming=True)
    async def create_poll_cmd(self, event):
        """Создать опрос по шаблону.
        
        Usage: {prefix}poll <шаблон> <вопрос>
        """
        if not check_permission(event, min_level="TRUSTED"): return

        args_split = event.message.text.split(maxsplit=2)
        if len(args_split) < 3:
            available = ", ".join([f"`{k}`" for k in self.templates.keys()])
            return await build_and_edit(event, [
                {"text": "ℹ️ Используйте: .poll <шаблон> <вопрос>\n", "entity": MessageEntityItalic},
                {"text": "Доступные шаблоны: ", "entity": MessageEntityBold},
                {"text": available if available else "Нет шаблонов"}
            ])

        tpl_name = args_split[1].lower()
        question_text = args_split[2]
        
        # Ищем entities вопроса
        raw_text = event.text
        question_offset = raw_text.find(question_text, len(args_split[0]) + 1)
        
        if tpl_name not in self.templates:
             return await build_and_edit(event, [{"text": f"❌ Шаблон '{tpl_name}' не найден.", "entity": MessageEntityBold}])

        template_data = self.templates[tpl_name]
        options_data = template_data["options"]
        flags = template_data["flags"]

        if not options_data:
             return await build_and_edit(event, [{"text": f"❌ Шаблон '{tpl_name}' пуст.", "entity": MessageEntityBold}])

        try:
            # 1. Варианты ответов
            answers = []
            for i, opt_data in enumerate(options_data):
                txt = opt_data['text']
                ents = deserialize_entities(opt_data.get('entities', []))
                answers.append(PollAnswer(
                    text=TextWithEntities(text=txt, entities=ents), 
                    option=bytes([i])
                ))
            
            # 2. Вопрос
            question_entities = []
            if event.entities:
                for e in event.entities:
                    if e.offset >= question_offset:
                        d = e.to_dict()
                        d['offset'] = e.offset - question_offset
                        d.pop('_', None)
                        cls = type(e)
                        question_entities.append(cls(**d))

            poll = Poll(
                id=random.randint(0, 2**63),
                question=TextWithEntities(text=question_text, entities=question_entities),
                answers=answers,
                closed=False,
                public_voters=flags.get("public", True),
                multiple_choice=flags.get("multi", False),
                quiz=flags.get("quiz", False),
                close_period=None,
                close_date=None
            )

            sent_msg = await event.client.send_message(
                event.chat_id,
                file=InputMediaPoll(poll=poll)
            )
            await event.delete()
            
            # 3. Закрепление
            if flags.get("pin", False):
                try:
                    await sent_msg.pin()
                except Exception:
                    # Если не удалось закрепить, отправляем тихое уведомление
                    err_msg = await event.client.send_message(
                        event.chat_id, 
                        "⚠️ **Не удалось закрепить опрос (нет прав).**", 
                        reply_to=sent_msg
                    )
                    await asyncio.sleep(5)
                    await err_msg.delete()

        except Exception as e:
            await build_and_edit(event, [{"text": f"❌ Ошибка создания опроса: {e}"}])

    @register("pollcfg", incoming=True)
    async def pollcfg_cmd(self, event):
        """Открыть настройки опросов.
        
        Usage: {prefix}pollcfg
        """
        if not check_permission(event, min_level="TRUSTED"): return
        await build_and_edit(event, [{"text": "⚙️ Открываю настройки...", "entity": MessageEntityItalic}])
        await _call_inline_bot(event, "poll:menu")

    @register("pollscan", incoming=True)
    async def pollscan_handler(self, event):
        """Сканирует опрос и показывает результаты.
        
        Usage: {prefix}pollscan (в ответ на опрос)
        """
        if not check_permission(event, min_level="TRUSTED"): return

        reply_msg = await event.get_reply_message()
        if not reply_msg or not reply_msg.poll:
            return await build_and_edit(event, [{"text": "❌ Ответьте на опрос.", "entity": MessageEntityBold}])

        poll = reply_msg.poll.poll
        if not poll.public_voters:
            return await build_and_edit(event, [{"text": "ℹ️ Опрос анонимный. Данные недоступны.", "entity": MessageEntityItalic}])

        try:
            await event.edit("🔄 Сканирую результаты...")
            options_map, user_map, all_voter_ids = await _fetch_poll_data(event.client, event.chat_id, reply_msg.id, poll)
            
            text_content = ""
            entities = []
            current_offset = 0

            def append_part(text, entity_class=None, **kwargs):
                nonlocal text_content, entities, current_offset
                text_content += text
                if entity_class:
                    utf16_len = len(text.encode('utf-16-le')) // 2
                    if utf16_len > 0:
                        entities.append(entity_class(offset=current_offset, length=utf16_len, **kwargs))
                current_offset += len(text.encode('utf-16-le')) // 2

            append_part("📋", MessageEntityCustomEmoji, document_id=POLL_EMOJI_ID)
            append_part(" Сканер опроса\n", MessageEntityBold)
            append_part(f"{poll.question.text}\n\n", MessageEntityItalic)

            for i, (option_text, user_ids) in enumerate(options_map.items(), 1):
                append_part("✅", MessageEntityCustomEmoji, document_id=VOTE_EMOJI_ID)
                append_part(f" {i}. {option_text} ({len(user_ids)})\n", MessageEntityBold)
                if not user_ids:
                    append_part("    (Нет голосов)\n\n", MessageEntityItalic)
                    continue
                for user_id in user_ids:
                    user = user_map.get(user_id)
                    name = _format_name(user, user_id)
                    append_part(f"    • {name}", MessageEntityTextUrl, url=f"tg://user?id={user_id}")
                    append_part("\n")
                append_part("\n")

            non_voters = await _get_non_voters(event.client, event.chat_id, all_voter_ids)
            append_part("❌", MessageEntityCustomEmoji, document_id=NO_VOTE_EMOJI_ID)
            append_part(f" Не голосовали ({len(non_voters)})\n", MessageEntityBold)

            if not non_voters:
                append_part("    (Все проголосовали или нет данных)\n", MessageEntityItalic)
            else:
                for user in non_voters:
                    name = _format_name(user, user.id)
                    append_part(f"    • {name}", MessageEntityTextUrl, url=f"tg://user?id={user.id}")
                    append_part("\n")

            text_len_utf16 = len(text_content.encode('utf-16-le')) // 2
            if text_len_utf16 > 0:
                entities.insert(0, MessageEntityBlockquote(offset=0, length=text_len_utf16, collapsed=True))

            await event.edit(text_content, formatting_entities=entities, link_preview=False)

        except Exception as e:
            await build_and_edit(event, [{"text": f"❌ Ошибка: {e}", "entity": MessageEntityBold}])

    @register("polltag", incoming=True)
    async def polltag_handler(self, event):
        """Тегает пользователей из выбранной категории опроса.
        
        Usage:
        {prefix}polltag <номер_варианта> [текст]
        {prefix}polltag novote [текст]
        """
        if not check_permission(event, min_level="TRUSTED"): return

        args = event.message.text.split(maxsplit=2)
        if len(args) < 2:
            p = db.get_setting("prefix", ".")
            return await build_and_edit(event, [{"text": f"❌ Использование: {p}polltag <номер|novote> [текст]" }])

        category_arg = args[1].lower()
        custom_text = args[2] if len(args) > 2 else ""

        reply_msg = await event.get_reply_message()
        if not reply_msg or not reply_msg.poll:
            return await build_and_edit(event, [{"text": "❌ Ответьте на опрос."}])

        poll = reply_msg.poll.poll
        if not poll.public_voters:
            return await build_and_edit(event, [{"text": "❌ Опрос анонимный."}])

        await event.edit("🔄 Сбор пользователей...")

        try:
            options_map, user_map, all_voter_ids = await _fetch_poll_data(event.client, event.chat_id, reply_msg.id, poll)
            target_users = []
            target_label = ""

            if category_arg == "novote":
                non_voters = await _get_non_voters(event.client, event.chat_id, all_voter_ids)
                target_users = non_voters
                target_label = "Не проголосовавшие"
            elif category_arg.isdigit():
                idx = int(category_arg) - 1
                option_keys = list(options_map.keys())
                if 0 <= idx < len(option_keys):
                    option_text = option_keys[idx]
                    user_ids = options_map[option_text]
                    for uid in user_ids:
                        user = user_map.get(uid)
                        if user: target_users.append(user)
                    target_label = f"Выбравшие '{option_text}'"
                else:
                    return await build_and_edit(event, [{"text": f"❌ Нет варианта №{idx+1}."}])
            else:
                return await build_and_edit(event, [{"text": "❌ Неверная категория."}])

            if not target_users:
                return await build_and_edit(event, [{"text": f"ℹ️ В категории '{target_label}' никого нет."}])

            await event.delete()
            chunk_size = 5
            for i in range(0, len(target_users), chunk_size):
                chunk = target_users[i:i + chunk_size]
                mentions = []
                for user in chunk:
                    if user.username:
                        mentions.append(f"@{user.username}")
                    else:
                        name = get_display_name(user)
                        mentions.append(f'<a href="tg://user?id={user.id}">{html.escape(name)}</a>')
                
                mentions_str = " ".join(mentions)
                final_html = f"{html.escape(custom_text)}\n{mentions_str}" if custom_text else mentions_str
                    
                try:
                    await event.client.send_message(event.chat_id, final_html, parse_mode='html')
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    print(f"Error sending tag chunk: {e}")

        except Exception as e:
            await event.respond(f"❌ Ошибка: {e}")


    # --- INLINE HANDLERS ---

    @inline_handler(r"poll:menu", title="Настройки Опросов", description="Шаблоны и параметры")
    async def poll_menu_inline(self, event):
        """Главное меню."""
        text = "<b>📂 Шаблоны опросов</b>\n\nВыберите шаблон для настройки или создания опроса:"
        buttons = []
        for name in self.templates.keys():
            buttons.append([Button.inline(f"📝 {name}", data=f"poll:tpl:edit:{name}")])
        buttons.append([Button.inline("➕ Создать новый", data="poll:tpl:create")])
        buttons.append([Button.inline("❌ Закрыть", data="close_panel")])
        return text, buttons

    @callback_handler(r"poll:menu")
    async def poll_menu_cb(self, event):
        """Возврат в главное меню."""
        if event.sender_id in self.waiting_input: del self.waiting_input[event.sender_id]
        text = "<b>📂 Шаблоны опросов</b>\n\nВыберите шаблон для настройки или создания опроса:"
        buttons = []
        for name in self.templates.keys():
            buttons.append([Button.inline(f"📝 {name}", data=f"poll:tpl:edit:{name}")])
        buttons.append([Button.inline("➕ Создать новый", data="poll:tpl:create")])
        buttons.append([Button.inline("❌ Закрыть", data="close_panel")])
        await event.edit(text, buttons=buttons, parse_mode="html")

    @callback_handler(r"poll:tpl:create")
    async def poll_tpl_create_cb(self, event):
        self.waiting_input[event.sender_id] = {"type": "new_template"}
        await event.edit(
            "⌨️ <b>Введите название для нового шаблона.</b>\n\nОтправьте сообщение в этот чат.", 
            buttons=[[Button.inline("🔙 Назад", data="poll:menu")]],
            parse_mode="html"
        )

    @callback_handler(r"poll:tpl:edit:(.+)")
    async def poll_tpl_edit_cb(self, event):
        """Меню редактирования конкретного шаблона."""
        
        # ❗️ ИСПРАВЛЕНИЕ: Убрал .decode()
        tpl_name = event.pattern_match.group(1)
        
        if tpl_name not in self.templates:
            return await event.answer("Шаблон не найден", alert=True)
        
        data = self.templates[tpl_name]
        opts = data["options"]
        flags = data["flags"]

        text = f"<b>Шаблон:</b> <code>{tpl_name}</code>\n\n"
        text += f"⚙️ <b>Настройки:</b>\n"
        text += f"• Публичный: {'✅' if flags['public'] else '❌'}\n"
        text += f"• Множ. выбор: {'✅' if flags['multi'] else '❌'}\n"
        text += f"• Викторина: {'✅' if flags['quiz'] else '❌'}\n"
        text += f"• 📌 Закреп: {'✅' if flags['pin'] else '❌'}\n\n"
        
        text += "<b>Варианты ответов:</b>\n"
        for i, opt in enumerate(opts, 1):
            txt = opt['text']
            text += f"{i}. {txt}\n"
        
        buttons = [
            [
                Button.inline(f"{'✅' if flags['public'] else '❌'} Публичный", data=f"poll:set:{tpl_name}:public"),
                Button.inline(f"{'✅' if flags['multi'] else '❌'} Multi", data=f"poll:set:{tpl_name}:multi"),
            ],
            [
                Button.inline(f"{'✅' if flags['quiz'] else '❌'} Викторина", data=f"poll:set:{tpl_name}:quiz"),
                Button.inline(f"{'✅' if flags['pin'] else '❌'} 📌 Закреп", data=f"poll:set:{tpl_name}:pin"),
            ],
            [
                Button.inline("➕ Вариант", data=f"poll:opt:add:{tpl_name}"),
                Button.inline("➖ Вариант", data=f"poll:opt:del_menu:{tpl_name}")
            ],
            [Button.inline("🗑️ Удалить шаблон", data=f"poll:tpl:del:{tpl_name}")],
            [Button.inline("🔙 Назад", data="poll:menu")]
        ]
        await event.edit(text, buttons=buttons, parse_mode="html")

    @callback_handler(r"poll:set:(.+):(\w+)")
    async def poll_toggle_flag_cb(self, event):
        """Переключение флагов шаблона."""
        
        # ❗️ ИСПРАВЛЕНИЕ: Убрал .decode()
        tpl_name = event.pattern_match.group(1)
        flag = event.pattern_match.group(2)
        
        if tpl_name in self.templates:
            current = self.templates[tpl_name]["flags"].get(flag, False)
            self.templates[tpl_name]["flags"][flag] = not current
            self.save_data()
        
        await self.poll_tpl_edit_cb(event)

    @callback_handler(r"poll:opt:add:(.+)")
    async def poll_opt_add_cb(self, event):
        # ❗️ ИСПРАВЛЕНИЕ: Убрал .decode()
        tpl_name = event.pattern_match.group(1)
        
        self.waiting_input[event.sender_id] = {"type": "add_option", "tpl": tpl_name}
        await event.edit(
            f"⌨️ <b>Введите вариант ответа для '{tpl_name}'.</b>",
            buttons=[[Button.inline("🔙 Назад", data=f"poll:tpl:edit:{tpl_name}")]],
            parse_mode="html"
        )

    @callback_handler(r"poll:opt:del_menu:(.+)")
    async def poll_opt_del_menu_cb(self, event):
        # ❗️ ИСПРАВЛЕНИЕ: Убрал .decode()
        tpl_name = event.pattern_match.group(1)
        
        opts = self.templates[tpl_name]["options"]
        
        text = f"<b>Удаление варианта из '{tpl_name}':</b>"
        buttons = []
        for i, opt in enumerate(opts):
            txt = opt['text']
            buttons.append([Button.inline(f"❌ {txt}", data=f"poll:opt:del:{tpl_name}:{i}")])
        buttons.append([Button.inline("🔙 Назад", data=f"poll:tpl:edit:{tpl_name}")])
        await event.edit(text, buttons=buttons, parse_mode="html")

    @callback_handler(r"poll:opt:del:(.+):(\d+)")
    async def poll_opt_del_cb(self, event):
        # ❗️ ИСПРАВЛЕНИЕ: Убрал .decode()
        tpl_name = event.pattern_match.group(1)
        idx = int(event.pattern_match.group(2))
        
        if tpl_name in self.templates:
            opts = self.templates[tpl_name]["options"]
            if 0 <= idx < len(opts):
                opts.pop(idx)
                self.save_data()
        
        await self.poll_opt_del_menu_cb(event)

    @callback_handler(r"poll:tpl:del:(.+)")
    async def poll_tpl_del_cb(self, event):
        # ❗️ ИСПРАВЛЕНИЕ: Убрал .decode()
        tpl_name = event.pattern_match.group(1)
        
        if tpl_name in self.templates:
            del self.templates[tpl_name]
            self.save_data()
            await event.answer("Шаблон удален!")
        await self.poll_menu_cb(event)

    @watcher(incoming=True, outgoing=True)
    async def poll_input_watcher(self, event):
        if event.sender_id not in self.waiting_input: return
        
        data = self.waiting_input.pop(event.sender_id)
        text_val = event.raw_text.strip()
        
        if not text_val: return
        
        try: await event.delete()
        except: pass

        if data["type"] == "new_template":
            name = text_val.lower()
            if name in self.templates:
                await event.respond(f"⚠️ Шаблон '{name}' уже существует.", alert=True)
            else:
                self.templates[name] = {
                    "options": [],
                    "flags": {"public": True, "multi": False, "quiz": False, "pin": False}
                }
                self.save_data()
                msg = await event.respond(f"✅ Шаблон '{name}' создан! Теперь настройте его.")
                await asyncio.sleep(2)
                try: await msg.delete()
                except: pass
        
        elif data["type"] == "add_option":
            tpl = data["tpl"]
            if tpl in self.templates:
                if len(self.templates[tpl]["options"]) >= 10:
                    await event.respond("⚠️ Максимум 10 вариантов!", alert=True)
                else:
                    from telethon.tl.types import MessageEntityCustomEmoji
                    ents_serialized = []
                    if event.entities:
                        for e in event.entities:
                            d = e.to_dict()
                            d['_'] = type(e).__name__
                            ents_serialized.append(d)
                        
                    self.templates[tpl]["options"].append({
                        "text": text_val, 
                        "entities": ents_serialized
                    })
                    self.save_data()
                    msg = await event.respond(f"✅ Вариант добавлен.")
                    await asyncio.sleep(1)
                    try: await msg.delete()
                    except: pass

# --- Вспомогательные функции ---
async def _fetch_poll_data(client, chat_id, msg_id, poll):
    option_text_by_id = {answer.option: answer.text.text for answer in poll.answers}
    options_map = {text: [] for text in option_text_by_id.values()}
    user_map = {}
    all_voter_ids = set()

    for option_bytes, option_text in option_text_by_id.items():
        offset = None
        while True:
            result = await client(functions.messages.GetPollVotesRequest(
                peer=chat_id, id=msg_id, option=option_bytes, offset=offset, limit=100
            ))
            for user in result.users: user_map[user.id] = user
            for vote in result.votes:
                uid = None
                if hasattr(vote.peer, 'user_id'): uid = vote.peer.user_id
                elif hasattr(vote.peer, 'channel_id'): uid = vote.peer.channel_id
                elif hasattr(vote.peer, 'chat_id'): uid = vote.peer.chat_id
                if uid:
                    if uid not in options_map[option_text]:
                        options_map[option_text].append(uid)
                        all_voter_ids.add(uid)
            if not result.next_offset: break
            offset = result.next_offset
    return options_map, user_map, all_voter_ids

async def _get_non_voters(client, chat_id, voter_ids):
    try:
        participants = await client.get_participants(chat_id, limit=3000)
        non_voters = []
        for user in participants:
            if user.bot or user.deleted: continue
            if user.id not in voter_ids:
                non_voters.append(user)
        return non_voters
    except Exception:
        return []

def _format_name(user, uid):
    if not user: return f"ID: {uid}"
    if user.username: return f"@{user.username}"
    name = get_display_name(user)
    return name if name else f"User {uid}"