import inspect

from src.application import REPOSITORY_CACHE_VERSION, _repository


def test_repository_cache_is_explicitly_versioned() -> None:
    parameters = inspect.signature(_repository).parameters

    assert "cache_version" in parameters
    assert REPOSITORY_CACHE_VERSION == "usage-baseline-v1"
