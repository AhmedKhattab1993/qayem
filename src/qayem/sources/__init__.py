"""Source registry: name → class. Tier-1 resale sources."""

from __future__ import annotations

from .aqarexit import AqarExitSource
from .aqarmap import AqarmapSource
from .base import BaseSource, NormalizedListing
from .coldwellbanker import ColdwellBankerSource
from .gpm import GpmSource
from .nawy import NawyPrimarySource, NawySource
from .opensooq import OpenSooqSource
from .semsar import SemsarSource

SOURCE_REGISTRY: dict[str, type[BaseSource]] = {
    NawySource.name: NawySource,
    NawyPrimarySource.name: NawyPrimarySource,
    OpenSooqSource.name: OpenSooqSource,
    AqarmapSource.name: AqarmapSource,
    SemsarSource.name: SemsarSource,
    GpmSource.name: GpmSource,
    ColdwellBankerSource.name: ColdwellBankerSource,
    AqarExitSource.name: AqarExitSource,
}

__all__ = ["SOURCE_REGISTRY", "BaseSource", "NormalizedListing"]
