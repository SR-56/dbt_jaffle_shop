"""AI に公開するデータとコンテキストを、コマンドラインから確かめる。

中身は MCP サーバーと同じ部品（mcp_server/semantic.py）を使う。

使い方:
    uv run python scripts/public_data.py context          # 公開モデル・列・指標・saved query の一覧
    uv run python scripts/public_data.py sql "select ..."  # 公開モデルだけに読み取り専用で SQL を実行

前提: `dbt build` 済みで target/semantic_manifest.json と jaffle_shop.duckdb がある。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_server import semantic  # noqa: E402


def cmd_context(manifest: dict, _args) -> None:
    print(semantic.describe_context(manifest))


def cmd_sql(manifest: dict, args) -> None:
    try:
        result = semantic.run_sql(manifest, args.query, args.limit)
    except semantic.SqlError as e:
        sys.exit(f"ERROR: {e}")
    columns = result["columns"]
    print("| " + " | ".join(columns) + " |")
    print("|" + "---|" * len(columns))
    for row in result["rows"]:
        print("| " + " | ".join("" if row[c] is None else str(row[c]) for c in columns) + " |")
    if result["truncated"]:
        print(f"\n（先頭 {args.limit} 行だけを表示。--limit で変更できる）")


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = parser.add_subparsers(required=True)
sub.add_parser("context", help="公開モデル・列・指標・saved query を表示する").set_defaults(func=cmd_context)
p_sql = sub.add_parser("sql", help="公開モデルだけに読み取り専用で SQL を実行する")
p_sql.add_argument("query")
p_sql.add_argument("--limit", type=int, default=100)
p_sql.set_defaults(func=cmd_sql)

args = parser.parse_args()
args.func(semantic.load_manifest(), args)
