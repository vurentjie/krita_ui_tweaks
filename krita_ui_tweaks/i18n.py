# SPDX-License-Identifier: CC0-1.0

from krita import Krita

# from .pyqt import QStandardPaths, QSettings, QByteArray
import os
import json


_translations: dict[str, str] | None = None

def i18n_reset():
    global _translations 
    _translations = None

def i18n(val: str) -> str:
    global _translations
    if _translations is None:
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.json"
        )
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    j = json.load(f)
                    _translations = j.get("translated", {})
            except Exception:
                pass
    if not isinstance(_translations, dict):
        _translations = {}
    translated = _translations.get(val, "")
    if not translated.strip():
        translated = Krita.krita_i18n(val)
    return translated


# def i18n_lang() -> list[str]:
#     configPath = QStandardPaths.writableLocation(
#         QStandardPaths.StandardLocation.GenericConfigLocation
#     )
#     configPath = os.path.join(configPath, "klanguageoverridesrc")
#     if os.path.exists(configPath):
#         print(configPath)
#         settings = QSettings(configPath, QSettings.Format.IniFormat)
#         lang = settings.value("Language/krita")
#         if isinstance(lang, QByteArray):
#             lang = lang.data().decode("utf-8")
#         if isinstance(lang, str):
#             return lang.split(":")
#
#     return []
#
#
# def i18n(val: str) -> str:
#     global _translations
#     if _translations is None:
#         i18nPath = os.path.join(
#             os.path.dirname(os.path.abspath(__file__)), "i18n"
#         )
#         for lang in i18n_lang():
#             path = os.path.join(i18nPath, lang + ".json")
#             if os.path.exists(path):
#                 try:
#                     with open(path, "r", encoding="utf-8") as f:
#                         _translations = json.load(f)
#                 except Exception:
#                     pass
#                 if _translations is not None:
#                     break
#     if not isinstance(_translations, dict):
#         _translations = {}
#     return _translations.get(val, Krita.krita_i18n(val))
