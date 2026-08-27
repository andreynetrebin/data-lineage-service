import textwrap
from pathlib import Path

from lineage_service.config import load_settings


def write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_defaults_when_no_file(tmp_path):
    s = load_settings(config_path=tmp_path / "missing.yaml", env={})
    assert s.clickhouse.host == "localhost"
    assert s.clickhouse.port == 8123
    assert s.clickhouse.batch_size == 1000
    assert s.sinks == {"clickhouse": True, "json": True}
    assert s.enabled_sources() == {}
    assert s.datalens_org_id is None


def test_yaml_values_and_env_priority(tmp_path):
    cfg = write_yaml(tmp_path, """
        clickhouse:
          host: yaml-host
          port: 9100
          database: yamldb
        sources:
          datalens: {enabled: true}
          clickhouse_catalog: {enabled: false, databases: [extractor]}
        sinks: {clickhouse: true, json: false}
    """)
    env = {"CLICKHOUSE_HOST": "env-host", "DATALENS_ORG_ID": "org1"}
    s = load_settings(config_path=cfg, env=env)

    assert s.clickhouse.host == "env-host"     # env выше yaml
    assert s.clickhouse.port == 9100           # yaml выше дефолта
    assert s.clickhouse.database == "yamldb"
    assert s.datalens_org_id == "org1"
    assert s.sinks == {"clickhouse": True, "json": False}
    assert set(s.enabled_sources()) == {"datalens"}
    assert s.sources["clickhouse_catalog"].params == {"databases": ["extractor"]}