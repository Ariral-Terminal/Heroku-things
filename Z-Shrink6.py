import aiohttp
import io
from telethon.extensions import html
from .. import loader, utils

# meta developer: @desertedowl
# scope: heroku_only

@loader.tds
class ZShrinkMod(loader.Module):
    """URL Shortener for Text, Media, Stickers, and GIFs"""
    strings = {"name": "Z-Shrink"}

    def __init__(self):
        self.api_base = "https://s.zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz.ru"
        self.config = loader.ModuleConfig(
            "provider",
            "catbox",
            "Provider to upload: catbox, envs, x0, tmpfiles"
        )

    async def _upload(self, file_bytes, filename, provider):
        """Robust upload helper with error handling for various host structures."""
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            
            try:
                if provider == "catbox":
                    data.add_field("reqtype", "fileupload")
                    data.add_field("fileToUpload", file_bytes, filename=filename)
                    async with session.post("https://catbox.moe/user/api.php", data=data) as resp:
                        return (await resp.text()).strip()
                
                elif provider == "envs":
                    data.add_field("file", file_bytes, filename=filename)
                    async with session.post("https://envs.sh", data=data) as resp:
                        return (await resp.text()).strip()
                
                elif provider == "0x0":
                    data.add_field("file", file_bytes, filename=filename)
                    data.add_field("secret", "True") 
                    async with session.post("https://0x0.st", data=data) as resp:
                        return (await resp.text()).strip()
                
                elif provider == "x0":
                    data.add_field("file", file_bytes, filename=filename)
                    async with session.post("https://x0.at", data=data) as resp:
                        return (await resp.text()).strip()
                
                elif provider == "kappa":
                    data.add_field("file", file_bytes, filename=filename)
                    async with session.post("https://kappa.lol/api/upload", data=data) as resp:
                        js = await resp.json()
                        return f"https://kappa.lol/{js['id']}" if "id" in js else js.get("link")
                
                elif provider == "tmpfiles":
                    data.add_field("file", file_bytes, filename=filename)
                    async with session.post("https://tmpfiles.org/api/v1/upload", data=data) as resp:
                        js = await resp.json()
                        return js["data"]["url"] if "data" in js else js.get("url")
                
                else:
                    raise ValueError(f"Unknown provider: {provider}")
            except Exception as e:
                raise Exception(f"Provider {provider} error: {str(e)}")

    async def zzzcmd(self, message):
        """<url> - Create a shortened link, you can also reply"""
        args = utils.get_args(message)
        reply = await message.get_reply_message()
        
        url = None
        alias = None

        if reply:
            # In reply mode, the first argument is always the alias
            alias = args[0] if args else None
            file_bytes = b""
            
            # Determine File Extension
            ext = ".jpg"
            if hasattr(reply, 'file') and reply.file:
                ext = reply.file.ext
            elif not reply.media and reply.text:
                ext = ".txt"

            # Determine Filename (use alias as name if provided)
            base_name = alias if alias else f"file_{reply.id}"
            filename = f"{base_name}{ext}"

            # 1. Handle Media
            if reply.media:
                await utils.answer(message, "<b>[Z-Shrink]</b> Downloading content... ⏳")
                file_bytes = await message.client.download_media(reply, bytes)
                
            # 2. Handle Formatted Text
            elif reply.text:
                await utils.answer(message, "<b>[Z-Shrink]</b> Processing text... ⏳")
                # Preserve HTML tags (<b>, <i>, etc.)
                content = html.unparse(reply.message, reply.entities)
                file_bytes = content.encode('utf-8')
            
            else:
                await utils.answer(message, "<b>[Z-Shrink]</b> Reply to text, media, or stickers.")
                return

            try:
                # Upload the file to the chosen provider
                url = await self._upload(file_bytes, filename, self.config["provider"])
            except Exception as e:
                await utils.answer(message, f"<b>[Z-Shrink]</b> Upload failed: <code>{str(e)}</code>")
                return
        else:
            # Manual URL mode (No reply)
            if not args:
                await utils.answer(message, "<b>[Z-Shrink]</b> Usage: <code>.zzz <url> [alias]</code>")
                return
            url = args[0]
            alias = args[1] if len(args) > 1 else None

        if not url:
            return

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        await utils.answer(message, "<b>[Z-Shrink]</b> Shortening link... ⏳")

        # Shorten via Z-Shrink API
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"url": url}
                if alias:
                    payload["alias"] = alias
                
                async with session.post(f"{self.api_base}/api/shorten", json=payload) as resp:
                    data = await resp.json()
                    if resp.status in [200, 201]:
                        link = data.get("full_short_url") or data.get("short_url") or data.get("result")
                        await utils.answer(message, f"<b>[Z-Shrink]</b> Done! 🔗 {link}")
                    else:
                        error_msg = data.get("message") or f"Status {resp.status}"
                        await utils.answer(message, f"<b>[Z-Shrink]</b> API Error: <code>{error_msg}</code>")
        except Exception as e:
            await utils.answer(message, f"<b>[Z-Shrink]</b> Failed: <code>{str(e)}</code>")