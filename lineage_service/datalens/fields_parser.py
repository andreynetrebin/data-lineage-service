"""Парсер ответа getDataset: источники, таблицы, аватары, джойны, зависимости полей."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import sqlglot
from sqlglot import exp


@dataclass
class SourceInfo:
    id: str
    source_type: str
    title: str
    tables: List[str] = field(default_factory=list)
    connection_id: Optional[str] = None
    subsql: Optional[str] = None


@dataclass
class AvatarInfo:
    id: str
    title: str
    source_id: str
    is_root: bool


@dataclass
class JoinCondition:
    left_source: str
    right_source: str
    operator: str


@dataclass
class AvatarRelation:
    id: str
    left_avatar_id: str
    right_avatar_id: str
    join_type: str
    conditions: List[JoinCondition] = field(default_factory=list)


@dataclass
class FieldInfo:
    guid: str
    title: str
    type: str
    data_type: str
    calc_mode: str
    formula: Optional[str] = None
    avatar_id: Optional[str] = None
    source: Optional[str] = None


@dataclass
class FieldDependency:
    field_id: str
    depends_on: List[str] = field(default_factory=list)


@dataclass
class ParsedDataset:
    dataset_id: str
    name: str
    sources: List[SourceInfo] = field(default_factory=list)
    avatars: List[AvatarInfo] = field(default_factory=list)
    avatar_relations: List[AvatarRelation] = field(default_factory=list)
    fields: List[FieldInfo] = field(default_factory=list)
    field_dependencies: List[FieldDependency] = field(default_factory=list)


def extract_tables_from_sql(sql: str, dialect: str = "clickhouse") -> List[str]:
    if not sql:
        return []
    try:
        parsed = sqlglot.parse(sql, read=dialect)
    except Exception:
        return []
    ctes: Set[str] = set()
    tables: Set[str] = set()
    for statement in parsed:
        if statement is None:
            continue
        for cte in statement.find_all(exp.CTE):
            if cte.alias:
                ctes.add(str(cte.alias).lower())
        for tbl in statement.find_all(exp.Table):
            name = tbl.name
            db = tbl.db
            if not name:
                continue
            if name.lower() in ctes or name.lower() in ("range", "numbers"):
                continue
            tables.add(f"{db}.{name}" if db else name)
    return sorted(tables)


def parse_dataset(resp: Dict[str, Any]) -> ParsedDataset:
    if not isinstance(resp, dict):
        raise ValueError("Ожидался словарь ответа getDataset")

    dataset = resp.get("dataset") or {}
    parsed = ParsedDataset(
        dataset_id=str(resp.get("id") or ""),
        name=str(resp.get("name") or ""),
    )

    # Источники
    for src in dataset.get("sources", []) or []:
        src_type = src.get("source_type", "")
        params = src.get("parameters", {}) or {}
        title = src.get("title") or src.get("id") or ""
        tables: List[str] = []
        subsql: Optional[str] = None
        if src_type == "CH_TABLE":
            db = params.get("db_name")
            tbl = params.get("table_name")
            if tbl:
                tables.append(f"{db}.{tbl}" if db else tbl)
        elif src_type == "CH_SUBSELECT":
            subsql = params.get("subsql") or ""
            tables = extract_tables_from_sql(subsql)
        parsed.sources.append(SourceInfo(
            id=str(src.get("id") or ""),
            source_type=src_type,
            title=str(title),
            tables=tables,
            connection_id=src.get("connection_id"),
            subsql=subsql,
        ))

    # Аватары (source_avatars в dataset, не в options)
    for av in dataset.get("source_avatars", []) or []:
        parsed.avatars.append(AvatarInfo(
            id=str(av.get("id") or ""),
            title=str(av.get("title") or ""),
            source_id=str(av.get("source_id") or ""),
            is_root=bool(av.get("is_root")),
        ))

    # Джойны между аватарами
    for rel in dataset.get("avatar_relations", []) or []:
        conditions = []
        for cond in rel.get("conditions", []) or []:
            left = (cond.get("left") or {}).get("source")
            right = (cond.get("right") or {}).get("source")
            operator = cond.get("operator", "eq")
            if left and right:
                conditions.append(JoinCondition(
                    left_source=str(left),
                    right_source=str(right),
                    operator=str(operator),
                ))
        parsed.avatar_relations.append(AvatarRelation(
            id=str(rel.get("id") or ""),
            left_avatar_id=str(rel.get("left_avatar_id") or ""),
            right_avatar_id=str(rel.get("right_avatar_id") or ""),
            join_type=str(rel.get("join_type") or ""),
            conditions=conditions,
        ))

    # Поля
    for f in dataset.get("result_schema", []) or []:
        parsed.fields.append(FieldInfo(
            guid=str(f.get("guid") or ""),
            title=str(f.get("title") or ""),
            type=str(f.get("type") or ""),
            data_type=str(f.get("data_type") or f.get("cast") or ""),
            calc_mode=str(f.get("calc_mode") or ""),
            formula=f.get("formula"),
            avatar_id=f.get("avatar_id"),
            source=f.get("source"),
        ))

    # Зависимости полей
    aux = dataset.get("result_schema_aux") or {}
    inter = aux.get("inter_dependencies") or {}
    for dep in inter.get("deps", []) or []:
        field_id = dep.get("dep_field_id")
        refs = dep.get("ref_field_ids") or []
        if field_id:
            parsed.field_dependencies.append(FieldDependency(
                field_id=str(field_id),
                depends_on=[str(r) for r in refs],
            ))

    return parsed


def all_tables(parsed: ParsedDataset) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for src in parsed.sources:
        for t in src.tables:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return sorted(out)


def tables_by_source(parsed: ParsedDataset) -> Dict[str, List[str]]:
    return {src.id: list(src.tables) for src in parsed.sources}
