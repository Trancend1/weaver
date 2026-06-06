"""Open a URL in the user's real default browser.

Editors such as VS Code inject a ``BROWSER`` environment variable into their
integrated terminal so that :func:`webbrowser.open` routes to the editor's
embedded "Simple Browser" / port-forwarder instead of the OS default browser.
For the local cockpit we want the user's actual browser (Chrome, Edge, Firefox,
...), so we deliberately bypass that override when opening.

This lives at the CLI boundary: failing to pop a browser is never fatal — the
caller has already printed the URL for manual use.
"""

from __future__ import annotations

import os
import webbrowser

# Controllers to try, in order, after the editor override is removed. ``None``
# asks :mod:`webbrowser` for its platform default; the named controllers exist
# only on their own platform and are skipped elsewhere.
_PREFERRED = ("windows-default", "macosx", None)


def open_in_external_browser(url: str) -> bool:
    """Open *url* in the OS-default browser, ignoring an editor's ``$BROWSER``.

    Returns ``True`` when a browser controller reported success, ``False``
    otherwise. Never raises: the caller treats auto-open as best-effort.
    """
    saved = os.environ.pop("BROWSER", None)
    try:
        for name in _PREFERRED:
            try:
                controller = webbrowser.get(name)
            except webbrowser.Error:
                continue
            try:
                if controller.open(url, new=2):
                    return True
            except webbrowser.Error:
                continue
        return False
    finally:
        if saved is not None:
            os.environ["BROWSER"] = saved
