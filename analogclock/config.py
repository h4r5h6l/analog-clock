"""JSON persistence: the single source of truth for everything written to disk.

Stores the window x/y plus appearance settings (manual palette, both
timezone names) so they survive restarts. The widget builds
the payload dict and unpacks the restored dict; this module only does the
file I/O.
"""

import json
from pathlib import Path

POSITION_CONFIG_DIR = Path.home() / ".config" / "analog-clock"
POSITION_CONFIG_PATH = POSITION_CONFIG_DIR / "window_position.json"


def save_window_position(payload: dict):
    """Persist ``payload`` as JSON. Best-effort: never raise to the caller."""
    try:
        POSITION_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        POSITION_CONFIG_PATH.write_text(json.dumps(payload))
    except (OSError, ValueError):
        # Persistence is best-effort; never break dragging over it.
        pass


def restore_window_position() -> dict | None:
    """Return the saved payload dict, or None when missing/corrupt."""
    try:
        return json.loads(POSITION_CONFIG_PATH.read_text())
    except (OSError, ValueError, TypeError, KeyError):
        return None
