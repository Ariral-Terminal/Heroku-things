# meta developer: @ke_mods

import subprocess
import re
from .. import loader, utils

@loader.tds
class FastfetchMod(loader.Module):
    strings = {
        "name": "Fastfetch",
        "not_installed": "<b>Please, install</b> <i>fastfetch</i> <b>package</b>",
    }

    strings_ru = {
        "not_installed": "<b>Пожалуйста, установите пакет</b> <i>fastfetch</i>",
    }

    strings_ua = {
        "not_installed": "<b>Будь ласка, встановіть пакет</b> <i>fastfetch</i>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "SHOW_LOGO",
                True,
                "Show system logo (True/False)",
                validator=loader.validators.Boolean(),
            ),
        )

    @loader.command(
        ru_doc="- запустить команду fastfetch",
        ua_doc="- запустити команду fastfetch",
    )
    async def fastfetch(self, message):
        """- run fastfetch command"""
        args = ["fastfetch"]
        
        if not self.config["SHOW_LOGO"]:
            args.extend(["--logo", "none"])

        try:
            result = subprocess.run(args, capture_output=True, text=True)
            output = result.stdout

            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean_output = ansi_escape.sub('', output)

            await utils.answer(message, f"<b>Fastfetch output:</b>\n<pre>{utils.escape_html(clean_output)}</pre>")
            
        except FileNotFoundError:
            await utils.answer(message, self.strings("not_installed"))
            