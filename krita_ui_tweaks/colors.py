from .pyqt import (
    QColor,
)

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

def adjustColor(c, saturation=1.15, lightness=0.9):
    if saturation is None:
        saturation = 1.2 if lightness < 1 else 0.8

    h, s, l, a = c.getHsl()
    if h == -1:
        return (
            c.darker(int((1 + (1 - lightness)) * 100))
            if lightness < 1
            else c.lighter(int(lightness * 100))
        )
    s = min(255, int(s * saturation))
    l = min(255, max(0, int(l * lightness)))
    return QColor.fromHsl(h, s, l, a)

