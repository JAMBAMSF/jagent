# tests/conftest.py
import os, pathlib, sqlite3, pytest

@pytest.fixture
def tmp_db_path(tmp_path, monkeypatch):
    # point the app at a throwaway DB file for each test session
    db = tmp_path / "test.db"
    # monkeypatch agent.config.DB_PATH BEFORE importing agent.memory
    monkeypatch.setenv("DB_PATH", str(db))          # if your config reads env
    # also patch the module attribute directly after import
    import agent.config as cfg
    cfg.DB_PATH = str(db)
    return str(db)

@pytest.fixture
def conn(tmp_db_path):
    from agent.memory import connect
    c = connect(tmp_db_path)
    try:
        yield c
    finally:
        c.close()
