#   _   _  _               _         
#  | | | |(_)             | |        
#  | |_| | _  ___   ___   | | __  __ _ 
#  |  _  || |/ __| / _ \  | |/ / / _` |
#  | | | || |\__ \| (_) | |   < | (_| |
#  \_| |_/|_||___/ \___/  |_|\_\ \__,_|
#
# meta developer: @xyecoder
# meta banner: https://pomf2.lain.la/f/jhep1ua2.jpg
# scope: hikka_only
# scope: hikka_min 1.6.3
# requires: Pillow

import logging
import os
import subprocess
import asyncio
from PIL import Image
from .. import loader, utils
from herokutl.types import Message

logger = logging.getLogger(__name__)

@loader.tds
class shakalizatorMod(loader.Module):
    """Цэ потужни шакализатор"""
    
    strings = {
        "name": "shakalizator",
        "processing": "⏳ <b>Потужна деградация запущена...</b>",
        "no_reply": "<b>❌ Нужно ответить на медиафайл.</b>",
        "error": "<b>❌ Ошибка при уничтожении качества.</b>",
        "caption": "ШакаліZOVaно✅"
    }

    strings_ru = {
        "processing": "⏳ <b>Уничтожение качества контента...</b>",
        "no_reply": "<b>❌ Ответь на медиафайл, чтобы применить шакализатор.</b>",
        "caption": "ШакаліZOVaно✅"
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "pixel_size",
                10,
                "Размер одного пикселя. Чем выше число, тем крупнее квадраты.",
                validator=loader.validators.Integer(minimum=2, maximum=50)
            )
        )

    @loader.command(
        ru_doc="Шакализируй это дерьмо",
        en_doc="Shakalize this shit"
    )
    async def shakalcmd(self, message: Message):
        """Шакализируй это дерьмо"""
        reply = await message.get_reply_message()
        if not reply or not (reply.photo or reply.video or reply.sticker or reply.document):
            await utils.answer(message, self.strings("no_reply"))
            return

        status = await utils.answer(message, self.strings("processing"))
        path = await self._client.download_media(reply)
        output = ""

        try:
            p_size = self.config["pixel_size"]

            if reply.photo or (reply.document and reply.file.mime_type.startswith("image/")):
                output = "shakal.jpg"
                img = Image.open(path)
                w, h = img.size
                img_small = img.resize((max(w // p_size, 1), max(h // p_size, 1)), resample=Image.NEAREST)
                img_pixel = img_small.resize((w, h), resample=Image.NEAREST)
                img_pixel.convert("RGB").save(output, "JPEG", quality=5)
                
            elif reply.video or (reply.document and reply.file.mime_type.startswith("video/")):
                output = "shakal.mp4"
                cmd = (
                    f'ffmpeg -y -i "{path}" -vf "scale=128:-2:flags=neighbor,format=yuv420p" '
                    f'-vcodec libx264 -crf 51 -b:v 32k -acodec mp3 -ab 16k -ar 8000 "{output}"'
                )
                process = await asyncio.create_subprocess_shell(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                await process.communicate()

            if output and os.path.exists(output):
                await self._client.send_file(
                    message.chat_id,
                    output,
                    reply_to=reply.id,
                    caption=self.strings("caption")
                )
                await status.delete()
                await message.delete()
            else:
                await utils.answer(message, self.strings("error"))

        except Exception as e:
            logger.exception("Shakalizator failure")
            await utils.answer(message, f"{self.strings('error')}\n<code>{e}</code>")
        
        finally:
            for f in [path, output]:
                if f and os.path.exists(f):
                    os.remove(f)