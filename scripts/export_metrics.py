"""saved query をすべて `mf query` で実行し、ダッシュボード用の JSON を site/data/ に書き出す。

前提: `dbt build` 済みで target/semantic_manifest.json がある。
実行: DBT_PROFILES_DIR=. uv run python scripts/export_metrics.py

`mf query` には JSON 出力がないので、CSV に書き出してから JSON に変換する。
指標のラベルと説明も semantic_manifest.json から一緒に書き出し、ダッシュボード側で定義を持たないようにする。
"""

import csv
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "target" / "semantic_manifest.json"
OUT_DIR = ROOT / "site" / "data"


def to_number(value: str):
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() and "." not in value else number


def run_saved_query(name: str) -> tuple[list[str], list[dict]]:
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / f"{name}.csv"
        subprocess.run(
            ["mf", "query", "--saved-query", name, "--csv", str(csv_path), "--quiet"],
            cwd=ROOT,
            check=True,
        )
        if not csv_path.exists():
            raise RuntimeError(f"mf query --saved-query {name} が CSV を出力しなかった")
        with csv_path.open(newline="") as f:
            reader = csv.DictReader(f)
            rows = [{k: to_number(v) for k, v in row.items()} for row in reader]
            columns = list(reader.fieldnames or [])
    # 1列目（時間やカテゴリ）で並べる。mf の --order は saved query ごとに列名が違うので使わない
    rows.sort(key=lambda r: tuple(str(r[c]) for c in columns if c not in metric_names))
    return columns, rows


manifest = json.loads(MANIFEST.read_text())
metrics = {
    m["name"]: {"label": m.get("label") or m["name"], "description": m.get("description") or ""}
    for m in manifest["metrics"]
}
metric_names = set(metrics)

OUT_DIR.mkdir(parents=True, exist_ok=True)
index = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "datasets": []}

for sq in manifest["saved_queries"]:
    columns, rows = run_saved_query(sq["name"])
    used = sq["query_params"]["metrics"]
    dataset = {
        "name": sq["name"],
        "description": sq.get("description") or "",
        "metrics": {name: metrics[name] for name in used},
        "dimensions": [c for c in columns if c not in metric_names],
        "rows": rows,
    }
    (OUT_DIR / f"{sq['name']}.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2))
    index["datasets"].append(sq["name"])
    print(f"{sq['name']}: {len(rows)} rows")

(OUT_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))
