"""Weaver exception hierarchy. No internal imports allowed."""


class WeaverError(Exception):
    """Base class for all Weaver-raised exceptions."""


class ConfigError(WeaverError):
    """Invalid or unparseable project configuration."""


class EpubReadError(WeaverError):
    """Source EPUB cannot be read or is malformed."""


class EpubWriteError(WeaverError):
    """Translated EPUB cannot be written."""


class ProviderError(WeaverError):
    """Base class for LLM provider failures."""

    retryable: bool = False


class ProviderTimeout(ProviderError):
    """Provider call exceeded the configured timeout."""

    retryable: bool = True


class ProviderUnavailable(ProviderError):
    """Provider is unreachable or unhealthy."""

    retryable: bool = False


class ProviderResponseError(ProviderError):
    """Provider returned an unexpected or malformed response."""

    retryable: bool = True


class GlossaryConflictError(WeaverError):
    """Two approved glossary terms disagree on the same source."""


class ParserError(WeaverError):
    """Provider JSON output could not be parsed even after repair."""


class SegmentNotFoundError(WeaverError):
    """Requested segment id does not exist in the project database."""


class ChapterNotFoundError(WeaverError):
    """Requested chapter id does not exist in the project database."""


class DatabaseError(WeaverError):
    """SQLite operation failed in an unrecoverable way."""
