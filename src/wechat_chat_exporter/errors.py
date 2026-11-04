"""Exception hierarchy and process exit codes."""

from __future__ import annotations


class WxError(Exception):
    """Base class for all expected errors."""

    exit_code = 5


class UsageError(WxError):
    """Bad CLI usage or unsupported option combination."""

    exit_code = 2


class KeySourceError(WxError):
    """The database key is missing or malformed."""

    exit_code = 3


class DecryptError(WxError):
    """Decryption failed (wrong key, corrupt page, unsupported cipher profile)."""

    exit_code = 3


class UnsupportedSchemaError(WxError):
    """The database layout is not a supported WeChat 4.x schema."""

    exit_code = 3


class MediaError(WxError):
    """Media decoding failed for one item; usually downgraded, not fatal."""

    exit_code = 5


class ExportError(WxError):
    """Writing an output file failed."""

    exit_code = 5


class ValidationError(WxError):
    """Export validation failed."""

    exit_code = 4
