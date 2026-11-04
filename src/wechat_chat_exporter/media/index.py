"""Fast md5 -> .dat path lookup for WeChat 4.x attachments."""

from __future__ import annotations

from pathlib import Path

_SUFFIXES = ("_t", "_h", "_b", "_c", "_w", "_l")


def _base_name(stem: str) -> str:
    for suffix in _SUFFIXES:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


class ImageIndex:
    def __init__(self, attach_dir: Path | None, account_dir: Path | None = None):
        self.attach_dir = attach_dir
        self.account_dir = account_dir
        self._index: dict[str, Path] | None = None

    def _priority(self, stem: str) -> int:
        if stem.endswith("_t"):
            return 4
        if stem.endswith("_h"):
            return 1
        if stem.endswith("_b"):
            return 2
        if stem.endswith(("_c", "_w", "_l")):
            return 3
        return 0

    def _build(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        if not self.attach_dir or not self.attach_dir.is_dir():
            return index
        for path in self.attach_dir.rglob("*.dat"):
            if not path.is_file():
                continue
            try:
                if self.account_dir and self.account_dir.resolve() not in path.resolve().parents:
                    continue
            except OSError:
                continue
            stem = path.stem.lower()
            key = _base_name(stem)
            current = index.get(key)
            if current is None or self._priority(stem) < self._priority(current.stem.lower()):
                index[key] = path
        return index

    def find(self, md5: str) -> Path | None:
        if not md5:
            return None
        if self._index is None:
            self._index = self._build()
        return self._index.get(md5.lower())
