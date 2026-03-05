import random
import re
from .. import loader, utils

# meta developer: @desertedowl
# scope: heroku_only

class TsundereMod(loader.Module):
    """Module for changing your speech to Tsundere style with controlled frequency."""
    strings = {"name": "Tsundere"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "enabled",
                False,
                "Status of Tsundere mode",
                validator=loader.validators.Boolean()
            ),
            loader.ConfigValue(
                "chance",
                0.3,
                "Chance of triggering (0.1 = 10%, 1.0 = 100%)",
                validator=loader.validators.Float()
            )
        )

    async def tsunderecmd(self, message):
        """- Toggle tsundere mode"""
        new_state = not self.config["enabled"]
        self.config["enabled"] = new_state
        status = "ВКЛЮЧЕН" if new_state else "ВЫКЛЮЧЕН"
        await utils.answer(message, f"<b>[Tsundere]</b> Режим {status}. Н-не то чтобы мне было дело...")

    async def watcher(self, message):
        if not self.config["enabled"]:
            return
        
        # Only process our own messages
        if not hasattr(message, "out") or not message.out:
            return

        # Don't process empty messages or commands
        if not message.text or message.text.startswith((".", "/", "!", "?")):
            return

        # PROBABILITY CHECK: If random number is higher than chance, skip
        if random.random() > self.config["chance"]:
            return

        # --- Massive English Word Bank ---
        en_prefixes = [
            "H-hmph! ", "I-It's not like I wanted to say this, but... ", 
            "Don't get the wrong idea, idiot! ", "Ugh, fine. ", "B-baka! ", 
            "Listen closely, because I won't repeat myself! ", "W-whatever! ",
            "I'm only telling you this because I pity you! ", "A-are you even listening? ",
            "S-stop staring at me! ", "It's just a coincidence! ", "Stop being so annoying! ",
            "D-don't make me say it twice! ", "I suppose I can tell you... ",
            "Hey! Look at me when I'm talking! ", "Dummy... "
        ]
        en_suffixes = [
            "... d-don't look at me like that!", "... baka!", "... it's purely a coincidence!", 
            "... dummy!", "... a-anyway, forget it!", "... it's not because I like you!",
            "... hmph!", "... geez, you're so annoying!", "... don't get used to this!",
            "... you're such a pain!", "... stop smiling like that!", "... whatever!",
            "... I-I'm going now!", "... don't think this makes us friends!"
        ]

        # --- Massive Russian Word Bank ---
        ru_prefixes = [
            "П-пф! ", "Ч-что уставился? ", "Эй, дурак! ", 
            "Н-не думай, что я делаю это ради тебя! ", "Уф, ладно... ", 
            "Т-только в этот раз! ", "С-слушай сюда, придурок! ",
            "Я говорю это только потому, что ты сам бы не додумался! ", "Б-бесишь... ",
            "Н-не делай таких выводов! ", "П-просто слушай! ", "Н-неужели ты такой тупой? ",
            "Х-хватит на меня так смотреть! ", "Д-дурак, чего застыл? ",
            "Слушай, придурок... ", "Да что с тобой не так?! "
        ]
        ru_suffixes = [
            "... б-бака!", "... н-не обольщайся!", "... идиот!", "... д-дурак!", 
            "... ч-чтоб ты знал!", "... бесишь!", "... н-не пойми неправильно!",
            "... д-даже не смотри на меня так!", "... п-придурок!", "... и вообще, забудь!",
            "... н-не беси меня!", "... иди уже куда шел!", "... х-хватит лыбиться!",
            "... и не надейся на большее!"
        ]

        # Prevent double-editing
        all_checks = en_prefixes + en_suffixes + ru_prefixes + ru_suffixes
        if any(x in message.text for x in all_checks):
            return

        is_ru = bool(re.search(r'[а-яА-ЯёЁ]', message.text))

        if is_ru:
            pre = random.choice(ru_prefixes + [""] * 5) # Increased weight of empty strings
            suf = random.choice(ru_suffixes + [""] * 3)
        else:
            pre = random.choice(en_prefixes + [""] * 5)
            suf = random.choice(en_suffixes + [""] * 3)

        # Force a change if random choice picked two empty strings
        if not pre and not suf:
            suf = random.choice(ru_suffixes if is_ru else en_suffixes)

        final_text = f"{pre}{message.text}{suf}"
        await message.edit(final_text)
