import json
import time
from pathlib import Path

import pytest

from lineage_service.config import ClickHouseSettings, Settings
from lineage_service.datalens import auth


def make_settings(tmp_path: Path) -> Settings:
    return Settings(clickhouse=ClickHouseSettings(), sources={}, sinks={},
                    out_dir=tmp_path / "out", iam_cache_file=tmp_path / "cache.json")


def write_cache(path: Path, token: str, ts: float):
    path.write_text(json.dumps({"token": token, "timestamp": ts}), encoding="utf-8")


def test_env_token_has_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("DATALENS_IAM_TOKEN", "env-tok")
    write_cache(tmp_path / "cache.json", "cache-tok", time.time())
    assert auth.get_iam_token(make_settings(tmp_path)) == "env-tok"


def test_fresh_cache_is_used(tmp_path):
    s = make_settings(tmp_path)
    write_cache(s.iam_cache_file, "cache-tok", time.time())
    assert auth.get_iam_token(s) == "cache-tok"


def test_expired_cache_triggers_fetch(tmp_path, monkeypatch):
    s = make_settings(tmp_path)
    write_cache(s.iam_cache_file, "old", time.time() - s.iam_ttl_seconds - 10)
    monkeypatch.setattr(auth, "find_yc_executable", lambda: "yc")
    monkeypatch.setattr(auth.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "new-tok\n"})())
    assert auth.get_iam_token(s) == "new-tok"
    assert json.loads(s.iam_cache_file.read_text())["token"] == "new-tok"


def test_fetch_raises_without_yc(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "find_yc_executable", lambda: None)
    with pytest.raises(auth.AuthError):
        auth.fetch_new_token(tmp_path / "cache.json")


def test_fetch_raises_on_empty_token(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "find_yc_executable", lambda: "yc")
    monkeypatch.setattr(auth.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "  \n"})())
    with pytest.raises(auth.AuthError):
        auth.fetch_new_token(tmp_path / "cache.json")


def test_find_yc_uses_env_path(tmp_path, monkeypatch):
    exe = tmp_path / "yc.exe"
    exe.write_text("")
    monkeypatch.setenv("YC_CLI_PATH", str(exe))
    assert auth.find_yc_executable() == str(exe)


def test_refresh_uses_different_fresh_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("DATALENS_IAM_TOKEN", raising=False)
    s = make_settings(tmp_path)
    write_cache(s.iam_cache_file, "fresh-other", time.time())
    assert auth.refresh_iam_token(s, "used-tok") == "fresh-other"


def test_refresh_fetches_when_same_token(tmp_path, monkeypatch):
    monkeypatch.delenv("DATALENS_IAM_TOKEN", raising=False)
    s = make_settings(tmp_path)
    write_cache(s.iam_cache_file, "same", time.time())
    monkeypatch.setattr(auth, "find_yc_executable", lambda: "yc")
    monkeypatch.setattr(auth.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "brand-new"})())
    assert auth.refresh_iam_token(s, "same") == "brand-new"