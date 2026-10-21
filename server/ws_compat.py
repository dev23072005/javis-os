"""WebSocket compression off for every launch path (0.197.1).

Why. Safari drops the dashboard's live socket for minutes while Chrome, open on the same server at the same moment,
stays connected (customer report 17/10/2026). uvicorn negotiates permessage-deflate by default, and Safari's
implementation of it fails on some compressed messages: the browser closes the socket with a protocol error (Apple
developer forums threads 744018 and 706961). The message that trips it is sent again on every reconnect (the `hello`
snapshot, the next streamed chunk), so the page reconnects into the same failure over and over. Without compression
the frames are plain and every browser reads them.

How. uvicorn is started in several ways: the Docker image (`python -m uvicorn` CLI), install.sh's systemd unit and
nohup line, update.sh, launchd, and `python main.py`. Units already written on users' machines are not rewritten by an
update, so a launch flag alone would miss them. uvicorn reads `config.ws_per_message_deflate` each time a WebSocket
connection is built, and main.py is imported before the first connection, so `disable_deflate()` (called at main.py
import) turns the setting into a read-only False on the Config class: a data descriptor on the class wins over the
value uvicorn's __init__ stored on the instance. The cost is bandwidth only: chat frames are small text deltas.

`JAVIS_WS_DEFLATE=1` keeps uvicorn's compression (for a setup that needs it and has no Safari users).
"""
from __future__ import annotations

import os


def wanted() -> bool:
    """True when the operator asked to keep WebSocket compression on."""
    return str(os.environ.get("JAVIS_WS_DEFLATE", "")).strip().lower() in ("1", "true", "yes", "on")


def disable_deflate() -> bool:
    """Make every uvicorn Config report ws_per_message_deflate=False. Returns True when applied."""
    if wanted():
        return False
    try:
        from uvicorn import config as uv_config
    except Exception:  # noqa: BLE001 - no uvicorn (tests, another server): nothing to change
        return False
    uv_config.Config.ws_per_message_deflate = property(lambda self: False, lambda self, value: None)
    return True
