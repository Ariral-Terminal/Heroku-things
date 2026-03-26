"""
    📦 GitHubManager - Управление репозиториями через GitHub API
    
    Этот модуль позволяет загружать (обновлять) файлы в указанный репозиторий GitHub
    с помощью REST API и персонального токена.
    
"""

__version__ = (6, 3, 11)

# meta developer: @sxozuo forked by @desertedowl
# requires: aiohttp

import contextlib
import aiohttp
import base64
import io
import logging
import json
import mimetypes
import re
from typing import Optional, Any

from .. import loader, utils
from herokutl.types import Message

logger = logging.getLogger(__name__)

# URL для GitHub Content API: /repos/{owner}/{repo}/contents/{path}
GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"
# Регулярное выражение для поиска префикса диска Windows (e: , c: и т.д.)
WINDOWS_DRIVE_PREFIX_REGEX = re.compile(r"^[a-zA-Z]:")

@loader.tds
class GitHubManagerMod(loader.Module):
    """Управление файлами в репозиториях GitHub"""
    
    strings = {
        "name": "GitHubManager",
        "no_config": "❌ <b>Ошибка:</b> Пожалуйста, настройте <code>github_token</code> в конфиге модуля.",
        "no_repo_set": "❌ <b>Ошибка:</b> Репозиторий по умолчанию не установлен. Пожалуйста, укажите <code>repo_owner</code> и <code>repo_name</code> в конфиге модуля.",
        "no_reply": "❌ <b>Ошибка:</b> Ответьте на сообщение с файлом, который нужно загрузить.",
        "api_error": "❌ <b>GitHub API Ошибка (HTTP {status}):</b> {error}",
        "internal_error": "❌ <b>Внутренняя Ошибка:</b> {}",
        "no_filename": "❌ <b>Ошибка:</b> Не удалось определить имя файла из сообщения. Убедитесь, что это документ или медиафайл.",
        "downloading": "⏳ Скачиваю файл...",
        "uploading": "⏳ Загружаю файл в репозиторий <code>{owner}/{repo}</code> по пути <code>{path}</code>...",
        "success_create": "✅ <b>Файл создан:</b> <code>{path}</code>\nURL: {url}",
        "success_update": "✅ <b>Файл обновлен:</b> <code>{path}</code>\nURL: {url}",
        "files_list_header": "📄 <b>Файлы в репозитории <code>{owner}/{repo}</code></b>\nПуть: <code>{path}</code>\nСтраница <code>{page}</code>/<code>{total_pages}</code> · <code>{per_page}</code> файлов на страницу.",
        "files_list_empty": "ℹ️ <b>Файлы не найдены.</b>\nРепозиторий или выбранный путь не содержит файлов.",
        "files_list_truncated": "⚠️ <b>Показано только часть списка.</b>",
        "files_list_path_error": "❌ <b>Ошибка:</b> Не удалось получить список файлов для пути: <code>{path}</code>.",
        "files_list_bad_page": "❌ <b>Ошибка:</b> Такой страницы не существует.",
        "files_list_bad_per_page": "❌ <b>Ошибка:</b> <code>files_per_list</code> должен быть положительным числом.",
        "files_list_next": "След.",
        "files_list_prev": "Назад",
        "files_list_close": "❌ Закрыть",
        "repo_set_success": "✅ <b>Репозиторий установлен:</b> <code>{owner}/{repo}</code>",
        "repo_list_header": "📁 <b>Ваши репозитории на GitHub:</b>\nВыберите репозиторий, который нужно установить по умолчанию для загрузки (<code>.ghupload</code>).",
        "no_repos": "❌ Не удалось найти репозитории, доступные для токена, или список пуст.",
        "info_guide": (
            "🚀 <b>Гайд по модулю GitHubManager</b>\n\n"
            "Этот модуль позволяет загружать файлы в ваш репозиторий GitHub.\n\n"
            "### ⚙️ Настройка (Обязательно)\n"
            "1. Получите Персональный Токен (PAT) на GitHub с правами <code>repo</code>.\n"
            "2. **Установите в конфиге модуля следующие параметры:**\n"
            "    - <code>github_token</code>: Ваш PAT.\n"
            "    - <code>repo_owner</code>: Владелец целевого репозитория (например, <code>sxozuo</code>).\n"
            "    - <code>repo_name</code>: Имя целевого репозитория (например, <code>userbot_files</code>).\n\n"
            "### 💾 Использование\n"
            "Команда: <code>ghupload</code> [сообщение коммита]\n"
            "<b>Действие:</b> Ответьте этой командой на сообщение с файлом.\n"
            "    - Файл будет загружен или обновлен (если уже существует).\n"
            "    - <b>[сообщение коммита]</b> — опционально. Если не указано, используется имя файла.\n\n"
            "Команда: <code>ghfiles</code> [путь]\n"
            "<b>Действие:</b> Показывает список файлов в репозитории в виде копируемых <code>...</code> строк.\n"
            "    - <b>[путь]</b> — опционально. Можно указать папку или файл.\n"
            "    - Размер страницы задается в конфиге <code>files_per_list</code>.\n\n"
            "Команда: <code>ghget</code> &lt;путь&gt;\n"
            "<b>Действие:</b> Отправляет файл из репозитория документом вместе с подробной информацией о нем.\n\n"
            "<b>✨ Дополнительно:</b> <code>ghrepos</code> для интерактивного выбора репозитория."
        ),
        "update_start": "📂 <b>Выберите файл для обновления</b> в репозитории <code>{owner}/{repo}</code> по пути <code>{path}</code>:",
        "update_path": "📂 <b>Содержимое:</b> <code>{path}</code>",
        "update_prompt": "✅ <b>Файл выбран:</b> <code>{path}</code>\nТеперь ответьте на сообщение с новым файлом и введите сообщение коммита.",
        "update_prompt_saved_reply": "✅ <b>Файл выбран:</b> <code>{path}</code>\nТеперь отправьте <code>.ghupdate [коммит]</code>, чтобы обновить его уже сохраненным файлом.",
        "update_no_path": "❌ <b>Ошибка:</b> Не удалось получить список файлов для пути: <code>{path}</code>.",
        "update_auto_found": "✅ <b>Найден файл в репозитории:</b> <code>{path}</code>\nЗапускаю автоматическое обновление.",
        "update_auto_not_found": "ℹ️ <b>Файл <code>{filename}</code> не найден в репозитории.</b>\nОткрываю выбор файла вручную.",
        "update_auto_ambiguous": "⚠️ <b>Найдено несколько совпадений для <code>{filename}</code>:</b> <code>{count}</code>\nОткрываю выбор файла вручную.",
        "update_back": "⬅️ Назад",
        "update_cancel": "❌ Отмена",
        "user_id_error": "❌ Внутренняя ошибка: Не удалось определить ID пользователя, нажавшего кнопку. Проверьте логи.",
        "update_timeout": "❌ <b>Ошибка:</b> Режим обновления файла не активен. Сначала используйте <code>.ghupdatecmd</code> без аргументов и выберите файл.",
        "delete_start": "🗑 <b>Выберите файл для удаления</b> в репозитории <code>{owner}/{repo}</code>\nПуть: <code>{path}</code>",
        "delete_confirm": "⚠️ <b>Удалить файл?</b>\n<code>{path}</code>\nРепозиторий: <code>{owner}/{repo}</code>",
        "delete_btn_confirm": "✅ Удалить",
        "delete_btn_cancel": "❌ Отмена",
        "success_delete": "🗑 <b>Файл удалён:</b> <code>{path}</code>",
        "delete_not_found": "❌ <b>Файл не найден:</b> <code>{path}</code>",
        "get_no_path": "❌ <b>Ошибка:</b> Укажите путь к файлу в репозитории.",
        "get_fetching": "⏳ Получаю файл <code>{path}</code> из репозитория <code>{owner}/{repo}</code>...",
        "get_not_file": "❌ <b>Ошибка:</b> Путь <code>{path}</code> не указывает на файл в репозитории.",
        "get_send_failed": "❌ <b>Ошибка:</b> Не удалось отправить файл: {}",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "github_token",
                "",
                "Персональный токен GitHub (PAT) с правами 'repo'",
                validator=loader.validators.Hidden()
            ),
            loader.ConfigValue(
                "repo_owner",
                "",
                "Владелец репозитория (устанавливается только через конфиг)",
                validator=loader.validators.String()
            ),
            loader.ConfigValue(
                "repo_name",
                "",
                "Название репозитория (устанавливается только через конфиг)",
                validator=loader.validators.String()
            ),
            loader.ConfigValue(
                "files_per_list",
                25,
                "Максимум файлов на одну страницу в ghfiles",
                validator=loader.validators.String()
            ),
        )

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self.session: Optional[aiohttp.ClientSession] = None
        self.temp_update_path = {}
        # Pre-stored reply message when user calls .ghupdate as reply to a file
        self.temp_update_reply: dict = {}
    async def on_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _ensure_session(self):
        """Создает или пересоздает асинхронную сессию aiohttp с актуальным токеном."""
        if self.session and not self.session.closed:
            return
        
        token = self.config['github_token'].strip()
        if not token:
            self.session = None
            return
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Heroku-UserBot-GitHubManager",
        }
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        )

    # --- Утилиты ID ---
    def _find_id_recursively(self, obj: Any, visited: set) -> Optional[int]:
        """Рекурсивно ищет целое число, которое может быть ID пользователя."""
        
        if obj is None or obj in visited:
            return None
        visited.add(obj)
        
        try:
            if isinstance(obj, int) and obj > 0:
                return obj
            
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(key, str) and ('user' in key or 'from' in key or 'sender' in key or key == 'id'):
                        if isinstance(value, int) and value > 0:
                            return value
                    result = self._find_id_recursively(value, visited)
                    if result is not None:
                        return result

            if isinstance(obj, (list, tuple)):
                for item in obj:
                    result = self._find_id_recursively(item, visited)
                    if result is not None:
                        return result
            
            if hasattr(obj, '__dict__'):
                for key, value in vars(obj).items():
                    if 'id' in key:
                         if isinstance(value, int) and value > 0:
                            return value
                    
                    result = self._find_id_recursively(value, visited)
                    if result is not None:
                        return result
                        
        except Exception:
            pass
            
        return None

    def _get_user_id_from_call(self, call: Message) -> Optional[int]:
        """Пытается получить ID пользователя из объекта InlineCall, используя все известные атрибуты и глубокий поиск."""
        
        # 1. Прямые атрибуты (наиболее часто используемые)
        for attr in ['from_id', 'sender_id', 'user_id']:
            if hasattr(call, attr) and isinstance(getattr(call, attr), int) and getattr(call, attr) > 0:
                # ✅ ИСПРАВЛЕНИЕ ОШИБКИ: заменена ] на )
                return getattr(call, attr)
        
        # 2. Атрибут 'sender'
        if hasattr(call, 'sender') and hasattr(call.sender, 'id') and isinstance(call.sender.id, int) and call.sender.id > 0:
            return call.sender.id
            
        # 3. Аварийный глубокий рекурсивный поиск
        return self._find_id_recursively(call, set())

    def _extract_message_id(self, obj: Any) -> Optional[int]:
        """Извлекает ID сообщения из Message/InlineCall-подобных объектов."""

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

    async def _close_inline_message(self, call: Message, fallback_text: str = "✔️ Меню закрыто."):
        """Закрывает inline-сообщение через редактирование текущей формы."""

        with contextlib.suppress(Exception):
            await call.answer()

        with contextlib.suppress(Exception):
            await call.edit(text=fallback_text, reply_markup=None)
            return

        with contextlib.suppress(Exception):
            await call.edit(fallback_text, reply_markup=None)
            return

        with contextlib.suppress(Exception):
            msg_id = self._extract_message_id(getattr(call, "message", None)) or self._extract_message_id(call)
            chat_id = getattr(call, "chat_id", None)
            if self._client and chat_id and msg_id:
                await self._client.delete_messages(chat_id, msg_id)
                return

    async def _answer_or_edit(self, entity: Message, text: str, reply_markup=None):
        """Редактирует текущее сообщение, если возможно, иначе отправляет новый ответ."""

        if hasattr(entity, "edit"):
            with contextlib.suppress(Exception):
                await entity.edit(text=text, reply_markup=reply_markup)
                return

            with contextlib.suppress(Exception):
                await entity.edit(text, reply_markup=reply_markup)
                return

        await utils.answer(entity, text, reply_markup=reply_markup)

    # --- Конец Утилит ID ---
    
    @loader.command(
        ru_doc="Показывает мини-гайд по настройке и использованию модуля.",
        en_doc="Shows a mini-guide on how to set up and use the module."
    )
    async def ghinfocmd(self, message: Message):
        """Показывает мини-гайд по модулю GitHubManager."""
        await utils.answer(message, self.strings("info_guide"))
        

    @loader.command(
        ru_doc="Выводит список ваших репозиториев в виде Inline-кнопок для интерактивного выбора.",
        en_doc="Shows a list of your repositories as Inline buttons for interactive selection."
    )
    async def ghreposcmd(self, message: Message):
        """Выводит список репозиториев пользователя."""
        if not self.config["github_token"]:
            await utils.answer(message, self.strings("no_config"))
            return

        await self._ensure_session()

        if not self.session:
            await utils.answer(message, self.strings("no_config"))
            return

        status_message = await utils.answer(message, "⏳ Получаю список репозиториев...")
        
        url = "https://api.github.com/user/repos?type=all&per_page=50"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    repos_data = await response.json()
                else:
                    error_json = await response.json()
                    error_message = error_json.get("message", "Неизвестная ошибка")
                    await utils.answer(status_message, self.strings("api_error").format(
                        status=response.status,
                        error=utils.escape_html(error_message)
                    ))
                    return
        except Exception as e:
            await utils.answer(status_message, self.strings("internal_error").format(f"Запрос API: {e}"))
            logger.exception(e)
            return

        if not repos_data:
            await utils.answer(status_message, self.strings("no_repos"))
            return
            
        buttons = []
        for repo in repos_data:
            owner = repo.get("owner", {}).get("login")
            repo_name = repo.get("name")
            full_name = f"{owner}/{repo_name}"
            
            buttons.append([
                {
                    "text": full_name,
                    "data": f"ghm_set_{owner}|{repo_name}",
                }
            ])

        buttons.append([
            {"text": "❌ Закрыть", "data": "ghm_close"}
        ])

        await utils.answer(status_message, self.strings("repo_list_header"), reply_markup=buttons)


    @loader.command(
        ru_doc="[сообщение коммита] - Загружает файл из ответа. Использует оригинальное имя файла. Сообщение коммита опционально.",
        en_doc="[commit message] - Uploads file from reply. Uses original file name. Commit message is optional."
    )
    async def ghuploadcmd(self, message: Message):
        """Загрузка нового файла в GitHub repository."""
        
        commit_message = utils.get_args_raw(message).strip()
        
        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings("no_reply"))
            return
        
        file_path = self._get_file_name(reply)

        if not file_path:
            await utils.answer(message, self.strings("no_filename"))
            return

        if not commit_message:
            commit_message = f"File upload: {utils.escape_html(file_path)}"
        
        await self._process_upload(message, reply, file_path, commit_message, is_update=False)


    @loader.command(
        ru_doc="<путь_к_файлу> [сообщение коммита] - Обновляет файл в репозитории по указанному пути, используя файл из ответа. Если путь не указан, открывает интерактивный выбор файла. Если команда вызвана реплаем, использует путь из режима ожидания.",
        en_doc="<file_path> [commit message] - Updates a file at the specified path, using the file from the reply. If no path is specified, opens an interactive file selector. If called as a reply, uses the path from the waiting mode."
    )
    async def ghupdatecmd(self, message: Message):
        """Интерактивное или прямое обновление существующего файла в GitHub repository."""

        user_id = message.sender_id
        args = utils.get_args(message)
        reply = await message.get_reply_message()
        stored_reply = self.temp_update_reply.get(user_id)

        if not self.config["github_token"]:
            await utils.answer(message, self.strings("no_config"))
            return
        
        owner = self.config["repo_owner"]
        repo = self.config["repo_name"]

        if not owner or not repo:
            await utils.answer(message, self.strings("no_repo_set"))
            return
        
        # --- ЛОГИКА РЕЖИМА ОЖИДАНИЯ (интерактивный режим) ---
        if reply and reply.media and user_id in self.temp_update_path:
            # 1. Мы в режиме ожидания (пользователь выбрал файл, и теперь отвечает новым файлом)
            repo_path = self.temp_update_path[user_id]
            
            commit_message = utils.get_args_raw(message).strip()
            
            # Сообщение коммита по умолчанию
            if not commit_message:
                commit_message = f"File update: {utils.escape_html(repo_path)}"

            try:
                # Выполняем обновление
                await self._process_upload(message, reply, repo_path, commit_message, is_update=True)
            finally:
                # ГАРАНТИРОВАННЫЙ СБРОС СЕССИИ
                self.temp_update_path.pop(user_id, None)
                self.temp_update_reply.pop(user_id, None)
            return

        if not reply and stored_reply and user_id in self.temp_update_path:
            repo_path = self.temp_update_path[user_id]
            commit_message = utils.get_args_raw(message).strip()

            if not commit_message:
                commit_message = f"File update: {utils.escape_html(repo_path)}"

            try:
                await self._process_upload(message, stored_reply, repo_path, commit_message, is_update=True)
            finally:
                self.temp_update_path.pop(user_id, None)
                self.temp_update_reply.pop(user_id, None)
            return
            
        # --- ЛОГИКА ПРЯМОГО ВЫЗОВА / ИНТЕРАКТИВНОГО ЗАПУСКА ---
        
        if args:
            # 2. Прямое обновление: .ghupdate path/to/file commit message (как раньше)
            repo_path = args[0]
            commit_message = " ".join(args[1:])
            
            if not reply or not reply.media:
                await utils.answer(message, self.strings("no_reply"))
                return

            if not commit_message:
                default_name = self._get_file_name(reply) or "новый файл"
                commit_message = f"File update: {utils.escape_html(repo_path)} (from {default_name})"

            try:
                await self._process_upload(message, reply, repo_path, commit_message, is_update=True)
            finally:
                self.temp_update_reply.pop(user_id, None)
        
        elif reply and reply.media:
            # 3. Reply to a file: try to auto-detect the repository path by file name first.
            reply_file_name = self._get_file_name(reply)
            if reply_file_name:
                matches = await self._find_repo_matches_for_file(owner, repo, reply_file_name)
                if len(matches) == 1:
                    repo_path = matches[0]
                    commit_message = f"File update: {utils.escape_html(repo_path)}"
                    status_message = await utils.answer(
                        message,
                        self.strings("update_auto_found").format(path=utils.escape_html(repo_path)),
                    )
                    await self._process_upload(status_message, reply, repo_path, commit_message, is_update=True)
                    return

                if len(matches) > 1:
                    status_message = await utils.answer(
                        message,
                        self.strings("update_auto_ambiguous").format(
                            filename=utils.escape_html(reply_file_name),
                            count=len(matches),
                        ),
                    )
                else:
                    status_message = await utils.answer(
                        message,
                        self.strings("update_auto_not_found").format(
                            filename=utils.escape_html(reply_file_name),
                        ),
                    )
            else:
                status_message = await utils.answer(message, "⏳ Загружаю содержимое репозитория...")

            self.temp_update_reply[user_id] = reply
            await self._send_file_list(status_message, owner, repo, "", original_message=message, mode="update")
            
        else:
            # 4. Интерактивное обновление: .ghupdate (открываем браузер файлов)
            status_message = await utils.answer(message, "⏳ Загружаю содержимое репозитория...")
            
            await self._send_file_list(status_message, owner, repo, "", original_message=message, mode="update")

    @loader.command(
        ru_doc="[путь] - Показывает файлы репозитория в виде копируемых строк. Лимит страниц задается в конфиге.",
        en_doc="[path] - Shows repository files as copyable <code>...</code> lines. Page size is controlled by config."
    )
    async def ghfilescmd(self, message: Message):
        """Показывает список файлов репозитория."""

        if not self.config["github_token"]:
            await utils.answer(message, self.strings("no_config"))
            return

        owner = self.config["repo_owner"]
        repo = self.config["repo_name"]

        if not owner or not repo:
            await utils.answer(message, self.strings("no_repo_set"))
            return

        path = utils.get_args_raw(message).strip()
        status_message = await utils.answer(message, "⏳ Получаю список файлов...")
        await self._send_repo_file_list(status_message, owner, repo, path, page=1)

    @loader.command(
        ru_doc="<путь> - Получает файл из репозитория, отправляет его документом и показывает подробную информацию.",
        en_doc="<path> - Fetches a repository file, sends it as a document, and shows detailed information."
    )
    async def ghgetcmd(self, message: Message):
        """Отправляет файл из репозитория вместе с подробной информацией."""
        if not self.config["github_token"]:
            return await utils.answer(message, self.strings("no_config"))

        owner = self.config["repo_owner"]
        repo = self.config["repo_name"]
        if not owner or not repo:
            return await utils.answer(message, self.strings("no_repo_set"))

        path = self._normalize_repo_path(utils.get_args_raw(message))
        if not path:
            return await utils.answer(message, self.strings("get_no_path"))

        status_message = await utils.answer(
            message,
            self.strings("get_fetching").format(
                owner=utils.escape_html(owner),
                repo=utils.escape_html(repo),
                path=utils.escape_html(path),
            ),
        )
        await self._send_repo_file(status_message, owner, repo, path)

    @loader.command(
        ru_doc="<путь> [коммит] или без аргументов — удалить файл из репозитория.",
        en_doc="<path> [commit] or no args - delete a file from the repository."
    )
    async def ghdelcmd(self, message: Message):
        """Удаление файла из GitHub репозитория."""
        if not self.config["github_token"]:
            return await utils.answer(message, self.strings("no_config"))

        owner = self.config["repo_owner"]
        repo = self.config["repo_name"]
        if not owner or not repo:
            return await utils.answer(message, self.strings("no_repo_set"))

        args = utils.get_args(message)
        if args:
            path = args[0]
            commit_message = " ".join(args[1:]) or f"Delete {path}"
            await self._delete_file(message, owner, repo, path, commit_message)
            return

        status_message = await utils.answer(message, "⏳ Загружаю содержимое репозитория...")
        await self._send_file_list(status_message, owner, repo, "", original_message=message, mode="delete")

    def _normalize_repo_path(self, path: str) -> str:
        """Нормализует путь для GitHub API."""

        processed_path = WINDOWS_DRIVE_PREFIX_REGEX.sub("", path.strip())
        return processed_path.lstrip("/")

    async def _read_github_error(self, response: aiohttp.ClientResponse) -> str:
        """Безопасно достает сообщение об ошибке из ответа GitHub API."""

        with contextlib.suppress(Exception):
            error_json = await response.json()
            if isinstance(error_json, dict):
                message = error_json.get("message")
                if message:
                    return str(message)
                if error_json:
                    return json.dumps(error_json, ensure_ascii=False)

        with contextlib.suppress(Exception):
            text = await response.text()
            if text:
                return text

        return "Неизвестная ошибка"

    def _get_browser_mode_config(self, mode: str) -> tuple[str, str]:
        """Возвращает префикс callback-данных и заголовок для браузера файлов."""

        if mode == "delete":
            return "ghmd", "delete"
        return "ghmu", "update"

    async def _send_file_list(self, message: Message, owner: str, repo: str, path: str, original_message: Message, mode: str = "update"):
        """Получает и отображает список файлов/папок для указанного пути."""

        del original_message

        await self._ensure_session()
        if not self.session:
            await utils.answer(message, self.strings("no_config"))
            return

        normalized_path = self._normalize_repo_path(path)
        url = GITHUB_API_URL.format(owner=owner, repo=repo, path=normalized_path)
        prefix, header_mode = self._get_browser_mode_config(mode)

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    contents = await response.json()
                elif response.status == 404:
                    await utils.answer(message, self.strings("update_no_path").format(path=utils.escape_html(normalized_path or "/")))
                    return
                else:
                    error_message = await self._read_github_error(response)
                    await utils.answer(message, self.strings("api_error").format(
                        status=response.status,
                        error=utils.escape_html(error_message),
                    ))
                    return

            if isinstance(contents, dict):
                contents = [contents]

            buttons = []
            files = []
            dirs = []

            for item in contents:
                item_type = item.get("type")
                name = item.get("name")
                item_path = item.get("path")
                if not name or not item_path:
                    continue
                if item_type == "dir":
                    dirs.append((name, item_path))
                elif item_type == "file":
                    files.append((name, item_path))

            for name, item_path in sorted(dirs, key=lambda x: x[0].lower()):
                buttons.append([{
                    "text": f"📁 {name}",
                    "data": f"{prefix}_dir:{item_path}",
                }])

            for name, item_path in sorted(files, key=lambda x: x[0].lower()):
                buttons.append([{
                    "text": f"📄 {name}",
                    "data": f"{prefix}_file:{item_path}",
                }])

            if normalized_path:
                parent_path = "/".join(normalized_path.split("/")[:-1])
                buttons.append([{
                    "text": self.strings("update_back"),
                    "data": f"{prefix}_dir:{parent_path}",
                }])

            buttons.append([{
                "text": self.strings("update_cancel"),
                "data": f"{prefix}_close",
            }])

            if header_mode == "delete":
                text_header = self.strings("delete_start").format(
                    owner=utils.escape_html(owner),
                    repo=utils.escape_html(repo),
                    path=utils.escape_html(normalized_path or "/"),
                )
            else:
                text_header = self.strings("update_start").format(
                    owner=utils.escape_html(owner),
                    repo=utils.escape_html(repo),
                    path=utils.escape_html(normalized_path or "/"),
                ) if not normalized_path else self.strings("update_path").format(
                    path=utils.escape_html(normalized_path)
                )

            await utils.answer(message, text_header, reply_markup=buttons)

        except Exception as e:
            await utils.answer(message, self.strings("internal_error").format(str(e)))
            logger.exception(e)

    def _get_files_per_list(self) -> int:
        """Читает размер страницы из конфига и страхует от невалидных значений."""

        raw_value = self.config.get("files_per_list", 25)
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return 25
        return value if value > 0 else 0

    async def _collect_repo_files(self, owner: str, repo: str, path: str) -> Optional[list[str]]:
        """Рекурсивно собирает все файлы из репозитория или подпути."""

        await self._ensure_session()
        if not self.session:
            return []

        normalized_path = self._normalize_repo_path(path)
        collected_files = []
        queue = [normalized_path]
        visited_dirs = set()

        while queue:
            current_path = queue.pop(0)
            if current_path in visited_dirs:
                continue
            visited_dirs.add(current_path)

            url = GITHUB_API_URL.format(owner=owner, repo=repo, path=current_path)

            async with self.session.get(url) as response:
                if response.status == 200:
                    payload = await response.json()
                elif response.status == 404:
                    return None
                else:
                    error_message = await self._read_github_error(response)
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=error_message,
                    )

            if isinstance(payload, dict):
                if payload.get("type") == "file":
                    collected_files.append(payload.get("path", current_path))
                continue

            for item in payload:
                item_type = item.get("type")
                item_path = item.get("path")
                if item_type == "dir" and item_path:
                    if item_path not in visited_dirs:
                        queue.append(item_path)
                elif item_type == "file" and item_path:
                    collected_files.append(item_path)

        collected_files.sort(key=str.lower)
        return collected_files

    async def _find_repo_matches_for_file(self, owner: str, repo: str, file_name: str) -> list[str]:
        """Ищет пути в репозитории, совпадающие с именем файла из реплая."""

        normalized_name = self._normalize_repo_path(file_name)
        if not normalized_name:
            return []

        collected_files = await self._collect_repo_files(owner, repo, "")
        if not collected_files:
            return []

        normalized_lower = normalized_name.lower()
        exact_matches = [path for path in collected_files if path.lower() == normalized_lower]
        if exact_matches:
            return exact_matches

        basename = normalized_lower.rsplit("/", 1)[-1]
        return [
            path
            for path in collected_files
            if path.rsplit("/", 1)[-1].lower() == basename
        ]

    async def _send_repo_file_list(self, message: Message, owner: str, repo: str, path: str, page: int = 1):
        """Показывает список файлов в репозитории с пагинацией."""

        await self._ensure_session()
        if not self.session:
            await self._answer_or_edit(message, self.strings("no_config"))
            return

        per_page = self._get_files_per_list()
        if per_page <= 0:
            await self._answer_or_edit(message, self.strings("files_list_bad_per_page"))
            return

        try:
            normalized_path = self._normalize_repo_path(path)
            collected_files = await self._collect_repo_files(owner, repo, normalized_path)
            if collected_files is None:
                await self._answer_or_edit(
                    message,
                    self.strings("files_list_path_error").format(path=utils.escape_html(normalized_path or "/")),
                )
                return

            if not collected_files:
                await self._answer_or_edit(message, self.strings("files_list_empty"))
                return

            total_pages = max(1, (len(collected_files) + per_page - 1) // per_page)
            if page < 1 or page > total_pages:
                await self._answer_or_edit(message, self.strings("files_list_bad_page"))
                return

            start = (page - 1) * per_page
            end = start + per_page
            page_files = collected_files[start:end]
            truncated = total_pages > page

            lines = [
                self.strings("files_list_header").format(
                    owner=utils.escape_html(owner),
                    repo=utils.escape_html(repo),
                    path=utils.escape_html(normalized_path or "/"),
                    page=page,
                    total_pages=total_pages,
                    per_page=per_page,
                )
            ]

            for index, file_path in enumerate(page_files, start=start + 1):
                lines.append(f"{index}. <code>{utils.escape_html(file_path)}</code>")

            if truncated:
                lines.append(self.strings("files_list_truncated"))

            buttons = []
            nav_buttons = []
            if page > 1:
                nav_buttons.append({
                    "text": self.strings("files_list_prev"),
                    "data": f"ghfl_page:{page - 1}|{normalized_path}",
                })
            if page < total_pages:
                nav_buttons.append({
                    "text": self.strings("files_list_next"),
                    "data": f"ghfl_page:{page + 1}|{normalized_path}",
                })
            if nav_buttons:
                buttons.append(nav_buttons)
            buttons.append([{
                "text": self.strings("files_list_close"),
                "data": "ghfl_close",
            }])

            await self._answer_or_edit(message, "\n".join(lines), reply_markup=buttons)

        except Exception as e:
            await self._answer_or_edit(message, self.strings("internal_error").format(str(e)))
            logger.exception(e)

    @loader.callback_handler(ru_doc="Обрабатывает нажатия кнопок списка репозиториев.")
    async def ghm_callback_handler(self, call: Message):
        """Обрабатывает колбэки от Inline-кнопок, созданных командой ghreposcmd."""

        data = call.data

        if data == "ghm_close":
            user_id = self._get_user_id_from_call(call)
            if user_id:
                self.temp_update_path.pop(user_id, None)
                self.temp_update_reply.pop(user_id, None)

            await self._close_inline_message(call)
            return

        if not data.startswith("ghm_set_"):
            return

        parts = data[8:].split("|")
        if len(parts) != 2:
            await call.answer("Ошибка данных колбэка", show_alert=True)
            return

        owner, repo_name = parts
        self.config["repo_owner"] = owner
        self.config["repo_name"] = repo_name

        await call.edit(
            self.strings("repo_set_success").format(
                owner=utils.escape_html(owner),
                repo=utils.escape_html(repo_name),
            )
        )
        await call.answer(f"Репозиторий установлен: {owner}/{repo_name}", show_alert=True)

    @loader.callback_handler(ru_doc="Обрабатывает нажатия кнопок интерактивного обновления файла.")
    async def ghmu_callback_handler(self, call: Message):
        """Обрабатывает колбэки для навигации по файлам при обновлении."""

        data = call.data

        if data == "ghmu_close":
            user_id = self._get_user_id_from_call(call)
            if user_id:
                self.temp_update_path.pop(user_id, None)
                self.temp_update_reply.pop(user_id, None)

            await self._close_inline_message(call)
            return

        if data.startswith("ghmu_dir:"):
            owner = self.config["repo_owner"]
            repo = self.config["repo_name"]
            path = data[len("ghmu_dir:"):]
            await self._send_file_list(call, owner, repo, path, original_message=call, mode="update")
            return

        if not data.startswith("ghmu_file:"):
            return

        user_id = self._get_user_id_from_call(call)
        if user_id is None:
            logger.error(
                "Критическая ошибка в ghmu_callback_handler: не найден ID пользователя. Vars(call): %s",
                vars(call),
            )
            await call.answer(self.strings("user_id_error"), show_alert=True)
            return

        path = data[len("ghmu_file:"):]
        self.temp_update_path[user_id] = path

        prompt_key = "update_prompt_saved_reply" if user_id in self.temp_update_reply else "update_prompt"
        await call.edit(
            self.strings(prompt_key).format(path=utils.escape_html(path)),
            reply_markup=[[{
                "text": self.strings("update_cancel"),
                "data": "ghmu_close",
            }]]
        )

        alert_text = (
            f"Выбран файл: {path}. Теперь отправьте .ghupdate [коммит] для обновления сохраненным файлом."
            if user_id in self.temp_update_reply
            else f"Выбран файл: {path}. Теперь ответьте на это сообщение новым файлом и командой .ghupdate [коммит]."
        )
        await call.answer(alert_text, show_alert=True)

    @loader.callback_handler(ru_doc="Обрабатывает нажатия кнопок интерактивного удаления файла.")
    async def ghmd_callback_handler(self, call: Message):
        """Обрабатывает колбэки для удаления файлов."""

        data = call.data

        if data == "ghmd_close":
            await self._close_inline_message(call)
            return

        owner = self.config["repo_owner"]
        repo = self.config["repo_name"]

        if data.startswith("ghmd_dir:"):
            path = data[len("ghmd_dir:"):]
            await self._send_file_list(call, owner, repo, path, original_message=call, mode="delete")
            return

        if data.startswith("ghmd_file:"):
            path = data[len("ghmd_file:"):]
            parent_path = "/".join(path.split("/")[:-1])
            reply_markup = [[{
                "text": self.strings("delete_btn_confirm"),
                "data": f"ghmd_confirm:{path}",
            }]]
            if path:
                reply_markup.append([{
                    "text": self.strings("update_back"),
                    "data": f"ghmd_dir:{parent_path}",
                }])
            reply_markup.append([{
                "text": self.strings("delete_btn_cancel"),
                "data": "ghmd_close",
            }])

            await call.edit(
                self.strings("delete_confirm").format(
                    path=utils.escape_html(path),
                    owner=utils.escape_html(owner),
                    repo=utils.escape_html(repo),
                ),
                reply_markup=reply_markup,
            )
            return

        if data.startswith("ghmd_confirm:"):
            path = data[len("ghmd_confirm:"):]
            await self._delete_file(call, owner, repo, path, f"Delete {path}")

    @loader.callback_handler(ru_doc="Обрабатывает пагинацию списка файлов репозитория.")
    async def ghfl_callback_handler(self, call: Message):
        """Обрабатывает кнопки пагинации для .ghfiles."""

        data = call.data
        if data == "ghfl_close":
            await self._close_inline_message(call)
            return

        if not data.startswith("ghfl_page:"):
            return

        try:
            page_part = data[len("ghfl_page:"):]
            page_str, path = page_part.split("|", 1)
            page = int(page_str)
        except Exception:
            await call.answer(self.strings("files_list_bad_page"), show_alert=True)
            return

        owner = self.config["repo_owner"]
        repo = self.config["repo_name"]
        if not owner or not repo:
            await call.answer(self.strings("no_repo_set"), show_alert=True)
            return

        await self._send_repo_file_list(call, owner, repo, path, page=page)

    def _format_bytes(self, size: int) -> str:
        """Возвращает человекочитаемый размер файла."""

        units = ("B", "KB", "MB", "GB", "TB")
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.2f} {unit}"
            value /= 1024
        return f"{int(size)} B"

    def _truncate(self, value: str, limit: int = 140) -> str:
        """Обрезает строку до безопасной длины для подписи."""

        if len(value) <= limit:
            return value
        return value[: limit - 3] + "..."

    def _build_file_info_caption(self, owner: str, repo: str, file_data: dict, last_commit: Optional[dict]) -> str:
        """Формирует подпись с подробной информацией о файле."""

        name = file_data.get("name") or "unknown"
        path = file_data.get("path") or name
        size = file_data.get("size")
        if not isinstance(size, int):
            size = 0

        mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        lines = [
            "📄 <b>Файл из GitHub</b>",
            f"Репозиторий: <code>{utils.escape_html(owner)}/{utils.escape_html(repo)}</code>",
            f"Имя: <code>{utils.escape_html(name)}</code>",
            f"Путь: <code>{utils.escape_html(path)}</code>",
            f"Размер: <code>{self._format_bytes(size)}</code> (<code>{size}</code> B)",
            f"MIME: <code>{utils.escape_html(mime_type)}</code>",
        ]

        sha = file_data.get("sha")
        if sha:
            lines.append(f"SHA: <code>{utils.escape_html(sha)}</code>")

        html_url = file_data.get("html_url")
        if html_url:
            lines.append(f"GitHub: {utils.escape_html(html_url)}")

        download_url = file_data.get("download_url")
        if download_url:
            lines.append(f"Download: {utils.escape_html(download_url)}")

        if last_commit:
            commit_sha = last_commit.get("sha")
            author = last_commit.get("author")
            date = last_commit.get("date")
            message = last_commit.get("message")
            if commit_sha:
                lines.append(f"Последний коммит: <code>{utils.escape_html(commit_sha)}</code>")
            if author:
                lines.append(f"Автор: <code>{utils.escape_html(author)}</code>")
            if date:
                lines.append(f"Дата: <code>{utils.escape_html(date)}</code>")
            if message:
                lines.append(f"Сообщение: <code>{utils.escape_html(self._truncate(message))}</code>")

        return "\n".join(lines)

    async def _get_last_commit_for_path(self, owner: str, repo: str, path: str) -> Optional[dict]:
        """Возвращает информацию о последнем коммите, затронувшем файл."""

        await self._ensure_session()
        if not self.session:
            return None

        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        try:
            async with self.session.get(url, params={"path": path, "per_page": 1}) as response:
                if response.status != 200:
                    return None
                payload = await response.json()
        except Exception:
            return None

        if not payload:
            return None

        commit = payload[0]
        commit_info = commit.get("commit", {})
        author_info = commit_info.get("author", {})
        return {
            "sha": (commit.get("sha") or "")[:7],
            "author": author_info.get("name") or commit.get("author", {}).get("login"),
            "date": author_info.get("date"),
            "message": commit_info.get("message"),
        }

    async def _download_repo_file_bytes(self, url: str, file_data: dict) -> bytes:
        """Скачивает байты файла через GitHub API."""

        async with self.session.get(url, headers={"Accept": "application/vnd.github.raw"}) as response:
            if response.status == 200:
                return await response.read()

        content = file_data.get("content")
        if content and file_data.get("encoding") == "base64":
            return base64.b64decode(content)

        raise ValueError("GitHub API did not return file bytes")

    async def _send_repo_file(self, message: Message, owner: str, repo: str, path: str):
        """Получает файл из GitHub и отправляет его документом с подробной информацией."""

        await self._ensure_session()
        if not self.session:
            await utils.answer(message, self.strings("no_config"))
            return

        normalized_path = self._normalize_repo_path(path)
        url = GITHUB_API_URL.format(owner=owner, repo=repo, path=normalized_path)

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    file_data = await response.json()
                elif response.status == 404:
                    await utils.answer(message, self.strings("delete_not_found").format(path=utils.escape_html(normalized_path)))
                    return
                else:
                    error_message = await self._read_github_error(response)
                    await utils.answer(message, self.strings("api_error").format(
                        status=response.status,
                        error=utils.escape_html(error_message),
                    ))
                    return

            if not isinstance(file_data, dict) or file_data.get("type") != "file":
                await utils.answer(message, self.strings("get_not_file").format(path=utils.escape_html(normalized_path)))
                return

            file_bytes = await self._download_repo_file_bytes(url, file_data)
            last_commit = await self._get_last_commit_for_path(owner, repo, normalized_path)

            file_buffer = io.BytesIO(file_bytes)
            file_buffer.name = file_data.get("name") or normalized_path.rsplit("/", 1)[-1] or "github_file"

            await message.respond(
                self._build_file_info_caption(owner, repo, file_data, last_commit),
                file=file_buffer,
                force_document=True,
            )

            with contextlib.suppress(Exception):
                await message.delete()

        except aiohttp.ClientResponseError as e:
            await utils.answer(
                message,
                self.strings("api_error").format(
                    status=e.status,
                    error=utils.escape_html(e.message),
                ),
            )
            logger.exception(e)
        except Exception as e:
            await utils.answer(message, self.strings("get_send_failed").format(utils.escape_html(str(e))))
            logger.exception(e)

    async def _delete_file(self, message: Message, owner: str, repo: str, path: str, commit_message: str):
        """Удаляет файл через GitHub API."""

        await self._ensure_session()
        if not self.session:
            await utils.answer(message, self.strings("no_config"))
            return

        normalized_path = self._normalize_repo_path(path)
        url = GITHUB_API_URL.format(owner=owner, repo=repo, path=normalized_path)
        status_message = await utils.answer(
            message,
            f"⏳ Удаляю файл <code>{utils.escape_html(normalized_path)}</code> из репозитория <code>{utils.escape_html(owner)}/{utils.escape_html(repo)}</code>...",
        )

        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    file_data = await response.json()
                elif response.status == 404:
                    await utils.answer(status_message, self.strings("delete_not_found").format(path=utils.escape_html(normalized_path)))
                    return
                else:
                    error_message = await self._read_github_error(response)
                    await utils.answer(status_message, self.strings("api_error").format(
                        status=response.status,
                        error=utils.escape_html(error_message),
                    ))
                    return

            sha = file_data.get("sha")
            if not sha:
                await utils.answer(status_message, self.strings("get_not_file").format(path=utils.escape_html(normalized_path)))
                return

            async with self.session.delete(url, json={"message": commit_message, "sha": sha}) as response:
                if response.status == 200:
                    await utils.answer(status_message, self.strings("success_delete").format(path=utils.escape_html(normalized_path)))
                    return
                if response.status == 404:
                    await utils.answer(status_message, self.strings("delete_not_found").format(path=utils.escape_html(normalized_path)))
                    return

                error_message = await self._read_github_error(response)
                await utils.answer(status_message, self.strings("api_error").format(
                    status=response.status,
                    error=utils.escape_html(error_message),
                ))

        except Exception as e:
            await utils.answer(status_message, self.strings("internal_error").format(str(e)))
            logger.exception(e)

    def _get_file_name(self, reply: Message) -> Optional[str]:
        """Утилита для определения имени файла из сообщения-ответа."""

        media_entity = reply.document or reply.photo or reply.video or reply.audio
        if not media_entity:
            return None

        file_path = getattr(media_entity, "file_name", None)
        if not file_path:
            file_path = getattr(media_entity, "name", None)

        if not file_path and getattr(media_entity, "attributes", None):
            for attr in media_entity.attributes:
                if hasattr(attr, "file_name"):
                    file_path = attr.file_name
                    break

        if not file_path and reply.photo:
            file_path = f"photo_{media_entity.id}.jpg"

        return file_path

    async def _process_upload(self, message: Message, reply: Message, file_path: str, commit_message: str, is_update: bool = False):
        """Проверка конфигурации, скачивание и вызов основной логики API."""

        if not self.config["github_token"]:
            await utils.answer(message, self.strings("no_config"))
            return

        owner = self.config["repo_owner"]
        repo = self.config["repo_name"]
        if not owner or not repo:
            await utils.answer(message, self.strings("no_repo_set"))
            return

        status_message = await utils.answer(message, self.strings("downloading"))

        try:
            file_bytes = await reply.download_media(bytes)
        except Exception as e:
            await utils.answer(status_message, self.strings("internal_error").format(f"Скачивание файла: {e}"))
            logger.exception(e)
            return

        await self._ensure_session()
        if not self.session:
            await utils.answer(status_message, self.strings("no_config"))
            return

        await self._upload_file(status_message, file_bytes, owner, repo, file_path, commit_message, is_update)

    async def _upload_file(self, message: Message, content_bytes: bytes, owner: str, repo: str, path: str, commit_msg: str, is_update: bool = False):
        """Основная логика загрузки/обновления файла через GitHub API."""

        processed_path = self._normalize_repo_path(path)
        url = GITHUB_API_URL.format(owner=owner, repo=repo, path=processed_path)

        await utils.answer(
            message,
            self.strings("uploading").format(
                owner=utils.escape_html(owner),
                repo=utils.escape_html(repo),
                path=utils.escape_html(processed_path),
            ),
        )

        sha = None
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    file_data = await response.json()
                    sha = file_data.get("sha")
                elif response.status == 404:
                    if is_update:
                        await utils.answer(message, self.strings("api_error").format(
                            status=404,
                            error=(
                                f"Файл <code>{utils.escape_html(processed_path)}</code> не найден "
                                f"в репозитории <code>{utils.escape_html(owner)}/{utils.escape_html(repo)}</code>. "
                                "Для создания используйте <code>.ghupload</code>."
                            ),
                        ))
                        return
                else:
                    error_message = await self._read_github_error(response)
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=error_message,
                    )

            payload = {
                "message": commit_msg,
                "content": base64.b64encode(content_bytes).decode("utf-8"),
            }
            if sha:
                payload["sha"] = sha

            async with self.session.put(url, json=payload) as response:
                response_json = await response.json()

                if response.status in (200, 201):
                    download_url = response_json.get("content", {}).get("download_url", "")
                    result_key = "success_create" if response.status == 201 else "success_update"
                    await utils.answer(message, self.strings(result_key).format(
                        path=utils.escape_html(processed_path),
                        url=download_url,
                    ))
                    return

                error_message = response_json.get("message", "Неизвестная ошибка")
                await utils.answer(message, self.strings("api_error").format(
                    status=response.status,
                    error=utils.escape_html(error_message),
                ))

        except aiohttp.ClientResponseError as e:
            await utils.answer(message, self.strings("api_error").format(
                status=e.status,
                error=utils.escape_html(e.message),
            ))
            logger.exception(e)
        except Exception as e:
            await utils.answer(message, self.strings("internal_error").format(str(e)))
            logger.exception(e)
