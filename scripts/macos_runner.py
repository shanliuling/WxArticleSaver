# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""Frozen entry point for the WxArticleSaver macOS application bundle."""

from __future__ import annotations

import sys


def _run_embedded_mitmdump() -> int:
    """Run mitmdump from this frozen executable with the internal flag removed."""
    try:
        marker = sys.argv[1:].index("--mitmdump") + 1
    except ValueError:
        raise RuntimeError("缺少内部 mitmdump 调度参数。")
    sys.argv = [sys.argv[0], *sys.argv[marker + 1 :]]
    from mitmproxy.tools.main import mitmdump

    return int(mitmdump() or 0)


if "--mitmdump" in sys.argv[1:]:
    raise SystemExit(_run_embedded_mitmdump())

from launcher_macos import main


if __name__ == "__main__":
    raise SystemExit(main())
