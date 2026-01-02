# SPDX-License-Identifier: CC0-1.0

from krita import Krita
from .plugin import Plugin

instance = Krita.instance()
instance.addExtension(Plugin(instance))
