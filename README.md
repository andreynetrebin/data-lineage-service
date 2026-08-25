# data-lineage-service

Data Catalog + Data Lineage для стека 1С → ClickHouse → Airflow → DataLens.
Разработка ведётся этапами с тест-гейтами: переход к этапу N+1 только после зелёных тестов этапа N.

## Установка и тесты
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
pytest -q
```