"""Реестр коннекторов источников."""
from .datalens import DataLensConnector
# Этап 5: from .clickhouse_catalog import ClickHouseCatalogConnector
# Этап 6: from .airflow import AirflowOpenLineageConnector
#         from .extractor1c import Extractor1CConnector

REGISTRY = {
    "datalens": DataLensConnector,
}
