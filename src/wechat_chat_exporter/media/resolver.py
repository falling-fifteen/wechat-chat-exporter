"""Attach decrypted image bytes to messages."""

from __future__ import annotations

from ..crypto.key_source import ImageKey
from ..model import local_type as lt
from ..model.message import Attachment, Message
from .image import decrypt_dat, key_candidates
from .index import ImageIndex

MAX_IMAGE_BYTES = 64 * 1024 * 1024


class ImageResolver:
    def __init__(
        self,
        index: ImageIndex,
        image_key: ImageKey | None = None,
        *,
        mode: str = "auto",
    ):
        self.index = index
        self.image_key = image_key
        self.mode = mode
        self._cache: dict[str, tuple[str, bytes] | None] = {}

    def resolve(self, msg: Message) -> None:
        if msg.base_type != lt.IMAGE or self.mode in ("none", "placeholder"):
            return
        md5 = str(msg.extra.get("image_md5") or "")
        if not md5:
            msg.attachment = Attachment(kind="image", error="no_md5")
            return
        if md5 in self._cache:
            cached = self._cache[md5]
            if cached is None:
                msg.attachment = Attachment(kind="image", error="unsupported")
            else:
                ext, data = cached
                msg.attachment = Attachment(kind="image", data=data, ext=ext)
            return

        path = self.index.find(md5)
        if path is None:
            self._cache[md5] = None
            msg.attachment = Attachment(kind="image", error="not_found")
            return
        try:
            if path.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError("image too large")
            raw = path.read_bytes()
            candidates = key_candidates(str(msg.extra.get("image_aeskey") or ""))
            if self.image_key:
                candidates.extend(self.image_key.aes_keys)
            xor_key = self.image_key.xor_key if self.image_key else 0
            ext, data = decrypt_dat(raw, xor_key=xor_key, aes_candidates=candidates)
        except (OSError, ValueError):
            self._cache[md5] = None
            msg.attachment = Attachment(kind="image", error="unsupported")
            return
        self._cache[md5] = (ext, data)
        msg.attachment = Attachment(kind="image", data=data, ext=ext, source_path=str(path))
