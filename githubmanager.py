"""
    📦 GitHubManager - Управление репозиториями через GitHub API
    
    Этот модуль позволяет загружать (обновлять) файлы в указанный репозиторий GitHub
    с помощью REST API и персонального токена.
    
"""

__version__ = (6, 3, 6) 

# meta developer: @sxozuo
# requires: aiohttp

import aiohttp
import base64
import logging
import json
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
            "Команда: <code>.ghupload</code> [сообщение коммита]\n"
            "<b>Действие:</b> Ответьте этой командой на сообщение с файлом.\n"
            "    - Файл будет загружен или обновлен (если уже существует).\n"
            "    - <b>[сообщение коммита]</b> — опционально. Если не указано, используется имя файла.\n\n"
            "<b>✨ Новая команда:</b> <code>.ghrepos</code> для интерактивного выбора репозитория."
        ),
        "update_start": "📂 **Выберите файл для обновления** в репозитории <code>{owner}/{repo}</code> по пути <code>{path}</code>:",
        "update_path": "📂 **Содержимое:** <code>{path}</code>",
        "update_prompt": "✅ **Файл выбран:** <code>{path}</code>\nТеперь ответьте на сообщение с **новым файлом** и введите сообщение коммита.",
        "update_no_path": "❌ <b>Ошибка:</b> Не удалось получить список файлов для пути: <code>{path}</code>.",
        "update_back": "⬅️ Назад",
        "update_cancel": "❌ Отмена",
        "user_id_error": "❌ Внутренняя ошибка: Не удалось определить ID пользователя, нажавшего кнопку. Проверьте логи.",
        "update_timeout": "❌ <b>Ошибка:</b> Режим обновления файла не активен. Сначала используйте <code>.ghupdatecmd</code> без аргументов и выберите файл."
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
        )

    async def client_ready(self, client, db):
        self._client = client
        self._db = db
        self.session: Optional[aiohttp.ClientSession] = None
        # Хранилище для пути к файлу, который пользователь собирается обновить
        # Ключ: ID пользователя, нажавшего кнопку
        self.temp_update_path = {} 

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
                if user_id in self.temp_update_path:
                    del self.temp_update_path[user_id]
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

            await self._process_upload(message, reply, repo_path, commit_message, is_update=True)
        
        elif reply and reply.media:
            # 3. Команда вызвана реплаем на медиафайл, но не в режиме ожидания и без аргументов
            await utils.answer(message, self.strings("update_timeout"))
            
        else:
            # 4. Интерактивное обновление: .ghupdate (открываем браузер файлов)
            status_message = await utils.answer(message, "⏳ Загружаю содержимое репозитория...")
            
            await self._send_file_list(status_message, owner, repo, "", original_message=message)


    async def _send_file_list(self, message: Message, owner: str, repo: str, path: str, original_message: Message):
        """Получает и отображает список файлов/папок для указанного пути."""
        url = GITHUB_API_URL.format(owner=owner, repo=repo, path=path.lstrip('/'))
        
        await self._ensure_session()
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    contents = await response.json()
                elif response.status == 404:
                    await utils.answer(message, self.strings("update_no_path").format(path=utils.escape_html(path)))
                    return
                else:
                    error_json = await response.json()
                    error_message = error_json.get("message", "Неизвестная ошибка")
                    await utils.answer(message, self.strings("api_error").format(
                        status=response.status, error=utils.escape_html(error_message)
                    ))
                    return

            buttons = []
            files = []
            dirs = []

            for item in contents:
                name = item['name']
                item_path = item['path']
                if item['type'] == 'dir':
                    dirs.append((name, item_path))
                elif item['type'] == 'file':
                    files.append((name, item_path))

            # Сортируем и добавляем кнопки (сначала папки, потом файлы)
            for name, item_path in sorted(dirs, key=lambda x: x[0].lower()):
                # ghmu_dir:PATH
                buttons.append([{
                    "text": f"📁 {name}", 
                    "data": f"ghmu_dir:{item_path}"
                }])

            for name, item_path in sorted(files, key=lambda x: x[0].lower()):
                # ghmu_file:PATH
                buttons.append([{
                    "text": f"📄 {name}", 
                    "data": f"ghmu_file:{item_path}"
                }])

            # Кнопка "Назад"
            if path:
                parent_path = "/".join(path.split("/")[:-1])
                buttons.append([{
                    "text": self.strings("update_back"),
                    "data": f"ghmu_dir:{parent_path}"
                }])

            buttons.append([{
                "text": self.strings("update_cancel"),
                "data": "ghmu_close"
            }])
            
            text_header = self.strings("update_start").format(
                owner=utils.escape_html(owner), 
                repo=utils.escape_html(repo), 
                path=utils.escape_html(path or "/")
            ) if not path else self.strings("update_path").format(path=utils.escape_html(path))

            await utils.answer(message, text_header, reply_markup=buttons)

        except Exception as e:
            await utils.answer(message, self.strings("internal_error").format(str(e)))
            logger.exception(e)
            
            
    @loader.callback_handler(ru_doc="Обрабатывает нажатия кнопок списка репозиториев.")
    async def ghm_callback_handler(self, call: Message):
        """Обрабатывает колбэки от Inline-кнопок, созданных командой ghreposcmd."""
        data = call.data
        
        if data == "ghm_close":
            # При закрытии интерактивного меню, очищаем потенциальный путь, если он есть
            user_id = self._get_user_id_from_call(call)
            if user_id and user_id in self.temp_update_path:
                del self.temp_update_path[user_id]
                
            await call.delete()
            return
            
        if data.startswith("ghm_set_"):
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
                    repo=utils.escape_html(repo_name)
                )
            )
            await call.answer(f"Репозиторий установлен: {owner}/{repo_name}", show_alert=True)


    @loader.callback_handler(ru_doc="Обрабатывает нажатия кнопок интерактивного обновления файла.")
    async def ghmu_callback_handler(self, call: Message):
        """Обрабатывает колбэки для навигации по файлам при обновлении."""
        data = call.data
        
        if data == "ghmu_close":
            # При закрытии интерактивного меню, очищаем потенциальный путь, если он есть
            user_id = self._get_user_id_from_call(call)
            if user_id and user_id in self.temp_update_path:
                del self.temp_update_path[user_id]
                
            await call.delete()
            return
            
        path = data[8:]
        
        if data.startswith("ghmu_dir:"):
            # Навигация в папку
            owner = self.config["repo_owner"]
            repo = self.config["repo_name"]
            
            await self._send_file_list(call, owner, repo, path, original_message=call)
            
        elif data.startswith("ghmu_file:"):
            # Выбран файл для обновления
            
            user_id = self._get_user_id_from_call(call)
            
            if user_id is None:
                # Логируем и отвечаем пользователю, если даже аварийный механизм не сработал
                logger.error(f"Критическая ошибка в ghm_callback_handler: не найден ID пользователя ни одним из способов. Vars(call): {vars(call)}")
                await call.answer(self.strings("user_id_error"), show_alert=True)
                return

            self.temp_update_path[user_id] = path
            
            await call.edit(
                self.strings("update_prompt").format(path=utils.escape_html(path)),
                reply_markup=[[{
                    "text": self.strings("update_cancel"),
                    "data": "ghmu_close"
                }]]
            )
            await call.answer(f"Выбран файл: {path}. Теперь ответьте на это сообщение новым файлом и командой .ghupdatecmd [коммит].", show_alert=True)


    def _get_file_name(self, reply: Message) -> Optional[str]:
        """Утилита для определения имени файла из сообщения-ответа."""
        media_entity = reply.document or reply.photo or reply.video or reply.audio
        
        if not media_entity:
            return None
            
        file_path = getattr(media_entity, 'file_name', None)
        
        if not file_path:
            file_path = getattr(media_entity, 'name', None)
            
        if not file_path and getattr(media_entity, 'attributes', None):
            for attr in media_entity.attributes:
                if hasattr(attr, 'file_name'):
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
        
        # ИЗМЕНЕНИЕ 6.3.5: Удаление префикса диска Windows из пути перед API-запросом.
        processed_path = WINDOWS_DRIVE_PREFIX_REGEX.sub("", path)
        
        url = GITHUB_API_URL.format(owner=owner, repo=repo, path=processed_path.lstrip('/'))
        
        await utils.answer(message, self.strings("uploading").format(owner=utils.escape_html(owner), repo=utils.escape_html(repo), path=utils.escape_html(processed_path)))
        
        sha = None
        try:
            # Шаг 1: Проверка существования файла для получения SHA (для обновления)
            async with self.session.get(url) as response:
                if response.status == 200:
                    file_data = await response.json()
                    sha = file_data.get("sha")
                    if is_update and not sha:
                         pass
                elif response.status == 404:
                    if is_update:
                        await utils.answer(message, self.strings("api_error").format(
                            status=404, 
                            error=f"Файл <code>{processed_path}</code> не найден в репозитории <code>{owner}/{repo}</code>. Для создания используйте <code>.ghupload</code>."
                        ))
                        return
                    pass
                else:
                    error_json = await response.json()
                    error_message = error_json.get("message", "Неизвестная ошибка")
                    raise aiohttp.ClientResponseError(
                        response.request_info, response.history, 
                        status=response.status, 
                        message=error_message
                    )

            # Шаг 2: Загрузка нового контента
            encoded_content = base64.b64encode(content_bytes).decode('utf-8')

            payload = {
                "message": commit_msg,
                "content": encoded_content,
            }
            if sha:
                payload["sha"] = sha
            
            async with self.session.put(url, json=payload) as response:
                response_json = await response.json()
                
                if response.status in (200, 201):
                    commit_type = "create" if response.status == 201 else "update"
                    download_url = response_json["content"]["download_url"]
                    
                    if commit_type == "create":
                        result_string = self.strings("success_create").format(
                            path=utils.escape_html(processed_path),
                            url=download_url
                        )
                    else:
                        result_string = self.strings("success_update").format(
                            path=utils.escape_html(processed_path),
                            url=download_url
                        )
                    
                    await utils.answer(message, result_string)
                else:
                    error_message = response_json.get("message", "Неизвестная ошибка")
                    error_string = self.strings("api_error").format(
                        status=response.status,
                        error=utils.escape_html(error_message)
                    )
                    await utils.answer(message, error_string)

        except aiohttp.ClientResponseError as e:
            error_string = self.strings("api_error").format(
                status=e.status,
                error=utils.escape_html(e.message)
            )
            await utils.answer(message, error_string)
            logger.exception(e)

        except Exception as e:
            await utils.answer(message, self.strings("internal_error").format(str(e)))
            logger.exception(e)