"""Sinks: приёмники собранных снапшотов графа."""
from .base import Sink
from .json_sink import JsonSink
from .clickhouse_sink import ClickHouseSink, create_client

__all__ = ["Sink", "JsonSink", "ClickHouseSink", "create_client"]