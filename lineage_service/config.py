"""Конфигурация: config.yaml + переменные окружения (env имеет приоритет)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*a, **k):  # type: ignore
        return None


@dataclass(frozen=True)
class ClickHouseSettings:
    host: str = "localhost"
    port: int = 9000
    user: str = "default"
    password: str = ""
    database: str = "default"
    batch_size: int = 1000


@dataclass(frozen=True)
class SourceSettings:
    enabled: bool = False
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Settings:
    clickhouse: ClickHouseSettings
    sources: Dict[str, SourceSettings]
    sinks: Dict[str, bool]
    out_dir: Path
    datalens_org_id: Optional[str] = None
    api_delay: float = 0.5
    iam_cache_file: Path = Path(".iam_token_cache.json")   # NEW
    iam_ttl_seconds: int = 11 * 60 * 60                    # NEW

    def enabled_sources(self) -> Dict[str, SourceSettings]:
        return {n: s for n, s in self.sources.items() if s.enabled}


def load_settings(config_path: Optional[Any] = None,
                  env: Optional[Dict[str, str]] = None) -> Settings:
    """Загружает настройки. `env` можно передать явно (для тестов)."""
    if env is None:
        load_dotenv()
        env_map: Dict[str, str] = os.environ
    else:
        env_map = env

    path = Path(config_path) if config_path else Path(env_map.get("LINEAGE_CONFIG", "config.yaml"))
    raw: Dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    ch = raw.get("clickhouse", {}) or {}
    clickhouse = ClickHouseSettings(
        host=env_map.get("CLICKHOUSE_HOST", ch.get("host", "localhost")),
        port=int(env_map.get("CLICKHOUSE_PORT", ch.get("port", 8123))),
        user=env_map.get("CLICKHOUSE_USER", ch.get("user", "default")),
        password=env_map.get("CLICKHOUSE_PASSWORD", ch.get("password", "")),
        database=env_map.get("CLICKHOUSE_DATABASE", ch.get("database", "default")),
        batch_size=int(ch.get("batch_size", 1000)),
    )

    sources = {
        name: SourceSettings(
            enabled=bool((s or {}).get("enabled", False)),
            params={k: v for k, v in (s or {}).items() if k != "enabled"},
        )
        for name, s in (raw.get("sources", {}) or {}).items()
    }

    sinks = dict(raw.get("sinks", {}) or {"clickhouse": True, "json": True})
    out_dir = Path((raw.get("output", {}) or {}).get("dir", "out"))
    _auth = raw.get("auth", {}) or {}

    return Settings(
        clickhouse=clickhouse,
        sources=sources,
        sinks=sinks,
        out_dir=out_dir,
        datalens_org_id=env_map.get("DATALENS_ORG_ID"),
        api_delay=float((raw.get("api", {}) or {}).get("delay", 0.5)),
        iam_cache_file=Path(env_map.get("IAM_TOKEN_CACHE_FILE", _auth.get("cache_file", ".iam_token_cache.json"))),
        iam_ttl_seconds=int(_auth.get("ttl_seconds", 11 * 60 * 60)),
    )