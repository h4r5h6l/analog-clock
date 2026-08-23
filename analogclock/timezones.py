"""Timezone model: default zones, safe lookups, and the top/bottom pair."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TOP_TZ = "Europe/Berlin"
DEFAULT_BOTTOM_TZ = "Asia/Kolkata"


def _safe_zoneinfo(name):
    """Return ZoneInfo(name), or None when invalid -> system local time."""
    try:
        return ZoneInfo(str(name))
    except Exception:
        return None


def now_for(tz):
    """Current time in ``tz``, falling back to local time when tz is None."""
    return datetime.now(tz) if tz is not None else datetime.now()


@dataclass
class TimezonePair:
    """The two displayed timezones plus their resolved ZoneInfo objects."""

    top_name: str = DEFAULT_TOP_TZ
    bottom_name: str = DEFAULT_BOTTOM_TZ
    top_tz: object = None
    bottom_tz: object = None

    def __post_init__(self):
        self.top_tz = _safe_zoneinfo(self.top_name)
        self.bottom_tz = _safe_zoneinfo(self.bottom_name)

    def set(self, top_name, bottom_name):
        """Adopt new timezone strings; invalid ones fall back to local time."""
        self.top_name = str(top_name).strip()
        self.bottom_name = str(bottom_name).strip()
        self.top_tz = _safe_zoneinfo(self.top_name)
        self.bottom_tz = _safe_zoneinfo(self.bottom_name)

    def now_top(self):
        return now_for(self.top_tz)

    def now_bottom(self):
        return now_for(self.bottom_tz)
