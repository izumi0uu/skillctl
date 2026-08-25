#!/usr/bin/env python3
# <xbar.title>Personal xbar</xbar.title>
# <xbar.version>3.2.0</xbar.version>
# <xbar.author>Local</xbar.author>
# <xbar.desc>Personal agents, AI.INPUT.IM health and subscription quota, and Spotify Web controls.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>

"""Thin xbar entrypoint; feature plugins are registered in personal_xbar.app."""

from __future__ import annotations

import sys
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve()
for support_root in (ENTRYPOINT.parent, ENTRYPOINT.parent / ".personal-xbar"):
    if (support_root / "personal_xbar").is_dir():
        sys.path.insert(0, str(support_root))
        break

# Preserve the public module surface used by the deterministic verifier.
from personal_xbar.runtime import *  # noqa: E402,F403
from personal_xbar.app import build_registry, main as run_personal_xbar  # noqa: E402,F401


if __name__ == "__main__":
    run_personal_xbar(ENTRYPOINT, sys.argv[1:])
