"""Shared reader interface and safety limits.

Every format-specific reader implements `sniff` (cheap, content-based format
detection) and `parse` (turn raw bytes into a `Measurement`). Readers never
receive a trusted file extension alone as a signal; `sniff` inspects
content, treating every upload as untrusted.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from biosensor.schema import Measurement

# Hard ceiling on bytes a reader will look at / hold in memory. Guards
# against a malformed or hostile upload causing unbounded resource use.
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_DATA_ROWS = 200_000


class UnsupportedFormatError(ValueError):
    """Raised when no reader's sniff() matches the given content."""


class ParseError(ValueError):
    """Raised when a reader recognizes the format but fails to parse it."""


class FileTooLargeError(ParseError):
    """Raised when a file exceeds the byte or data-row ceiling.

    A ParseError subclass, so existing `except ParseError` handlers still
    catch it, but distinguishable for error categorization.
    """


# Stable, user-facing error categories for batch reporting and the viewer.
ERROR_CATEGORIES = ("unsupported", "parse", "too_large", "corrupt", "unexpected")


def classify_error(exc: BaseException) -> str:
    """Map a parse-time exception to one of ERROR_CATEGORIES.

    The most specific types are checked first: FileTooLargeError and
    UnsupportedFormatError are both ValueError subclasses.
    """
    if isinstance(exc, FileTooLargeError):
        return "too_large"
    if isinstance(exc, UnsupportedFormatError):
        return "unsupported"
    if isinstance(exc, ParseError):
        return "parse"
    if isinstance(exc, ValueError):
        return "corrupt"
    return "unexpected"


class Reader(ABC):
    name: str = "base"

    @abstractmethod
    def sniff(self, raw: bytes, filename: str) -> bool:
        """Return True if this reader believes it can parse `raw`.

        Must be cheap (header/signature inspection only, not a full parse)
        and must not raise; a reader that can't tell should return False.
        """

    @abstractmethod
    def parse(self, raw: bytes, filename: str) -> Measurement:
        """Parse raw file bytes into a Measurement. May raise ParseError."""


def enforce_size_limit(raw: bytes, filename: str) -> None:
    if len(raw) > MAX_FILE_BYTES:
        raise FileTooLargeError(
            f"{filename}: file is {len(raw)} bytes, exceeds the "
            f"{MAX_FILE_BYTES} byte limit for parsing"
        )
