#  _____                          
# |_   _|____  ____ _ _ __   ___  
#   | |/ _ \ \/ / _` | '_ \ / _ \ 
#   | | (_) >  < (_| | | | | (_) |
#   |_|\___/_/\_\__,_|_| |_|\___/ 
#                              
# meta banner: https://i.ibb.co/r2VKP6yv/image-9709.jpg
# meta developer: @Toxano_Modules
# scope: @Toxano_Modules

import asyncio
import logging
import datetime
from typing import Union, Optional
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import Message
from .. import loader, utils

logger = logging.getLogger(__name__)

TIMEZONE_OFFSETS = {
    "MSK": 3,      # Москва
    "UTC": 0,      # Всемирное координированное время
    "GMT": 0,      # Среднее время по Гринвичу
    "CET": 1,      # Центральноевропейское время
    "EET": 2,      # Восточноевропейское время
    "AZT": 4,      # Азербайджанское время 
    "AMT": 4,      # Армянское время
    "GET": 4,      # Грузинское время
    "TJT": 5,      # Таджикистанское время
    "TMT": 5,      # Туркменистанское время
    "UZT": 5,      # Узбекистанское время
    "KGT": 6,      # Киргизское время
    "BDT": 6,      # Бангладешское время
    "IST": 5.5,    # Индийское время
    "THA": 7,      # Тайское время
    "ICT": 7,      # Индокитайское время
    "CST": 8,      # Китайское время
    "HKT": 8,      # Гонконгское время
    "JST": 9,      # Японское время
    "KST": 9,      # Корейское время
    "EST": -5,     # Восточное время (США)
    "EDT": -4,     # Восточное летнее время (США)
    "CDT": -5,     # Центральное летнее время (США)
    "MDT": -6,     # Горное летнее время (США)
    "PDT": -7,     # Тихоокеанское летнее время (США)
    "PST": -8,     # Тихоокеанское время (США)
    "AKST": -9,    # Аляскинское время
    "AEST": 10,    # Восточноавстралийское время
    "NZST": 12,   # Новозеландское время
    "IRKTSK": 8  #Иркутск
}

FONT_STYLES_DESC = """
1. 12:34 -> 12:34 (обычный)
2. 12:34 -> 『12:34』
3. 12:34 -> ➊➋:➌➍
4. 12:34 -> ⓵⓶:⓷⓸
5. 12:34 -> ①②:③④
6. 12:34 -> 𝟙𝟚:𝟛𝟜 
7. 12:34 -> ¹²'³⁴
8. 12:34 -> ₁₂‚₃₄
9. 12:34 -> 1️⃣2️⃣:3️⃣4️⃣
"""

FONT_STYLES = {
    1: lambda x: x,
    2: lambda x: f"『{x}』",
    3: lambda x: x.translate(str.maketrans("0123456789", "⓿➊➋➌➍➎➏➐➑➒")),
    4: lambda x: x.translate(str.maketrans("0123456789", "⓪⓵⓶⓷⓸⓹⓺⓻⓼⓽")),
    5: lambda x: x.translate(str.maketrans("0123456789", "⓪①②③④⑤⑥⑦⑧⑨")),
    6: lambda x: x.translate(str.maketrans("0123456789", "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡")),
    7: lambda x: x.translate(str.maketrans("0123456789:", "⁰¹²³⁴⁵⁶⁷⁸⁹'")),
    8: lambda x: x.translate(str.maketrans("0123456789:", "₀₁₂₃₄₅₆₇₈₉‚")),
    9: lambda x: "".join([i + "️⃣" if i.isdigit() else i for i in x])
}

class FontStyleValidator(loader.validators.Validator):
    """Кастомный валидатор для стиля шрифта"""
    
    def __init__(self):
        super().__init__(
            self._validate,
            {"en": "font style (1-9)", "ru": "стиль шрифта (1-9)"}
        )
    
    @staticmethod
    def _validate(value):
        if not isinstance(value, int):
            raise loader.validators.ValidationError("Значение должно быть числом")
        
        if value == 0:
            return 1
        
        if value < 1 or value > 9:
            raise loader.validators.ValidationError("Значение должно быть от 1 до 9")
        
        return value

@loader.tds
class TimeInNickMod(loader.Module):
    """Показывает текущее время в никнейме и био с разными стилями шрифтов"""
    
    strings = {
        "name": "TimeInNick",
        "time_enabled": "⏰ Отображение времени в никнейме включено",
        "time_disabled": "⏰ Отображение времени в никнейме выключено",
        "bio_enabled": "⏰ Отображение времени в био включено", 
        "bio_disabled": "⏰ Отображение времени в био выключено",
        "invalid_delay": "⚠️ Неверный интервал обновления (должно быть 0-60 минут)",
        "cfg_timezone": "Часовой пояс",
        "cfg_update": "Интервал обновления (0-60 минут, 0 = мгновенное обновление)",
        "cfg_nick_format": "Формат никнейма. Доступные переменные: {nickname}, {time}",
        "cfg_bio_format": "Формат био. Доступные переменные: {bio}, {time}",
        "error_updating": "⚠️ Ошибка обновления: {}",
        "error_timezone": "⚠️ Неверный часовой пояс. Используйте один из: {}",
        "error_max_retries": "⚠️ Превышено максимальное количество попыток обновления",
        "error_invalid_data": "⚠️ Некорректные сохраненные данные, сброс настроек"
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "TIMEZONE",
                "MSK",
                doc=lambda: self.strings("cfg_timezone"),
                validator=loader.validators.Choice(list(TIMEZONE_OFFSETS.keys()))
            ),
            loader.ConfigValue(
                "UPDATE_DELAY",
                0,
                doc=lambda: self.strings("cfg_update"),
                validator=loader.validators.Integer(minimum=0, maximum=60)
            ),
            loader.ConfigValue(
                "NICK_FORMAT",
                "{nickname} | {time}",
                doc=lambda: self.strings("cfg_nick_format"),
                validator=loader.validators.String()
            ),
            loader.ConfigValue(
                "BIO_FORMAT",
                "{bio} | {time}",
                doc=lambda: self.strings("cfg_bio_format"),
                validator=loader.validators.String()
            ),
            loader.ConfigValue(
                "FONT_STYLE",
                1,
                doc=FONT_STYLES_DESC,
                validator=FontStyleValidator()
            )
        )
        self.nick_active = False
        self.bio_active = False
        self.original_nick = None
        self.original_bio = None
        self.nick_task = None
        self.bio_task = None
        self.last_nick_time = None
        self.last_bio_time = None
        self.max_retries = 10
        self.current_nick_retries = 0
        self.current_bio_retries = 0

    async def client_ready(self, client, db):
        """Инициализация после загрузки модуля"""
        try:
            # Восстановление состояний с валидацией
            self.nick_active = self._db.get(self.strings["name"], "nick_active", False)
            self.bio_active = self._db.get(self.strings["name"], "bio_active", False)
            self.original_nick = self._db.get(self.strings["name"], "original_nick", None)
            self.original_bio = self._db.get(self.strings["name"], "original_bio", None)
            
            # Валидация и восстановление никнейма
            if self.nick_active:
                if not self.original_nick or not isinstance(self.original_nick, str):
                    logger.warning("Invalid nickname data, resetting")
                    await self._reset_nick_state()
                else:
                    self.nick_task = asyncio.create_task(self._update_nickname())
            
            # Валидация и восстановление био
            if self.bio_active:
                try:
                    full_user = await self._client(GetFullUserRequest("me"))
                    current_bio = full_user.full_user.about or ""
                    
                    if not self.original_bio:
                        self.original_bio = current_bio
                        self._db.set(self.strings["name"], "original_bio", current_bio)
                    
                    self.bio_task = asyncio.create_task(self._update_bio())
                except Exception as e:
                    logger.exception("Failed to restore bio on startup")
                    await self._reset_bio_state()
        except Exception as e:
            logger.exception("Error during client_ready")
            await self._reset_all_states()

    async def _reset_nick_state(self):
        """Сброс состояния никнейма"""
        self.nick_active = False
        self.original_nick = None
        if self.nick_task:
            self.nick_task.cancel()
        self._db.set(self.strings["name"], "nick_active", False)
        self._db.set(self.strings["name"], "original_nick", None)

    async def _reset_bio_state(self):
        """Сброс состояния био"""
        self.bio_active = False
        self.original_bio = None
        if self.bio_task:
            self.bio_task.cancel()
        self._db.set(self.strings["name"], "bio_active", False)
        self._db.set(self.strings["name"], "original_bio", None)

    async def _reset_all_states(self):
        """Сброс всех состояний"""
        await self._reset_nick_state()
        await self._reset_bio_state()

    async def get_formatted_time(self) -> str:
        """Получает текущее время с учетом часового пояса и стиля шрифта"""
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            
            timezone = self.config["TIMEZONE"].upper()
            if timezone not in TIMEZONE_OFFSETS:
                logger.error(f"Invalid timezone: {timezone}")
                timezone = "UTC"
                
            offset = TIMEZONE_OFFSETS[timezone]
            hour_offset = int(offset)
            minute_offset = int((offset - hour_offset) * 60)
            
            adjusted_time = now + datetime.timedelta(hours=hour_offset, minutes=minute_offset)
            time_str = adjusted_time.strftime("%H:%M")
            
            font_style = self.config["FONT_STYLE"]
            if font_style == 0 or font_style not in FONT_STYLES:
                font_style = 1
            
            return FONT_STYLES[font_style](time_str)
        except Exception as e:
            logger.exception("Error formatting time")
            return datetime.datetime.now().strftime("%H:%M")

    async def _update_nickname(self) -> None:
        """Обновляет никнейм с текущим временем"""
        update_delay = self.config["UPDATE_DELAY"] * 60 if self.config["UPDATE_DELAY"] > 0 else 1
        self.current_nick_retries = 0
        
        while self.nick_active and self.current_nick_retries < self.max_retries:
            try:
                current_time = await self.get_formatted_time()
                
                if current_time != self.last_nick_time:
                    new_nick = self.config["NICK_FORMAT"].format(
                        nickname=self.original_nick or "",
                        time=current_time
                    )

                    await self._client(UpdateProfileRequest(
                        first_name=new_nick[:70]
                    ))
                    self.last_nick_time = current_time
                    self.current_nick_retries = 0  # Сброс счетчика при успешном обновлении

            except Exception as e:
                self.current_nick_retries += 1
                logger.exception(f"Error updating nickname (attempt {self.current_nick_retries}): {e}")
                
                if self.current_nick_retries >= self.max_retries:
                    logger.error("Max retries exceeded for nickname updates")
                    await self._reset_nick_state()
                    break
                
                await asyncio.sleep(min(5 * self.current_nick_retries, 30))  # Экспоненциальная задержка
                continue

            await asyncio.sleep(update_delay)

    async def _update_bio(self) -> None:
        """Обновляет био с текущим временем"""
        update_delay = self.config["UPDATE_DELAY"] * 60 if self.config["UPDATE_DELAY"] > 0 else 1
        self.current_bio_retries = 0
        
        while self.bio_active and self.current_bio_retries < self.max_retries:
            try:
                current_time = await self.get_formatted_time()
                
                if current_time != self.last_bio_time:
                    new_bio = self.config["BIO_FORMAT"].format(
                        bio=self.original_bio or "",
                        time=current_time
                    )

                    await self._client(UpdateProfileRequest(
                        about=new_bio[:70]
                    ))
                    self.last_bio_time = current_time
                    self.current_bio_retries = 0  # Сброс счетчика при успешном обновлении

            except Exception as e:
                self.current_bio_retries += 1
                logger.exception(f"Error updating bio (attempt {self.current_bio_retries}): {e}")
                
                if self.current_bio_retries >= self.max_retries:
                    logger.error("Max retries exceeded for bio updates")
                    await self._reset_bio_state()
                    break
                
                await asyncio.sleep(min(5 * self.current_bio_retries, 30))  # Экспоненциальная задержка
                continue

            await asyncio.sleep(update_delay)

    async def _safely_restore_profile(self, restore_nick: bool = False, restore_bio: bool = False) -> bool:
        """Безопасно восстанавливает профиль"""
        try:
            if restore_nick and self.original_nick:
                await self._client(UpdateProfileRequest(
                    first_name=self.original_nick[:70]
                ))
            
            if restore_bio and self.original_bio is not None:
                await self._client(UpdateProfileRequest(
                    about=self.original_bio[:70]
                ))
            
            return True
        except Exception as e:
            logger.exception(f"Error restoring profile: {e}")
            return False

    @loader.command(
        ru_doc="Включить/выключить отображение времени в никнейме"
    )
    async def timenick(self, message: Message) -> None:
        """Включить/выключить отображение времени в никнейме"""
        if self.nick_active:
            self.nick_active = False
            if self.nick_task:
                self.nick_task.cancel()
                self.nick_task = None
            
            success = await self._safely_restore_profile(restore_nick=True)
            if not success:
                await utils.answer(
                    message,
                    self.strings["error_updating"].format("Не удалось восстановить никнейм")
                )
                return
            
            await self._reset_nick_state()
            await utils.answer(message, self.strings["time_disabled"])
            return
        
        try:
            me = await self._client.get_me()
            current_nick = me.first_name or ""
            
            # Извлечение оригинального никнейма
            if "|" in current_nick:
                self.original_nick = current_nick.split("|")[0].strip()
            else:
                self.original_nick = current_nick
            
            if not self.original_nick:
                self.original_nick = "User"
            
            self.nick_active = True
            self.current_nick_retries = 0
            
            self._db.set(self.strings["name"], "nick_active", True)
            self._db.set(self.strings["name"], "original_nick", self.original_nick)
            
            self.nick_task = asyncio.create_task(self._update_nickname())
            await utils.answer(message, self.strings["time_enabled"])
        except Exception as e:
            await self._reset_nick_state()
            logger.exception(f"Error enabling time in nickname: {e}")
            await utils.answer(
                message,
                self.strings["error_updating"].format(str(e))
            )

    @loader.command(
        ru_doc="Включить/выключить отображение времени в био"
    )
    async def timebio(self, message: Message) -> None:
        """Включить/выключить отображение времени в био"""
        if self.bio_active:
            self.bio_active = False
            if self.bio_task:
                self.bio_task.cancel()
                self.bio_task = None

            success = await self._safely_restore_profile(restore_bio=True)
            if not success:
                await utils.answer(
                    message,
                    self.strings["error_updating"].format("Не удалось восстановить био")
                )
                return

            await self._reset_bio_state()
            await utils.answer(message, self.strings["bio_disabled"])
            return

        try:
            full_user = await self._client(GetFullUserRequest("me"))
            current_bio = full_user.full_user.about or ""
            
            # Извлечение оригинального био
            if "|" in current_bio:
                self.original_bio = current_bio.split("|")[0].strip()
            else:
                self.original_bio = current_bio
            
            self.bio_active = True
            self.current_bio_retries = 0

            self._db.set(self.strings["name"], "bio_active", True)
            self._db.set(self.strings["name"], "original_bio", self.original_bio)

            self.bio_task = asyncio.create_task(self._update_bio())
            await utils.answer(message, self.strings["bio_enabled"])
        except Exception as e:
            await self._reset_bio_state()
            logger.exception(f"Error enabling time in bio: {e}")
            await utils.answer(
                message,
                self.strings["error_updating"].format(str(e))
            )

    async def on_unload(self) -> None:
        """Вызывается при выгрузке модуля"""
        try:
            # Остановка задач
            if self.nick_task:
                self.nick_task.cancel()
            if self.bio_task:
                self.bio_task.cancel()
            
            # Восстановление профиля
            if self.nick_active or self.bio_active:
                await self._safely_restore_profile(
                    restore_nick=self.nick_active,
                    restore_bio=self.bio_active
                )

        except Exception as e:
            logger.exception(f"Error during unload: {e}")
        finally:
            # Очистка состояний в любом случае
            await self._reset_all_states()