"""Give every test its own freshly seeded database."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from backend import db


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))
    db.seed()
    yield
