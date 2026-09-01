"""Реестр коннекторов источников."""
from .airflow_openlineage import AirflowOpenLineageConnector
from .clickhouse_catalog import ClickHouseCatalogConnector
from .datalens import DataLensConnector
from .extractor1c import Extractor1CConnector

REGISTRY = {
    "datalens": DataLensConnector,
    "clickhouse_catalog": ClickHouseCatalogConnector,
    "airflow_openlineage": AirflowOpenLineageConnector,
    "extractor_1c": Extractor1CConnector,
}
