# meta developer: @desertedowl / origin: @fiks_official
# meta version: 2.0.0
# meta name: StreamNoRTMP
# requires: ffmpeg hikkals
# zhelenoisty
import atexit
import asyncio
import contextlib
import mimetypes
import os
import re
import tempfile
import time

from hikkalls import HikkaLls, StreamType, types
from hikkalls.binding import Binding
from hikkalls.environment import Environment
from hikkalls.exceptions import AlreadyJoinedError, NoActiveGroupCall, TelegramServerError
from hikkalls.handlers import HandlersHolder
from hikkalls.methods import Methods
from hikkalls.methods.groups.change_volume_call import ChangeVolumeCall
from hikkalls.mtproto import MtProtoClient
from hikkalls.scaffold import Scaffold
from hikkalls.types import Cache
from hikkalls.types.call_holder import CallHolder
from hikkalls.types.update_solver import UpdateSolver
from telethon.tl.functions.phone import CreateGroupCallRequest
from telethon.tl.types import DocumentAttributeFilename, Message

from .. import loader, utils
from ..inline.types import InlineCall
from ..tl_cache import CustomTelegramClient


def detect_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        return "video"
    if mime.startswith("video"):
        return "video"
    if mime.startswith("audio"):
        return "audio"
    if mime.startswith("image"):
        return "image"
    return "video"


TYPE_ICON = {"video": "🎬", "audio": "🎵", "image": "🖼️"}
PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"]
TUNES = ["zerolatency", "film", "animation", "grain", "stillimage", "fastdecode"]
SCALES = ["off", "426x240", "640x360", "854x480", "1280x720", "1920x1080", "2560x1440"]
FPS_OPT = [24, 25, 30, 48, 60]
IMAGE_FPS = [8, 12, 15, 20, 24]
IMAGE_SCALES = ["off", "426x240", "640x360", "854x480", "1280x720"]
IMAGE_CLIP_SECONDS = 3


@loader.tds
class StreamMod(loader.Module):
    """📡 RTMP media streaming"""

    strings = {
        "name": "Stream",
        "status_active": "▶️ <b>Stream is live</b>\n\n{icon} <code>{file}</code>\n⏱ Time: <b>{elapsed}</b>\n🔢 PID: <code>{pid}</code>\n📡 <code>{endpoint}</code>\n🎥 <b>{vbr}</b> | <b>{fps}fps</b> | <b>{preset}</b>\n🔊 <b>{abr}</b>\n📋 Queue: <b>{queue}</b>",
        "status_idle": "⏸ <b>Stream is not active</b>",
        "status_queue": "\n📋 Queue: <b>{n}</b>",
        "stopped": "⏹ <b>Stream stopped.</b>",
        "downloading": "⏳ Downloading…",
        "dl_failed": "❌ Failed to download file.",
        "queued": "📋 Added to queue ({n})\n{icon} <code>{file}</code>",
        "not_running": "Not running",
        "queue_empty": "Queue is empty",
        "queue_header": "📋 Queue:\n",
        "settings_title": "⚙️ <b>Stream settings</b>",
        "btn_stop": "⏹ Stop",
        "btn_queue": "📋 Queue",
        "btn_refresh": "🔄 Refresh",
        "btn_settings": "⚙️ Settings",
        "btn_status": "📊 Status",
        "btn_back": "🔙 Back",
        "btn_preset": "🎞 Preset: {v}",
        "btn_tune": "🎭 Tune: {v}",
        "btn_vbr": "🎥 Video: {v}",
        "btn_abr": "🔊 Audio: {v}",
        "btn_fps": "📐 FPS: {v}",
        "btn_res": "🖥 Res: {v}",
        "btn_threads": "🧵 Threads: {v}",
        "btn_lowcpu": "🧊 Low CPU: {v}",
        "btn_cache": "🗃️ Cache: {v}",
        "ph_vbr": "Video bitrate, e.g. 2000k",
        "ph_abr": "Audio bitrate, e.g. 128k",
        "ph_threads": "Thread count (0 = auto)",
    }

    strings_ru = {
        "_cls_doc": "📡 RTMP стриминг медиафайлов",
        "name": "Stream",
        "status_active": "▶️ <b>Трансляция идёт</b>\n\n{icon} <code>{file}</code>\n⏱ Время: <b>{elapsed}</b>\n🔢 PID: <code>{pid}</code>\n📡 <code>{endpoint}</code>\n🎥 <b>{vbr}</b> | <b>{fps}fps</b> | <b>{preset}</b>\n🔊 <b>{abr}</b>\n📋 В очереди: <b>{queue}</b>",
        "status_idle": "⏸ <b>Трансляция не активна</b>",
        "status_queue": "\n📋 В очереди: <b>{n}</b>",
        "stopped": "⏹ <b>Трансляция остановлена.</b>",
        "downloading": "⏳ Скачиваю…",
        "dl_failed": "❌ Не удалось скачать файл.",
        "queued": "📋 Добавлено в очередь ({n} шт.)\n{icon} <code>{file}</code>",
        "not_running": "Не запущено",
        "queue_empty": "Очередь пуста",
        "queue_header": "📋 Очередь:\n",
        "settings_title": "⚙️ <b>Настройки трансляции</b>",
        "btn_stop": "⏹ Стоп",
        "btn_queue": "📋 Очередь",
        "btn_refresh": "🔄 Обновить",
        "btn_settings": "⚙️ Настройки",
        "btn_status": "📊 Статус",
        "btn_back": "🔙 Назад",
        "btn_preset": "🎞 Пресет: {v}",
        "btn_tune": "🎭 Tune: {v}",
        "btn_vbr": "🎥 Видео: {v}",
        "btn_abr": "🔊 Аудио: {v}",
        "btn_fps": "📐 FPS: {v}",
        "btn_res": "🖥 Разр: {v}",
        "btn_threads": "🧵 Треды: {v}",
        "btn_lowcpu": "🧊 Эконом: {v}",
        "btn_cache": "🗃️ Кэш: {v}",
        "ph_vbr": "Битрейт видео, напр. 2000k",
        "ph_abr": "Битрейт аудио, напр. 128k",
        "ph_threads": "Потоков (0 = авто)",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "silent_queue",
                False,
                "Do not notify about track changes in chat",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "repeat",
                True,
                "Repeat the queue",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "preset",
                "veryfast",
                "x264 preset",
                validator=loader.validators.Choice(PRESETS),
            ),
            loader.ConfigValue(
                "tune",
                "zerolatency",
                "x264 tune",
                validator=loader.validators.Choice(TUNES),
            ),
            loader.ConfigValue("vbitrate", "2000k", "Video bitrate (e.g. 1500k, 3000k)"),
            loader.ConfigValue("abitrate", "128k", "Audio bitrate (e.g. 64k, 192k)"),
            loader.ConfigValue(
                "fps",
                30,
                "Frames per second",
                validator=loader.validators.Integer(minimum=1, maximum=120),
            ),
            loader.ConfigValue(
                "resolution",
                "",
                "Output resolution (e.g. 1280x720, empty = no scaling)",
            ),
            loader.ConfigValue(
                "threads",
                0,
                "FFmpeg thread count (0 = auto)",
                validator=loader.validators.Integer(minimum=0, maximum=64),
            ),
            loader.ConfigValue(
                "low_cpu",
                True,
                "Use lower-cost image conversion settings",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "cache_images",
                True,
                "Cache converted image streams by file signature",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "image_fps",
                12,
                "FPS used for image-to-video conversion",
                validator=loader.validators.Integer(minimum=1, maximum=60),
            ),
            loader.ConfigValue(
                "image_scale",
                "640x360",
                "Target scale for image streams",
                validator=loader.validators.Choice(IMAGE_SCALES),
            ),
        )
        self._app = None
        self._dir = None
        self._queue: dict[int, list[dict]] = {}
        self._forms: dict[int, object] = {}
        self._muted: dict[int, bool] = {}
        self._paused: dict[int, bool] = {}
        self._image_cache: dict[str, str] = {}
        self._last_form_text: dict[int, str] = {}

    async def client_ready(self, client, db):
        class HikkaTLClient(MtProtoClient):
            def __init__(self, cache_duration: int, client: CustomTelegramClient):
                self._bind_client = None
                from hikkalls.mtproto.telethon_client import TelethonClient
                self._bind_client = TelethonClient(cache_duration, client)
                original_on_update = getattr(self._bind_client, "on_update", None)
                if callable(original_on_update) and not getattr(
                    original_on_update, "_stream_no_chat_guard", False
                ):

                    async def safe_on_update(update, *args, **kwargs):
                        if getattr(update, "chat_id", None) is None:
                            return
                        return await original_on_update(update, *args, **kwargs)

                    safe_on_update._stream_no_chat_guard = True
                    self._bind_client.on_update = safe_on_update

        class CustomPyTgCalls(HikkaLls):
            def __init__(
                self,
                app: CustomTelegramClient,
                cache_duration: int = 120,
                overload_quiet_mode: bool = False,
            ):
                Methods.__init__(self)
                Scaffold.__init__(self)
                ChangeVolumeCall.__init__(self)
                self._app = HikkaTLClient(cache_duration, app)
                self._is_running = False
                self._env_checker = Environment(
                    self._REQUIRED_NODEJS_VERSION,
                    self._REQUIRED_PYROGRAM_VERSION,
                    self._REQUIRED_TELETHON_VERSION,
                    self._app.client,
                )
                self._call_holder = CallHolder()
                self._cache_user_peer = Cache()
                self._wait_result = UpdateSolver()
                self._on_event_update = HandlersHolder()
                self._change_volume_call = ChangeVolumeCall()
                self._binding = Binding(overload_quiet_mode)

                def cleanup():
                    if self._async_core is not None:
                        self._async_core.cancel()

                atexit.register(cleanup)

        self._app = CustomPyTgCalls(client)
        self._dir = tempfile.mkdtemp(prefix="streammod_")
        await self._app.start()
        self._app._on_event_update.add_handler("STREAM_END_HANDLER", self.stream_ended)

    def _s(self, key: str, **kwargs) -> str:
        text = self.strings[key]
        return text.format(**kwargs) if kwargs else text

    def _running(self, chat_id: int) -> bool:
        return bool(self._queue.get(chat_id)) and self._queue[chat_id][0].get("playing", False)

    def _elapsed(self, chat_id: int) -> str:
        started = self._queue.get(chat_id, [{}])[0].get("started")
        if not started:
            return "00:00:00"
        elapsed = int(time.time() - started)
        return f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}"

    def _current_track(self, chat_id: int) -> dict | None:
        queue = self._queue.get(chat_id)
        return queue[0] if queue else None

    def _cleanup_track(self, track: dict):
        for path in track.get("cleanup", []):
            with contextlib.suppress(Exception):
                if path and os.path.exists(path):
                    os.remove(path)

    def _image_sig(self, path: str) -> str:
        st = os.stat(path)
        return f"{path}:{st.st_size}:{int(st.st_mtime)}"

    def _cleanup_queue(self, chat_id: int):
        for track in self._queue.get(chat_id, []):
            self._cleanup_track(track)

    def _file_label(self, path: str) -> str:
        return os.path.basename(path) or "stream"

    def _track_label(self, track: dict) -> str:
        return track.get("filename") or self._file_label(track.get("file", "stream"))

    def _res_label(self) -> str:
        r = self.config["resolution"]
        return r if r else "auto"

    def _thr_label(self) -> str:
        t = self.config["threads"]
        return str(t) if t else "auto"

    def _status_text(self, chat_id: int) -> str:
        queue = self._queue.get(chat_id, [])
        current = queue[0] if queue else None
        if not current:
            txt = self._s("status_idle")
            if queue:
                txt += self._s("status_queue", n=len(queue))
            return txt
        return self._s(
            "status_active",
            icon=TYPE_ICON.get(current.get("kind", "video"), "📄"),
            file=self._track_label(current),
            elapsed=self._elapsed(chat_id),
            pid=current.get("pid", "—"),
            endpoint="voice_chat://telegram",
            vbr=self.config["vbitrate"],
            fps=self.config["fps"],
            preset=self.config["preset"],
            abr=self.config["abitrate"],
            queue=len(queue),
        )

    def _main_markup(self, chat_id: int) -> list:
        running = self._running(chat_id)
        return [
            [
                {"text": self._s("btn_stop"), "callback": self._cb_stop, "args": (chat_id,)} if running
                else {"text": self._s("btn_queue"), "callback": self._cb_queue, "args": (chat_id,)},
                {"text": self._s("btn_refresh"), "callback": self._cb_refresh, "args": (chat_id,)},
            ],
            [
                {"text": self._s("btn_settings"), "callback": self._cb_settings, "args": (chat_id,)},
                {"text": self._s("btn_status"), "callback": self._cb_status, "args": (chat_id,)},
            ],
        ]

    def _settings_markup(self, chat_id: int) -> list:
        return [
            [
                {"text": self._s("btn_preset", v=self.config["preset"]), "callback": self._cb_set_preset, "args": (chat_id,)},
                {"text": self._s("btn_tune", v=self.config["tune"]), "callback": self._cb_set_tune, "args": (chat_id,)},
            ],
            [
                {"text": self._s("btn_vbr", v=self.config["vbitrate"]), "input": self._s("ph_vbr"), "handler": self._ih_vbr, "args": (chat_id,)},
                {"text": self._s("btn_abr", v=self.config["abitrate"]), "input": self._s("ph_abr"), "handler": self._ih_abr, "args": (chat_id,)},
            ],
            [
                {"text": self._s("btn_fps", v=self.config["fps"]), "callback": self._cb_set_fps, "args": (chat_id,)},
                {"text": self._s("btn_res", v=self._res_label()), "callback": self._cb_set_res, "args": (chat_id,)},
            ],
            [
                {"text": self._s("btn_threads", v=self._thr_label()), "input": self._s("ph_threads"), "handler": self._ih_threads, "args": (chat_id,)},
            ],
            [
                {"text": self._s("btn_lowcpu", v="on" if self.config["low_cpu"] else "off"), "callback": self._cb_lowcpu, "args": (chat_id,)},
                {"text": self._s("btn_cache", v="on" if self.config["cache_images"] else "off"), "callback": self._cb_cache, "args": (chat_id,)},
            ],
            [{"text": self._s("btn_back"), "callback": self._cb_back, "args": (chat_id,)}],
        ]

    async def _update_form(self, chat_id: int, message):
        text = self._status_text(chat_id)
        if self._last_form_text.get(chat_id) == text and chat_id in self._forms:
            return
        self._last_form_text[chat_id] = text
        markup = self._main_markup(chat_id)
        with contextlib.suppress(Exception):
            if chat_id in self._forms:
                await self._forms[chat_id].delete()
        self._forms[chat_id] = await self.inline.form(text, message=message, reply_markup=markup)

    async def _ih_vbr(self, call: InlineCall, query: str, chat_id: int):
        q = query.strip()
        if q.endswith("k") and q[:-1].isdigit():
            self.config["vbitrate"] = q
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _ih_abr(self, call: InlineCall, query: str, chat_id: int):
        q = query.strip()
        if q.endswith("k") and q[:-1].isdigit():
            self.config["abitrate"] = q
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _ih_threads(self, call: InlineCall, query: str, chat_id: int):
        q = query.strip()
        if q.isdigit():
            self.config["threads"] = int(q)
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _convert_image(self, path: str) -> tuple[str, bool]:
        sig = self._image_sig(path)
        if self.config["cache_images"] and sig in self._image_cache:
            cached = self._image_cache[sig]
            if cached and os.path.exists(cached):
                return cached, False

        out = os.path.join(self._dir, f"{utils.rand(8)}.mp4")
        scale = self.config["resolution"] or self.config["image_scale"]
        fps = int(self.config["fps"] or self.config["image_fps"])
        if self.config["low_cpu"]:
            if scale == "off":
                scale = "640x360"
            fps = min(fps, 12)
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            path,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            str(IMAGE_CLIP_SECONDS),
            "-vf",
            f"scale=trunc(iw/2)*2:trunc(ih/2)*2{',scale=' + scale if scale != 'off' else ''}",
            "-r",
            str(fps),
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast" if self.config["low_cpu"] else "veryfast",
            "-crf",
            "30" if self.config["low_cpu"] else "24",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            out,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        code = await proc.wait()
        if code != 0 or not os.path.exists(out):
            raise RuntimeError("ffmpeg image conversion failed")
        if self.config["cache_images"]:
            self._image_cache[sig] = out
        return out, True

    async def _stream_track(self, chat_id: int, track: dict, reattempt: bool = False):
        path = track["stream_path"]
        if track["kind"] == "audio":
            stream = types.AudioPiped(path, types.HighQualityAudio())
        else:
            stream = types.AudioVideoPiped(
                path,
                types.HighQualityAudio(),
                types.HighQualityVideo(),
            )

        try:
            await asyncio.wait_for(
                self._app.join_group_call(
                    chat_id,
                    stream,
                    stream_type=StreamType().pulse_stream,
                ),
                timeout=20,
            )
        except AlreadyJoinedError:
            await asyncio.wait_for(self._app.change_stream(chat_id, stream), timeout=20)
        except NoActiveGroupCall:
            if reattempt:
                raise
            await self._client(CreateGroupCallRequest(chat_id))
            await self._stream_track(chat_id, track, True)
        except TelegramServerError:
            raise

    async def stream_ended(self, client: HikkaLls, update: types.Update):
        chat_id = update.chat_id
        queue = self._queue.get(chat_id)
        if not queue:
            with contextlib.suppress(Exception):
                await client.leave_group_call(chat_id)
            with contextlib.suppress(Exception):
                form = self._forms.pop(chat_id)
                await form.delete()
            self._last_form_text.pop(chat_id, None)
            return

        finished = queue.pop(0)
        if not self.config["repeat"]:
            self._cleanup_track(finished)

        if self.config["repeat"]:
            finished["playing"] = False
            queue.append(finished)

        if not queue:
            with contextlib.suppress(Exception):
                await client.leave_group_call(chat_id)
            with contextlib.suppress(Exception):
                form = self._forms.pop(chat_id)
                await form.delete()
            self._last_form_text.pop(chat_id, None)
            return

        queue[0]["playing"] = True
        queue[0]["started"] = time.time()
        try:
            await self._stream_track(chat_id, queue[0])
        except Exception:
            with contextlib.suppress(Exception):
                await client.leave_group_call(chat_id)

        if chat_id in self._forms and not self.config["silent_queue"]:
            with contextlib.suppress(Exception):
                await self._forms[chat_id].delete()
            self._forms[chat_id] = await self.inline.form(
                self._status_text(chat_id),
                message=chat_id,
                reply_markup=self._main_markup(chat_id),
            )

    @loader.command(ru_doc="[ответ на медиа] – начать трансляцию")
    async def stream(self, message: Message):
        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await self.inline.form(
                self._status_text(utils.get_chat_id(message)),
                message=message,
                reply_markup=self._main_markup(utils.get_chat_id(message)),
            )
            return

        status = await utils.answer(message, self._s("downloading"))
        try:
            path = await reply.download_media(file=self._dir)
        except Exception:
            path = None
        if not path:
            await status.edit(self._s("dl_failed"))
            return
        await status.delete()

        kind = detect_type(path)
        stream_path = path
        cleanup = [path]
        if kind == "image":
            try:
                stream_path, created = await self._convert_image(path)
                if created:
                    cleanup.append(stream_path)
            except Exception:
                await utils.answer(message, self._s("dl_failed"))
                return

        filename = await self._get_fn(reply) or self._file_label(path)
        filename = re.sub(r"\s+", " ", filename).strip() or self._file_label(path)

        chat_id = utils.get_chat_id(message)
        self._queue.setdefault(chat_id, []).append(
            {
                "file": path,
                "stream_path": stream_path,
                "cleanup": cleanup,
                "filename": filename,
                "kind": kind,
                "playing": False,
                "started": None,
                "pid": "—",
            }
        )

        if not any(i.get("playing") for i in self._queue[chat_id]):
            self._queue[chat_id][-1]["playing"] = True
            self._queue[chat_id][-1]["started"] = time.time()
            try:
                await self._stream_track(chat_id, self._queue[chat_id][0])
            except Exception:
                await utils.answer(message, "❌ Failed to start stream.")
                return

        if not self.config["silent_queue"]:
            await self._update_form(chat_id, message)
        else:
            await utils.answer(
                message,
                self._s("queued", n=len(self._queue[chat_id]), icon=TYPE_ICON.get(kind, "📄"), file=filename),
            )

    @loader.command(ru_doc="– открыть панель управления трансляцией")
    async def streamctl(self, message: Message):
        chat_id = utils.get_chat_id(message)
        await self.inline.form(
            self._status_text(chat_id),
            message=message,
            reply_markup=self._main_markup(chat_id),
        )

    @loader.command(ru_doc="– остановить трансляцию и очистить очередь")
    async def streamstop(self, message: Message):
        chat_id = utils.get_chat_id(message)
        self._cleanup_queue(chat_id)
        self._queue.pop(chat_id, None)
        self._paused.pop(chat_id, None)
        self._muted.pop(chat_id, None)
        with contextlib.suppress(Exception):
            await self._app.leave_group_call(chat_id)
        with contextlib.suppress(KeyError):
            form = self._forms.pop(chat_id)
            await form.delete()
        self._last_form_text.pop(chat_id, None)
        await utils.answer(message, self._s("stopped"))

    async def streamnext(self, message: Message):
        chat_id = utils.get_chat_id(message)
        if not self._queue.get(chat_id):
            await utils.answer(message, self._s("queue_empty"))
            return
        current = self._queue[chat_id].pop(0)
        self._cleanup_track(current)
        if not self._queue[chat_id]:
            with contextlib.suppress(Exception):
                await self._app.leave_group_call(chat_id)
            await utils.answer(message, self._s("queue_empty"))
            return
        self._queue[chat_id][0]["playing"] = True
        self._queue[chat_id][0]["started"] = time.time()
        await self._stream_track(chat_id, self._queue[chat_id][0])
        await self._update_form(chat_id, message)

    async def streampause(self, message: Message):
        chat_id = utils.get_chat_id(message)
        with contextlib.suppress(Exception):
            await self._app.pause_stream(chat_id)
        self._paused[chat_id] = True
        await self._update_form(chat_id, message)

    async def streamresume(self, message: Message):
        chat_id = utils.get_chat_id(message)
        with contextlib.suppress(Exception):
            await self._app.resume_stream(chat_id)
        self._paused[chat_id] = False
        await self._update_form(chat_id, message)

    async def streammute(self, message: Message):
        chat_id = utils.get_chat_id(message)
        with contextlib.suppress(Exception):
            await self._app.mute_stream(chat_id)
        self._muted[chat_id] = True
        await self._update_form(chat_id, message)

    async def streamunmute(self, message: Message):
        chat_id = utils.get_chat_id(message)
        with contextlib.suppress(Exception):
            await self._app.unmute_stream(chat_id)
        self._muted[chat_id] = False
        await self._update_form(chat_id, message)

    async def _get_fn(self, message: Message) -> str:
        filename = None
        with contextlib.suppress(Exception):
            attr = next(attr for attr in getattr(message, "document", message).attributes)
            filename = getattr(attr, "performer", "") + " - " + getattr(attr, "title", "")

        if not filename:
            with contextlib.suppress(Exception):
                filename = next(
                    attr
                    for attr in getattr(message, "document", message).attributes
                    if isinstance(attr, DocumentAttributeFilename)
                ).file_name

        return filename

    async def _cb_refresh(self, call: InlineCall, chat_id: int):
        await call.edit(self._status_text(chat_id), reply_markup=self._main_markup(chat_id))

    async def _cb_status(self, call: InlineCall, chat_id: int):
        await call.answer(self._elapsed(chat_id) if self._running(chat_id) else self._s("not_running"))

    async def _cb_stop(self, call: InlineCall, chat_id: int):
        self._cleanup_queue(chat_id)
        self._queue.pop(chat_id, None)
        self._paused.pop(chat_id, None)
        self._muted.pop(chat_id, None)
        with contextlib.suppress(Exception):
            await self._app.leave_group_call(chat_id)
        await call.edit(self._s("stopped"), reply_markup=self._main_markup(chat_id))
        self._forms.pop(chat_id, None)
        self._last_form_text.pop(chat_id, None)

    async def _cb_queue(self, call: InlineCall, chat_id: int):
        queue = self._queue.get(chat_id, [])
        if not queue:
            await call.answer(self._s("queue_empty"), show_alert=True)
            return
        lines = [
            f"{i}. {TYPE_ICON.get(item.get('kind', 'video'), '📄')} {self._track_label(item)}"
            for i, item in enumerate(queue, 1)
        ]
        await call.answer(self._s("queue_header") + "\n".join(lines), show_alert=True)

    async def _cb_back(self, call: InlineCall, chat_id: int):
        await call.edit(self._status_text(chat_id), reply_markup=self._main_markup(chat_id))

    async def _cb_settings(self, call: InlineCall, chat_id: int):
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _cb_repeat(self, call: InlineCall, chat_id: int):
        self.config["repeat"] = not self.config["repeat"]
        await call.edit(self._status_text(chat_id), reply_markup=self._main_markup(chat_id))

    async def _cb_set_preset(self, call: InlineCall, chat_id: int):
        cur = self.config["preset"]
        self.config["preset"] = PRESETS[(PRESETS.index(cur) + 1) % len(PRESETS)]
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _cb_set_tune(self, call: InlineCall, chat_id: int):
        cur = self.config["tune"]
        self.config["tune"] = TUNES[(TUNES.index(cur) + 1) % len(TUNES)]
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _cb_set_fps(self, call: InlineCall, chat_id: int):
        cur = self.config["fps"]
        self.config["fps"] = FPS_OPT[(FPS_OPT.index(cur) + 1) % len(FPS_OPT)] if cur in FPS_OPT else 30
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _cb_set_res(self, call: InlineCall, chat_id: int):
        cur = self.config["resolution"] or "off"
        idx = SCALES.index(cur) if cur in SCALES else 0
        nxt = SCALES[(idx + 1) % len(SCALES)]
        self.config["resolution"] = "" if nxt == "off" else nxt
        if self.config["resolution"] and self.config["resolution"] in IMAGE_SCALES:
            self.config["image_scale"] = self.config["resolution"]
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _cb_lowcpu(self, call: InlineCall, chat_id: int):
        self.config["low_cpu"] = not self.config["low_cpu"]
        if self.config["low_cpu"] and self.config["image_scale"] == "off":
            self.config["image_scale"] = "640x360"
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _cb_cache(self, call: InlineCall, chat_id: int):
        self.config["cache_images"] = not self.config["cache_images"]
        if not self.config["cache_images"]:
            self._image_cache.clear()
        await call.edit(self._s("settings_title"), reply_markup=self._settings_markup(chat_id))

    async def _cb_pause(self, call: InlineCall, chat_id: int):
        if self._paused.get(chat_id, False):
            with contextlib.suppress(Exception):
                await self._app.resume_stream(chat_id)
            self._paused[chat_id] = False
        else:
            with contextlib.suppress(Exception):
                await self._app.pause_stream(chat_id)
            self._paused[chat_id] = True
        await call.edit(self._status_text(chat_id), reply_markup=self._main_markup(chat_id))

    async def _cb_mute(self, call: InlineCall, chat_id: int):
        if self._muted.get(chat_id, False):
            with contextlib.suppress(Exception):
                await self._app.unmute_stream(chat_id)
            self._muted[chat_id] = False
        else:
            with contextlib.suppress(Exception):
                await self._app.mute_stream(chat_id)
            self._muted[chat_id] = True
        await call.edit(self._status_text(chat_id), reply_markup=self._main_markup(chat_id))

    async def _cb_next(self, call: InlineCall, chat_id: int):
        if not self._queue.get(chat_id):
            await call.answer(self._s("queue_empty"), show_alert=True)
            return
        current = self._queue[chat_id].pop(0)
        self._cleanup_track(current)
        if not self._queue[chat_id]:
            with contextlib.suppress(Exception):
                await self._app.leave_group_call(chat_id)
            await call.edit(self._s("stopped"), reply_markup=self._main_markup(chat_id))
            return
        self._queue[chat_id][0]["playing"] = True
        self._queue[chat_id][0]["started"] = time.time()
        await self._stream_track(chat_id, self._queue[chat_id][0])
        await call.edit(self._status_text(chat_id), reply_markup=self._main_markup(chat_id))
