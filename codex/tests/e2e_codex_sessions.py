#!/usr/bin/env python3
"""Compatibility wrapper for the shipped ALIVE E2E verifier."""

from __future__ import annotations

import os
import sys
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "e2e_codex_sessions.py"
os.execv(sys.executable, [sys.executable, str(RUNNER), *sys.argv[1:]])
