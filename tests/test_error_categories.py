"""Error taxonomy: every parse-time failure maps to a stable, user-facing
category, and the too-large signal is distinguishable from a generic parse
failure while still being caught by existing `except ParseError` handlers.
"""

from __future__ import annotations

from biosensor.readers.base import (
    ERROR_CATEGORIES,
    FileTooLargeError,
    ParseError,
    UnsupportedFormatError,
    classify_error,
)


def test_classify_error_maps_each_type_to_its_category():
    assert classify_error(FileTooLargeError("x")) == "too_large"
    assert classify_error(UnsupportedFormatError("x")) == "unsupported"
    assert classify_error(ParseError("x")) == "parse"
    assert classify_error(ValueError("x")) == "corrupt"
    assert classify_error(RuntimeError("x")) == "unexpected"


def test_too_large_is_checked_before_generic_parse():
    # FileTooLargeError subclasses ParseError, so the order in classify_error
    # matters: it must resolve to "too_large", never fall through to "parse".
    assert issubclass(FileTooLargeError, ParseError)
    assert classify_error(FileTooLargeError("x")) == "too_large"


def test_every_category_is_declared():
    for exc in (
        FileTooLargeError(""),
        UnsupportedFormatError(""),
        ParseError(""),
        ValueError(""),
        RuntimeError(""),
    ):
        assert classify_error(exc) in ERROR_CATEGORIES
