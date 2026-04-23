"""Custom exception hierarchy for orcSONAR."""


class OrcSonarError(Exception):
    """Base exception for all orcSONAR errors."""


class DataSourceError(OrcSonarError):
    """Raised when a local data file is missing or malformed."""


class APIError(OrcSonarError):
    """Raised when a remote API call fails after all retries."""

    def __init__(self, source: str, message: str) -> None:
        self.source = source
        super().__init__(f"[{source}] {message}")


class CacheError(OrcSonarError):
    """Raised on SQLite cache read/write failure."""


class ScoringError(OrcSonarError):
    """Raised when score computation cannot proceed."""
