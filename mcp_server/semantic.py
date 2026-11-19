"""semantic layer（target/semantic_manifest.json）で決めた範囲だけを扱う部品。

公開の範囲:
- モデル: semantic model になっているもの（`semantic_model` が有効なもの）
- 列: entity か dimension にした列（derived の dimension は、その式の結果の列として見える）

SQL は、公開する列だけをメモリ上の DuckDB にコピーしてから元の DB を切り離し、
ファイルへのアクセスと設定の変更を禁止した状態で実行する。
そのため、semantic layer に載っていないモデルや列には、SQL をどう書いても届かない。
"""

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SEMANTIC_MANIFEST = ROOT / "target" / "semantic_manifest.json"
DATABASE = ROOT / "jaffle_shop.duckdb"

# run_sql の上限。公開する場合も、1人で使う前提の値
SQL_MEMORY_LIMIT = "1GB"
SQL_THREADS = 2
SQL_TIMEOUT_SECONDS = 20
MAX_ROWS = 1000

TIME_GRAINS = ["day", "week", "month", "quarter", "year"]


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def load_manifest() -> dict:
    return json.loads(SEMANTIC_MANIFEST.read_text())


@dataclass
class Column:
    name: str
    expr: str
    description: str
    role: str


@dataclass
class Table:
    name: str
    source: str
    description: str
    primary_entity: str | None
    columns: dict[str, Column]
    dimensions: list[dict]


def public_tables(manifest: dict) -> list[Table]:
    """semantic model ごとに、公開するテーブル名・元の場所・列を返す。"""
    tables = []
    for sm in manifest["semantic_models"]:
        columns: dict[str, Column] = {}
        primary = None
        # entity の列名は expr（無ければ entity 名）。SQL では entity 名ではなく列名を使う
        for e in sm["entities"]:
            col = e.get("expr") or e["name"]
            if e["type"] == "primary":
                primary = e["name"]
            columns.setdefault(col, Column(col, quote(col), e.get("description") or "", f"entity: {e['name']}（{e['type']}）"))
        # dimension の列名は dimension 名。expr があれば（derived）その式で作る
        for d in sm["dimensions"]:
            expr = d.get("expr") or quote(d["name"])
            columns.setdefault(d["name"], Column(d["name"], expr, d.get("description") or "", f"dimension（{d['type']}）"))
        rel = sm["node_relation"]
        tables.append(Table(
            name=sm["name"],
            source=f'src.{quote(rel["schema_name"])}.{quote(rel["alias"])}',
            description=sm.get("description") or "",
            primary_entity=primary,
            columns=columns,
            dimensions=sm["dimensions"],
        ))
    return sorted(tables, key=lambda t: t.name)


def sandbox(tables: list[Table]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"ATTACH '{DATABASE}' AS src (READ_ONLY)")
    for t in tables:
        cols = ", ".join(f"{c.expr} AS {quote(c.name)}" for c in t.columns.values())
        con.execute(f"CREATE TABLE {quote(t.name)} AS SELECT {cols} FROM {t.source}")
    con.execute("DETACH src")
    con.execute(f"SET memory_limit = '{SQL_MEMORY_LIMIT}'")
    con.execute(f"SET threads = {SQL_THREADS}")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def group_by_names(tables: list[Table]) -> list[str]:
    """mf query の group_by に使える代表的な名前（`<entity>__<dimension>` と metric_time）。"""
    names = [f"metric_time__{g}" for g in TIME_GRAINS]
    for t in tables:
        if not t.primary_entity:
            continue
        for d in t.dimensions:
            base = f"{t.primary_entity}__{d['name']}"
            names.append(base + ("__<grain>" if d["type"] == "time" else ""))
    return names


def describe_context(manifest: dict) -> str:
    tables = public_tables(manifest)
    con = sandbox(tables)
    out = ["# 公開モデル（run_sql で参照できるテーブル）", ""]
    for t in tables:
        types = dict(con.execute(
            "select column_name, data_type from information_schema.columns where table_name = ?", [t.name]
        ).fetchall())
        rows = con.execute(f"select count(*) from {quote(t.name)}").fetchall()[0][0]
        out += [f"## {t.name}（{rows:,} 行）", t.description, ""]
        out += [f"- {c.name} ({types.get(c.name, '?')}, {c.role}): {c.description}" for c in t.columns.values()]
        out.append("")

    out += ["# 指標（query_metrics で使う）", ""]
    for m in sorted(manifest["metrics"], key=lambda x: x["name"]):
        desc = m.get("description") or ""
        out.append(f"- {m['name']}: {m.get('label') or ''}{'。' + desc if desc else ''}")

    out += ["", "# group_by に使える名前（代表的なもの。使えない組み合わせは query_metrics がエラーで候補を返す）", ""]
    out += [f"- {n}" for n in group_by_names(tables)]

    out += ["", "# saved query（ダッシュボードに載せている定型の集計。query_metrics の saved_query に名前を渡す）", ""]
    for sq in manifest["saved_queries"]:
        p = sq["query_params"]
        out.append(f"- {sq['name']}: {sq.get('description') or ''}（metrics: {', '.join(p['metrics'])}; group_by: {', '.join(p['group_by']) or 'なし'}）")
    return "\n".join(out)


class SqlError(Exception):
    pass


def run_sql(manifest: dict, query: str, limit: int) -> dict:
    limit = max(1, min(limit, MAX_ROWS))
    con = sandbox(public_tables(manifest))
    timer = threading.Timer(SQL_TIMEOUT_SECONDS, con.interrupt)
    timer.start()
    try:
        rel = con.sql(query)
        if rel is None:
            raise SqlError("結果を返すクエリ（select / with）だけを実行できる")
        columns = rel.columns
        rows = rel.limit(limit + 1).fetchall()
    except duckdb.InterruptException as e:
        raise SqlError(f"{SQL_TIMEOUT_SECONDS} 秒を超えたので打ち切った。集計してから出すか、条件を絞る") from e
    except duckdb.Error as e:
        raise SqlError(str(e)) from e
    finally:
        timer.cancel()
        con.close()
    return {
        "columns": columns,
        "rows": [dict(zip(columns, (to_json(v) for v in r))) for r in rows[:limit]],
        "truncated": len(rows) > limit,
    }


def to_json(value):
    """DuckDB の値を JSON にできる形にする（decimal・日付など）。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    try:
        f = float(value)
        return int(f) if f.is_integer() and "." not in str(value) else f
    except (TypeError, ValueError):
        return str(value)
