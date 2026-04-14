"""Library subsystem — provider-based game/app discovery."""

from pixiis.library.base import LibraryProvider
from pixiis.library.icons import IconCache
from pixiis.library.manual import ManualProvider
from pixiis.library.registry import AppRegistry, LibraryUpdatedEvent
from pixiis.library.startmenu import StartMenuProvider
from pixiis.library.steam import SteamProvider
from pixiis.library.xbox import XboxProvider

__all__ = [
    "AppRegistry",
    "IconCache",
    "LibraryProvider",
    "LibraryUpdatedEvent",
    "ManualProvider",
    "StartMenuProvider",
    "SteamProvider",
    "XboxProvider",
]
