"""AI に公開するデータとコンテキストを扱う。

公開の範囲は semantic layer（target/semantic_manifest.json）で決まる:
- モデル: semantic model になっているもの（`semantic_model` が有効なもの）
- 列: entity か dimension にした列（derived の dimension は、その式の結果の列として見える）

使い方:
    uv run python scripts/public_data.py context          # 公開モデル・列・指標・saved query の一覧
    uv run python scripts/public_data.py sql "select ..."  # 公開モデルだけに読み取り専用で SQL を実行

`sql` は、公開する列だけをメモリ上の DuckDB にコピーしてから元の DB を切り離し、
ファイルへのアクセスと設定の変更を禁止した状態でクエリを実行する。
そのため、semantic layer に載っていないモデルや列には、SQL をどう書いても届かない。

前提: `dbt build` 済みで target/semantic_manifest.json と jaffle_shop.duckdb がある。
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SEMANTIC_MANIFEST = ROOT / "target" / "semantic_manifest.json"
DATABASE = ROOT / "jaffle_shop.duckdb"


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def public_tables(semantic: dict) -> list[dict]:
    """semantic model ごとに、公開するテーブル名・元の場所・列（名前, SQL 式, 説明）を返す。"""
    tables = []
    for sm in semantic["semantic_models"]:
        columns: dict[str, dict] = {}
        # entity の列名は expr（無ければ entity 名）。AI は entity 名ではなく列名で SQL を書く
        for e in sm["entities"]:
            col = e.get("expr") or e["name"]
            columns.setdefault(col, {"expr": quote(col), "description": e.get("description") or "", "role": f"entity: {e['name']}（{e['type']}）"})
        # dimension の列名は dimension 名。expr があれば（derived）その式で作る
        for d in sm["dimensions"]:
            expr = d.get("expr") or quote(d["name"])
            columns.setdefault(d["name"], {"expr": expr, "description": d.get("description") or "", "role": f"dimension（{d['type']}）"})
        rel = sm["node_relation"]
        tables.append({
            "name": sm["name"],
            "source": f'src.{quote(rel["schema_name"])}.{quote(rel["alias"])}',
            "description": sm.get("description") or "",
            "columns": columns,
        })
    return sorted(tables, key=lambda t: t["name"])


def sandbox(tables: list[dict]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"ATTACH '{DATABASE}' AS src (READ_ONLY)")
    for t in tables:
        cols = ", ".join(f"{c['expr']} AS {quote(name)}" for name, c in t["columns"].items())
        con.execute(f"CREATE TABLE {quote(t['name'])} AS SELECT {cols} FROM {t['source']}")
    con.execute("DETACH src")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def cmd_context(semantic: dict, _args) -> None:
    tables = public_tables(semantic)
    con = sandbox(tables)
    print("# 公開モデル（SQL で参照できるテーブル）\n")
    for t in tables:
        types = dict(con.execute(
            "select column_name, data_type from information_schema.columns where table_name = ?", [t["name"]]
        ).fetchall())
        rows = con.execute(f"select count(*) from {quote(t['name'])}").fetchall()[0][0]
        print(f"## {t['name']}（{rows:,} 行）\n{t['description']}\n")
        for name, c in t["columns"].items():
            print(f"- {name} ({types.get(name, '?')}, {c['role']}): {c['description']}")
        print()

    print("# 指標（mf query で使う。定義は models/marts/_marts.yml）\n")
    for metric in sorted(semantic["metrics"], key=lambda x: x["name"]):
        desc = metric.get("description") or ""
        print(f"- {metric['name']}: {metric.get('label') or ''}{'。' + desc if desc else ''}")
    print("\n# saved query（ダッシュボードに載せている定型の集計）\n")
    for sq in semantic["saved_queries"]:
        p = sq["query_params"]
        print(f"- {sq['name']}: {sq.get('description') or ''}（metrics: {', '.join(p['metrics'])}; group_by: {', '.join(p['group_by']) or 'なし'}）")


def cmd_sql(semantic: dict, args) -> None:
    con = sandbox(public_tables(semantic))
    try:
        rel = con.sql(args.query)
    except duckdb.Error as e:
        sys.exit(f"ERROR: {e}")
    if rel is None:
        sys.exit("ERROR: 結果を返すクエリ（select / with）だけを実行できる")
    columns = rel.columns
    rows = rel.fetchall()
    print("| " + " | ".join(columns) + " |")
    print("|" + "---|" * len(columns))
    for row in rows[: args.limit]:
        print("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    if len(rows) > args.limit:
        print(f"\n（{len(rows):,} 行のうち先頭 {args.limit} 行を表示。--limit で変更できる）")


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = parser.add_subparsers(required=True)
sub.add_parser("context", help="公開モデル・列・指標・saved query を表示する").set_defaults(func=cmd_context)
p_sql = sub.add_parser("sql", help="公開モデルだけに読み取り専用で SQL を実行する")
p_sql.add_argument("query")
p_sql.add_argument("--limit", type=int, default=100)
p_sql.set_defaults(func=cmd_sql)

args = parser.parse_args()
args.func(json.loads(SEMANTIC_MANIFEST.read_text()), args)
