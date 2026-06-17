from __future__ import annotations

import os
import subprocess
import sys
import time


class NetworkPathReconnector:
    _global_last_attempt: dict[str, float] = {}

    def __init__(self, enabled: bool = True, interval_seconds: int = 60) -> None:
        self.enabled = enabled
        self.interval_seconds = max(5, int(interval_seconds))

    def ensure_paths(self, paths: list[str]) -> list[str]:
        errors: list[str] = []
        if not self.enabled:
            return errors
        for path in paths:
            root = self._root_for(path)
            if not root or not self._should_attempt(root):
                continue
            try:
                self._poke(root)
            except Exception as exc:
                errors.append(f"网络路径重连失败 {root}: {exc}")
        return errors

    def _should_attempt(self, root: str) -> bool:
        now = time.monotonic()
        last = self._global_last_attempt.get(root, 0.0)
        if now - last < self.interval_seconds:
            return False
        self._global_last_attempt[root] = now
        return True

    def _root_for(self, path: str) -> str:
        path = (path or "").strip()
        if not path:
            return ""
        normalized = os.path.normpath(path)
        drive, _tail = os.path.splitdrive(normalized)
        if drive:
            return drive + os.sep
        if normalized.startswith("\\\\"):
            parts = [part for part in normalized.split("\\") if part]
            if len(parts) >= 2:
                return "\\\\" + parts[0] + "\\" + parts[1]
        return ""

    def _poke(self, root: str) -> None:
        if os.path.exists(root):
            return
        if not sys.platform.startswith("win"):
            os.path.exists(root)
            return

        drive = root.rstrip("\\/")
        if len(drive) == 2 and drive[1] == ":":
            subprocess.run(
                ["cmd", "/c", "net", "use", drive],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            subprocess.run(
                ["cmd", "/c", "dir", root],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            try:
                os.listdir(root)
            except FileNotFoundError:
                raise
