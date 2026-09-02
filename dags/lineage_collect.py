"""Airflow DAG: ежедневный сбор lineage + diff с предыдущим снапшотом."""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def collect_task():
    from lineage_service import cli
    cli.collect()


def diff_task(**context):
    from lineage_service import cli
    from lineage_service.sinks.clickhouse_sink import ClickHouseSink, create_client
    from lineage_service import config

    client = create_client(config.CLICKHOUSE)
    sink = ClickHouseSink(client)
    snaps = sink.list_snapshots(limit=2)
    if len(snaps) < 2:
        print("Недостаточно снапшотов для diff")
        return

    to_snap = snaps[0][0]
    from_snap = snaps[1][0]
    print(f"Diff: {from_snap} -> {to_snap}")
    cli.diff(from_snap, to_snap)


with DAG(
    dag_id="lineage_collect",
    start_date=datetime(2026, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    default_args={
        "owner": "data-team",
        "depends_on_past": False,
        "email_on_failure": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["lineage", "metadata"],
) as dag:
    collect_op = PythonOperator(
        task_id="collect_metadata",
        python_callable=collect_task,
    )

    diff_op = PythonOperator(
        task_id="diff_and_alert",
        python_callable=diff_task,
    )

    collect_op >> diff_op
