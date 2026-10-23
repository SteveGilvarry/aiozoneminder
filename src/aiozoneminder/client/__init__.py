"""ZoneMinder clients, one per API.

ZoneMinder has two APIs:

* :class:`~.legacy.ZoneMinderLegacyClient` - ZoneMinder's built-in CakePHP API.
* :class:`~.v3.ZoneMinderV3Client` - the standalone ``zm-api`` Rust REST server.

Both implement :class:`~.base.ZoneMinderClient`, so callers don't need to
know which one they have.
"""

from .base import ZoneMinderClient
from .legacy import ZoneMinderLegacyClient
from .v3 import ZoneMinderV3Client

__all__ = [
    "ZoneMinderClient",
    "ZoneMinderLegacyClient",
    "ZoneMinderV3Client",
]
