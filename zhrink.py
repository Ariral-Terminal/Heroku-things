import aiohttp
from .. import loader, utils

# meta developer: @desertedowl
# scope: heroku_only

class ZShrinkMod(loader.Module):
    """URL Shortener / Redirector for s.zzzzzz...ru"""
    strings = {"name": "Z-Shrink"}

    def __init__(self):
        self.api_base = "https://s.zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz.ru"

    async def zzzcmd(self, message):
        """- Create a short link <url> [alias]"""
        args = utils.get_args(message)
        if not args:
            await utils.answer(message, "<b>[Z-Shrink]</b> Usage: <code>.zzz <url> <alias></code>")
            return

        url = args[0]
        alias = args[1] if len(args) > 1 else None
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        await utils.answer(message, "<b>[Z-Shrink]</b> Working... ⏳")

        try:
            async with aiohttp.ClientSession() as session:
                payload = {"url": url}
                if alias:
                    payload["alias"] = alias
                
                async with session.post(f"{self.api_base}/api/shorten", json=payload) as resp:
                    data = await resp.json()
                    
                    if resp.status in [200, 201]:
                        # The API uses 'full_short_url' based on your logs
                        link = (
                            data.get("full_short_url") or 
                            data.get("short_url") or 
                            data.get("result")
                        )
                        
                        if link:
                            await utils.answer(message, f"<b>[Z-Shrink]</b> Done! 🔗 {link}")
                        else:
                            await utils.answer(message, f"<b>[Z-Shrink]</b> Error: Link key not found in <code>{data}</code>")
                    else:
                        await utils.answer(message, f"<b>[Z-Shrink]</b> Server Error: {resp.status}")
        
        except Exception as e:
            await utils.answer(message, f"<b>[Z-Shrink]</b> Failed: <code>{str(e)}</code>")
