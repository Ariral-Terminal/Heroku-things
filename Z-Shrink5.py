import aiohttp
import io
from telethon.extensions import html
from .. import loader, utils

# meta developer: @desertedowl
# scope: heroku_only

@loader.tds
class ZShrinkMod(loader.Module):
    """URL Shortener with support for Formatted Text, Stickers, GIFs, and Media"""
    strings = {"name": "Z-Shrink"}

    def __init__(self):
        self.api_base = "https://s.zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz.ru"
        self.config = loader.ModuleConfig(
            "provider",
            "catbox",
            "Provider to upload: catbox, envs, kappa, 0x0, x0, tmpfiles"
        )

    async def _upload(self, file_bytes, filename, provider):
        """Helper to upload files with robust error handling for different API structures."""
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
                        # Safe check for 'id' to avoid KeyError
                        if "id" in js:
                            return f"https://kappa.lol/{js['id']}"
                        return js.get("link") or js.get("url")
                
                elif provider == "tmpfiles":
                    data.add_field("file", file_bytes, filename=filename)
                    async with session.post("https://tmpfiles.org/api/v1/upload", data=data) as resp:
                        js = await resp.json()
                        # Fixed the 'data' KeyError: check if key exists before accessing
                        if "data" in js and isinstance(js["data"], dict):
                            return js["data"].get("url")
                        return js.get("url") or str(js)
                
                else:
                    raise ValueError(f"Unknown provider: {provider}")
            except Exception as e:
                raise Exception(f"Provider {provider} failed: {str(e)}")

    async def zzzcmd(self, message):
        """<url> [alias] OR reply to text/media [alias] - Shorten and Auto-Upload"""
        args = utils.get_args(message)
        reply = await message.get_reply_message()
        
        url = None
        alias = None

        if reply:
            alias = args[0] if args else None
            file_bytes = b""
            filename = ""
            
            # 1. Handle Media (Stickers, GIFs, Photos, Videos, Custom Emojis)
            if reply.media:
                await utils.answer(message, "<b>[Z-Shrink]</b> Downloading content... ⏳")
                file_bytes = await message.client.download_media(reply, bytes)
                
                # Extract the correct extension (works for .webp, .tgs, .mp4, etc.)
                ext = ".jpg" 
                if hasattr(reply, 'file') and reply.file:
                    ext = reply.file.ext
                
                filename = getattr(reply.file, 'name', None) or f"file_{reply.id}"
                if not filename.lower().endswith(ext.lower()):
                    filename += ext
                
            # 2. Handle Text (Supporting HTML/Markdown formatting)
            elif reply.text:
                await utils.answer(message, "<b>[Z-Shrink]</b> Processing formatted text... ⏳")
                # Convert Telegram entities back to HTML tags (<b>, <i>, etc.)
                formatted_content = html.unparse(reply.message, reply.entities)
                file_bytes = formatted_content.encode('utf-8')
                filename = f"text_{reply.id}.txt"
            
            else:
                await utils.answer(message, "<b>[Z-Shrink]</b> Reply to something with text or media.")
                return

            if not file_bytes:
                await utils.answer(message, "<b>[Z-Shrink]</b> Could not extract content.")
                return

            try:
                url = await self._upload(file_bytes, filename, self.config["provider"])
            except Exception as e:
                await utils.answer(message, f"<b>[Z-Shrink]</b> Upload failed: <code>{str(e)}</code>")
                return
        else:
            # Manual URL mode
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
                        await utils.answer(message, f"<b>[Z-Shrink]</b> Server Error: {resp.status}")
        except Exception as e:
            await utils.answer(message, f"<b>[Z-Shrink]</b> Link shortening failed: <code>{str(e)}</code>")