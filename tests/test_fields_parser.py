"""Тесты парсера ответа getDataset на фикстуре «Коэффициент наценки»."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lineage_service.datalens import fields_parser as fp

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def koef_nacenki() -> dict:
    path = FIXTURE_DIR / "get_dataset_koef_nacenki.json"
    if not path.exists():
        pytest.skip(f"Фикстура не найдена: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_parse_returns_structured_dataset(koef_nacenki):
    parsed = fp.parse_dataset(koef_nacenki)
    assert parsed.dataset_id == "i4nfn0waon1q1"
    assert parsed.name == "Коэффициент наценки"
    assert len(parsed.sources) == 3
    assert len(parsed.avatars) == 3
    assert len(parsed.avatar_relations) == 2
    assert len(parsed.field_dependencies) == 7
    assert len(parsed.fields) >= 50


def test_parse_rejects_non_dict():
    with pytest.raises(ValueError):
        fp.parse_dataset([])


def test_avatars_parsed_with_source_id_and_is_root(koef_nacenki):
    parsed = fp.parse_dataset(koef_nacenki)
    by_id = {av.id: av for av in parsed.avatars}
    root = next(av for av in parsed.avatars if av.is_root)
    assert root.id == "bf3df1a0-76fc-11f1-9155-6d55ddd5ea47"
    assert root.title == "Коэф. наценки факт-план"
    assert root.source_id == "b943a3d2-76fc-11f1-9155-6d55ddd5ea47"

    nomenklatura = by_id["c3f6bec0-76fc-11f1-9155-6d55ddd5ea47"]
    assert nomenklatura.is_root is False
    assert nomenklatura.source_id == "c3f6bec2-76fc-11f1-9155-6d55ddd5ea47"


def test_extracts_tables_from_ch_table(koef_nacenki):
    parsed = fp.parse_dataset(koef_nacenki)
    ch_table_src = next(s for s in parsed.sources if s.source_type == "CH_TABLE")
    assert "extractor.Номенклатура" in ch_table_src.tables


def test_extracts_tables_from_subsql(koef_nacenki):
    parsed = fp.parse_dataset(koef_nacenki)
    subs = [s for s in parsed.sources if s.source_type == "CH_SUBSELECT"]
    all_tbls: set = set()
    for s in subs:
        all_tbls.update(s.tables)
    assert "extractor.РН_ДанныеПоПрибыли" in all_tbls
    assert "extractor.HW_ПлановыеПоказатели" in all_tbls
    assert "extractor.HW_ПризнакиНоменклатурыСрез" in all_tbls
    for cte in ("dpp_base", "dpp_by_nomenclature", "dpp_data", "plan_data"):
        assert cte not in all_tbls


def test_all_tables_returns_unique_sorted_list(koef_nacenki):
    parsed = fp.parse_dataset(koef_nacenki)
    tables = fp.all_tables(parsed)
    assert tables == sorted(set(tables))
    assert any(t.endswith("Номенклатура") for t in tables)


def test_extract_tables_from_sql_handles_cte():
    sql = """
    WITH base AS (SELECT x FROM extractor.t1)
    SELECT * FROM base JOIN extractor.t2 ON base.id = extractor.t2.id
    """
    assert fp.extract_tables_from_sql(sql) == ["extractor.t1", "extractor.t2"]


def test_extract_tables_returns_empty_for_invalid_sql():
    assert fp.extract_tables_from_sql("this is not sql !!!") == []


def test_avatar_relations_parsed(koef_nacenki):
    parsed = fp.parse_dataset(koef_nacenki)
    assert len(parsed.avatar_relations) == 2
    assert {r.join_type for r in parsed.avatar_relations} == {"left"}

    first = next(r for r in parsed.avatar_relations
                 if any(c.left_source == "НоменклатураГуид" and
                        c.right_source == "СсылкаГуид" for c in r.conditions))
    assert len(first.conditions) == 1
    assert first.conditions[0].operator == "eq"

    second = next(r for r in parsed.avatar_relations if len(r.conditions) == 2)
    sources = {(c.left_source, c.right_source) for c in second.conditions}
    assert ("Период", "Дата") in sources
    assert ("НоменклатураГуид", "НоменклатураГуид") in sources


def test_field_dependencies_parsed(koef_nacenki):
    parsed = fp.parse_dataset(koef_nacenki)
    deps_by_id = {d.field_id: d.depends_on for d in parsed.field_dependencies}
    assert "2ad94990-76fe-11f1-9155-6d55ddd5ea47" in deps_by_id
    assert set(deps_by_id["2ad94990-76fe-11f1-9155-6d55ddd5ea47"]) == {
        "vyruchkazakazyiu_1_1n92", "summazakupkizakazyiu_1_8skq",
    }
    assert set(deps_by_id["77b8a840-79e8-11f1-a607-6d1234bd4169"]) == {"priznak_yz0g"}


def test_result_schema_fields_parsed(koef_nacenki):
    parsed = fp.parse_dataset(koef_nacenki)
    by_guid = {f.guid: f for f in parsed.fields}

    period = by_guid["period_1rxa"]
    assert period.title == "Период"
    assert period.type == "DIMENSION"
    assert period.calc_mode == "direct"
    assert period.source == "Период"
    assert period.avatar_id == "bf3df1a0-76fc-11f1-9155-6d55ddd5ea47"

    koef = by_guid["2ad94990-76fe-11f1-9155-6d55ddd5ea47"]
    assert koef.type == "MEASURE"
    assert koef.calc_mode == "formula"
    assert koef.formula and "Выручка(ЗаказыИУ)" in koef.formula

    markup = by_guid["64a09e00-796d-11f1-917b-b58a72229363"]
    assert markup.data_type == "markup"
    assert markup.formula and "MARKUP" in markup.formula
