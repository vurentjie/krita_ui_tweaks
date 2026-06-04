# SPDX-License-Identifier: CC0-1.0

from krita import Krita

import os
import json

_translations: dict[str, str] | None = None


def i18n_reset():
    global _translations
    _translations = None


def i18n_translations_get() -> dict[str, str]:
    global _translations
    if _translations is None:
        app = Krita.instance()
        try:
            options = json.loads(
                app.readSetting("krita_ui_tweaks", "options", "")
            )
            _translations = options.get("translated", None)
        except:
            _translations = {}
    if not isinstance(_translations, dict):
        _translations = {}
    return _translations


def i18n(val: str, *args: str) -> str:
    translations = i18n_translations_get()
    translated = translations.get(val, "")
    if not translated.strip():
        translated = Krita.krita_i18n(val)

    for i, v in enumerate(args):
        translated = translated.replace(f"%{i+1}", v)

    return translated


