# Purpose: Exact-input JSON cache so re-running `code` on the same responses and codebook is free.
"""Exact-input cache keyed by sha256 of the canonical request.

Why a plain JSON file: researchers re-run the same batch many times while
adjusting thresholds; a file they can inspect, copy and delete beats a
database. Errors are never cached, only validated answers.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any

from .client import JevResponse


class ExactInputCache:
    def __init__(self, path: str | None):
        self.path = path
        self._entries: dict[str, dict[str, Any]] = {}
        self._dirty = False
        self._lock = threading.Lock()
        self.hits = 0
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError(f"cache file {path} is not a JSON object")
            self._entries = data

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> JevResponse | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self.hits += 1
        return JevResponse(model=entry["model"], answers=entry["answers"], usage=dict(entry.get("usage", {})), cached=True, key=key)

    def put(self, key: str, response: JevResponse) -> None:
        with self._lock:
            self._entries[key] = {
                "model": response.model,
                "answers": response.answers,
                "usage": response.usage,
                "cached_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            self._dirty = True

    def save(self) -> None:
        """Atomic write (temp file + rename) so an interrupted run never leaves a half-written cache."""
        if not self.path or not self._dirty:
            return
        with self._lock:
            directory = os.path.dirname(os.path.abspath(self.path)) or "."
            fd, tmp = tempfile.mkstemp(prefix=".jev-cache-", suffix=".tmp", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(self._entries, fh, ensure_ascii=False, indent=1, sort_keys=True)
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            self._dirty = False
