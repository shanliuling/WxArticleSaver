# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""Filesystem locations shared by source and packaged macOS runs."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
APP_DATA_DIR = Path.home() / "Library" / "Application Support" / "WxArticleSaver"


def data_root() -> Path:
    """Return a writable directory for runtime state and exported articles."""
    configured = os.environ.get("WXAS_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return APP_DATA_DIR
    return PROJECT_ROOT
