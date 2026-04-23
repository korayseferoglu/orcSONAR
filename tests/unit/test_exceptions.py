"""Unit tests for src/core/exceptions.py."""

from src.core.exceptions import APIError, CacheError, DataSourceError, OrcSonarError, ScoringError


def test_hierarchy():
    assert issubclass(DataSourceError, OrcSonarError)
    assert issubclass(APIError, OrcSonarError)
    assert issubclass(CacheError, OrcSonarError)
    assert issubclass(ScoringError, OrcSonarError)


def test_api_error_message():
    err = APIError(source="gnomAD", message="timeout after 3 retries")
    assert "[gnomAD]" in str(err)
    assert err.source == "gnomAD"


def test_catch_as_base():
    try:
        raise ScoringError("weight sum != 1.0")
    except OrcSonarError as e:
        assert "weight" in str(e)
