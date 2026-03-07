import aiohttp
import io
import re
from telethon.extensions import html
from .. import loader, utils

# meta developer: @desertedowl
# scope: heroku_only

@loader.tds
class ZShrinkMod(loader.Module):
    """URL Shortener with Enhanced Alias Support and Media Upload"""
    strings = {"name": "Z-Shrink"}

    def __init__(self):
        self.api_base = "https://s.zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz.ru"
        self.config = loader.ModuleConfig(
            "provider",
            "catbox",
            "Provider to upload: catbox, envs, kappa, 0x0, x0, tmpfiles"
        )

    async def _upload(self, file_bytes, filename, provider):
        """Standardized upload handler."""
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            try:
                # Prepare headers/data based on provider
                if provider == "catbox":
                    data.add_field("reqtype", "fileupload")
                    data.add_field("fileToUpload", file_bytes, filename=filename)
                    url = "https://catbox.moe/user/api.php"
                elif provider == "envs":
                    data.add_field("file", file_bytes, filename=filename)
                    url = "https://envs.sh"
                elif provider == "tmpfiles":
                    data.add_field("file", file_bytes, filename=filename)
                    async with session.post("https://tmpfiles.org/api/v1/upload", data=data) as resp:
                        js = await resp.json()
                        return js["data"]["url"] if "data" in js else js.get("url")
                else:
                    url_map = {"0x0": "https://0x0.st", "x0": "https://x0.at", "kappa": "https://kappa.lol/api/upload"}
                    data.add_field("file", file_bytes, filename=filename)
                    url = url_map.get(provider, "https://envs.sh")

                async with session.post(url, data=data) as resp:
                    if provider == "kappa":
                        js = await resp.json()
                        return f"https://kappa.lol/{js['id']}"
                    return (await resp.text()).strip()
            except Exception as e:
                raise Exception(f"Upload fail: {str(e)}")

    async def zzzcmd(self, message):
        """<url> [alias] OR reply to content [alias]"""
        args = utils.get_args(message)
        reply = await message.get_reply_message()
        
        url = None
        target_alias = None

        # --- ALIAS EXTRACTION ---
        if args:
            # If replying, the first word is the alias. If not, the second word is the alias.
            raw_alias = args[0] if reply else (args[1] if len(args) > 1 else None)
            if raw_alias:
                # Allow letters, numbers, dashes, and underscores
                target_alias = re.sub(r'[^a-zA-Z0-9\-_]', '', raw_alias)

        if reply:
            file_bytes = b""
            ext = ".jpg"
            if hasattr(reply, 'file') and reply.file:
                ext = reply.file.ext
            elif not reply.media and (reply.text or reply.raw_text):
                ext = ".txt"

            filename = f"{target_alias if target_alias else 'file'}{ext}"

            if reply.media:
                await utils.answer(message, "<b>[Z-Shrink]</b> Uploading media... ⏳")
                file_bytes = await message.client.download_media(reply, bytes)
            elif reply.text or reply.raw_text:
                await utils.answer(message, "<b>[Z-Shrink]</b> Uploading text... ⏳")
                content = html.unparse(reply.message, reply.entities) if reply.entities else reply.raw_text
                file_bytes = content.encode('utf-8')
            
            try:
                url = await self._upload(file_bytes, filename, self.config["provider"])
            except Exception as e:
                return await utils.answer(message, f"<b>[Z-Shrink]</b> ❌ {str(e)}")
        else:
            if not args:
                return await utils.answer(message, "<b>[Z-Shrink]</b> Usage: <code>.zzz <url> [alias]</code>")
            url = args[0]

        if not url or not url.startswith("http"):
            return await utils.answer(message, "<b>[Z-Shrink]</b> ❌ Invalid URL.")

        await utils.answer(message, f"<b>[Z-Shrink]</b> Shortening with alias: <code>{target_alias or 'auto'}</code>... ⏳")

        try:
            async with aiohttp.ClientSession() as session:
                # We send multiple common keys at once so the server finds the one it likes
                payload = {
                    "url": url,
                    "alias": target_alias,
                    "custom_url": target_alias,
                    "slug": target_alias
                }
                
                async with session.post(f"{self.api_base}/api/shorten", json=payload) as resp:
                    data = await resp.json()
                    
                    if resp.status in [200, 201]:
                        link = data.get("full_short_url") or data.get("short_url") or data.get("result")
                        
                        # Case-insensitive verification
                        if target_alias and target_alias.lower() not in link.lower():
                            await utils.answer(message, f"<b>[Z-Shrink]</b> ⚠️ Alias <code>{target_alias}</code> was ignored. Server likely requires an API key for custom links.\n🔗 {link}")
                        else:
                            await utils.answer(message, f"<b>[Z-Shrink]</b> Done! 🔗 {link}")
                    else:
                        msg = data.get("message") or data.get("error") or f"Error {resp.status}"
                        await utils.answer(message, f"<b>[Z-Shrink]</b> ❌ API Error: <code>{msg}</code>")
        except Exception as e:
            await utils.answer(message, f"<b>[Z-Shrink]</b> ❌ Shortening failed: <code>{str(e)}</code>")