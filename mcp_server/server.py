"""jaffle shop の semantic layer を、MCP のツールとして公開するサーバー。

起動（手元・stdio）:
    uv run python -m mcp_server.server

前提: `dbt build` 済みで target/semantic_manifest.json と jaffle_shop.duckdb がある。
"""

import anyio
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from . import metrics as mf
from . import semantic

INSTRUCTIONS = """\
jaffle shop（架空のカフェチェーン）の売上・注文・商品・店舗・顧客を分析するためのサーバー。
参照できるのは dbt の semantic layer に載せたモデル・列・指標だけ。

使い方:
1. 最初に get_context で、公開モデル・列・指標・group_by に使える名前・saved query を確認する
2. 質問の種類で、使うツールを選ぶ
   - 定義済みの指標（売上、注文数、平均注文単価、粗利など）を、期間・切り口・絞り込みを変えて見る → query_metrics
   - ダッシュボードと同じ定型の数字 → query_metrics の saved_query
   - 指標では表せない分析（分布、順位、顧客ごとの集計、併売、コホート、行レベルの調査など） → run_sql

守ること:
- 定義済みの指標の値は、必ず query_metrics で出す。run_sql で同じ数字を計算し直さない（定義とずれ、ダッシュボードと違う数字になるため）
- 答えには、数字と一緒に、使ったツールと条件（query_metrics の command、または run_sql の SQL）を示す
- query_metrics の数字（定義済みの指標）と run_sql の数字（その場の分析）を区別して書く。run_sql の数字には、何をどう数えたかを一言添える
- 公開されていないデータが必要な質問なら、推測で補わず、足りないものを伝える
- 同じ run_sql の分析が繰り返し必要なら、指標や saved query として dbt に追加することを提案する
- 指標は get_context に出たラベルのまま呼ぶ（例: average_order_value は「平均注文単価」。「客単価」などと言い換えない）
- 合計や全体の値が必要なときは、行を自分で足し算しない。group_by を外して query_metrics をもう一度呼ぶ（平均注文単価のような比率の指標は、足すと間違うため）
- 理由や傾向を述べるときは、ツールで確かめられるものは確かめてから書く（例: 粗利の差の理由なら items_sold や product_revenue を同じ条件で取る）。確かめないなら「仮説」と明記する
- データにないもの（メールアドレスなど）や、データを作った人の意図を推測で書かない
- 集計の区切りがデータの期間の端にかかるときは、途中で切れていることを書く（例: 2025年の第3四半期は 7〜8月の2か月分だけ）
- 「一緒に買われやすい」のような分析では、回数だけでなく、人気の差を除いた度合い（リフト値など）も検討する。回数だけで判断するなら、そう書く

データの注意:
- 金額はドル単位
- 注文単位の指標（revenue、order_count、average_order_value、ordering_customers、tax_paid）は、商品（product__*）では分けられない。商品で分けるときは明細単位の指標（items_sold、product_revenue、supply_cost、gross_profit）を使う
- revenue は税込、product_revenue は税抜の定価の合計。両者を足したり比べたりしない
- 注文データは 2024-09〜2025-08。店舗は6店あるが、注文があるのは Philadelphia と Brooklyn（2025-03 開店）だけ
"""

mcp = FastMCP("jaffle-shop", instructions=INSTRUCTIONS)


@mcp.tool
async def get_context() -> str:
    """公開モデル（テーブルと列の型・説明）、指標、group_by に使える名前、saved query の一覧を返す。分析の最初に呼ぶ。"""
    return await anyio.to_thread.run_sync(lambda: semantic.describe_context(semantic.load_manifest()))


@mcp.tool
async def query_metrics(
    metrics: list[str] = Field(default_factory=list, description="指標名（例: revenue, gross_profit）。saved_query を使うときは空でよい"),
    group_by: list[str] = Field(default_factory=list, description="切り口（例: metric_time__month, store__store_name, product__product_type）"),
    filters: list[mf.Filter] = Field(default_factory=list, description="絞り込み。すべて AND で結ばれる"),
    start_time: str | None = Field(None, description="期間の開始（ISO 形式、例: 2025-01-01）"),
    end_time: str | None = Field(None, description="期間の終わり（ISO 形式、例: 2025-03-31）"),
    order_by: list[str] = Field(default_factory=list, description="並べ替え。先頭に - を付けると降順（例: -revenue）"),
    limit: int = Field(100, description=f"返す行数の上限（最大 {semantic.MAX_ROWS}）"),
    saved_query: str | None = Field(None, description="saved query の名前。指定すると metrics・group_by・filters・期間は使わない"),
) -> dict:
    """MetricFlow で定義済みの指標を集計する。定義済みの指標の値は必ずこのツールで出す。"""
    manifest = semantic.load_manifest()
    try:
        args = mf.build_args(manifest, metrics, group_by, filters, start_time, end_time, order_by, limit, saved_query)
        return await anyio.to_thread.run_sync(lambda: mf.run(args, limit))
    except mf.MetricQueryError as e:
        raise ToolError(str(e)) from e


@mcp.tool
async def run_sql(
    query: str = Field(description="DuckDB の SQL（select / with）。参照できるのは get_context に出たテーブルと列だけ"),
    limit: int = Field(100, description=f"返す行数の上限（最大 {semantic.MAX_ROWS}）。集計してから出す"),
) -> dict:
    """公開モデルに、読み取り専用で SQL を実行する。指標では表せない分析にだけ使う。ファイルの読み書きや設定の変更はできない。"""
    manifest = semantic.load_manifest()
    try:
        result = await anyio.to_thread.run_sync(lambda: semantic.run_sql(manifest, query, limit))
    except semantic.SqlError as e:
        raise ToolError(str(e)) from e
    return {"query": query, **result}


def main() -> None:
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
