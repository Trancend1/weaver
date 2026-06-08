"""Weaver exception hierarchy. No internal imports allowed."""


class WeaverError(Exception):
    """Base class for all Weaver-raised exceptions."""


class ConfigError(WeaverError):
    """Invalid or unparseable project configuration."""


class EpubReadError(WeaverError):
    """Source EPUB cannot be read or is malformed."""


class EpubWriteError(WeaverError):
    """Translated EPUB cannot be written."""


class ExportError(WeaverError):
    """A TXT or HTML export artifact cannot be written."""


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


class GlossaryTermNotFoundError(WeaverError):
    """Requested glossary term source does not exist in the project."""


class CharacterNotFoundError(WeaverError):
    """Requested character (by Japanese name) does not exist in the project."""


class TranslationMemoryNotFoundError(WeaverError):
    """Requested translation-memory entry (by source hash) does not exist."""


class SecretNotFoundError(WeaverError):
    """Requested secret (by env-var name) is not in the local secret store."""


class GlossaryCandidateNotFoundError(WeaverError):
    """Requested glossary candidate id does not exist (or was already actioned)."""


class ParserError(WeaverError):
    """Provider JSON output could not be parsed even after repair."""


class SegmentNotFoundError(WeaverError):
    """Requested segment id does not exist in the project database."""


class ChapterNotFoundError(WeaverError):
    """Requested chapter id does not exist in the project database."""


class VolumeNotFoundError(WeaverError):
    """Requested volume id does not exist in the project database."""


class DatabaseError(WeaverError):
    """SQLite operation failed in an unrecoverable way."""


class ProjectNotFoundError(WeaverError):
    """Requested project directory does not exist under the books dir."""


class CandidateNotFoundError(WeaverError):
    """Requested translation candidate (by id) does not exist."""


class CharacterDraftNotFoundError(WeaverError):
    """Requested character page draft (by id) does not exist."""
