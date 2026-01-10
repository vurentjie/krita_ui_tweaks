from dataclasses import dataclass
from typing import Protocol

from .helper import Helper

@dataclass
class ColorScheme:
    bar: str
    tab: str
    tabSeparator: str
    tabSelected: str
    tabActive: str
    tabText: str
    tabClose: str
    menuSeparator: str
    splitHandle: str
    dropZone: str
    dragTab: str


class HasColorScheme(Protocol):
    def colors(self) -> ColorScheme: ...
    def helper(self) -> Helper: ...
