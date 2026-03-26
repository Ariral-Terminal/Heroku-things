#  This file is part of SenkoGuardianModules
#  Copyright (c) 2025 Senko
#  This software is released under the MIT License.
#  https://opensource.org/licenses/MIT
__version__ = (7, 3, 2)
# meta developer: forked by @desertedowl / origin module dev @senkoguardianmodules
import re
import os
import io
import json
import uuid
import base64
import shutil
import random
import asyncio
import logging
import tempfile
import contextlib
from datetime import datetime

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import pytz
except ImportError:
    pytz = None

try:
    from markdown_it import MarkdownIt
except ImportError:
    MarkdownIt = None

from telethon import types as tg_types
from telethon.tl.types import (
    Message,
    DocumentAttributeAnimated,
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
)
from telethon.utils import get_display_name, get_peer_id
from telethon.errors.rpcerrorlist import (
    ChatAdminRequiredError,
    UserNotParticipantError,
    ChannelPrivateError,
)

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

DB_HISTORY_KEY = "chatgptcodex_conversations_v1"
DB_GAUTO_HISTORY_KEY = "chatgptcodex_gauto_conversations_v1"
DB_IMPERSONATION_KEY = "chatgptcodex_impersonation_chats"
DB_PRESETS_KEY = "chatgptcodex_prompt_presets"
DB_MEMORY_DISABLED_KEY = "chatgptcodex_memory_disabled_chats"
DB_CGIMG_PROMPT_HISTORY_KEY = "chatgptcodex_cgimg_prompt_history_v1"

REQUEST_TIMEOUT = 240
CODEX_TIMEOUT = 300

TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/html",
    "text/css",
    "text/csv",
    "application/json",
    "application/xml",
    "application/x-python",
    "text/x-python",
    "application/javascript",
    "application/x-sh",
}

IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

AUDIO_EXTENSIONS = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/oga": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
}

REASONING_EFFORT_VALUES = ("none", "minimal", "low", "medium", "high", "xhigh")


class ChatGPTCodex(loader.Module):
    """ChatGPT API + Codex CLI для Heroku"""

    strings = {
        "name": "ChatGPTCodex",
        "cfg_backend_doc": "Активный backend: 'chatgpt' или 'codex'.",
        "cfg_api_key_doc": "OpenAI API key для ChatGPT/Image API. Будет скрыт.",
        "cfg_chatgpt_model_doc": "Модель OpenAI API для текстовых ответов.",
        "cfg_codex_path_doc": "Путь до бинарника codex. Для Heroku можно указать полный путь, если codex не находится через PATH.",
        "cfg_codex_model_doc": "Модель для Codex CLI. Оставьте пустым, чтобы использовать дефолт CLI.",
        "cfg_reasoning_effort_doc": "Reasoning effort для поддерживаемых reasoning-моделей: none, minimal, low, medium, high, xhigh. Для Codex CLI значение none означает использовать дефолт модели без override.",
        "cfg_codex_yolo_mode_doc": "YOLO mode для Codex CLI: отключает sandbox и подтверждения. Codex сможет выполнять команды и менять файлы без вопросов. Опасно.",
        "cfg_codex_auto_install_doc": "Автоматически ставить Codex CLI, если он не найден.",
        "cfg_codex_install_dir_doc": "Куда автоматически ставить Codex CLI. Пусто = ~/.chatgptcodex/codex-cli",
        "cfg_image_model_doc": "Модель OpenAI Image API (например: gpt-image-1.5).",
        "cfg_buttons_doc": "Включить интерактивные кнопки.",
        "cfg_system_instruction_doc": "Системный промпт для ChatGPT/Codex.",
        "cfg_max_history_length_doc": "Макс. кол-во пар 'вопрос-ответ' в памяти (0 - без лимита).",
        "cfg_timezone_doc": "Ваш часовой пояс. Список: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
        "cfg_proxy_doc": "Прокси для API/CLI. Формат: http://user:pass@host:port",
        "cfg_auto_reply_chats_doc": "Чаты для авто-ответа. IDs или @username через запятую/новую строку. Это заменяет .cgauto для постоянной настройки.",
        "cfg_memory_disabled_chats_doc": "Чаты, где память отключена. IDs или @username через запятую/новую строку.",
        "cfg_impersonation_prompt_doc": "Промпт для режима авто-ответа. {my_name} и {chat_history} будут заменены.",
        "cfg_impersonation_history_limit_doc": "Сколько последних сообщений из чата отправлять в качестве контекста для авто-ответа.",
        "cfg_impersonation_reply_chance_doc": "Вероятность ответа в режиме cgauto (от 0.0 до 1.0). 0.2 = 20% шанс.",
        "cfg_temperature_doc": "Температура генерации ChatGPT API. От 0.0 до 2.0.",
        "cfg_autoretry_doc": "Сколько раз автоматически повторять текстовый запрос, если backend не вернул ответ или упал. 0 = выключено.",
        "cfg_audio_transcribe_model_doc": "Модель OpenAI для транскрибации аудио/голосовых/музыки при анализе медиа.",
        "cfg_media_frame_count_doc": "Сколько кадров извлекать из GIF/видео/анимированных стикеров для анализа.",
        "cfg_inline_pagination_doc": "Использовать инлайн-кнопки для длинных ответов.",
        "cfg_cgimg_history_limit_doc": "Сколько последних prompt-ов для cgimg хранить на чат.",
        "cfg_cgimg_upload_service_doc": "Сервис загрузки для кнопки cgimg upload: catbox, envs, kappa, oxo, x0, tmpfiles, pomf, bashupload.",
        "no_api_key": (
            '❗️ <b>OpenAI API key не настроен.</b>\n'
            'Получить ключ можно <a href="https://platform.openai.com/settings/organization/api-keys">здесь</a>.\n'
            '<b>Укажите его в cfg:</b> <code>api_key</code>'
        ),
        "invalid_api_key": '❗️ <b>OpenAI API key недействителен.</b>\nПроверьте ключ и права проекта в <a href="https://platform.openai.com/settings/organization/api-keys">OpenAI API keys</a>.',
        "no_codex_login": "❗️ <b>Codex CLI не авторизован.</b>\nВойдите в shell через <code>codex login</code> или выполните <code>.cgauth codex</code>.",
        "codex_not_found": "❗️ <b>Команда <code>codex</code> не найдена в системе.</b>\nПроверьте PATH или заполните <code>codex_path</code> в cfg.",
        "codex_prepare": "⌛️ <b>Проверяю Codex CLI...</b>",
        "codex_installing": "⬇️ <b>Codex CLI не найден. Ставлю автоматически...</b>",
        "codex_install_done": "✅ <b>Codex CLI установлен автоматически.</b>\n<code>{}</code>",
        "codex_install_failed": "❗️ <b>Не удалось автоматически установить Codex CLI.</b>\n<code>{}</code>",
        "codex_npm_missing": "❗️ <b>Команда <code>npm</code> не найдена, автоматическая установка Codex CLI невозможна.</b>",
        "processing": "<emoji document_id=5386367538735104399>⌛️</emoji> <b>Обработка...</b>",
        "image_processing": "<emoji document_id=5325547803936572038>✨</emoji> <b>Генерирую изображение...</b>",
        "text_regenerating": "<emoji document_id=5386367538735104399>⌛️</emoji> <b>Генерирую другой ответ{}</b>",
        "api_timeout": f"❗️ <b>Таймаут ответа от backend ({REQUEST_TIMEOUT} сек).</b>",
        "empty_backend_response": "Backend не вернул финальный ответ.",
        "generic_error": "❗️ <b>Ошибка:</b>\n<code>{}</code>",
        "question_prefix": "💬 <b>Запрос:</b>",
        "response_prefix": "<emoji document_id=5325547803936572038>✨</emoji> <b>{}:</b>",
        "memory_status": "🧠 [{}/{}]",
        "memory_status_unlimited": "🧠 [{}/∞]",
        "memory_cleared": "🧹 <b>Память диалога очищена.</b>",
        "memory_cleared_gauto": "🧹 <b>Память cgauto в этом чате очищена.</b>",
        "no_memory_to_clear": "ℹ️ <b>В этом чате нет истории.</b>",
        "no_gauto_memory_to_clear": "ℹ️ <b>В этом чате нет истории cgauto.</b>",
        "memory_chats_title": "🧠 <b>Чаты с историей ({}):</b>",
        "memory_chat_line": "  • {} (<code>{}</code>)",
        "no_memory_found": "ℹ️ Память пуста.",
        "media_reply_placeholder": "[запрос по медиа]",
        "btn_clear": "🧹 Очистить",
        "btn_regenerate": "🔄 Другой ответ",
        "btn_retry_request": "🔄 Повторить запрос",
        "btn_cancel_request": "❌ Отменить запрос",
        "request_cancelling": "⏳ Отменяю запрос...",
        "btn_cgimg_retry": "🔄 Повтор",
        "btn_cgimg_edit": "✏️ Изм. промпт",
        "btn_cgimg_history": "🕘 История",
        "btn_cgimg_back": "◀️ Назад",
        "btn_cgimg_upload": "☁️ Загрузить",
        "btn_cgimg_close": "❌ Закрыть",
        "no_last_request": "Последний запрос не найден для повторной генерации.",
        "request_cancelled": "⛔️ <b>Запрос отменен.</b>",
        "cgimg_no_last_request": "ℹ️ <b>Для cgimg пока нет сохраненного запроса в этом чате.</b>",
        "cgimg_history_empty": "ℹ️ <b>История prompt-ов cgimg пуста.</b>",
        "cgimg_history_title": "🕘 <b>История prompt-ов cgimg</b>",
        "cgimg_edit_input_prompt": "✏️ Введите новый prompt для cgimg",
        "cgimg_panel_hint": "💡 Reply на сгенерированную картинку с <code>.cgimg новый prompt</code> изменит её.",
        "cgimg_regenerating": "<emoji document_id=5325547803936572038>✨</emoji> <b>Генерирую изображение{}</b>",
        "cgimg_uploading": "☁️ <b>Загружаю изображение на {}</b>",
        "cgimg_uploaded": "✅ <b>Изображение загружено на {}</b>",
        "cgimg_request_expired": "⚠️ <b>Сохраненный cgimg-запрос уже недоступен.</b>",
        "cgimg_empty_prompt": "⚠️ <b>Prompt не должен быть пустым.</b>",
        "memory_fully_cleared": "🧹 <b>Вся память полностью очищена (затронуто {} чатов).</b>",
        "gauto_memory_fully_cleared": "🧹 <b>Вся память cgauto полностью очищена (затронуто {} чатов).</b>",
        "no_memory_to_fully_clear": "ℹ️ <b>Память и так пуста.</b>",
        "no_gauto_memory_to_fully_clear": "ℹ️ <b>Память cgauto и так пуста.</b>",
        "response_too_long": "Ответ был слишком длинным и отправлен файлом.",
        "cgclear_usage": "ℹ️ <b>Использование:</b> <code>.cgclear [auto]</code>",
        "auto_mode_on": "🎭 <b>Режим авто-ответа включен в этом чате.</b>\nЯ буду отвечать на сообщения с вероятностью {}%.",
        "auto_mode_off": "🎭 <b>Режим авто-ответа выключен в этом чате.</b>",
        "auto_mode_chats_title": "🎭 <b>Чаты с активным авто-ответом ({}):</b>",
        "no_auto_mode_chats": "ℹ️ Нет чатов с включенным режимом авто-ответа.",
        "auto_mode_usage": "ℹ️ <b>Использование:</b> <code>.cgauto on/off</code> или <code>.cgauto [id/username] on/off</code>",
        "cgauto_chat_not_found": "🚫 <b>Не удалось найти чат:</b> <code>{}</code>",
        "cgauto_state_updated": "🎭 <b>Режим авто-ответа для чата {} {}</b>",
        "cgauto_enabled": "включен",
        "cgauto_disabled": "выключен",
        "cgch_usage": "ℹ️ <b>Использование:</b>\n<code>.cgch &lt;кол-во&gt; &lt;вопрос&gt;</code>\n<code>.cgch &lt;id чата&gt; &lt;кол-во&gt; &lt;вопрос&gt;</code>",
        "cgch_processing": "<emoji document_id=5386367538735104399>⌛️</emoji> <b>Анализирую {} сообщений...</b>",
        "cgch_result_caption_from_chat": "Анализ последних {} сообщений из чата <b>{}</b>",
        "cgch_chat_error": "❗️ <b>Ошибка доступа к чату</b> <code>{}</code>: <i>{}</i>",
        "cgprompt_usage": "ℹ️ <b>Использование:</b>\n<code>.cgprompt &lt;текст/пресет&gt;</code> — установить.\n<code>.cgprompt -c</code> — очистить.\n<code>.cgpresets</code> — база пресетов.",
        "cgprompt_updated": "✅ <b>Системный промпт обновлен.</b>\nДлина: {} символов.",
        "cgprompt_cleared": "🗑 <b>Системный промпт очищен.</b>",
        "cgprompt_current": "📝 <b>Текущий системный промпт:</b>",
        "cgprompt_file_error": "❗️ <b>Ошибка чтения файла:</b> {}",
        "cgprompt_file_too_big": "❗️ <b>Файл слишком большой</b> (лимит 1 МБ).",
        "cgprompt_not_text": "❗️ Это не похоже на текстовый файл.",
        "cgmodel_usage": "ℹ️ <b>Использование:</b> <code>.cgmodel [модель]</code>, <code>.cgmodel -s</code>, <code>.cgmodel [chatgpt/codex] [модель]</code>",
        "cgmodel_list_error": "❗️ Ошибка получения списка моделей: {}",
        "cgmodel_reasoning_note": "ℹ️ <i>Reasoning effort применяется только на поддерживаемых reasoning-моделях.</i>",
        "cgmodel_reasoning_updated": "✅ Reasoning effort: {}",
        "cgmodel_reasoning_already": "Уже выбрано: {}",
        "cgauth_usage": (
            "ℹ️ <b>Авторизация:</b>\n"
            "• <code>.cgauth status</code> — показать статус\n"
            "• <code>.cgauth codex</code> — автоустановка Codex CLI + device auth\n"
            "• <code>.cgauth apikey sk-...</code> — сохранить OpenAI API key\n"
            "• <code>.cgauth clear</code> — удалить сохраненный API key"
        ),
        "cgpresets_usage": (
            "ℹ️ <b>Управление пресетами:</b>\n"
            "• <code>.cgpresets save [Имя] текст</code> — сохранить.\n"
            "• <code>.cgpresets load 1</code> или <code>имя</code> — загрузить.\n"
            "• <code>.cgpresets del 1</code> или <code>имя</code> — удалить.\n"
            "• <code>.cgpresets list</code> — список."
        ),
        "cgpreset_loaded": "✅ <b>Установлен пресет:</b> [<code>{}</code>]\nДлина: {} симв.",
        "cgpreset_saved": "💾 <b>Пресет сохранен.</b>\n🏷 <b>Имя:</b> {}\n№ <b>Индекс:</b> {}",
        "cgpreset_deleted": "🗑 <b>Пресет удален:</b> {}",
        "cgpreset_not_found": "🚫 Пресет с таким именем или индексом не найден.",
        "cgpreset_list_head": "📋 <b>Ваши пресеты:</b>\n",
        "cgpreset_empty": "📂 Список пресетов пуст.",
        "unsupported_media": "⚠️ <b>Этот тип медиа пока не поддерживается для ChatGPT/Codex:</b> <code>{}</code>",
        "media_ffmpeg_missing": "⚠️ <b>ffmpeg/ffprobe не найдены.</b> GIF, видео и анимированные стикеры будут доступны только как метаданные без кадров.",
        "media_frame_extract_failed": "⚠️ <b>Не удалось извлечь кадры из медиа:</b> <code>{}</code>",
        "media_audio_transcribe_failed": "⚠️ <b>Не удалось расшифровать аудио:</b> <code>{}</code>",
        "media_sticker_download_failed": "⚠️ <b>Не удалось подготовить стикер для анализа:</b> <code>{}</code>",
        "media_sticker_preview_used": "[Для анализа использовано превью стикера]",
        "auth_saved": "✅ <b>OpenAI API key сохранен и проверен.</b>",
        "auth_cleared": "🗑 <b>OpenAI API key удален.</b>",
        "codex_auth_already": "✅ <b>Codex CLI уже авторизован.</b>\n<code>{}</code>",
        "codex_auth_running": "⌛️ <b>Запускаю device auth для Codex CLI...</b>",
        "codex_auth_done": "✅ <b>Codex CLI успешно авторизован.</b>\n<code>{}</code>",
        "codex_auth_failed": "❗️ <b>Device auth Codex CLI не завершился успешно.</b>\n<code>{}</code>",
        "status_title": "🔐 <b>Статус авторизации:</b>",
        "status_backend": "• Backend: <code>{}</code>",
        "status_chatgpt": "• ChatGPT API key: {}",
        "status_codex": "• Codex CLI: {}",
        "status_reasoning": "• Reasoning effort: <code>{}</code>",
        "status_codex_yolo": "• Codex YOLO: <code>{}</code>",
        "status_set": "настроен",
        "status_missing": "не настроен",
        "status_logged_in": "авторизован",
        "status_not_logged": "не авторизован",
        "codex_models_note": (
            "📋 <b>Codex CLI не отдает live-список моделей через команду.</b>\n"
            "Текущее сохраненное значение: <code>{}</code>\n"
            "Можно указать любой валидный model id для вашего Codex CLI."
        ),
        "cgimg_usage": (
            "🎨 <b>Использование:</b>\n"
            "<code>.cgimg prompt</code> — генерация\n"
            "<code>.cgimg prompt</code> reply на фото — редактирование\n"
            "<code>.cgimg -r</code> — повторить последний запрос\n"
            "<code>.cgimg -e новый prompt</code> — изменить prompt последнего запроса\n"
            "<code>.cgimg -h</code> — история prompt-ов"
        ),
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "backend",
                "chatgpt",
                self.strings["cfg_backend_doc"],
                validator=loader.validators.Choice(["chatgpt", "codex"]),
            ),
            loader.ConfigValue(
                "api_key",
                "",
                self.strings["cfg_api_key_doc"],
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "chatgpt_model",
                "gpt-4.1-mini",
                self.strings["cfg_chatgpt_model_doc"],
            ),
            loader.ConfigValue(
                "codex_path",
                "",
                self.strings["cfg_codex_path_doc"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "codex_model",
                "",
                self.strings["cfg_codex_model_doc"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "reasoning_effort",
                "medium",
                self.strings["cfg_reasoning_effort_doc"],
                validator=loader.validators.Choice(list(REASONING_EFFORT_VALUES)),
            ),
            loader.ConfigValue(
                "codex_yolo_mode",
                False,
                self.strings["cfg_codex_yolo_mode_doc"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "codex_auto_install",
                True,
                self.strings["cfg_codex_auto_install_doc"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "codex_install_dir",
                "",
                self.strings["cfg_codex_install_dir_doc"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "image_model_name",
                "gpt-image-1.5",
                self.strings["cfg_image_model_doc"],
            ),
            loader.ConfigValue(
                "interactive_buttons",
                True,
                self.strings["cfg_buttons_doc"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "system_instruction",
                "",
                self.strings["cfg_system_instruction_doc"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "max_history_length",
                100,
                self.strings["cfg_max_history_length_doc"],
                validator=loader.validators.Integer(minimum=0),
            ),
            loader.ConfigValue(
                "timezone",
                "Europe/Moscow",
                self.strings["cfg_timezone_doc"],
            ),
            loader.ConfigValue(
                "proxy",
                "",
                self.strings["cfg_proxy_doc"],
            ),
            loader.ConfigValue(
                "auto_reply_chats",
                "",
                self.strings["cfg_auto_reply_chats_doc"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "memory_disabled_chats",
                "",
                self.strings["cfg_memory_disabled_chats_doc"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "impersonation_prompt",
                (
                    "Ты — это я, пользователь Telegram по имени {my_name}. Твоя задача — отвечать в чате от моего имени, "
                    "основываясь на последних сообщениях. Веди себя естественно, как обычный человек, а не как ассистент. "
                    "Не признавайся, что ты — ИИ.\n"
                    "Правила:\n"
                    "- Отвечай кратко и по делу.\n"
                    "- Используй естественный живой язык.\n"
                    "- Не отвечай на каждое сообщение.\n"
                    "- Не используй префиксы и кавычки.\n\n"
                    "ИСТОРИЯ ЧАТА:\n{chat_history}\n\n{my_name}:"
                ),
                self.strings["cfg_impersonation_prompt_doc"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "impersonation_history_limit",
                20,
                self.strings["cfg_impersonation_history_limit_doc"],
                validator=loader.validators.Integer(minimum=5, maximum=100),
            ),
            loader.ConfigValue(
                "impersonation_reply_chance",
                0.25,
                self.strings["cfg_impersonation_reply_chance_doc"],
                validator=loader.validators.Float(minimum=0.0, maximum=1.0),
            ),
            loader.ConfigValue(
                "gauto_in_pm",
                False,
                "Разрешить авто-ответы в личных сообщениях (ЛС).",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "temperature",
                1.0,
                self.strings["cfg_temperature_doc"],
                validator=loader.validators.Float(minimum=0.0, maximum=2.0),
            ),
            loader.ConfigValue(
                "autoretry",
                0,
                self.strings["cfg_autoretry_doc"],
                validator=loader.validators.Integer(minimum=0, maximum=10),
            ),
            loader.ConfigValue(
                "audio_transcribe_model",
                "gpt-4o-mini-transcribe",
                self.strings["cfg_audio_transcribe_model_doc"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "media_frame_count",
                4,
                self.strings["cfg_media_frame_count_doc"],
                validator=loader.validators.Integer(minimum=1, maximum=8),
            ),
            loader.ConfigValue(
                "inline_pagination",
                False,
                self.strings["cfg_inline_pagination_doc"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "cgimg_prompt_history_limit",
                15,
                self.strings["cfg_cgimg_history_limit_doc"],
                validator=loader.validators.Integer(minimum=1, maximum=100),
            ),
            loader.ConfigValue(
                "cgimg_upload_service",
                "x0",
                self.strings["cfg_cgimg_upload_service_doc"],
                validator=loader.validators.Choice(["catbox", "envs", "kappa", "oxo", "x0", "tmpfiles", "pomf", "bashupload"]),
            ),
        )
        self.prompt_presets = []
        self.conversations = {}
        self.gauto_conversations = {}
        self.last_requests = {}
        self.impersonation_chats = set()
        self.memory_disabled_chats = set()
        self.pager_cache = {}
        self._cfg_sync_cache = {}
        self.cgimg_prompt_history = {}
        self.cgimg_request_cache = {}
        self.cgimg_last_request_by_chat = {}
        self.cgimg_request_by_message = {}
        self.active_text_requests = {}
        self._codex_install_lock = asyncio.Lock()

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self.me = await client.get_me()
        self.conversations = self._load_history_from_db(DB_HISTORY_KEY)
        self.gauto_conversations = self._load_history_from_db(DB_GAUTO_HISTORY_KEY)
        self.prompt_presets = self.db.get(self.strings["name"], DB_PRESETS_KEY, [])
        if isinstance(self.prompt_presets, dict):
            self.prompt_presets = [{"name": k, "content": v} for k, v in self.prompt_presets.items()]
        self.impersonation_chats = set(self.db.get(self.strings["name"], DB_IMPERSONATION_KEY, []))
        self.memory_disabled_chats = set(self.db.get(self.strings["name"], DB_MEMORY_DISABLED_KEY, []))
        self.cgimg_prompt_history = self._load_history_from_db(DB_CGIMG_PROMPT_HISTORY_KEY)
        self._migrate_runtime_lists_to_config()
        await self._sync_runtime_config(force=True)

    @loader.command()
    async def cg(self, message: Message):
        """[текст или reply] — спросить у ChatGPT/Codex."""
        await self._sync_runtime_config()
        status_msg = await utils.answer(message, self.strings["processing"])
        status_msg = await self.client.get_messages(status_msg.chat_id, ids=status_msg.id)
        payload, warnings = await self._prepare_request_payload(message)
        if warnings and status_msg:
            try:
                await status_msg.edit(f"{status_msg.text}\n\n" + "\n".join(warnings))
            except Exception:
                pass
        if not payload:
            return await utils.answer(status_msg, "⚠️ <i>Нужен текст, reply или поддерживаемое медиа.</i>")
        await self._send_request(message=message, payload=payload, status_msg=status_msg)

    @loader.command()
    async def cgimg(self, message: Message):
        """<промпт> [reply на фото] — генерация/редактирование изображения через OpenAI Image API."""
        await self._sync_runtime_config()
        if not aiohttp:
            return await utils.answer(message, self._handle_error(RuntimeError("Библиотека aiohttp не установлена.")))
        api_key = self.config["api_key"].strip()
        if not api_key:
            return await utils.answer(message, self.strings["no_api_key"])
        args = utils.get_args_raw(message).strip()
        args_lower = args.lower()
        chat_id = utils.get_chat_id(message)
        reply = await message.get_reply_message()
        if args_lower in {"-h", "--history", "history"}:
            return await self._show_cgimg_history(message, chat_id)

        request_context = self._resolve_cgimg_request(chat_id, reply)
        if args_lower in {"-r", "--retry", "retry"}:
            if not request_context:
                return await utils.answer(message, self.strings["cgimg_no_last_request"])
            status_msg = await utils.answer(message, self.strings["image_processing"])
            request_data = self._clone_cgimg_request(request_context)
            request_data["reply_target"] = self._get_reply_target_id(message, fallback=request_context.get("reply_target"))
            return await self._execute_cgimg_request(status_msg, request_data)

        edit_mode = False
        prompt = args
        if args_lower.startswith("-e "):
            prompt = args[3:].strip()
            edit_mode = True
        elif args_lower.startswith("--edit "):
            prompt = args[7:].strip()
            edit_mode = True
        elif args_lower.startswith("edit "):
            prompt = args[5:].strip()
            edit_mode = True

        input_image = None
        input_mime = "image/png"
        if reply and self._message_contains_image(reply):
            input_image, input_mime = await self._download_image_from_message(reply)
        elif edit_mode and request_context and request_context.get("input_image"):
            input_image = request_context.get("input_image")
            input_mime = request_context.get("input_mime") or input_mime

        if not prompt:
            return await utils.answer(message, self.strings["cgimg_usage"])

        status_msg = await utils.answer(message, self.strings["image_processing"])
        request_data = {
            "chat_id": chat_id,
            "prompt": prompt,
            "model": self.config["image_model_name"].strip(),
            "input_image": input_image,
            "input_mime": input_mime,
            "reply_target": self._get_reply_target_id(message),
            "source_message_id": message.id,
            "source_reply_id": getattr(reply, "id", None),
            "mode": "edit" if input_image else "generate",
            "uploads": {},
        }
        self._remember_cgimg_prompt(chat_id, prompt, request_data["mode"], request_data["model"])
        await self._execute_cgimg_request(status_msg, request_data)

    def _message_contains_image(self, message: Message) -> bool:
        if not message:
            return False
        if getattr(message, "photo", None):
            return True
        document = getattr(message, "document", None)
        return bool(document and getattr(document, "mime_type", "").startswith("image/"))

    async def _download_image_from_message(self, message: Message):
        input_mime = "image/png"
        if message.photo:
            return await self.client.download_media(message, bytes), "image/jpeg"
        if message.document and getattr(message.document, "mime_type", "").startswith("image/"):
            input_mime = message.document.mime_type or input_mime
            return await self.client.download_media(message, bytes), input_mime
        return None, input_mime

    def _clone_cgimg_request(self, request: dict) -> dict:
        return {
            "request_id": request.get("request_id"),
            "chat_id": request.get("chat_id"),
            "prompt": request.get("prompt", ""),
            "model": request.get("model") or self.config["image_model_name"].strip(),
            "input_image": request.get("input_image"),
            "input_mime": request.get("input_mime") or "image/png",
            "reply_target": request.get("reply_target"),
            "source_message_id": request.get("source_message_id"),
            "source_reply_id": request.get("source_reply_id"),
            "mode": "edit" if request.get("input_image") else "generate",
            "uploads": {},
        }

    def _extract_message_id(self, obj):
        if obj is None:
            return None
        if getattr(obj, "message_id", None):
            return obj.message_id
        if getattr(obj, "id", None):
            return obj.id
        message = getattr(obj, "message", None)
        if message is not None:
            if getattr(message, "message_id", None):
                return message.message_id
            if getattr(message, "id", None):
                return message.id
        return None

    def _save_cgimg_prompt_history_sync(self):
        self.db.set(self.strings["name"], DB_CGIMG_PROMPT_HISTORY_KEY, self.cgimg_prompt_history)

    def _remember_cgimg_prompt(self, chat_id: int, prompt: str, mode: str, model: str):
        hist = self.cgimg_prompt_history.setdefault(str(chat_id), [])
        hist.append({
            "prompt": prompt,
            "mode": mode,
            "model": model,
            "date": int(datetime.utcnow().timestamp()),
        })
        limit = int(self.config["cgimg_prompt_history_limit"])
        if limit > 0 and len(hist) > limit:
            hist = hist[-limit:]
        self.cgimg_prompt_history[str(chat_id)] = hist
        self._save_cgimg_prompt_history_sync()

    def _resolve_cgimg_request(self, chat_id: int, reply: Message = None):
        if reply:
            req_id = self.cgimg_request_by_message.get(f"{chat_id}:{reply.id}")
            if req_id:
                request = self.cgimg_request_cache.get(req_id)
                if request:
                    return request
        req_id = self.cgimg_last_request_by_chat.get(str(chat_id))
        if req_id:
            return self.cgimg_request_cache.get(req_id)
        return None

    def _remember_cgimg_runtime_request(self, request_data: dict):
        req_id = request_data.get("request_id") or uuid.uuid4().hex[:10]
        request_data["request_id"] = req_id
        self.cgimg_request_cache[req_id] = request_data
        self.cgimg_last_request_by_chat[str(request_data["chat_id"])] = req_id
        for msg_id in (request_data.get("source_message_id"), request_data.get("result_message_id"), request_data.get("panel_message_id")):
            if msg_id:
                self.cgimg_request_by_message[f"{request_data['chat_id']}:{msg_id}"] = req_id
        while len(self.cgimg_request_cache) > 12:
            old_req_id = next(iter(self.cgimg_request_cache))
            old_data = self.cgimg_request_cache.pop(old_req_id, {})
            old_chat_key = str(old_data.get("chat_id"))
            if self.cgimg_last_request_by_chat.get(old_chat_key) == old_req_id:
                self.cgimg_last_request_by_chat.pop(old_chat_key, None)
            for msg_id in (old_data.get("source_message_id"), old_data.get("result_message_id"), old_data.get("panel_message_id")):
                if msg_id:
                    self.cgimg_request_by_message.pop(f"{old_data.get('chat_id')}:{msg_id}", None)
        return req_id

    async def _cgimg_update_ui(self, entity, text: str, reply_markup=None, photo: str = None):
        if isinstance(entity, InlineCall):
            kwargs = {"text": text, "reply_markup": reply_markup}
            if photo:
                kwargs["photo"] = photo
            await entity.edit(**kwargs)
            return self._extract_message_id(entity)
        if photo:
            form = await self.inline.form(
                text=text,
                message=entity,
                reply_markup=reply_markup,
                photo=photo,
                silent=True,
            )
            if form:
                with contextlib.suppress(Exception):
                    await entity.delete()
                return self._extract_message_id(form)
        updated = await utils.answer(entity, text, reply_markup=reply_markup)
        return self._extract_message_id(updated) or self._extract_message_id(entity)

    def _build_cgimg_loading_text(self, request_data: dict, suffix: str = "") -> str:
        prompt = utils.escape_html((request_data.get("prompt") or "")[:800])
        return "\n".join([
            self.strings["cgimg_regenerating"].format(suffix),
            f"📜 <code>{prompt}</code>",
        ])

    async def _cgimg_update_loading_text(self, entity, text: str):
        if isinstance(entity, InlineCall):
            await entity.edit(text=text, reply_markup=None)
            return self._extract_message_id(entity)
        if hasattr(entity, "edit"):
            with contextlib.suppress(Exception):
                updated = await entity.edit(text, parse_mode="html")
                return self._extract_message_id(updated) or self._extract_message_id(entity)
        updated = await utils.answer(entity, text)
        return self._extract_message_id(updated) or self._extract_message_id(entity)

    async def _animate_cgimg_loading(self, entity, request_data: dict):
        suffixes = ["", ".", "..", "..."]
        index = 0
        while True:
            try:
                await self._cgimg_update_loading_text(
                    entity,
                    self._build_cgimg_loading_text(request_data, suffix=suffixes[index % len(suffixes)]),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                return
            index += 1
            await asyncio.sleep(0.9)

    async def _cancel_cgimg_loading(self, task):
        await self._cancel_loading_task(task)

    def _build_text_regeneration_loading_text(self, display_prompt: str, suffix: str = "") -> str:
        prompt = utils.escape_html((display_prompt or self.strings["media_reply_placeholder"])[:800])
        return "\n".join([
            self.strings["text_regenerating"].format(suffix),
            self.strings["question_prefix"],
            f"<blockquote>{prompt}</blockquote>",
        ])

    async def _animate_text_regeneration(self, call: InlineCall, display_prompt: str, chat_id: int, base_message_id: int):
        suffixes = ["", ".", "..", "..."]
        index = 0
        while True:
            try:
                await call.edit(
                    self._build_text_regeneration_loading_text(display_prompt, suffix=suffixes[index % len(suffixes)]),
                    reply_markup=self._get_loading_buttons(chat_id, base_message_id),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                return
            index += 1
            await asyncio.sleep(0.9)

    async def _cancel_loading_task(self, task):
        if not task:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def _delete_message_entity(self, entity):
        if not entity:
            return
        with contextlib.suppress(Exception):
            if hasattr(entity, "delete"):
                await entity.delete()
                return
        chat_id = getattr(entity, "chat_id", None)
        if chat_id is None:
            chat_id = getattr(getattr(entity, "message", None), "chat_id", None)
        message_id = self._extract_message_id(entity)
        if chat_id and message_id:
            with contextlib.suppress(Exception):
                await self.client.delete_messages(chat_id, message_id)

    async def _update_text_request_ui(self, entity, text: str, reply_markup=None):
        if isinstance(entity, InlineCall):
            await entity.edit(text, reply_markup=reply_markup)
            return entity
        if hasattr(entity, "edit"):
            with contextlib.suppress(Exception):
                await entity.edit(text, reply_markup=reply_markup)
                return entity
        updated = await utils.answer(entity, text, reply_markup=reply_markup)
        if updated and self._extract_message_id(updated) != self._extract_message_id(entity):
            await self._delete_message_entity(entity)
        return updated or entity

    async def _set_text_request_loading_ui(self, entity, text: str, chat_id: int, base_message_id: int):
        return await self._update_text_request_ui(
            entity,
            text,
            reply_markup=self._get_loading_buttons(chat_id, base_message_id),
        )

    async def _restart_cgimg_as_loading_message(self, call: InlineCall, request_data: dict):
        old_message_id = self._extract_message_id(getattr(call, "message", None)) or self._extract_message_id(call)
        if old_message_id:
            self.cgimg_request_by_message.pop(f"{request_data['chat_id']}:{old_message_id}", None)
        with contextlib.suppress(Exception):
            await call.delete()
        if old_message_id:
            with contextlib.suppress(Exception):
                await self.client.delete_messages(call.chat_id, old_message_id)
        return await self.client.send_message(
            call.chat_id,
            self._build_cgimg_loading_text(request_data),
            reply_to=request_data.get("reply_target"),
            parse_mode="html",
            link_preview=False,
        )

    async def _ensure_cgimg_preview_url(self, request_data: dict) -> str:
        if request_data.get("preview_url"):
            return request_data["preview_url"]
        direct_services = ["x0", "oxo", "catbox", "envs", "pomf"]
        preferred = self.config["cgimg_upload_service"]
        if preferred in direct_services:
            direct_services = [preferred] + [service for service in direct_services if service != preferred]
        last_error = None
        for service in direct_services:
            try:
                url = await self._upload_cgimg_result(
                    request_data["result_image"],
                    request_data.get("result_filename") or "image.png",
                    service,
                )
                request_data["preview_url"] = url
                request_data["preview_service"] = service
                return url
            except Exception as e:
                last_error = e
        raise RuntimeError(last_error or "Не удалось получить preview URL.")

    async def _run_cgimg_api_request(self, request_data: dict):
        api_key = self.config["api_key"].strip()
        if not api_key:
            raise RuntimeError(self.strings["no_api_key"])
        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = self._get_proxy()
        model = request_data["model"]
        prompt = request_data["prompt"]
        input_image = request_data.get("input_image")
        input_mime = request_data.get("input_mime") or "image/png"

        async with aiohttp.ClientSession(headers=headers) as session:
            if input_image:
                form = aiohttp.FormData()
                form.add_field("model", model)
                form.add_field("prompt", prompt)
                form.add_field("image[]", input_image, filename="input.png", content_type=input_mime)
                async with session.post(
                    "https://api.openai.com/v1/images/edits",
                    data=form,
                    proxy=proxy,
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(self._parse_openai_error(resp.status, body))
            else:
                payload = {"model": model, "prompt": prompt}
                async with session.post(
                    "https://api.openai.com/v1/images/generations",
                    json=payload,
                    proxy=proxy,
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(self._parse_openai_error(resp.status, body))
            data = json.loads(body)

        image_b64 = None
        for item in data.get("data", []):
            if item.get("b64_json"):
                image_b64 = item["b64_json"]
                break
        if not image_b64:
            raise RuntimeError("API не вернул изображение.")
        return base64.b64decode(image_b64)

    def _build_cgimg_panel_text(self, request_data: dict, heading: str = None) -> str:
        prompt = utils.escape_html((request_data.get("prompt") or "")[:800])
        mode = "edit" if request_data.get("input_image") else "generate"
        lines = [
            heading or "🎨 <b>OpenAI Image</b>",
            f"🧠 <code>{utils.escape_html(request_data.get('model') or self.config['image_model_name'])}</code>",
            f"🖼 <b>Режим:</b> <code>{mode}</code>",
            f"📜 <code>{prompt}</code>",
        ]
        uploads = request_data.get("uploads") or {}
        if uploads:
            lines.append("")
            lines.append("🔗 <b>Upload links:</b>")
            for name, url in uploads.items():
                lines.append(f"• <a href=\"{utils.escape_html(url)}\">{utils.escape_html(name)}</a>")
        lines.append("")
        lines.append(self.strings["cgimg_panel_hint"])
        return "\n".join(lines)

    def _get_cgimg_upload_service_label(self, service: str = None) -> str:
        service = service or self.config["cgimg_upload_service"]
        return {
            "catbox": "catbox.moe",
            "envs": "envs.sh",
            "kappa": "kappa.lol",
            "oxo": "0x0.st",
            "x0": "x0.at",
            "tmpfiles": "tmpfiles",
            "pomf": "pomf.lain.la",
            "bashupload": "bashupload.com",
        }.get(service, service)

    def _get_cgimg_buttons(self, req_id: str):
        return [
            [
                {"text": self.strings["btn_cgimg_retry"], "callback": self._cgimg_retry_callback, "args": (req_id,)},
                {
                    "text": self.strings["btn_cgimg_edit"],
                    "input": self.strings["cgimg_edit_input_prompt"],
                    "handler": self._cgimg_edit_input_handler,
                    "kwargs": {"req_id": req_id},
                },
            ],
            [
                {"text": self.strings["btn_cgimg_history"], "callback": self._cgimg_history_callback, "args": (req_id,)},
                {"text": self.strings["btn_cgimg_upload"], "callback": self._cgimg_upload_callback, "args": (req_id,)},
            ],
            [
                {"text": self.strings["btn_cgimg_close"], "callback": self._cgimg_close_callback, "args": ()},
            ],
        ]

    def _get_cgimg_error_buttons(self, req_id: str):
        return [[
            {"text": self.strings["btn_cgimg_retry"], "callback": self._cgimg_retry_callback, "args": (req_id,)},
            {
                "text": self.strings["btn_cgimg_edit"],
                "input": self.strings["cgimg_edit_input_prompt"],
                "handler": self._cgimg_edit_input_handler,
                "kwargs": {"req_id": req_id},
            },
            {"text": self.strings["btn_cgimg_history"], "callback": self._cgimg_history_callback, "args": (req_id,)},
        ]]

    async def _execute_cgimg_request(self, entity, request_data: dict):
        request_data = self._clone_cgimg_request(request_data)
        loading_task = None
        try:
            await self._cgimg_update_loading_text(entity, self._build_cgimg_loading_text(request_data))
            loading_task = asyncio.create_task(self._animate_cgimg_loading(entity, request_data))
            image_bytes = await self._run_cgimg_api_request(request_data)
            request_data["result_image"] = image_bytes
            request_data["result_filename"] = f"chatgpt_{uuid.uuid4().hex[:6]}.png"
            preview_url = await self._ensure_cgimg_preview_url(request_data)
            await self._cancel_cgimg_loading(loading_task)
            loading_task = None
            req_id = self._remember_cgimg_runtime_request(request_data)
            buttons = self._get_cgimg_buttons(req_id) if self.config["interactive_buttons"] else None
            result_message_id = await self._cgimg_update_ui(
                entity,
                self._build_cgimg_panel_text(request_data),
                reply_markup=buttons,
                photo=preview_url,
            )
            request_data["result_message_id"] = result_message_id
            request_data["panel_message_id"] = result_message_id
            self._remember_cgimg_runtime_request(request_data)
        except Exception as e:
            await self._cancel_cgimg_loading(loading_task)
            req_id = self._remember_cgimg_runtime_request(request_data)
            buttons = self._get_cgimg_error_buttons(req_id) if self.config["interactive_buttons"] else None
            await self._cgimg_update_ui(entity, self._handle_error(e), reply_markup=buttons)

    async def _show_cgimg_history(self, entity, chat_id: int, req_id: str = None):
        history = self.cgimg_prompt_history.get(str(chat_id), [])
        if not history:
            text = self.strings["cgimg_history_empty"]
        else:
            lines = [self.strings["cgimg_history_title"], ""]
            for index, entry in enumerate(reversed(history[-15:]), 1):
                dt = datetime.fromtimestamp(entry.get("date", 0)).strftime("%d.%m %H:%M")
                mode = entry.get("mode", "generate")
                model = utils.escape_html(entry.get("model", ""))
                prompt = utils.escape_html(str(entry.get("prompt", ""))[:250])
                lines.append(f"{index}. <b>{dt}</b> • <code>{mode}</code> • <code>{model}</code>")
                lines.append(f"<code>{prompt}</code>")
                lines.append("")
            text = "\n".join(lines).strip()
        buttons = None
        if req_id:
            buttons = [[{"text": self.strings["btn_cgimg_back"], "callback": self._cgimg_back_callback, "args": (req_id,)}]]
        await self._cgimg_update_ui(entity, text, reply_markup=buttons)

    async def _cgimg_retry_callback(self, call: InlineCall, req_id: str):
        request_data = self.cgimg_request_cache.get(req_id)
        if not request_data:
            return await call.answer(self.strings["cgimg_request_expired"], show_alert=True)
        retry_request = self._clone_cgimg_request(request_data)
        self._remember_cgimg_prompt(retry_request["chat_id"], retry_request["prompt"], retry_request["mode"], retry_request["model"])
        status_msg = await self._restart_cgimg_as_loading_message(call, retry_request)
        retry_request["source_message_id"] = self._extract_message_id(status_msg)
        retry_request["result_message_id"] = None
        retry_request["panel_message_id"] = None
        await self._execute_cgimg_request(status_msg, retry_request)

    async def _cgimg_edit_input_handler(self, call: InlineCall, *args, req_id: str = None, **kwargs):
        request_data = self.cgimg_request_cache.get(req_id)
        if not request_data:
            return await call.answer(self.strings["cgimg_request_expired"], show_alert=True)
        new_prompt = kwargs.get("query") or kwargs.get("text") or kwargs.get("value")
        if not isinstance(new_prompt, str):
            for arg in args:
                if isinstance(arg, str) and arg != req_id:
                    new_prompt = arg
                    break
        new_prompt = (new_prompt or "").strip()
        if not new_prompt:
            return await call.answer(re.sub(r"<.*?>", "", self.strings["cgimg_empty_prompt"]), show_alert=True)
        updated_request = self._clone_cgimg_request(request_data)
        updated_request["prompt"] = new_prompt
        self._remember_cgimg_prompt(updated_request["chat_id"], new_prompt, updated_request["mode"], updated_request["model"])
        status_msg = await self._restart_cgimg_as_loading_message(call, updated_request)
        updated_request["source_message_id"] = self._extract_message_id(status_msg)
        updated_request["result_message_id"] = None
        updated_request["panel_message_id"] = None
        await self._execute_cgimg_request(status_msg, updated_request)

    async def _cgimg_history_callback(self, call: InlineCall, req_id: str):
        request_data = self.cgimg_request_cache.get(req_id)
        if not request_data:
            return await call.answer(self.strings["cgimg_request_expired"], show_alert=True)
        await self._show_cgimg_history(call, request_data["chat_id"], req_id=req_id)

    async def _cgimg_back_callback(self, call: InlineCall, req_id: str):
        request_data = self.cgimg_request_cache.get(req_id)
        if not request_data:
            return await call.answer(self.strings["cgimg_request_expired"], show_alert=True)
        await self._cgimg_update_ui(
            call,
            self._build_cgimg_panel_text(request_data),
            reply_markup=self._get_cgimg_buttons(req_id),
            photo=request_data.get("preview_url"),
        )

    async def _cgimg_upload_callback(self, call: InlineCall, req_id: str):
        request_data = self.cgimg_request_cache.get(req_id)
        if not request_data:
            return await call.answer(self.strings["cgimg_request_expired"], show_alert=True)
        if not request_data.get("result_image"):
            return await call.answer("Нет сгенерированного изображения для загрузки.", show_alert=True)
        service = self.config["cgimg_upload_service"]
        service_name = self._get_cgimg_upload_service_label(service)
        if request_data.get("uploads", {}).get(service_name):
            await self._cgimg_update_ui(
                call,
                self._build_cgimg_panel_text(request_data),
                reply_markup=self._get_cgimg_buttons(req_id),
                photo=request_data.get("preview_url"),
            )
            return await call.answer(self.strings["cgimg_uploaded"].format(service_name), show_alert=False)
        try:
            await call.answer(self.strings["cgimg_uploading"].format(service_name), show_alert=False)
            if request_data.get("preview_service") == service and request_data.get("preview_url"):
                url = request_data["preview_url"]
            else:
                url = await self._upload_cgimg_result(request_data["result_image"], request_data.get("result_filename") or "image.png", service)
            request_data.setdefault("uploads", {})[service_name] = url
            self._remember_cgimg_runtime_request(request_data)
            await self._cgimg_update_ui(
                call,
                self._build_cgimg_panel_text(request_data),
                reply_markup=self._get_cgimg_buttons(req_id),
                photo=request_data.get("preview_url"),
            )
        except Exception as e:
            await call.answer(f"Ошибка загрузки на {service_name}: {str(e)[:180]}", show_alert=True)

    async def _cgimg_close_callback(self, call: InlineCall):
        req_id = None
        with contextlib.suppress(Exception):
            message = getattr(call, "message", None)
            if message is not None:
                req_id = self.cgimg_request_by_message.get(f"{call.chat_id}:{self._extract_message_id(message)}")
        if req_id:
            request_data = self.cgimg_request_cache.pop(req_id, None) or {}
            if self.cgimg_last_request_by_chat.get(str(request_data.get("chat_id"))) == req_id:
                self.cgimg_last_request_by_chat.pop(str(request_data.get("chat_id")), None)
            for msg_id in (request_data.get("source_message_id"), request_data.get("result_message_id"), request_data.get("panel_message_id")):
                if msg_id:
                    self.cgimg_request_by_message.pop(f"{request_data.get('chat_id')}:{msg_id}", None)
        with contextlib.suppress(Exception):
            await call.delete()
            return
        msg_id = self._extract_message_id(call)
        if msg_id:
            with contextlib.suppress(Exception):
                await self.client.delete_messages(call.chat_id, msg_id)

    async def _upload_cgimg_result(self, image_bytes: bytes, filename: str, service: str) -> str:
        if not aiohttp:
            raise RuntimeError("Библиотека aiohttp не установлена.")
        proxy = self._get_proxy()
        headers = {"User-Agent": "ChatGPTCodex/7.1 (Heroku cgimg uploader)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            if service == "catbox":
                form = aiohttp.FormData()
                form.add_field("fileToUpload", image_bytes, filename=filename, content_type="image/png")
                form.add_field("reqtype", "fileupload")
                async with session.post("https://catbox.moe/user/api.php", data=form, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
                    body = (await resp.text()).strip()
                    if resp.status != 200:
                        raise RuntimeError(body or f"HTTP {resp.status}")
                if not body.startswith("http"):
                    raise RuntimeError("catbox.moe не вернул ссылку.")
                return body

            if service == "envs":
                form = aiohttp.FormData()
                form.add_field("file", image_bytes, filename=filename, content_type="image/png")
                async with session.post("https://envs.sh", data=form, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
                    body = (await resp.text()).strip()
                    if resp.status != 200:
                        raise RuntimeError(body or f"HTTP {resp.status}")
                if not body.startswith("http"):
                    raise RuntimeError("envs.sh не вернул ссылку.")
                return body

            if service == "kappa":
                form = aiohttp.FormData()
                form.add_field("file", image_bytes, filename=filename, content_type="image/png")
                async with session.post("https://kappa.lol/api/upload", data=form, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(body.strip() or f"HTTP {resp.status}")
                data = json.loads(body)
                image_id = data.get("id")
                if not image_id:
                    raise RuntimeError("kappa.lol не вернул id файла.")
                return f"https://kappa.lol/{image_id}"

            if service == "oxo":
                form = aiohttp.FormData()
                form.add_field("file", image_bytes, filename=filename, content_type="image/png")
                form.add_field("secret", "true")
                async with session.post("https://0x0.st", data=form, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
                    body = (await resp.text()).strip()
                    if resp.status != 200:
                        raise RuntimeError(body or f"HTTP {resp.status}")
                if not body.startswith("http"):
                    raise RuntimeError("0x0.st не вернул ссылку.")
                return body

            if service == "x0":
                form = aiohttp.FormData()
                form.add_field("file", image_bytes, filename=filename, content_type="image/png")
                async with session.post("https://x0.at/", data=form, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
                    body = (await resp.text()).strip()
                    if resp.status != 200:
                        raise RuntimeError(body or f"HTTP {resp.status}")
                if not body.startswith("http"):
                    raise RuntimeError("x0.at не вернул ссылку.")
                return body

            if service == "tmpfiles":
                form = aiohttp.FormData()
                form.add_field("file", image_bytes, filename=filename, content_type="image/png")
                async with session.post("https://tmpfiles.org/api/v1/upload", data=form, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
                    body = (await resp.text()).strip()
                    if resp.status != 200:
                        raise RuntimeError(body or f"HTTP {resp.status}")
                data = json.loads(body)
                url = data.get("data", {}).get("url") or data.get("url")
                if not url:
                    raise RuntimeError("tmpfiles не вернул URL.")
                return url

            if service == "pomf":
                form = aiohttp.FormData()
                form.add_field("files[]", image_bytes, filename=filename, content_type="image/png")
                async with session.post("https://pomf.lain.la/upload.php", data=form, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(body.strip() or f"HTTP {resp.status}")
                data = json.loads(body)
                files = data.get("files") or []
                if not files or not files[0].get("url"):
                    raise RuntimeError("pomf.lain.la не вернул URL.")
                return files[0]["url"]

            if service == "bashupload":
                async with session.put("https://bashupload.com", data=image_bytes, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(body.strip() or f"HTTP {resp.status}")
                urls = [line for line in body.splitlines() if "wget" in line]
                if not urls:
                    raise RuntimeError("bashupload.com не вернул URL.")
                return urls[0].split()[-1]

        raise RuntimeError(f"Неизвестный upload service: {service}")

    @loader.command()
    async def cgauth(self, message: Message):
        """status | codex | apikey <key> | clear — авторизация backend-ов."""
        args = utils.get_args_raw(message).strip()
        if not args or args == "status":
            return await utils.answer(message, await self._format_auth_status())

        parts = args.split(maxsplit=1)
        action = parts[0].lower()

        if action == "clear":
            self.config["api_key"] = ""
            return await utils.answer(message, self.strings["auth_cleared"])

        if action == "apikey":
            if len(parts) < 2:
                return await utils.answer(message, self.strings["cgauth_usage"])
            key = parts[1].strip()
            old_key = self.config["api_key"]
            self.config["api_key"] = key
            ok, info = await self._validate_chatgpt_api_key(key)
            if ok:
                return await utils.answer(message, self.strings["auth_saved"])
            self.config["api_key"] = old_key
            return await utils.answer(message, self._handle_error(RuntimeError(info)))

        if action == "codex":
            status_msg = await utils.answer(message, self.strings["codex_prepare"])
            try:
                await self._ensure_codex_available(status_msg=status_msg)
            except Exception as e:
                return await utils.answer(status_msg, self._handle_error(e))
            logged_in, status = await self._get_codex_status_for_runtime()
            if logged_in:
                return await utils.answer(status_msg, self.strings["codex_auth_already"].format(utils.escape_html(status)))
            await utils.answer(status_msg, self.strings["codex_auth_running"])
            ok, output = await self._run_codex_device_auth(status_msg=status_msg)
            key = "codex_auth_done" if ok else "codex_auth_failed"
            return await utils.answer(status_msg, self.strings[key].format(utils.escape_html(output)))

        await utils.answer(message, self.strings["cgauth_usage"])

    @loader.command()
    async def cgch(self, message: Message):
        """<[id чата]> <кол-во> <вопрос> — проанализировать историю чата."""
        await self._sync_runtime_config()
        args_str = utils.get_args_raw(message)
        if not args_str:
            return await utils.answer(message, self.strings["cgch_usage"])
        parts = args_str.split()
        target_chat_id = utils.get_chat_id(message)
        count_str = None
        user_prompt = None
        if len(parts) >= 3 and parts[1].isdigit():
            try:
                entity = await self.client.get_entity(int(parts[0]) if parts[0].lstrip("-").isdigit() else parts[0])
                target_chat_id = entity.id
                count_str = parts[1]
                user_prompt = " ".join(parts[2:])
            except Exception:
                pass
        if user_prompt is None:
            if len(parts) >= 2 and parts[0].isdigit():
                count_str = parts[0]
                user_prompt = " ".join(parts[1:])
            else:
                return await utils.answer(message, self.strings["cgch_usage"])
        try:
            count = int(count_str)
        except Exception:
            return await utils.answer(message, "❗️ Кол-во должно быть числом.")

        status_msg = await utils.answer(message, self.strings["cgch_processing"].format(count))
        try:
            entity = await self.client.get_entity(target_chat_id)
            chat_name = utils.escape_html(get_display_name(entity))
            chat_log = await self._get_recent_chat_text(target_chat_id, count=count, skip_last=False)
        except (ValueError, TypeError, ChatAdminRequiredError, UserNotParticipantError, ChannelPrivateError) as e:
            return await utils.answer(status_msg, self.strings["cgch_chat_error"].format(target_chat_id, e.__class__.__name__))
        except Exception as e:
            return await utils.answer(status_msg, self.strings["cgch_chat_error"].format(target_chat_id, e))

        prompt = (
            "Проанализируй следующую историю чата и ответь на вопрос пользователя. "
            "Отвечай только на основе переданной истории.\n\n"
            f"ВОПРОС ПОЛЬЗОВАТЕЛЯ: \"{user_prompt}\"\n\n"
            f"ИСТОРИЯ ЧАТА:\n---\n{chat_log}\n---"
        )
        payload = {
            "text": prompt,
            "images": [],
            "display_prompt": user_prompt,
        }
        try:
            result = await self._run_backend_request(
                target_chat_id,
                payload,
                system_prompt=self.config["system_instruction"].strip() or None,
                history_override=[],
            )
            header = self.strings["cgch_result_caption_from_chat"].format(count, chat_name)
            resp_html = self._markdown_to_html(result["text"])
            text = (
                f"<b>{header}</b>\n\n"
                f"{self.strings['question_prefix']}\n"
                f"<blockquote expandable='true'>{utils.escape_html(user_prompt)}</blockquote>\n\n"
                f"{self.strings['response_prefix'].format(utils.escape_html(result['label']))}\n"
                f"{self._format_response_with_smart_separation(resp_html)}"
            )
            if len(text) > 4096:
                f = io.BytesIO(result["text"].encode("utf-8"))
                f.name = "analysis.txt"
                await status_msg.delete()
                await message.reply(file=f, caption=f"📝 {header}")
            else:
                await utils.answer(status_msg, text)
        except Exception as e:
            await utils.answer(status_msg, self._handle_error(e))

    @loader.command()
    async def cgprompt(self, message: Message):
        """<текст/-c/ответ на файл> — установить системный промпт."""
        await self._sync_runtime_config()
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        if args == "-c":
            self.config["system_instruction"] = ""
            return await utils.answer(message, self.strings["cgprompt_cleared"])

        new_prompt = None
        preset = self._find_preset(args)
        if preset:
            new_prompt = preset["content"]
        elif reply and reply.file:
            if reply.file.size > 1024 * 1024:
                return await utils.answer(message, self.strings["cgprompt_file_too_big"])
            try:
                file_data = await self.client.download_file(reply.media, bytes)
                try:
                    new_prompt = file_data.decode("utf-8")
                except UnicodeDecodeError:
                    return await utils.answer(message, self.strings["cgprompt_not_text"])
            except Exception as e:
                return await utils.answer(message, self.strings["cgprompt_file_error"].format(e))
        elif args:
            new_prompt = args

        if new_prompt is not None:
            self.config["system_instruction"] = new_prompt
            return await utils.answer(message, self.strings["cgprompt_updated"].format(len(new_prompt)))

        current_prompt = self.config["system_instruction"]
        if not current_prompt:
            return await utils.answer(message, self.strings["cgprompt_usage"])
        if len(current_prompt) > 4000:
            file = io.BytesIO(current_prompt.encode("utf-8"))
            file.name = "system_instruction.txt"
            await self.client.send_file(
                message.chat_id,
                file=file,
                caption=self.strings["cgprompt_current"],
                reply_to=self._get_reply_target_id(message),
            )
        else:
            await utils.answer(message, f"{self.strings['cgprompt_current']}\n<code>{utils.escape_html(current_prompt)}</code>")

    @loader.command()
    async def cgauto(self, message: Message):
        """<on/off/[id]> — вкл/выкл авто-ответ в чате."""
        await self._sync_runtime_config()
        args = utils.get_args_raw(message).split()
        if not args:
            return await utils.answer(message, self.strings["auto_mode_usage"])
        chat_id = utils.get_chat_id(message)
        state = args[0].lower()
        target = chat_id
        if len(args) == 2:
            try:
                entity = await self.client.get_entity(args[0])
                target = entity.id
                state = args[1].lower()
            except Exception:
                return await utils.answer(message, self.strings["cgauto_chat_not_found"].format(args[0]))
        if state == "on":
            await self._update_chat_list_config("auto_reply_chats", target, True)
            txt = self.strings["auto_mode_on"].format(int(self.config["impersonation_reply_chance"] * 100)) if target == chat_id else self.strings["cgauto_state_updated"].format(f"<code>{target}</code>", self.strings["cgauto_enabled"])
            return await utils.answer(message, txt)
        if state == "off":
            await self._update_chat_list_config("auto_reply_chats", target, False)
            txt = self.strings["auto_mode_off"] if target == chat_id else self.strings["cgauto_state_updated"].format(f"<code>{target}</code>", self.strings["cgauto_disabled"])
            return await utils.answer(message, txt)
        await utils.answer(message, self.strings["auto_mode_usage"])

    @loader.command()
    async def cgautochats(self, message: Message):
        """— показать чаты с активным авто-ответом."""
        await self._sync_runtime_config()
        if not self.impersonation_chats:
            return await utils.answer(message, self.strings["no_auto_mode_chats"])
        out = [self.strings["auto_mode_chats_title"].format(len(self.impersonation_chats))]
        for cid in self.impersonation_chats:
            try:
                entity = await self.client.get_entity(cid)
                name = utils.escape_html(get_display_name(entity))
                out.append(self.strings["memory_chat_line"].format(name, cid))
            except Exception:
                out.append(self.strings["memory_chat_line"].format("Неизвестный чат", cid))
        await utils.answer(message, "\n".join(out))

    @loader.command()
    async def cgclear(self, message: Message):
        """[auto] — очистить память в чате. auto для cgauto."""
        await self._sync_runtime_config()
        args = utils.get_args_raw(message)
        chat_id = utils.get_chat_id(message)
        if args == "auto":
            if str(chat_id) in self.gauto_conversations:
                self._clear_history(chat_id, gauto=True)
                return await utils.answer(message, self.strings["memory_cleared_gauto"])
            return await utils.answer(message, self.strings["no_gauto_memory_to_clear"])
        if not args:
            if str(chat_id) in self.conversations:
                self._clear_history(chat_id)
                return await utils.answer(message, self.strings["memory_cleared"])
            return await utils.answer(message, self.strings["no_memory_to_clear"])
        await utils.answer(message, self.strings["cgclear_usage"])

    @loader.command()
    async def cgpresets(self, message: Message):
        """<save/load/del/list> — управление пресетами."""
        await self._sync_runtime_config()
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, self.strings["cgpresets_usage"])
        match = re.match(r"^(\w+)(?:\s+\[(.+?)\]|\s+(\S+))?(?:\s+(.*))?$", args, re.DOTALL)
        if not match:
            return await utils.answer(message, self.strings["cgpresets_usage"])
        action = match.group(1).lower()
        name = match.group(2) or match.group(3)
        content = match.group(4)

        if action == "list":
            if not self.prompt_presets:
                return await utils.answer(message, self.strings["cgpreset_empty"])
            text = self.strings["cgpreset_list_head"]
            for idx, preset in enumerate(self.prompt_presets, 1):
                text += f"<b>{idx}.</b> <code>{utils.escape_html(preset['name'])}</code> ({len(preset['content'])} симв.)\n"
            return await utils.answer(message, text)

        if action == "save":
            if not name:
                return await utils.answer(message, "❌ Укажите имя: <code>.cgpresets save [Имя] текст</code>")
            reply = await message.get_reply_message()
            if not content and reply:
                if reply.text:
                    content = reply.text
                elif reply.file:
                    try:
                        content = (await self.client.download_file(reply.media, bytes)).decode("utf-8", errors="ignore")
                    except Exception:
                        pass
            if not content:
                return await utils.answer(message, "❌ Нет текста для сохранения.")
            existing = self._find_preset(name)
            if existing:
                existing["content"] = content
            else:
                self.prompt_presets.append({"name": name, "content": content})
            self.db.set(self.strings["name"], DB_PRESETS_KEY, self.prompt_presets)
            return await utils.answer(message, self.strings["cgpreset_saved"].format(name, len(self.prompt_presets)))

        if action == "load":
            target = self._find_preset(name)
            if not target:
                return await utils.answer(message, self.strings["cgpreset_not_found"])
            self.config["system_instruction"] = target["content"]
            return await utils.answer(message, self.strings["cgpreset_loaded"].format(target["name"], len(target["content"])))

        if action == "del":
            target = self._find_preset(name)
            if not target:
                return await utils.answer(message, self.strings["cgpreset_not_found"])
            self.prompt_presets.remove(target)
            self.db.set(self.strings["name"], DB_PRESETS_KEY, self.prompt_presets)
            return await utils.answer(message, self.strings["cgpreset_deleted"].format(target["name"]))

        await utils.answer(message, self.strings["cgpresets_usage"])

    @loader.command()
    async def cgmemdel(self, message: Message):
        """[N] — удалить последние N пар сообщений из памяти."""
        await self._sync_runtime_config()
        try:
            pairs = int(utils.get_args_raw(message) or 1)
        except Exception:
            pairs = 1
        cid = utils.get_chat_id(message)
        hist = self._get_structured_history(cid)
        if pairs > 0 and len(hist) >= pairs * 2:
            self.conversations[str(cid)] = hist[: -(pairs * 2)]
            self._save_history_sync()
            return await utils.answer(message, f"🧹 Удалено последних <b>{pairs}</b> пар сообщений из памяти.")
        await utils.answer(message, "Недостаточно истории для удаления.")

    @loader.command()
    async def cgmemchats(self, message: Message):
        """— показать список чатов с активной памятью."""
        await self._sync_runtime_config()
        if not self.conversations:
            return await utils.answer(message, self.strings["no_memory_found"])
        out = [self.strings["memory_chats_title"].format(len(self.conversations))]
        shown = set()
        for cid in list(self.conversations.keys()):
            if not str(cid).lstrip("-").isdigit():
                continue
            chat_id = int(cid)
            if chat_id in shown:
                continue
            shown.add(chat_id)
            try:
                entity = await self.client.get_entity(chat_id)
                name = get_display_name(entity)
            except Exception:
                name = f"Unknown ({chat_id})"
            out.append(self.strings["memory_chat_line"].format(name, chat_id))
        if len(out) == 1:
            return await utils.answer(message, self.strings["no_memory_found"])
        await utils.answer(message, "\n".join(out))

    @loader.command()
    async def cgmemexport(self, message: Message):
        """[<id/@юз чата>] [auto] [-s] — экспорт истории."""
        await self._sync_runtime_config()
        args = utils.get_args_raw(message).split()
        save_to_self = "-s" in args
        if save_to_self:
            args.remove("-s")
        gauto = "auto" in args
        if gauto:
            args.remove("auto")
        src_id = int(args[0]) if args and args[0].lstrip("-").isdigit() else utils.get_chat_id(message)
        hist = self._get_structured_history(src_id, gauto=gauto)
        if not hist:
            return await utils.answer(message, "История для экспорта пуста.")
        data = json.dumps(hist, ensure_ascii=False, indent=2)
        f = io.BytesIO(data.encode("utf-8"))
        f.name = f"chatgptcodex_{'cgauto_' if gauto else ''}{src_id}.json"
        dest = "me" if save_to_self else message.chat_id
        caption = "Экспорт истории cgauto" if gauto else "Экспорт памяти"
        if src_id != utils.get_chat_id(message):
            caption += f" из чата <code>{src_id}</code>"
        await self.client.send_file(dest, f, caption=caption)
        if save_to_self:
            return await utils.answer(message, "💾 История экспортирована в избранное.")
        if args:
            await message.delete()

    @loader.command()
    async def cgmemimport(self, message: Message):
        """[auto] — импорт истории из json-файла (ответом)."""
        await self._sync_runtime_config()
        reply = await message.get_reply_message()
        if not reply or not reply.document:
            return await utils.answer(message, "Ответьте на json-файл с памятью.")
        gauto = "auto" in utils.get_args_raw(message)
        try:
            raw = await self.client.download_media(reply, bytes)
            hist = json.loads(raw)
            if not isinstance(hist, list):
                raise ValueError("JSON должен содержать список.")
            cid = utils.get_chat_id(message)
            target = self.gauto_conversations if gauto else self.conversations
            target[str(cid)] = hist
            self._save_history_sync(gauto)
            await utils.answer(message, "Память успешно импортирована.")
        except Exception as e:
            await utils.answer(message, f"Ошибка импорта: {utils.escape_html(str(e))}")

    @loader.command()
    async def cgmemfind(self, message: Message):
        """[слово] — поиск в памяти текущего чата."""
        await self._sync_runtime_config()
        query = utils.get_args_raw(message).lower().strip()
        if not query:
            return await utils.answer(message, "Укажите слово для поиска.")
        cid = utils.get_chat_id(message)
        hist = self._get_structured_history(cid)
        found = [
            f"{entry['role']}: {utils.escape_html(str(entry.get('content', ''))[:200])}"
            for entry in hist
            if query in str(entry.get("content", "")).lower()
        ]
        if not found:
            return await utils.answer(message, "Ничего не найдено.")
        await utils.answer(message, "\n\n".join(found[:10]))

    @loader.command()
    async def cgmem(self, message: Message):
        """— переключить память в этом чате."""
        await self._sync_runtime_config()
        chat_id = str(utils.get_chat_id(message))
        is_enabled = self._is_memory_enabled(chat_id)
        await self._update_chat_list_config("memory_disabled_chats", chat_id, is_enabled)
        await utils.answer(message, "Память в этом чате отключена." if is_enabled else "Память в этом чате включена.")

    @loader.command()
    async def cgmemshow(self, message: Message):
        """[auto] — показать память чата (до 20 последних запросов)."""
        await self._sync_runtime_config()
        gauto = "auto" in utils.get_args_raw(message)
        cid = utils.get_chat_id(message)
        hist = self._get_structured_history(cid, gauto=gauto)
        if not hist:
            return await utils.answer(message, "Память пуста.")
        out = []
        for entry in hist[-40:]:
            role = entry.get("role")
            content = utils.escape_html(str(entry.get("content", ""))[:300])
            if role == "user":
                out.append(content)
            else:
                out.append(f"<b>Assistant:</b> {content}")
        await utils.answer(message, "<blockquote expandable='true'>" + "\n".join(out) + "</blockquote>")

    @loader.command()
    async def cgmodel(self, message: Message):
        """[model] [-s] — узнать/сменить модель."""
        await self._sync_runtime_config()
        args_raw = utils.get_args_raw(message).strip()
        if not args_raw:
            return await utils.answer(message, self._build_cgmodel_panel_text(), reply_markup=self._get_reasoning_effort_buttons())

        args_list = args_raw.split()
        is_list = "-s" in [arg.lower() for arg in args_list]
        target_backend = self.config["backend"]
        model_value = args_raw.replace("-s", "").strip()
        if args_list and args_list[0].lower() in {"chatgpt", "codex"}:
            target_backend = args_list[0].lower()
            model_value = " ".join(arg for arg in args_list[1:] if arg.lower() != "-s").strip()

        if is_list:
            if target_backend == "chatgpt":
                status_msg = await utils.answer(message, self.strings["processing"])
                try:
                    models = await self._list_chatgpt_models()
                    if not models:
                        raise RuntimeError("Список моделей пуст.")
                    text = "📋 <b>Доступные модели OpenAI API:</b>\n" + "\n".join(f"• <code>{utils.escape_html(mid)}</code>" for mid in models)
                    file = io.BytesIO(text.encode("utf-8"))
                    file.name = "openai_models.txt"
                    await self.client.send_file(
                        message.chat_id,
                        file=file,
                        caption="📋 OpenAI Models",
                        reply_to=self._get_reply_target_id(message),
                    )
                    await status_msg.delete()
                except Exception as e:
                    await utils.answer(status_msg, self.strings["cgmodel_list_error"].format(utils.escape_html(str(e))))
                return
            note = self.strings["codex_models_note"].format(utils.escape_html(self.config["codex_model"] or "default"))
            return await utils.answer(message, note)

        if not model_value:
            return await utils.answer(message, self.strings["cgmodel_usage"])

        if target_backend == "chatgpt":
            self.config["chatgpt_model"] = model_value
            return await utils.answer(message, f"✅ <b>ChatGPT model:</b> <code>{utils.escape_html(model_value)}</code>")
        self.config["codex_model"] = model_value
        await utils.answer(message, f"✅ <b>Codex model:</b> <code>{utils.escape_html(model_value)}</code>")

    @loader.command()
    async def cgres(self, message: Message):
        """[auto] — очистить всю память."""
        await self._sync_runtime_config()
        if utils.get_args_raw(message) == "auto":
            if not self.gauto_conversations:
                return await utils.answer(message, self.strings["no_gauto_memory_to_fully_clear"])
            count = len(self.gauto_conversations)
            self.gauto_conversations.clear()
            self._save_history_sync(True)
            return await utils.answer(message, self.strings["gauto_memory_fully_cleared"].format(count))
        if not self.conversations:
            return await utils.answer(message, self.strings["no_memory_to_fully_clear"])
        count = len(self.conversations)
        self.conversations.clear()
        self._save_history_sync(False)
        await utils.answer(message, self.strings["memory_fully_cleared"].format(count))

    @loader.callback_handler()
    async def chatgptcodex_callback_handler(self, call: InlineCall):
        if not call.data.startswith("chatgptcodex:"):
            return
        parts = call.data.split(":")
        action = parts[1]
        if action == "noop":
            await call.answer()
            return
        if action == "pg":
            uid = parts[2]
            page = int(parts[3])
            await self._render_page(uid, page, call)
            return
        if action == "re":
            effort = parts[2] if len(parts) > 2 else ""
            await self._set_reasoning_effort_callback(call, effort)

    @loader.watcher(only_incoming=True, ignore_edited=True)
    async def watcher(self, message: Message):
        await self._sync_runtime_config()
        if not hasattr(message, "chat_id"):
            return
        cid = utils.get_chat_id(message)
        if cid not in self.impersonation_chats:
            return
        if message.is_private and not self.config["gauto_in_pm"]:
            return
        if message.out or (isinstance(message.from_id, tg_types.PeerUser) and message.from_id.user_id == self.me.id):
            return
        sender = await message.get_sender()
        if isinstance(sender, tg_types.User) and sender.bot:
            return
        if random.random() > self.config["impersonation_reply_chance"]:
            return
        payload, warnings = await self._prepare_request_payload(message)
        if warnings:
            logger.warning("cgauto warnings: %s", warnings)
        if not payload:
            return
        resp = await self._send_request(message=message, payload=payload, impersonation_mode=True)
        if resp and resp.strip():
            clean = resp.strip()
            await asyncio.sleep(random.uniform(2, 8))
            try:
                await self.client.send_read_acknowledge(cid, message=message)
            except Exception:
                pass
            async with message.client.action(cid, "typing"):
                await asyncio.sleep(min(25.0, max(1.5, len(clean) * random.uniform(0.06, 0.15))))
            await message.reply(clean)

    async def _send_request(
        self,
        message,
        payload: dict,
        regeneration: bool = False,
        call: InlineCall = None,
        status_msg=None,
        chat_id_override: int = None,
        impersonation_mode: bool = False,
    ):
        msg_obj = None
        current_task = asyncio.current_task()
        if regeneration:
            chat_id = chat_id_override
            base_message_id = message
            try:
                msg_obj = await self.client.get_messages(chat_id, ids=base_message_id)
            except Exception:
                msg_obj = None
            current_payload, display_prompt, retry_count = self._normalize_last_request_state(
                self.last_requests.get(f"{chat_id}:{base_message_id}"),
                fallback_payload=payload,
            )
            retry_count += 1
            self._set_last_request_state(chat_id, base_message_id, current_payload, display_prompt, retry_count)
        else:
            chat_id = utils.get_chat_id(message)
            base_message_id = message.id
            msg_obj = message
            current_payload = payload
            display_prompt = payload.get("display_prompt") or self.strings["media_reply_placeholder"]
            retry_count = 0
            self._set_last_request_state(chat_id, base_message_id, current_payload, display_prompt, retry_count)

        request_key = self._get_text_request_key(chat_id, base_message_id)
        if not impersonation_mode and current_task:
            self.active_text_requests[request_key] = {"task": current_task}

        loading_task = None
        status_entity = status_msg
        try:
            if impersonation_mode:
                my_name = get_display_name(self.me)
                chat_history_text = await self._get_recent_chat_text(chat_id)
                system_prompt = self.config["impersonation_prompt"].format(my_name=my_name, chat_history=chat_history_text)
            else:
                system_prompt = (self.config["system_instruction"].strip() or None)

            if regeneration and call:
                loading_task = asyncio.create_task(self._animate_text_regeneration(call, display_prompt, chat_id, base_message_id))
            elif status_msg and not impersonation_mode:
                status_entity = await self._set_text_request_loading_ui(
                    status_entity,
                    getattr(status_msg, "text", None) or self.strings["processing"],
                    chat_id,
                    base_message_id,
                )

            autoretry_left = max(0, int(self.config["autoretry"]))
            while True:
                try:
                    result = await self._run_backend_request(
                        chat_id,
                        current_payload,
                        system_prompt=system_prompt,
                        gauto=impersonation_mode,
                        regeneration=regeneration,
                    )
                    result_text = (result.get("text") or "").strip()
                    if not result_text:
                        raise RuntimeError(self.strings["empty_backend_response"])
                    break
                except Exception as e:
                    if autoretry_left <= 0 or not self._should_autoretry_backend_error(e):
                        raise
                    autoretry_left -= 1
                    retry_count += 1
                    self._set_last_request_state(chat_id, base_message_id, current_payload, display_prompt, retry_count)
                    await asyncio.sleep(1)

            label = result["label"]
            model_name = result["model"]

            await self._sync_runtime_config()
            if self._is_memory_enabled(str(chat_id)):
                self._update_history(chat_id, current_payload, result_text, regeneration=regeneration, message=msg_obj, gauto=impersonation_mode)

            if impersonation_mode:
                return result_text

            hist_len = len(self._get_structured_history(chat_id)) // 2
            mem_ind = self.strings["memory_status"].format(hist_len, self.config["max_history_length"])
            if self.config["max_history_length"] <= 0:
                mem_ind = self.strings["memory_status_unlimited"].format(hist_len)

            response_html = self._markdown_to_html(result_text)
            formatted_body = self._format_response_with_smart_separation(response_html)
            question_html = f"<blockquote>{utils.escape_html(display_prompt[:250])}</blockquote>"
            model_info = f"<i>{utils.escape_html(label)}: <code>{utils.escape_html(model_name)}</code></i>"
            reply_target_id = self._get_reply_target_id(msg_obj, fallback=base_message_id)
            text_to_send = (
                f"{mem_ind}\n{model_info}\n\n"
                f"{self.strings['question_prefix']}\n{question_html}\n\n"
                f"{self.strings['response_prefix'].format(utils.escape_html(label))}\n{formatted_body}"
            )
            buttons = self._get_inline_buttons(chat_id, base_message_id) if self.config["interactive_buttons"] else None

            if len(result_text) > 3500 and self.config["inline_pagination"]:
                await self._cancel_loading_task(loading_task)
                loading_task = None
                chunks = self._paginate_text(result_text, 3000)
                uid = uuid.uuid4().hex[:6]
                header = (
                    f"{mem_ind}\n{model_info}\n\n"
                    f"{self.strings['question_prefix']}\n<blockquote>{utils.escape_html(display_prompt[:100])}</blockquote>\n\n"
                    f"{self.strings['response_prefix'].format(utils.escape_html(label))}\n"
                )
                self.pager_cache[uid] = {
                    "chunks": chunks,
                    "total": len(chunks),
                    "header": header,
                    "chat_id": chat_id,
                    "msg_id": base_message_id,
                }
                await self._render_page(uid, 0, call or status_entity)
            elif len(text_to_send) > 4096:
                await self._cancel_loading_task(loading_task)
                loading_task = None
                file = io.BytesIO(result_text.encode("utf-8"))
                file.name = "chatgptcodex_response.txt"
                if call:
                    await call.answer("Ответ длинный, отправляю файлом...", show_alert=False)
                    await self.client.send_file(
                        call.chat_id,
                        file,
                        caption=self.strings["response_too_long"],
                        reply_to=self._extract_message_id(getattr(call, "message", None)) or self._extract_message_id(call),
                    )
                elif status_entity:
                    await self._delete_message_entity(status_entity)
                    await self.client.send_file(chat_id, file, caption=self.strings["response_too_long"], reply_to=reply_target_id)
            else:
                await self._cancel_loading_task(loading_task)
                loading_task = None
                if call:
                    await call.edit(text_to_send, reply_markup=buttons)
                elif status_entity:
                    status_entity = await self._update_text_request_ui(status_entity, text_to_send, reply_markup=buttons)
        except asyncio.CancelledError:
            await self._cancel_loading_task(loading_task)
            loading_task = None
            self.last_requests.pop(request_key, None)
            if not impersonation_mode:
                with contextlib.suppress(Exception):
                    if call:
                        await call.edit(self.strings["request_cancelled"], reply_markup=None)
                    elif status_entity:
                        await self._update_text_request_ui(status_entity, self.strings["request_cancelled"], reply_markup=None)
            return None if impersonation_mode else ""
        except Exception as e:
            error_text = self._handle_error(e)
            if impersonation_mode:
                logger.error("cgauto backend error: %s", error_text)
            elif call:
                await self._cancel_loading_task(loading_task)
                loading_task = None
                await call.edit(error_text, reply_markup=self._get_error_buttons(chat_id, base_message_id))
            elif status_entity:
                buttons = self._get_error_buttons(chat_id, base_message_id)
                try:
                    status_entity = await self._update_text_request_ui(status_entity, error_text, reply_markup=buttons)
                except Exception:
                    target_message = msg_obj or status_entity
                    await self._update_text_request_ui(target_message, error_text, reply_markup=buttons)
        finally:
            await self._cancel_loading_task(loading_task)
            active = self.active_text_requests.get(request_key)
            if active and active.get("task") is current_task:
                self.active_text_requests.pop(request_key, None)
        return None if impersonation_mode else ""

    async def _run_backend_request(
        self,
        chat_id: int,
        payload: dict,
        system_prompt: str = None,
        gauto: bool = False,
        regeneration: bool = False,
        history_override=None,
    ):
        backend = self.config["backend"]
        if backend == "codex":
            return await self._run_codex_request(
                chat_id,
                payload,
                system_prompt=system_prompt,
                gauto=gauto,
                history_override=history_override,
            )
        return await self._run_chatgpt_request(
            chat_id,
            payload,
            system_prompt=system_prompt,
            gauto=gauto,
            history_override=history_override,
        )

    async def _run_chatgpt_request(
        self,
        chat_id: int,
        payload: dict,
        system_prompt: str = None,
        gauto: bool = False,
        history_override=None,
    ):
        if not aiohttp:
            raise RuntimeError("Библиотека aiohttp не установлена.")
        api_key = self.config["api_key"].strip()
        if not api_key:
            raise RuntimeError(self.strings["no_api_key"])

        model = self.config["chatgpt_model"].strip()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "input": self._build_openai_input(chat_id, payload, gauto=gauto, history_override=history_override),
            "store": False,
            "truncation": "auto",
            "text": {"format": {"type": "text"}},
            "temperature": float(self.config["temperature"]),
        }
        reasoning_effort = self._get_chatgpt_reasoning_effort(model)
        if reasoning_effort is not None:
            body["reasoning"] = {"effort": reasoning_effort}
        if system_prompt:
            body["instructions"] = system_prompt

        proxy = self._get_proxy()
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                "https://api.openai.com/v1/responses",
                json=body,
                proxy=proxy,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                raw = await resp.text()
                if resp.status != 200:
                    raise RuntimeError(self._parse_openai_error(resp.status, raw))
                data = json.loads(raw)
        return {
            "text": self._extract_openai_output_text(data),
            "model": data.get("model", model),
            "label": "ChatGPT",
        }

    async def _run_codex_request(
        self,
        chat_id: int,
        payload: dict,
        system_prompt: str = None,
        gauto: bool = False,
        history_override=None,
    ):
        codex_path = await self._ensure_codex_available()
        logged_in, status = await self._get_codex_status_for_runtime()
        if not logged_in:
            raise RuntimeError(status or self.strings["no_codex_login"])

        prompt = self._build_codex_prompt(chat_id, payload, gauto=gauto, history_override=history_override)
        env = self._build_subprocess_env()
        selected_model = self.config["codex_model"].strip()
        reasoning_effort = self._get_codex_reasoning_effort()
        yolo_mode = bool(self.config["codex_yolo_mode"])

        with tempfile.TemporaryDirectory(prefix="chatgptcodex_") as tempdir:
            output_file = os.path.join(tempdir, "last_message.txt")
            image_paths = []
            for idx, image in enumerate(payload.get("images", []), 1):
                ext = self._guess_extension(image.get("mime_type", "image/png"))
                path = os.path.join(tempdir, f"input_{idx}{ext}")
                with open(path, "wb") as file_obj:
                    file_obj.write(image["data"])
                image_paths.append(path)

            workdir = os.getcwd() if yolo_mode else tempdir
            args = [
                codex_path,
                "exec",
                "--skip-git-repo-check",
                "-C",
                workdir,
                "--color",
                "never",
                "-o",
                output_file,
                "-c",
                'web_search="disabled"',
                "-c",
                'hide_agent_reasoning=true',
            ]
            if yolo_mode:
                args.append("--dangerously-bypass-approvals-and-sandbox")
            else:
                args.extend([
                    "--sandbox",
                    "read-only",
                    "-c",
                    'approval_policy="never"',
                ])
            if workdir != tempdir:
                args.extend(["--add-dir", tempdir])
            if selected_model:
                args.extend(["-m", selected_model])
            if reasoning_effort:
                args.extend(["-c", f"model_reasoning_effort={self._toml_string(reasoning_effort)}"])
            if system_prompt:
                args.extend(["-c", f"developer_instructions={self._toml_string(system_prompt)}"])
            for image_path in image_paths:
                args.extend(["-i", image_path])

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(prompt.encode("utf-8")),
                    timeout=CODEX_TIMEOUT,
                )
            except asyncio.CancelledError:
                proc.kill()
                with contextlib.suppress(Exception):
                    await proc.communicate()
                raise
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise RuntimeError(f"Codex CLI превысил таймаут ({CODEX_TIMEOUT} сек).")

            stdout_text = stdout.decode("utf-8", errors="ignore").strip()
            stderr_text = stderr.decode("utf-8", errors="ignore").strip()
            final_text = ""
            if os.path.exists(output_file):
                with open(output_file, "r", encoding="utf-8", errors="ignore") as file_obj:
                    final_text = file_obj.read().strip()
            if not final_text:
                final_text = self._extract_codex_stdout(stdout_text)
            if proc.returncode != 0 and not final_text:
                raise RuntimeError(stderr_text or stdout_text or f"Codex CLI завершился с кодом {proc.returncode}.")
            if not final_text:
                raise RuntimeError("Codex CLI не вернул финальный ответ.")

        return {
            "text": final_text,
            "model": selected_model or "default",
            "label": "Codex",
        }

    async def _prepare_request_payload(self, message: Message, custom_text: str = None):
        warnings = []
        prompt_chunks = []
        images = []
        default_media_instruction = None
        user_args = custom_text if custom_text is not None else utils.get_args_raw(message).strip()
        reply = await message.get_reply_message()

        if reply and getattr(reply, "text", None):
            try:
                reply_sender = await reply.get_sender()
                reply_author_name = get_display_name(reply_sender) if reply_sender else "Unknown"
                prompt_chunks.append(f"{reply_author_name}: {reply.text}")
            except Exception:
                prompt_chunks.append(f"Ответ на: {reply.text}")

        try:
            current_sender = await message.get_sender()
            current_user_name = get_display_name(current_sender) if current_sender else "User"
        except Exception:
            current_user_name = "User"

        media_source = message if (message.media or message.sticker) else reply
        has_media = bool(media_source and (media_source.media or media_source.sticker))
        if has_media:
            if media_source.sticker:
                document = media_source.sticker
                mime_type = getattr(document, "mime_type", "application/octet-stream") or "application/octet-stream"
                filename = self._get_document_filename(document, mime_type, default="sticker")
                sticker_attr = self._get_sticker_attribute(document)
                video_attr = self._get_video_attribute(document)
                alt_text = getattr(sticker_attr, "alt", None) or "?"
                is_video_sticker = self._is_video_sticker(media_source, mime_type, document)
                is_animated_sticker = self._is_animated_sticker(mime_type, filename)

                prompt_chunks.append(
                    self._format_sticker_metadata(
                        alt_text,
                        filename,
                        mime_type,
                        is_video_sticker=is_video_sticker,
                        is_animated_sticker=is_animated_sticker,
                        video_attr=video_attr,
                    )
                )
                default_media_instruction = "Проанализируй приложенный стикер и ответь по содержимому."

                if mime_type.startswith("image/") and not is_animated_sticker:
                    try:
                        data = await self.client.download_media(media_source, bytes)
                        if not data:
                            raise RuntimeError("sticker download failed")
                        images.append({"mime_type": mime_type, "data": data, "filename": filename})
                    except Exception as e:
                        preview = await self._download_media_preview_image(media_source, os.path.splitext(filename)[0] or "sticker")
                        if preview:
                            images.append(preview)
                            prompt_chunks.append(self.strings["media_sticker_preview_used"])
                        else:
                            warnings.append(self.strings["media_sticker_download_failed"].format(utils.escape_html(str(e))))
                else:
                    try:
                        frame_count = min(3, int(self.config["media_frame_count"]))
                        frames = await self._extract_visual_frames_from_message(media_source, mime_type, filename, frame_count)
                        images.extend(frames)
                        prompt_chunks.append(f"[Из стикера извлечено кадров: {len(frames)}]")
                    except Exception as e:
                        msg = str(e)
                        if msg.startswith("⚠️"):
                            warnings.append(msg)
                        else:
                            warnings.append(self.strings["media_frame_extract_failed"].format(utils.escape_html(msg)))
                        preview = await self._download_media_preview_image(media_source, os.path.splitext(filename)[0] or "sticker")
                        if preview:
                            images.append(preview)
                            prompt_chunks.append(self.strings["media_sticker_preview_used"])
            elif media_source.photo:
                data = await self.client.download_media(media_source, bytes)
                images.append({"mime_type": "image/jpeg", "data": data, "filename": "photo.jpg"})
                default_media_instruction = "Опиши и обработай приложенное изображение."
            elif getattr(media_source, "document", None):
                document = media_source.document
                mime_type = getattr(document, "mime_type", "application/octet-stream") or "application/octet-stream"
                filename = self._get_document_filename(document, mime_type)
                audio_attr = self._get_audio_attribute(document)
                video_attr = self._get_video_attribute(document)
                gif_like = self._is_gif_like_media(media_source, mime_type, document)

                if mime_type.startswith("image/") and not gif_like:
                    data = await self.client.download_media(media_source, bytes)
                    images.append({"mime_type": mime_type, "data": data, "filename": filename})
                    default_media_instruction = "Опиши и обработай приложенное изображение."
                elif gif_like or mime_type.startswith("video/") or video_attr:
                    prompt_chunks.append(self._format_video_metadata(filename, mime_type, video_attr, gif_like=gif_like))
                    default_media_instruction = "Проанализируй приложенные кадры из GIF/видео и ответь по содержимому."
                    try:
                        frame_count = min(3, int(self.config["media_frame_count"])) if gif_like else int(self.config["media_frame_count"])
                        frames = await self._extract_visual_frames_from_message(media_source, mime_type, filename, frame_count)
                        images.extend(frames)
                        prompt_chunks.append(f"[Из медиа извлечено кадров: {len(frames)}]")
                    except Exception as e:
                        msg = str(e)
                        if msg.startswith("⚠️"):
                            warnings.append(msg)
                        else:
                            warnings.append(self.strings["media_frame_extract_failed"].format(utils.escape_html(msg)))
                elif audio_attr or mime_type.startswith("audio/") or getattr(media_source, "voice", False):
                    prompt_chunks.append(self._format_audio_metadata(filename, mime_type, audio_attr))
                    default_media_instruction = "Проанализируй приложенное аудио или музыку и ответь по содержимому."
                    transcribe_prompt = None
                    prompt_parts = []
                    if getattr(audio_attr, "performer", None):
                        prompt_parts.append(f"Performer: {audio_attr.performer}")
                    if getattr(audio_attr, "title", None):
                        prompt_parts.append(f"Title: {audio_attr.title}")
                    if prompt_parts:
                        transcribe_prompt = ". ".join(prompt_parts)
                    try:
                        transcript = await self._transcribe_audio_from_message(media_source, mime_type, filename, prompt=transcribe_prompt)
                        if transcript:
                            prompt_chunks.append("[Транскрипция аудио]:\n" + transcript)
                    except Exception as e:
                        msg = str(e)
                        if msg.startswith("⚠️"):
                            warnings.append(msg)
                        else:
                            warnings.append(self.strings["media_audio_transcribe_failed"].format(utils.escape_html(msg)))
                elif mime_type in TEXT_MIME_TYPES or filename.split(".")[-1].lower() in {"txt", "py", "js", "json", "md", "html", "css", "sh"}:
                    try:
                        data = await self.client.download_media(media_source, bytes)
                        file_content = data.decode("utf-8", errors="ignore")
                        prompt_chunks.insert(0, f"[Содержимое файла '{filename}']:\n```\n{file_content}\n```")
                        default_media_instruction = "Проанализируй содержимое приложенного файла."
                    except Exception as e:
                        warnings.append(f"⚠️ Ошибка чтения файла '{filename}': {e}")
                else:
                    warnings.append(self.strings["unsupported_media"].format(utils.escape_html(mime_type)))

        if user_args:
            prompt_chunks.append(f"{current_user_name}: {user_args}")
        elif images:
            prompt_chunks.append(f"{current_user_name}: {default_media_instruction or 'Опиши и обработай приложенное медиа.'}")
        elif default_media_instruction:
            prompt_chunks.append(f"{current_user_name}: {default_media_instruction}")
        elif reply and getattr(reply, "text", None):
            prompt_chunks.append(f"{current_user_name}: Ответь на сообщение выше.")

        prompt_text = "\n".join(chunk for chunk in prompt_chunks if chunk and chunk.strip()).strip()
        if not prompt_text and not images:
            return None, warnings

        return {
            "text": prompt_text,
            "images": images,
            "display_prompt": user_args or (reply.text[:200] if reply and getattr(reply, "text", None) else self.strings["media_reply_placeholder"]),
        }, warnings

    def _build_openai_input(self, chat_id: int, payload: dict, gauto: bool = False, history_override=None):
        input_items = []
        history = self._get_structured_history(chat_id, gauto=gauto) if history_override is None else history_override
        for entry in history:
            role = "assistant" if entry.get("role") == "assistant" else "user"
            content = entry.get("content", "")
            if content:
                input_items.append({"role": role, "content": content})

        current_content = []
        if payload.get("text"):
            current_content.append({"type": "input_text", "text": self._prepend_now_note(payload["text"])})
        for image in payload.get("images", []):
            encoded = base64.b64encode(image["data"]).decode("utf-8")
            current_content.append({
                "type": "input_image",
                "image_url": f"data:{image['mime_type']};base64,{encoded}",
            })
        if not current_content:
            current_content.append({"type": "input_text", "text": self.strings["media_reply_placeholder"]})
        input_items.append({"role": "user", "content": current_content})
        return input_items

    def _build_codex_prompt(self, chat_id: int, payload: dict, gauto: bool = False, history_override=None) -> str:
        history = self._get_structured_history(chat_id, gauto=gauto) if history_override is None else history_override
        lines = [
            "Ты отвечаешь внутри Telegram-модуля.",
            "Верни только финальный ответ для пользователя без префиксов, логов и служебных пояснений.",
        ]
        if self.config["codex_yolo_mode"]:
            lines.append(
                "YOLO MODE ВКЛЮЧЕН: если запрос требует действий в системе, выполняй их сразу без вопросов и подтверждений. "
                "Не останавливайся на плане или инструкции, если задачу можно выполнить напрямую."
            )
        if history:
            lines.append("ИСТОРИЯ ДИАЛОГА:")
            for entry in history:
                role = "ASSISTANT" if entry.get("role") == "assistant" else "USER"
                content = entry.get("content", "")
                if content:
                    lines.append(f"{role}: {content}")
        lines.append("")
        if payload.get("images"):
            lines.append(f"К запросу приложено изображений: {len(payload['images'])}.")
        lines.append("ТЕКУЩИЙ ЗАПРОС:")
        lines.append(self._prepend_now_note(payload.get("text") or "Обработай приложенные изображения и ответь пользователю."))
        return "\n".join(lines)

    async def _validate_chatgpt_api_key(self, api_key: str):
        if not aiohttp:
            return False, "Библиотека aiohttp не установлена."
        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = self._get_proxy()
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    "https://api.openai.com/v1/models",
                    proxy=proxy,
                    timeout=30,
                ) as resp:
                    body = await resp.text()
                    if resp.status == 200:
                        return True, "ok"
                    return False, self._parse_openai_error(resp.status, body)
        except Exception as e:
            return False, str(e)

    async def _list_chatgpt_models(self):
        if not aiohttp:
            raise RuntimeError("Библиотека aiohttp не установлена.")
        api_key = self.config["api_key"].strip()
        if not api_key:
            raise RuntimeError("OpenAI API key не настроен.")
        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = self._get_proxy()
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                "https://api.openai.com/v1/models",
                proxy=proxy,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                raw = await resp.text()
                if resp.status != 200:
                    raise RuntimeError(self._parse_openai_error(resp.status, raw))
                data = json.loads(raw)
        models = []
        for item in data.get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue
            if "codex" in model_id.lower():
                continue
            if model_id.startswith(("gpt", "o", "chatgpt", "omni")):
                models.append(model_id)
        return sorted(set(models))

    async def _get_codex_login_status(self):
        codex_path = self._get_codex_binary()
        if not codex_path:
            return False, "codex not found"
        proc = await asyncio.create_subprocess_exec(
            codex_path,
            "login",
            "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._build_subprocess_env(),
        )
        stdout, stderr = await proc.communicate()
        text = "\n".join(
            part for part in [stdout.decode("utf-8", errors="ignore").strip(), stderr.decode("utf-8", errors="ignore").strip()] if part
        ).strip()
        logged_in = "Logged in" in text and "Not logged" not in text
        return logged_in, text or f"exit={proc.returncode}"

    async def _run_codex_device_auth(self, status_msg=None):
        codex_path = self._get_codex_binary()
        if not codex_path:
            return False, "codex not found"
        proc = await asyncio.create_subprocess_exec(
            codex_path,
            "login",
            "--device-auth",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._build_subprocess_env(),
        )

        # Read stdout line by line to capture URL and code before process exits
        verification_url = None
        user_code = None
        all_lines = []
        ansi_escape = re.compile(r"\x1b\[[0-9;]*m")

        async def read_output():
            nonlocal verification_url, user_code
            async for raw_line in proc.stdout:
                line = ansi_escape.sub("", raw_line.decode("utf-8", errors="ignore")).strip()
                if not line:
                    continue
                all_lines.append(line)
                if not verification_url and line.startswith("https://"):
                    verification_url = line
                elif not user_code and re.match(r"^[A-Z0-9]{4}-[A-Z0-9]{4,6}$", line):
                    user_code = line
                if verification_url and user_code and status_msg:
                    try:
                        await status_msg.edit(
                            "🔐 <b>Codex device auth</b>\n\n"
                            f"1. Откройте ссылку:\n<code>{utils.escape_html(verification_url)}</code>\n\n"
                            f"2. Введите код:\n<code>{utils.escape_html(user_code)}</code>\n\n"
                            "<i>Ожидаю подтверждения (до 3 минут)...</i>",
                            parse_mode="html",
                        )
                    except Exception:
                        pass

        try:
            await asyncio.wait_for(
                asyncio.gather(read_output(), proc.wait()),
                timeout=180,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()

        stderr_data = await proc.stderr.read() if not proc.stderr.at_eof() else b""
        stderr_text = ansi_escape.sub("", stderr_data.decode("utf-8", errors="ignore")).strip()
        if stderr_text:
            all_lines.append(stderr_text)
        output = "\n".join(all_lines).strip()

        logged_in, login_status = await self._get_codex_login_status()
        return logged_in, login_status if logged_in else (output or login_status or f"exit={proc.returncode}")

    async def _format_auth_status(self):
        codex_logged, codex_status = await self._get_codex_status_for_runtime()
        out = [self.strings["status_title"]]
        out.append(self.strings["status_backend"].format(utils.escape_html(self.config["backend"])))
        out.append(self.strings["status_chatgpt"].format(self.strings["status_set"] if self.config["api_key"].strip() else self.strings["status_missing"]))
        out.append(self.strings["status_codex"].format(self.strings["status_logged_in"] if codex_logged else self.strings["status_not_logged"]))
        out.append(self.strings["status_reasoning"].format(utils.escape_html(self._get_reasoning_effort())))
        out.append(self.strings["status_codex_yolo"].format("on" if self.config["codex_yolo_mode"] else "off"))
        if codex_status:
            out.append(f"<code>{utils.escape_html(codex_status[:300])}</code>")
        return "\n".join(out)

    def _get_reasoning_effort(self) -> str:
        effort = str(self.config["reasoning_effort"] or "medium").strip().lower()
        return effort if effort in REASONING_EFFORT_VALUES else "medium"

    def _supports_responses_reasoning_effort(self, model: str) -> bool:
        model_name = (model or "").strip().lower()
        return model_name.startswith(("gpt-5", "o1", "o3", "o4"))

    def _get_chatgpt_reasoning_effort(self, model: str):
        if not self._supports_responses_reasoning_effort(model):
            return None
        return self._get_reasoning_effort()

    def _get_codex_reasoning_effort(self):
        effort = self._get_reasoning_effort()
        return None if effort == "none" else effort

    def _build_cgmodel_panel_text(self) -> str:
        return (
            f"🔀 <b>Backend:</b> <code>{utils.escape_html(self.config['backend'])}</code>\n"
            f"🧠 <b>ChatGPT:</b> <code>{utils.escape_html(self.config['chatgpt_model'])}</code>\n"
            f"🛠 <b>Codex:</b> <code>{utils.escape_html(self.config['codex_model'] or 'default')}</code>\n"
            f"🧩 <b>Reasoning:</b> <code>{utils.escape_html(self._get_reasoning_effort())}</code>\n"
            f"🔥 <b>Codex YOLO:</b> <code>{'on' if self.config['codex_yolo_mode'] else 'off'}</code>\n"
            f"🎨 <b>Image:</b> <code>{utils.escape_html(self.config['image_model_name'])}</code>\n\n"
            f"{self.strings['cgmodel_reasoning_note']}"
        )

    def _get_reasoning_effort_buttons(self):
        values = list(REASONING_EFFORT_VALUES)
        current = self._get_reasoning_effort()
        rows = []
        for index in range(0, len(values), 3):
            row = []
            for effort in values[index:index + 3]:
                is_active = effort == current
                row.append({
                    "text": f"• {effort}" if is_active else effort,
                    "data": "chatgptcodex:noop" if is_active else f"chatgptcodex:re:{effort}",
                })
            rows.append(row)
        return rows

    async def _set_reasoning_effort_callback(self, call: InlineCall, effort: str):
        effort = (effort or "").strip().lower()
        if effort not in REASONING_EFFORT_VALUES:
            return await call.answer("Unsupported reasoning effort.", show_alert=True)
        if effort == self._get_reasoning_effort():
            return await call.answer(self.strings["cgmodel_reasoning_already"].format(effort), show_alert=False)
        self.config["reasoning_effort"] = effort
        await call.edit(self._build_cgmodel_panel_text(), reply_markup=self._get_reasoning_effort_buttons())
        await call.answer(self.strings["cgmodel_reasoning_updated"].format(utils.escape_html(effort)), show_alert=False)

    def _extract_openai_output_text(self, data: dict) -> str:
        texts = []
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    texts.append(content["text"])
        result = "\n".join(texts).strip()
        if result:
            return result
        top_level = data.get("output_text")
        if isinstance(top_level, str) and top_level.strip():
            return top_level.strip()
        raise RuntimeError("OpenAI API вернул пустой текстовый ответ.")

    def _extract_codex_stdout(self, stdout_text: str) -> str:
        cleaned = []
        for line in stdout_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("WARNING:"):
                continue
            cleaned.append(line)
        return "\n".join(cleaned).strip()

    def _parse_openai_error(self, status: int, raw: str) -> str:
        message = raw
        try:
            data = json.loads(raw)
            message = data.get("error", {}).get("message", raw)
        except Exception:
            pass
        low = message.lower()
        if status == 401 or "incorrect api key" in low or "invalid api key" in low:
            return self.strings["invalid_api_key"]
        if status == 429:
            return f"❗️ <b>Rate limit / quota exceeded.</b>\n<code>{utils.escape_html(message)}</code>"
        return f"❗️ <b>OpenAI API error {status}:</b>\n<code>{utils.escape_html(message)}</code>"

    def _handle_error(self, e: Exception) -> str:
        logger.exception("ChatGPTCodex execution error")
        if isinstance(e, asyncio.TimeoutError):
            return self.strings["api_timeout"]
        msg = str(e)
        if "OpenAI API key недействителен" in msg:
            return self.strings["invalid_api_key"]
        if msg.startswith("❗️") or msg.startswith("⚠️"):
            return msg
        return self.strings["generic_error"].format(utils.escape_html(msg))

    def _get_proxy(self):
        proxy = self.config["proxy"].strip()
        return proxy or None

    def _build_subprocess_env(self):
        env = os.environ.copy()
        proxy = self._get_proxy()
        if proxy:
            for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
                env[key] = proxy
        return env

    async def _update_status_message(self, status_msg, text: str):
        if not status_msg:
            return
        with contextlib.suppress(Exception):
            await status_msg.edit(text, parse_mode="html")

    def _prepend_now_note(self, text: str) -> str:
        if not text:
            return text
        tz = self._get_timezone()
        now = datetime.now(tz) if tz else datetime.utcnow()
        stamp = now.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
        return f"[System Info: Current local time is {stamp}]\n\n{text}"

    def _get_timezone(self):
        if not pytz:
            return None
        try:
            return pytz.timezone(self.config["timezone"])
        except Exception:
            return pytz.utc

    def _guess_extension(self, mime_type: str) -> str:
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "application/x-tgsticker": ".tgs",
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/quicktime": ".mov",
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
            "audio/aac": ".aac",
            "audio/ogg": ".ogg",
            "audio/oga": ".ogg",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/webm": ".webm",
        }
        return mapping.get(mime_type, ".bin")

    def _get_document_filename(self, document, mime_type: str = "", default: str = "file") -> str:
        if document:
            for attr in getattr(document, "attributes", []) or []:
                if isinstance(attr, DocumentAttributeFilename) and getattr(attr, "file_name", None):
                    return attr.file_name
        ext = self._guess_extension(mime_type) if mime_type else ""
        return f"{default}{ext}"

    def _get_audio_attribute(self, document):
        if not document:
            return None
        return next((attr for attr in getattr(document, "attributes", []) or [] if isinstance(attr, DocumentAttributeAudio)), None)

    def _get_sticker_attribute(self, document):
        if not document:
            return None
        return next((attr for attr in getattr(document, "attributes", []) or [] if isinstance(attr, DocumentAttributeSticker)), None)

    def _get_video_attribute(self, document):
        if not document:
            return None
        return next((attr for attr in getattr(document, "attributes", []) or [] if isinstance(attr, DocumentAttributeVideo)), None)

    def _is_animated_sticker(self, mime_type: str, filename: str = "") -> bool:
        mime = (mime_type or "").strip().lower()
        name = (filename or "").strip().lower()
        return mime == "application/x-tgsticker" or name.endswith(".tgs")

    def _is_video_sticker(self, message: Message, mime_type: str, document) -> bool:
        if not getattr(message, "sticker", None):
            return False
        if (mime_type or "").strip().lower() == "video/webm":
            return True
        return self._get_video_attribute(document) is not None

    def _is_gif_like_media(self, message: Message, mime_type: str, document) -> bool:
        if mime_type == "image/gif":
            return True
        if getattr(message, "gif", False):
            return True
        return any(isinstance(attr, DocumentAttributeAnimated) for attr in (getattr(document, "attributes", []) or []))

    def _detect_image_mime_type(self, data: bytes):
        if not data:
            return None
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data[:6] in {b"GIF87a", b"GIF89a"}:
            return "image/gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return None

    async def _download_media_preview_image(self, media_source: Message, base_name: str = "preview"):
        for thumb in (-1, 0, 1):
            with contextlib.suppress(Exception):
                data = await self.client.download_media(media_source, file=bytes, thumb=thumb)
                mime_type = self._detect_image_mime_type(data)
                if not mime_type:
                    continue
                return {
                    "mime_type": mime_type,
                    "data": data,
                    "filename": f"{base_name}{self._guess_extension(mime_type)}",
                }
        return None

    async def _run_media_tool(self, *args, timeout: int = 120):
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._build_subprocess_env(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"{os.path.basename(args[0])} timeout")
        return proc.returncode, stdout.decode("utf-8", errors="ignore").strip(), stderr.decode("utf-8", errors="ignore").strip()

    async def _probe_media_duration(self, input_path: str):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None
        code, stdout, _ = await self._run_media_tool(
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            input_path,
            timeout=30,
        )
        if code != 0 or not stdout:
            return None
        try:
            duration = float(stdout.strip())
        except Exception:
            return None
        return duration if duration > 0 else None

    def _build_media_frame_timestamps(self, duration, frame_count: int):
        if frame_count <= 1 or not duration or duration <= 0:
            return [0.0]
        upper = max(0.0, duration - 0.05)
        if upper <= 0:
            return [0.0]
        points = []
        for index in range(frame_count):
            ts = round(duration * (index + 1) / (frame_count + 1), 2)
            points.append(min(upper, max(0.0, ts)))
        result = []
        seen = set()
        for ts in points:
            if ts in seen:
                continue
            seen.add(ts)
            result.append(ts)
        return result or [0.0]

    async def _extract_visual_frames_from_message(self, media_source: Message, mime_type: str, filename: str, frame_count: int):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            raise RuntimeError(self.strings["media_ffmpeg_missing"])

        frame_count = max(1, min(int(frame_count or 1), 8))
        stem, _ = os.path.splitext(filename or "media")
        with tempfile.TemporaryDirectory(prefix="chatgptcodex_media_") as tempdir:
            ext = os.path.splitext(filename or "")[1] or self._guess_extension(mime_type)
            input_path = os.path.join(tempdir, f"input{ext}")
            saved = await self.client.download_media(media_source, file=input_path)
            if not saved or not os.path.exists(input_path):
                raise RuntimeError("media download failed")

            duration = await self._probe_media_duration(input_path)
            timestamps = self._build_media_frame_timestamps(duration, frame_count)
            frames = []
            for index, ts in enumerate(timestamps, start=1):
                output_path = os.path.join(tempdir, f"frame_{index}.jpg")
                args = [
                    ffmpeg,
                    "-loglevel",
                    "error",
                    "-y",
                ]
                if ts > 0:
                    args.extend(["-ss", f"{ts:.2f}"])
                args.extend([
                    "-i",
                    input_path,
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=min(1280\\,iw):-2",
                    "-q:v",
                    "3",
                    output_path,
                ])
                code, _, stderr = await self._run_media_tool(*args, timeout=120)
                if code != 0:
                    logger.warning("ChatGPTCodex: ffmpeg frame extraction failed: %s", stderr or code)
                    continue
                if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                    continue
                with open(output_path, "rb") as file_obj:
                    frame_data = file_obj.read()
                if not frame_data:
                    continue
                frames.append({
                    "mime_type": "image/jpeg",
                    "data": frame_data,
                    "filename": f"{stem or 'frame'}_{index}.jpg",
                })
            if not frames:
                raise RuntimeError("no frames extracted")
            return frames

    async def _transcribe_audio_from_message(self, media_source: Message, mime_type: str, filename: str, prompt: str = None):
        if not aiohttp:
            return None
        api_key = self.config["api_key"].strip()
        if not api_key:
            return None
        model = self.config["audio_transcribe_model"].strip() or "gpt-4o-mini-transcribe"
        headers = {"Authorization": f"Bearer {api_key}"}
        proxy = self._get_proxy()

        with tempfile.TemporaryDirectory(prefix="chatgptcodex_audio_") as tempdir:
            ext = os.path.splitext(filename or "")[1] or AUDIO_EXTENSIONS.get(mime_type) or self._guess_extension(mime_type)
            input_path = os.path.join(tempdir, f"audio{ext}")
            saved = await self.client.download_media(media_source, file=input_path)
            if not saved or not os.path.exists(input_path):
                raise RuntimeError("audio download failed")

            form = aiohttp.FormData()
            form.add_field("model", model)
            form.add_field("response_format", "json")
            if prompt:
                form.add_field("prompt", prompt[:1000])

            with open(input_path, "rb") as file_obj:
                form.add_field("file", file_obj, filename=filename or os.path.basename(input_path), content_type=mime_type or "application/octet-stream")
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        data=form,
                        proxy=proxy,
                        timeout=REQUEST_TIMEOUT,
                    ) as resp:
                        raw = await resp.text()
                        if resp.status != 200:
                            raise RuntimeError(self._parse_openai_error(resp.status, raw))
                        data = json.loads(raw)
            return (data.get("text") or "").strip()

    def _format_audio_metadata(self, filename: str, mime_type: str, audio_attr) -> str:
        details = []
        if filename:
            details.append(f"файл={filename}")
        if getattr(audio_attr, "performer", None):
            details.append(f"исполнитель={audio_attr.performer}")
        if getattr(audio_attr, "title", None):
            details.append(f"название={audio_attr.title}")
        if getattr(audio_attr, "duration", None):
            details.append(f"длительность={audio_attr.duration}с")
        if getattr(audio_attr, "voice", False):
            details.append("тип=voice")
        elif mime_type:
            details.append(f"MIME={mime_type}")
        return "[Аудио: " + ", ".join(details or ["без метаданных"]) + "]"

    def _format_sticker_metadata(
        self,
        alt_text: str,
        filename: str,
        mime_type: str,
        is_video_sticker: bool = False,
        is_animated_sticker: bool = False,
        video_attr=None,
    ) -> str:
        details = []
        if alt_text and alt_text != "?":
            details.append(f"emoji={alt_text}")
        if filename:
            details.append(f"файл={filename}")
        if getattr(video_attr, "duration", None):
            details.append(f"длительность={video_attr.duration}с")
        width = getattr(video_attr, "w", None)
        height = getattr(video_attr, "h", None)
        if width and height:
            details.append(f"размер={width}x{height}")
        if mime_type:
            details.append(f"MIME={mime_type}")
        if is_video_sticker:
            details.append("тип=video-sticker")
        elif is_animated_sticker:
            details.append("тип=animated-sticker")
        else:
            details.append("тип=static-sticker")
        return "[Стикер: " + ", ".join(details or ["без метаданных"]) + "]"

    def _format_video_metadata(self, filename: str, mime_type: str, video_attr, gif_like: bool = False) -> str:
        details = []
        if filename:
            details.append(f"файл={filename}")
        if getattr(video_attr, "duration", None):
            details.append(f"длительность={video_attr.duration}с")
        width = getattr(video_attr, "w", None)
        height = getattr(video_attr, "h", None)
        if width and height:
            details.append(f"размер={width}x{height}")
        if mime_type:
            details.append(f"MIME={mime_type}")
        label = "GIF/анимация" if gif_like else "Видео"
        return f"[{label}: " + ", ".join(details or ["без метаданных"]) + "]"

    def _get_default_codex_install_dir(self):
        return os.path.join(os.path.expanduser("~"), ".chatgptcodex", "codex-cli")

    def _get_managed_codex_install_dir(self):
        configured = self.config["codex_install_dir"].strip()
        return configured or self._get_default_codex_install_dir()

    def _get_managed_codex_binary(self):
        install_dir = self._get_managed_codex_install_dir()
        return os.path.join(install_dir, "bin", "codex")

    def _get_codex_binary(self):
        configured = self.config["codex_path"].strip()
        if configured:
            if "/" in configured:
                return configured if os.path.exists(configured) else None
            return shutil.which(configured)
        managed = self._get_managed_codex_binary()
        if os.path.exists(managed):
            return managed
        return shutil.which("codex")

    async def _install_codex_cli(self, status_msg=None):
        async with self._codex_install_lock:
            current = self._get_codex_binary()
            if current:
                return current

            npm_path = shutil.which("npm")
            if not npm_path:
                raise RuntimeError(self.strings["codex_npm_missing"])

            install_dir = self._get_managed_codex_install_dir()
            os.makedirs(install_dir, exist_ok=True)
            await self._update_status_message(status_msg, self.strings["codex_installing"])

            env = self._build_subprocess_env()
            env.setdefault("NPM_CONFIG_UPDATE_NOTIFIER", "false")
            env.setdefault("NPM_CONFIG_FUND", "false")
            env.setdefault("NPM_CONFIG_AUDIT", "false")

            proc = await asyncio.create_subprocess_exec(
                npm_path,
                "install",
                "-g",
                "--prefix",
                install_dir,
                "@openai/codex",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            except asyncio.CancelledError:
                proc.kill()
                with contextlib.suppress(Exception):
                    await proc.communicate()
                raise
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise RuntimeError("Автоустановка Codex CLI превысила таймаут (600 сек).")

            output = "\n".join(
                part for part in [
                    stdout.decode("utf-8", errors="ignore").strip(),
                    stderr.decode("utf-8", errors="ignore").strip(),
                ] if part
            ).strip()
            managed = self._get_managed_codex_binary()
            if proc.returncode != 0 or not os.path.exists(managed):
                raise RuntimeError(self.strings["codex_install_failed"].format(utils.escape_html((output or f"npm exit={proc.returncode}")[:900])))

            self.config["codex_path"] = managed
            await self._update_status_message(status_msg, self.strings["codex_install_done"].format(utils.escape_html(managed)))
            return managed

    async def _ensure_codex_available(self, status_msg=None):
        current = self._get_codex_binary()
        if current:
            if not self.config["codex_path"].strip() and current == self._get_managed_codex_binary():
                self.config["codex_path"] = current
            return current
        if not self.config["codex_auto_install"]:
            raise RuntimeError(self.strings["codex_not_found"])
        return await self._install_codex_cli(status_msg=status_msg)

    async def _get_codex_status_for_runtime(self):
        try:
            await self._ensure_codex_available()
        except Exception as e:
            return False, str(e)
        logged_in, status = await self._get_codex_login_status()
        if logged_in:
            return True, status
        if status == "codex not found":
            return False, self.strings["codex_not_found"]
        if status:
            return False, f"{self.strings['no_codex_login']}\n<code>{utils.escape_html(status[:300])}</code>"
        return False, self.strings["no_codex_login"]

    def _toml_string(self, value: str) -> str:
        escaped = (
            value.replace("\\", "\\\\")
            .replace("\b", "\\b")
            .replace("\t", "\\t")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace('"', '\\"')
        )
        return f'"{escaped}"'

    def _save_history_sync(self, gauto: bool = False):
        data, key = (self.gauto_conversations, DB_GAUTO_HISTORY_KEY) if gauto else (self.conversations, DB_HISTORY_KEY)
        self.db.set(self.strings["name"], key, data)

    def _load_history_from_db(self, key):
        data = self.db.get(self.strings["name"], key, {})
        return data if isinstance(data, dict) else {}

    def _migrate_runtime_lists_to_config(self):
        if not self.config["auto_reply_chats"].strip() and self.impersonation_chats:
            self.config["auto_reply_chats"] = "\n".join(str(chat_id) for chat_id in sorted(self.impersonation_chats, key=str))
        if not self.config["memory_disabled_chats"].strip() and self.memory_disabled_chats:
            self.config["memory_disabled_chats"] = "\n".join(sorted((str(chat_id) for chat_id in self.memory_disabled_chats), key=str))

    def _split_cfg_chat_values(self, raw: str):
        return [item.strip() for item in re.split(r"[\n,;]+", raw or "") if item.strip()]

    async def _resolve_cfg_chat_values(self, raw: str):
        resolved = set()
        for item in self._split_cfg_chat_values(raw):
            if item.lstrip("-").isdigit():
                resolved.add(int(item))
                continue
            try:
                entity = await self.client.get_entity(item)
                resolved.add(entity.id)
            except Exception:
                logger.warning("ChatGPTCodex: не удалось разрешить chat target из cfg: %s", item)
        return resolved

    async def _sync_runtime_config(self, force: bool = False):
        auto_raw = self.config["auto_reply_chats"]
        if force or self._cfg_sync_cache.get("auto_reply_chats") != auto_raw:
            self.impersonation_chats = await self._resolve_cfg_chat_values(auto_raw)
            self.db.set(self.strings["name"], DB_IMPERSONATION_KEY, list(sorted(self.impersonation_chats, key=str)))
            self._cfg_sync_cache["auto_reply_chats"] = auto_raw

        memory_raw = self.config["memory_disabled_chats"]
        if force or self._cfg_sync_cache.get("memory_disabled_chats") != memory_raw:
            resolved_memory = await self._resolve_cfg_chat_values(memory_raw)
            self.memory_disabled_chats = {str(chat_id) for chat_id in resolved_memory}
            self.db.set(self.strings["name"], DB_MEMORY_DISABLED_KEY, list(sorted(self.memory_disabled_chats)))
            self._cfg_sync_cache["memory_disabled_chats"] = memory_raw

    async def _update_chat_list_config(self, key: str, target, enabled: bool):
        values = []
        seen = set()
        for item in self._split_cfg_chat_values(self.config[key]):
            if item == str(target):
                continue
            if item not in seen:
                values.append(item)
                seen.add(item)
        if enabled and str(target) not in seen:
            values.append(str(target))
        self.config[key] = "\n".join(values)
        await self._sync_runtime_config(force=True)

    def _get_structured_history(self, cid, gauto: bool = False):
        data = self.gauto_conversations if gauto else self.conversations
        if str(cid) not in data:
            data[str(cid)] = []
        return data[str(cid)]

    def _update_history(self, chat_id: int, payload: dict, model_response: str, regeneration: bool = False, message: Message = None, gauto: bool = False):
        if not self._is_memory_enabled(str(chat_id)):
            return
        history = self._get_structured_history(chat_id, gauto)
        now = int(datetime.utcnow().timestamp())
        user_id = self.me.id
        user_name = get_display_name(self.me)
        message_id = getattr(message, "id", None)
        if message:
            try:
                peer_id = get_peer_id(message)
                if peer_id:
                    user_id = peer_id
            except Exception:
                if message.sender_id:
                    user_id = message.sender_id
            if getattr(message, "sender", None):
                user_name = get_display_name(message.sender)
        user_text = payload.get("text") or self.strings["media_reply_placeholder"]
        if regeneration and history:
            for idx in range(len(history) - 1, -1, -1):
                if history[idx].get("role") == "assistant":
                    history[idx].update({"content": model_response, "date": now})
                    break
        else:
            history.extend([
                {
                    "role": "user",
                    "type": "text",
                    "content": user_text,
                    "date": now,
                    "user_id": user_id,
                    "message_id": message_id,
                    "user_name": user_name,
                },
                {
                    "role": "assistant",
                    "type": "text",
                    "content": model_response,
                    "date": now,
                    "user_id": None,
                },
            ])
        limit = self.config["max_history_length"]
        if limit > 0 and len(history) > limit * 2:
            history = history[-(limit * 2):]
        target = self.gauto_conversations if gauto else self.conversations
        target[str(chat_id)] = history
        self._save_history_sync(gauto)

    def _clear_history(self, cid, gauto: bool = False):
        data = self.gauto_conversations if gauto else self.conversations
        if str(cid) in data:
            del data[str(cid)]
            self._save_history_sync(gauto)

    async def _get_recent_chat_text(self, cid, count=None, skip_last=False):
        limit = (count or self.config["impersonation_history_limit"]) + (1 if skip_last else 0)
        lines = []
        try:
            messages = await self.client.get_messages(cid, limit=limit)
            if skip_last and messages:
                messages = messages[1:]
            for item in messages:
                if not item:
                    continue
                if not (item.text or item.sticker or item.photo or item.file or item.media):
                    continue
                name = get_display_name(await item.get_sender()) or "Unknown"
                txt = item.text or ""
                if item.sticker:
                    alt = "?"
                    if hasattr(item.sticker, "attributes"):
                        alt = next((attr.alt for attr in item.sticker.attributes if isinstance(attr, DocumentAttributeSticker)), "?")
                    txt += f" [Стикер: {alt}]"
                elif item.photo:
                    txt += " [Фото]"
                elif item.file:
                    txt += " [Файл]"
                elif item.media and not txt:
                    txt += " [Медиа]"
                if txt.strip():
                    lines.append(f"{name}: {txt.strip()}")
        except Exception:
            pass
        return "\n".join(reversed(lines))

    def _find_preset(self, query):
        if not query:
            return None
        if str(query).isdigit():
            idx = int(query) - 1
            if 0 <= idx < len(self.prompt_presets):
                return self.prompt_presets[idx]
        for preset in self.prompt_presets:
            if preset["name"].lower() == str(query).lower():
                return preset
        return None

    def _markdown_to_html(self, text: str) -> str:
        def heading_replacer(match):
            level = len(match.group(1))
            title = match.group(2).strip()
            indent = "   " * (level - 1)
            return f"{indent}<b>{title}</b>"

        text = re.sub(r"^(#+)\s+(.*)", heading_replacer, text, flags=re.MULTILINE)
        text = re.sub(r"^([ \t]*)[-*+]\s+", lambda m: f"{m.group(1)}• ", text, flags=re.MULTILINE)
        if MarkdownIt:
            md = MarkdownIt("commonmark", {"html": True, "linkify": True})
            md.enable("strikethrough")
            md.disable("hr")
            md.disable("heading")
            md.disable("list")
            html_text = md.render(text)
        else:
            html_text = utils.escape_html(text).replace("\n", "<br>")
        def format_code(match):
            lang = utils.escape_html(match.group(1).strip())
            code = utils.escape_html(match.group(2).strip())
            return f'<pre><code class="language-{lang}">{code}</code></pre>' if lang else f"<pre><code>{code}</code></pre>"
        html_text = re.sub(r"```(.*?)\n([\s\S]+?)\n```", format_code, html_text)
        html_text = re.sub(r"<p>(<pre>[\s\S]*?</pre>)</p>", r"\1", html_text, flags=re.DOTALL)
        html_text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.IGNORECASE)
        html_text = html_text.replace("<p>", "").replace("</p>", "\n").strip()
        return html_text

    def _format_response_with_smart_separation(self, text: str, expandable: bool = True) -> str:
        parts = re.split(r"(<pre.*?>[\s\S]*?</pre>)", text, flags=re.DOTALL)
        result_parts = []
        blockquote_open = '<blockquote expandable="true">' if expandable else "<blockquote>"
        for idx, part in enumerate(parts):
            if not part or part.isspace():
                continue
            if idx % 2 == 1:
                result_parts.append(part.strip())
            else:
                stripped = part.strip()
                if stripped:
                    result_parts.append(f"{blockquote_open}{stripped}</blockquote>")
        return "\n".join(result_parts)

    def _get_reply_target_id(self, message: Message, fallback: int = None) -> int:
        if message is None:
            return fallback
        reply_to_id = getattr(message, "reply_to_msg_id", None)
        if reply_to_id:
            return reply_to_id
        reply_to = getattr(message, "reply_to", None)
        if reply_to is not None:
            nested_reply_id = getattr(reply_to, "reply_to_msg_id", None)
            if nested_reply_id:
                return nested_reply_id
        return getattr(message, "id", None) or fallback

    def _normalize_last_request_state(self, state, fallback_payload: dict = None):
        payload = fallback_payload or {}
        display_prompt = payload.get("display_prompt") or self.strings["media_reply_placeholder"]
        retry_count = 0
        if isinstance(state, dict):
            payload = state.get("payload") or payload
            display_prompt = state.get("display_prompt") or payload.get("display_prompt") or display_prompt
            retry_count = state.get("retry_count", 0) or 0
        elif isinstance(state, (tuple, list)):
            if len(state) > 0 and state[0]:
                payload = state[0]
            if len(state) > 1 and state[1]:
                display_prompt = state[1]
            if len(state) > 2:
                retry_count = state[2] or 0
        try:
            retry_count = max(0, int(retry_count))
        except Exception:
            retry_count = 0
        return payload, display_prompt, retry_count

    def _set_last_request_state(self, chat_id: int, base_message_id: int, payload: dict, display_prompt: str, retry_count: int = 0):
        self.last_requests[f"{chat_id}:{base_message_id}"] = {
            "payload": payload,
            "display_prompt": display_prompt,
            "retry_count": max(0, int(retry_count or 0)),
        }

    def _get_text_request_key(self, chat_id: int, base_message_id: int) -> str:
        return f"{chat_id}:{base_message_id}"

    def _get_last_request_retry_count(self, chat_id: int, base_message_id: int) -> int:
        _, _, retry_count = self._normalize_last_request_state(self.last_requests.get(f"{chat_id}:{base_message_id}"))
        return retry_count

    def _format_retry_button_text(self, text: str, retry_count: int) -> str:
        return f"{text} [{max(0, int(retry_count or 0))}]"

    def _should_autoretry_backend_error(self, error: Exception) -> bool:
        if isinstance(error, asyncio.TimeoutError):
            return True
        msg = str(error or "")
        if not msg:
            return True
        permanent_markers = (
            "OpenAI API key не настроен",
            "OpenAI API key недействителен",
            "Codex CLI не авторизован",
            "Команда <code>codex</code> не найдена",
            "Команда <code>npm</code> не найдена",
            "Библиотека aiohttp не установлена",
            "Rate limit / quota exceeded",
            "OpenAI API error 4",
        )
        return not any(marker in msg for marker in permanent_markers)

    def _get_inline_buttons(self, chat_id, base_message_id):
        retry_count = self._get_last_request_retry_count(chat_id, base_message_id)
        return [[
            {"text": self.strings["btn_clear"], "callback": self._clear_callback, "args": (chat_id,)},
            {"text": self._format_retry_button_text(self.strings["btn_regenerate"], retry_count), "callback": self._regenerate_callback, "args": (base_message_id, chat_id)},
        ]]

    def _get_loading_buttons(self, chat_id, base_message_id):
        return [[
            {"text": self.strings["btn_cancel_request"], "callback": self._cancel_request_callback, "args": (base_message_id, chat_id)},
        ]]

    def _get_error_buttons(self, chat_id, base_message_id):
        retry_count = self._get_last_request_retry_count(chat_id, base_message_id)
        return [[
            {"text": self._format_retry_button_text(self.strings["btn_retry_request"], retry_count), "callback": self._regenerate_callback, "args": (base_message_id, chat_id)},
            {"text": self.strings["btn_cancel_request"], "callback": self._cancel_request_callback, "args": (base_message_id, chat_id)},
        ]]

    async def _clear_callback(self, call: InlineCall, chat_id: int):
        self._clear_history(chat_id, gauto=False)
        await call.edit(self.strings["memory_cleared"], reply_markup=None)

    async def _regenerate_callback(self, call: InlineCall, mid, cid):
        key = self._get_text_request_key(cid, mid)
        if key not in self.last_requests:
            return await call.answer(self.strings["no_last_request"], show_alert=True)
        payload, _, _ = self._normalize_last_request_state(self.last_requests.get(key))
        await self._send_request(mid, payload, regeneration=True, call=call, chat_id_override=cid)

    async def _cancel_request_callback(self, call: InlineCall, mid, cid):
        key = self._get_text_request_key(cid, mid)
        active = self.active_text_requests.get(key)
        task = active.get("task") if active else None
        if task and not task.done():
            with contextlib.suppress(Exception):
                await call.answer(self.strings["request_cancelling"], show_alert=False)
            task.cancel()
            return
        self.last_requests.pop(key, None)
        await call.edit(self.strings["request_cancelled"], reply_markup=None)

    async def _close_callback(self, call: InlineCall, uid: str):
        await call.answer()
        self.pager_cache.pop(uid, None)
        try:
            await self.client.delete_messages(
                call.chat_id,
                self._extract_message_id(getattr(call, "message", None)) or self._extract_message_id(call),
            )
        except Exception:
            try:
                await call.edit("✔️ Сессия закрыта.", reply_markup=None)
            except Exception:
                pass

    async def _render_page(self, uid, page_num, entity):
        data = self.pager_cache.get(uid)
        if not data:
            if isinstance(entity, InlineCall):
                await entity.edit("⚠️ <b>Сессия истекла.</b>", reply_markup=None)
            return
        chunks = data["chunks"]
        total = data["total"]
        header = data.get("header", "")
        raw_text_chunk = chunks[page_num]
        safe_text = self._markdown_to_html(raw_text_chunk)
        formatted_body = self._format_response_with_smart_separation(safe_text, expandable=False)
        text_to_show = f"{header}\n{formatted_body}"
        nav_row = []
        if page_num > 0:
            nav_row.append({"text": "◀️", "data": f"chatgptcodex:pg:{uid}:{page_num - 1}"})
        nav_row.append({"text": f"{page_num + 1}/{total}", "data": "chatgptcodex:noop"})
        if page_num < total - 1:
            nav_row.append({"text": "▶️", "data": f"chatgptcodex:pg:{uid}:{page_num + 1}"})
        extra_row = [{"text": "❌ Закрыть", "callback": self._close_callback, "args": (uid,)}]
        if data.get("chat_id") and data.get("msg_id"):
            extra_row.append({"text": "🔄", "callback": self._regenerate_callback, "args": (data["msg_id"], data["chat_id"])})
        buttons = [nav_row, extra_row]
        if isinstance(entity, Message):
            form = await self.inline.form(text=text_to_show, message=entity, reply_markup=buttons)
            if form:
                await self._delete_message_entity(entity)
        elif isinstance(entity, InlineCall):
            await entity.edit(text=text_to_show, reply_markup=buttons)
        elif hasattr(entity, "edit"):
            try:
                await entity.edit(text=text_to_show, reply_markup=buttons)
            except Exception:
                pass

    def _paginate_text(self, text: str, limit: int) -> list:
        pages = []
        current_page_lines = []
        current_len = 0
        in_code_block = False
        current_code_lang = ""
        for line in text.split("\n"):
            line_len = len(line) + 1
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code_block:
                    in_code_block = False
                    current_code_lang = ""
                else:
                    in_code_block = True
                    current_code_lang = stripped.replace("```", "").strip()
            if current_len + line_len > limit:
                if current_page_lines:
                    if in_code_block:
                        current_page_lines.append("```")
                    pages.append("\n".join(current_page_lines))
                    current_page_lines = []
                    current_len = 0
                    if in_code_block:
                        header = f"```{current_code_lang}"
                        current_page_lines.append(header)
                        current_len += len(header) + 1
                if line_len > limit:
                    chunks = [line[i : i + limit] for i in range(0, len(line), limit)]
                    for chunk in chunks:
                        if current_len + len(chunk) > limit:
                            pages.append("\n".join(current_page_lines))
                            current_page_lines = [chunk]
                            current_len = len(chunk)
                        else:
                            current_page_lines.append(chunk)
                            current_len += len(chunk)
                    continue
            current_page_lines.append(line)
            current_len += line_len
        if current_page_lines:
            pages.append("\n".join(current_page_lines))
        return pages

    def _is_memory_enabled(self, chat_id: str) -> bool:
        return chat_id not in self.memory_disabled_chats