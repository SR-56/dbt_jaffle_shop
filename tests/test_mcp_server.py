"""MCP サーバーのツールを、MCP クライアント経由で確かめる。

実行: DBT_PROFILES_DIR=. uv run python -m pytest tests -q
前提: `dbt build` 済み
"""

import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_server.server import mcp


async def call(name: str, **kwargs):
    async with Client(mcp) as client:
        result = await client.call_tool(name, kwargs)
        return result.data if result.data is not None else json.loads(result.content[0].text)


async def test_tools_listed():
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {"get_context", "query_metrics", "run_sql"}


async def test_context_hides_private_columns():
    text = await call("get_context")
    assert "fct_orders" in text and "order_total" in text
    assert "customer_name" not in text
    assert "stg_orders" not in text and "metricflow_time_spine" not in text


async def test_query_metrics_matches_known_value():
    r = await call(
        "query_metrics",
        metrics=["revenue", "order_count", "gross_profit"],
        group_by=["metric_time__month", "store__store_name"],
        order_by=["metric_time__month"],
        limit=1,
    )
    row = r["rows"][0]
    assert row["store__store_name"] == "Philadelphia"
    assert (row["revenue"], row["order_count"], row["gross_profit"]) == (16130.21, 1497, 12072.25)
    assert r["truncated"] is True


async def test_query_metrics_filters_and_saved_query():
    r = await call(
        "query_metrics",
        metrics=["product_revenue"],
        group_by=["product__product_type"],
        filters=[{"dimension": "store__store_name", "operator": "=", "value": "Brooklyn"}],
        start_time="2025-06-01",
        end_time="2025-08-31",
        order_by=["product__product_type"],
    )
    assert [(x["product__product_type"], x["product_revenue"]) for x in r["rows"]] == [("beverage", 86288), ("jaffle", 42114)]
    total = await call("query_metrics", saved_query="kpi_total")
    assert total["rows"][0]["revenue"] == 671425.37


@pytest.mark.parametrize("kwargs", [
    {"metrics": ["revenue"], "group_by": ["store__store_name; drop"]},
    {"metrics": ["not_a_metric"]},
    {"metrics": ["revenue"], "filters": [{"dimension": "store__store_name", "operator": "=", "value": "{{ 1 }}"}]},
    {"metrics": ["revenue"], "start_time": "2025-01-01' or 1=1"},
    {"saved_query": "nope"},
])
async def test_query_metrics_rejects_bad_input(kwargs):
    with pytest.raises(ToolError):
        await call("query_metrics", **kwargs)


async def test_query_metrics_quotes_values():
    # 値に ' を入れても SQL にならず、ただの文字列として扱われる（該当なしで 0 行）
    r = await call(
        "query_metrics", metrics=["revenue"], group_by=["store__store_name"],
        filters=[{"dimension": "store__store_name", "operator": "=", "value": "x' OR 1=1 OR 'a'='a"}],
    )
    assert r["rows"] == []


async def test_run_sql_adhoc_and_matches_metric():
    r = await call("run_sql", query="select sum(order_total) as total from fct_orders")
    assert r["rows"][0]["total"] == 671425.37


@pytest.mark.parametrize("query", [
    "select customer_name from dim_customers",
    "select * from stg_orders",
    "select * from metricflow_time_spine",
    "select * from read_csv('seeds/raw_customers.csv')",
    "ATTACH 'jaffle_shop.duckdb' AS x",
    "SET enable_external_access = true",
    "COPY fct_orders TO 'out.csv'",
])
async def test_run_sql_blocks_outside_scope(query):
    with pytest.raises(ToolError):
        await call("run_sql", query=query)


async def test_run_sql_limit():
    r = await call("run_sql", query="select * from fct_orders", limit=5)
    assert len(r["rows"]) == 5 and r["truncated"] is True


async def test_command_is_readable():
    r = await call(
        "query_metrics", metrics=["gross_profit"], group_by=["product__product_type"],
        filters=[{"dimension": "store__store_name", "operator": "=", "value": "Brooklyn"}],
    )
    assert "--where \"{{ Dimension('store__store_name') }} = 'Brooklyn'\"" in r["command"]


def test_instructions_cover_answer_rules():
    # 試用で見つかった答え方の癖（言い換え、自前の足し算、推測、期間の端、併売の回数だけの判断）への対策
    for phrase in ["ラベルのまま", "group_by を外して", "仮説", "途中で切れている", "リフト値"]:
        assert phrase in mcp.instructions
