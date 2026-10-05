import pytest


@pytest.fixture(autouse=True)
def every_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixtures mix sources; production uses AqarExit only (QAYEM_SOURCES). Tests opt back in to all."""
    monkeypatch.setenv("QAYEM_SOURCES", "all")
