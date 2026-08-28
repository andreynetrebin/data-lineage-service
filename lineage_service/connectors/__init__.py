"""Реестр коннекторов источников."""
from .clickhouse_catalog import ClickHouseCatalogConnector
from .datalens import DataLensConnector
# Этап 6:
# from .airflow import AirflowOpenLineageConnector
# from .extractor1c import Extractor1CConnector

REGISTRY = {
    "datalens": DataLensConnector,
    "clickhouse_catalog": ClickHouseCatalogConnector,
}