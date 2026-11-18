---
name: analyze-data
description: jaffle shop の売上・注文・商品・店舗・顧客について、自然言語で分析を頼まれたときに使う。「先月の売上は？」のような定義済みの指標の質問から、「リピートする顧客の特徴は？」「一緒に買われやすい商品は？」のような指標を超えた分析まで扱う。参照できるのは dbt で公開したモデルと指標だけ。
---

# 公開されたモデルと指標で分析する

## 参照してよいもの

- MetricFlow の指標（`mf` CLI）
- semantic layer に載っているモデルの、entity か dimension になっている列（`scripts/public_data.py`）
- それらの説明（`scripts/public_data.py context`）

staging、seed（`seeds/*.csv`）、`jaffle_shop.duckdb` を直接読んではいけない。`duckdb` や Python で DB に直接つなぐのも禁止。公開の範囲を決めているのは dbt の定義なので、その外を見ると、ダッシュボードや他の人と違う前提で答えることになる。

## 手順

1. `target/semantic_manifest.json` がなければ、先に `uv run dbt build` を実行する
2. `uv run python scripts/public_data.py context` で、公開モデル・列・指標・saved query を確認する
3. 質問の種類で、使う道具を選ぶ

| 質問 | 使うもの |
|---|---|
| 定義済みの指標を、期間・切り口・絞り込みを変えて見る（「Brooklyn の四半期ごとの粗利」） | `mf query`。saved query にない組み合わせでもよい |
| ダッシュボードと同じ定型の数字（「全期間の KPI」） | `mf query --saved-query <名前>` |
| 指標では表せない分析（分布、順位、顧客ごとの集計、併売、コホート、行レベルの調査など） | `uv run python scripts/public_data.py sql "<SQL>"` |

**定義済みの指標（売上、注文数、平均注文単価、粗利など）の値は、必ず `mf query` で出す。** SQL で同じ数字を計算し直さない。定義と数字がずれるのを防ぎ、ダッシュボードと同じ値を返すため。SQL は、指標の外側の分析にだけ使う。両方が必要な分析では、組み合わせて使う（例: SQL で「リピート顧客」の特徴を調べ、売上への影響は `mf query --group-by customer__customer_type` で出す）。

### mf query の書き方

- 指標と切り口の確認: `uv run mf list metrics` / `uv run mf list dimensions --metrics <指標>`
- 値の候補: `uv run mf list dimension-values --metrics <指標> --dimension <切り口>`
- `uv run mf query --metrics <指標,...> --group-by <切り口,...>`
  - 時間の粒度: `metric_time__day` / `__week` / `__month` / `__quarter` / `__year`
  - 期間: `--start-time 2025-01-01 --end-time 2025-03-31`
  - 絞り込み: `--where "{{ Dimension('store__store_name') }} = 'Brooklyn'"`
  - 並べ替えと件数: `--order -revenue --limit 5`（`-` を付けると降順）
  - 小数の桁: `--decimals 2`
  - 生成される SQL: `--explain`

### public_data.py sql の書き方

- DuckDB の SQL。参照できるのは `context` に出たテーブルと列だけ
- 結果は先頭 100 行まで表示される（`--limit` で変更）。集計してから出す
- 読み取り専用。ファイルの読み書きや設定の変更はできない

## 答え方

- 数字と一緒に、実行した `mf query` または SQL を示す
- `mf query` で出した数字（定義済みの指標）と、SQL で出した数字（その場の分析）を区別して書く。SQL の数字には、何をどう数えたかを一言添える
- 同じ SQL の分析を何度も頼まれるなら、指標や saved query として `models/marts/_marts.yml` に追加することを提案する（追加したら `uv run dbt build` と `uv run mf validate-configs` で確認する）
- 公開モデルにないデータが必要な質問なら、推測で補わず、足りないものを伝える

## 注意

- 金額はドル単位
- 注文単位の指標（`revenue`、`order_count`、`average_order_value`、`ordering_customers`、`tax_paid`）は、商品（`product__*`）では分けられない。1つの注文に複数の商品があるので、分けると数字が重複するため。商品で分けるときは明細単位の指標（`items_sold`、`product_revenue`、`supply_cost`、`gross_profit`）を使う
- `revenue` は税込で、`product_revenue` は税抜の定価の合計。両者を足したり比べたりしない
- 注文データは 2024-09〜2025-08。店舗は6店あるが、注文があるのは Philadelphia と Brooklyn（2025-03 開店）だけ
