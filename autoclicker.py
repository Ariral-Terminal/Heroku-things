# modules/autoclicker.py
"""
<manifest>
version: 2.0.0
source: https://t.me/KoteModulesMint
author: Kote
</manifest>

Автокликер для CombatMafiaSOBot (Solo Mode).
Логика Instant-click, аналогичная combat_twins.
"""

import re
import asyncio
import unicodedata
from telethon import events
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from telethon.tl.types import MessageEntityBold, MessageEntityCode
from telethon.errors import BotResponseTimeoutError, FloodWaitError

from core import register, Module, watcher
from utils import database as db
from utils.message_builder import build_and_edit
from utils.security import check_permission

MODULE_NAME = "combat" # Оставляем старое имя модуля для совместимости с БД
DEFAULT_BOT_USERNAME = "CombatMafiaSOBot"

# Глобальные настройки в памяти для скорости
CACHED_SETTINGS = {
    "enabled": False,
    "arena_chat_id": 0,
    "bot_username": DEFAULT_BOT_USERNAME,
    "auto_vote_confirm": True,
    "click_delay_ms": 100 
}

# Текущее состояние игрока
PLAYER_DATA = {'my_color': None}
# Текущая стратегия
CURRENT_STRATEGY = {'mode': 'last', 'target_name': None, 'direction': None}

async def force_click(client, peer, msg_id, data):
    """
    Агрессивный кликер (Instant Mode).
    Жмет кнопку до победного, игнорируя таймауты.
    """
    for i in range(10): 
        try:
            await asyncio.wait_for(
                client(GetBotCallbackAnswerRequest(
                    peer=peer,
                    msg_id=msg_id,
                    data=data
                )),
                timeout=0.8
            )
            return 
        except (asyncio.TimeoutError, BotResponseTimeoutError):
            await asyncio.sleep(0.1)
            continue
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception:
            return

def normalize_nick(nick):
    if not nick: return ""
    normalized = unicodedata.normalize('NFKD', nick)
    cleaned = ''.join(
        c for c in normalized 
        if c.isalnum() or c.isspace() or (0x0400 <= ord(c) <= 0x04FF) 
    )
    return ' '.join(cleaned.strip().split()).lower()

def get_target_button(rows, my_color, strategy):
    """Логика выбора цели (1 в 1 как в twins)."""
    if not rows: return None
    mode = strategy.get('mode', 'last')
    player_pattern = re.compile(r"(\d+)\.(🌝|🌚)\s*(.+)", re.UNICODE)

    # 1. По имени
    if mode == 'name':
        target_name = strategy.get('target_name')
        if not target_name: return None
        tnorm = normalize_nick(target_name)
        for row in rows:
            for btn in row.buttons:
                match = player_pattern.search(btn.text)
                if match:
                    _, _, name = match.groups()
                    if tnorm in normalize_nick(name): return btn
        return None

    # 2. Позиционная
    if not my_color: return None
    direction = strategy.get('direction')
    opposite_color = '🌚' if my_color == '🌝' else '🌝'
    enemies = []
    
    for row in rows:
        row_candidates = []
        for btn in row.buttons:
            match = player_pattern.search(btn.text)
            if match:
                _, color, name = match.groups()
                if color == opposite_color:
                    row_candidates.append({'btn': btn, 'name': name.strip()})
        
        if direction == 'left' and row_candidates: enemies.append(row_candidates[0])
        elif direction == 'right' and row_candidates: enemies.append(row_candidates[-1])
        else: enemies.extend(row_candidates)

    if not enemies: return None
    if mode == 'prelast' and len(enemies) >= 2: return enemies[-2]['btn']
    return enemies[-1]['btn'] # Last

class CombatModule(Module):
    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        # Загружаем настройки
        saved = self.db.get_module_data(MODULE_NAME, "settings", default={})
        CACHED_SETTINGS.update(saved)
        # Кэшируем свой ник
        me = await client.get_me()
        self.my_nick = normalize_nick(me.first_name or "")
        
    def save_settings(self):
        self.db.set_module_data(MODULE_NAME, "settings", CACHED_SETTINGS)

    @register("combat", incoming=True)
    async def combat_cmd(self, event):
        """Настройка Combat (Solo).
        Usage: {prefix}combat <on/off/set/settings/autovote>
        """
        if not check_permission(event, min_level="TRUSTED"): return
        args = event.message.text.split()
        if len(args) < 2: return await build_and_edit(event, "❌ Команды: on, off, set, settings, autovote")
        
        cmd = args[1].lower()
        
        if cmd == "on":
            CACHED_SETTINGS["enabled"] = True
            self.save_settings()
            await build_and_edit(event, "✅ Combat Solo: ВКЛЮЧЕН")
            
        elif cmd == "off":
            CACHED_SETTINGS["enabled"] = False
            self.save_settings()
            await build_and_edit(event, "❌ Combat Solo: ВЫКЛЮЧЕН")
            
        elif cmd == "set":
            # Установка Арены
            try:
                target_id = int(args[2]) if len(args) > 2 else event.chat_id
            except: target_id = event.chat_id
            CACHED_SETTINGS["arena_chat_id"] = target_id
            self.save_settings()
            await build_and_edit(event, f"✅ Арена установлена: `{target_id}`")

        elif cmd == "autovote":
             state = args[2].lower() == "on" if len(args) > 2 else not CACHED_SETTINGS["auto_vote_confirm"]
             CACHED_SETTINGS["auto_vote_confirm"] = state
             self.save_settings()
             await build_and_edit(event, f"✅ Авто-лайк/дизлайк: {state}")

        elif cmd == "settings":
             status = "ВКЛ" if CACHED_SETTINGS["enabled"] else "ВЫКЛ"
             avote = "ВКЛ" if CACHED_SETTINGS["auto_vote_confirm"] else "ВЫКЛ"
             parts = [
                 {"text": "⚙️ Combat Solo Settings", "entity": MessageEntityBold},
                 {"text": f"\n• Статус: {status}"},
                 {"text": f"\n• Арена: {CACHED_SETTINGS['arena_chat_id']}"},
                 {"text": f"\n• Авто-подтверждение: {avote}"},
                 {"text": f"\n• Delay: {CACHED_SETTINGS['click_delay_ms']}ms (ignored in force_click)"},
             ]
             await build_and_edit(event, parts)

    # --- СТРАТЕГИИ ---
    # Работают везде, меняют глобальную стратегию CURRENT_STRATEGY

    async def _strat(self, event, mode, target=None, direction=None, text=""):
        if not check_permission(event, min_level="TRUSTED"): return
        global CURRENT_STRATEGY
        CURRENT_STRATEGY = {'mode': mode, 'target_name': target, 'direction': direction}
        await build_and_edit(event, f"✅ Приказ (Solo): {text}")

    @register("веш", outgoing=True)
    async def vesh_cmd(self, event):
        """Голос в ник."""
        target = (event.pattern_match.group(1) or "").strip()
        await self._strat(event, 'name', target=target, text=f"Голос в {target}")

    @register("ласт", outgoing=True)
    async def last_cmd(self, event):
        """Голос в последнего."""
        await self._strat(event, 'last', text="Последний")

    @register("предласт", outgoing=True)
    async def prelast_cmd(self, event):
        """Голос в предпоследнего."""
        await self._strat(event, 'prelast', text="Предпоследний")
        
    @register("слева ласт", outgoing=True)
    async def ll_cmd(self, event): await self._strat(event, 'last', direction='left', text="Лев. Ласт")
    
    @register("справа ласт", outgoing=True)
    async def rl_cmd(self, event): await self._strat(event, 'last', direction='right', text="Прав. Ласт")

    @register("слева предласт", outgoing=True)
    async def lpl_cmd(self, event): await self._strat(event, 'prelast', direction='left', text="Лев. Пред")
    
    @register("справа предласт", outgoing=True)
    async def rpl_cmd(self, event): await self._strat(event, 'prelast', direction='right', text="Прав. Пред")


    # --- WATCHER ---

    @watcher(incoming=True)
    async def combat_watcher(self, event):
        if not CACHED_SETTINGS["enabled"]: return
        
        # Фильтр чата (если задан)
        if CACHED_SETTINGS["arena_chat_id"] and event.chat_id != CACHED_SETTINGS["arena_chat_id"]:
            # Если это ЛС с ботом - тоже обрабатываем (для определения цвета в начале)
            if not event.is_private: return

        try:
            sender = await event.get_sender()
            # Проверка бота (по username или ID если есть)
            if not sender or not sender.bot: return
            if DEFAULT_BOT_USERNAME.lower() not in (sender.username or "").lower(): return
        except: return

        msg_text = event.message.message
        if not msg_text: return

        # 1. ОПРЕДЕЛЕНИЕ ЦВЕТА (Парсим список живых)
        if "Живые игроки:" in msg_text:
            start = msg_text.find("Живые игроки:")
            end = msg_text.find("Из них:")
            if start != -1 and end != -1:
                section = msg_text[start:end]
                pattern = re.compile(r"(🌝|🌚)\s*(\d+)\.(.+?)(?=\n|$)", re.UNICODE)
                
                # Обновляем свой ник на всякий случай
                if not hasattr(self, 'my_nick'):
                     me = await self.client.get_me()
                     self.my_nick = normalize_nick(me.first_name or "")

                for match in pattern.finditer(section):
                    color, num, name = match.groups()
                    norm_name = normalize_nick(name)
                    if norm_name == self.my_nick or self.my_nick in norm_name or norm_name in self.my_nick:
                        PLAYER_DATA['my_color'] = color
                        break

        # 2. ГОЛОСОВАНИЕ (Выстрел)
        elif "Кого бы хотел убить?" in msg_text:
            if not event.message.reply_markup: return
            
            target_btn = get_target_button(
                event.message.reply_markup.rows, 
                PLAYER_DATA.get('my_color'), 
                CURRENT_STRATEGY
            )
            
            if target_btn:
                # INSTANT CLICK
                asyncio.create_task(force_click(
                    self.client,
                    event.chat_id,
                    event.message.id,
                    target_btn.data
                ))

        # 3. ПОДТВЕРЖДЕНИЕ (Лайк/Дизлайк)
        elif "Вы действительно" in msg_text and "повесить хотите?" in msg_text:
            if not CACHED_SETTINGS["auto_vote_confirm"]: return
            
            my_color = PLAYER_DATA.get('my_color')
            if not my_color: return
            
            # Ищем цвет жертвы в тексте
            target_color_match = re.search(r"(🌝|🌚)", msg_text)
            if not target_color_match: return
            target_color = target_color_match.group(1)
            
            # Свой цвет == Дизлайк, Чужой == Лайк
            action_key = "diss_asilan" if my_color == target_color else "like_asilan"
            
            if event.message.reply_markup:
                for row in event.message.reply_markup.rows:
                    for btn in row.buttons:
                        if action_key in btn.data.decode('utf-8', errors='ignore'):
                            asyncio.create_task(force_click(
                                self.client,
                                event.chat_id,
                                event.message.id,
                                btn.data
                            ))
                            return