"""MetricFlow（mf CLI）で指標を問い合わせる。

mf は sandbox の外で DuckDB 全体につないで動くので、利用者の入力を SQL として渡してはいけない。
- 名前（指標・group_by・並べ替え）は英小文字・数字・`_` だけを受け付け、指標と saved query は manifest にあるものに限る
- 絞り込みは「ディメンション・演算子・値」の組で受け取り、where 句はここで組み立てる（値は文字列リテラルとして quote する）
- mf にはシェルを通さず、引数のリストのまま渡す
"""

import csv
import os
import re
import shlex
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .semantic import MAX_ROWS, ROOT, to_json

MF_TIMEOUT_SECONDS = 60
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
ORDER = re.compile(r"^-?[a-z][a-z0-9_]*$")
ANSI = re.compile(r"\x1b\[[0-9;]*m")

Operator = Literal["=", "!=", ">", ">=", "<", "<=", "in", "not in"]
Scalar = str | int | float | bool


class Filter(BaseModel):
    dimension: str = Field(description="カテゴリのディメンション名（例: store__store_name）。期間の絞り込みは start_time / end_time を使う")
    operator: Operator
    value: Scalar | list[Scalar] = Field(description="in / not in のときはリスト")


class MetricQueryError(Exception):
    pass


def _check_name(kind: str, name: str, pattern: re.Pattern = NAME) -> str:
    if not pattern.match(name):
        raise MetricQueryError(f"{kind} の名前が不正: {name!r}（英小文字・数字・_ だけ）")
    return name


def _literal(value: Scalar) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    # { } は Jinja（mf の where はテンプレートとして展開される）、\ と制御文字は念のため拒否する
    if any(ch in value for ch in "{}\\") or any(ord(ch) < 32 for ch in value):
        raise MetricQueryError(f"値に使えない文字が含まれている: {value!r}")
    return "'" + value.replace("'", "''") + "'"


def _where(filters: list[Filter]) -> str:
    parts = []
    for f in filters:
        dim = _check_name("filters.dimension", f.dimension)
        if f.operator in ("in", "not in"):
            values = f.value if isinstance(f.value, list) else [f.value]
            if not values:
                raise MetricQueryError("in / not in の値が空")
            rhs = "(" + ", ".join(_literal(v) for v in values) + ")"
        else:
            if isinstance(f.value, list):
                raise MetricQueryError(f"演算子 {f.operator} にリストは渡せない")
            rhs = _literal(f.value)
        parts.append(f"{{{{ Dimension('{dim}') }}}} {f.operator.upper()} {rhs}")
    return " AND ".join(parts)


def _check_time(kind: str, value: str) -> str:
    try:
        (datetime if "T" in value else date).fromisoformat(value)
    except ValueError as e:
        raise MetricQueryError(f"{kind} は ISO 形式の日付（例: 2025-01-01）: {value!r}") from e
    return value


def build_args(
    manifest: dict,
    metrics: list[str],
    group_by: list[str],
    filters: list[Filter],
    start_time: str | None,
    end_time: str | None,
    order_by: list[str],
    limit: int,
    saved_query: str | None,
) -> list[str]:
    args = ["mf", "query"]
    if saved_query:
        names = {sq["name"] for sq in manifest["saved_queries"]}
        if saved_query not in names:
            raise MetricQueryError(f"saved query がない: {saved_query!r}（あるもの: {', '.join(sorted(names))}）")
        args += ["--saved-query", saved_query]
    else:
        known = {m["name"] for m in manifest["metrics"]}
        if not metrics:
            raise MetricQueryError("metrics を1つ以上指定する")
        unknown = [m for m in metrics if m not in known]
        if unknown:
            raise MetricQueryError(f"指標がない: {', '.join(unknown)}（あるもの: {', '.join(sorted(known))}）")
        args += ["--metrics", ",".join(metrics)]
        if group_by:
            args += ["--group-by", ",".join(_check_name("group_by", g) for g in group_by)]
        if filters:
            args += ["--where", _where(filters)]
        if start_time:
            args += ["--start-time", _check_time("start_time", start_time)]
        if end_time:
            args += ["--end-time", _check_time("end_time", end_time)]
    if order_by:
        args += ["--order", ",".join(_check_name("order_by", o, ORDER) for o in order_by)]
    args += ["--limit", str(max(1, min(limit, MAX_ROWS)) + 1)]
    return args


def _error_message(output: str) -> str:
    text = ANSI.sub("", output)
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith(("⠋", "⠙", "⠹", "⠸"))]
    for i, ln in enumerate(lines):
        if "ERROR" in ln:
            lines = lines[i:]
            break
    lines = [ln for ln in lines if not ln.startswith(("Log File", "Artifact Path", "Artifact Modified", "If you think", "    https://github.com/dbt-labs"))]
    return "\n".join(lines)[:3000]


def run(args: list[str], limit: int) -> dict:
    limit = max(1, min(limit, MAX_ROWS))
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "result.csv"
        env = {**os.environ, "DBT_PROFILES_DIR": str(ROOT)}
        try:
            proc = subprocess.run(
                [*args, "--csv", str(csv_path), "--quiet"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=MF_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise MetricQueryError(f"{MF_TIMEOUT_SECONDS} 秒を超えたので打ち切った") from e
        output = proc.stdout + "\n" + proc.stderr
        if proc.returncode != 0 or (not csv_path.exists() and "ERROR" in output):
            raise MetricQueryError(_error_message(output))
        if csv_path.exists():
            with csv_path.open(newline="") as f:
                reader = csv.DictReader(f)
                rows = [{k: to_json(_number(v)) for k, v in row.items()} for row in reader]
                columns = list(reader.fieldnames or [])
        else:
            # 結果が0行のとき、mf は正常終了するが CSV を作らない
            rows, columns = [], []
    # 表示するコマンドは、内部で1行多く取っている --limit を、指定された値に戻す
    shown = args[:-1] + [str(limit)] if args[-2] == "--limit" else args
    return {
        "command": " ".join(_shell_quote(a) for a in shown),
        "columns": columns,
        "rows": rows[:limit],
        "truncated": len(rows) > limit,
    }


def _shell_quote(arg: str) -> str:
    """表示用。where 句のように ' を含む引数は、読みやすいよう " で囲む（シェルにそのまま貼っても同じ意味になる形）。"""
    if "'" in arg and not any(ch in arg for ch in '"$`\\!'):
        return f'"{arg}"'
    return shlex.quote(arg)


def _number(value: str):
    if value == "":
        return None
    try:
        f = float(value)
    except ValueError:
        return value
    return int(f) if f.is_integer() and "." not in value else f
