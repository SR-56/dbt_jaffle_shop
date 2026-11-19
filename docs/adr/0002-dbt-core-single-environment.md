# ADR-0002: dbt-core 1.12 + dbt-duckdb + dbt-metricflow の1環境にする

- 状態: 採用
- 日付: 2026-11-18
- 関連: ADR-0001

## 背景

ADR-0001 で、MetricFlow の `mf` CLI をダッシュボード（CI）と AI（ローカル）の両方から使うことにした。それまでの環境は dbt v2（2.0.8）だった。

2026-10 に確認した事実:

- dbt v2 の `dbt sl` は dbt platform との接続が必要で、ローカルの DuckDB では使えない
- dbt-metricflow は `dbt-core>=1.11,<1.13` を必須の依存関係にしている。dbt-core と dbt v2 は `dbt` コマンドも `site-packages/dbt/` も同じ名前なので、同じ環境に入れると v2 が壊れる

## 検討した選択肢

| 選択肢 | 良い点 | 悪い点 |
|---|---|---|
| A. dbt v2 を残し、`mf` 用に dbt-core の環境を別に持つ | 最新の dbt（v2）を使い続けられる | 環境が2つになり、CI・Claude Code の手順・README がすべて2段になる。v2 だけが対応する設定を書くと `mf` が壊れる |
| B. dbt-core 1.12 + dbt-duckdb + dbt-metricflow の1環境 | `uv sync` だけで全部そろう。`dbt` と `mf` が同じアダプター・同じ設定で動く。構成図の「dbt Core」と一致する | dbt v2 は使わない |

## 決定

B を採用する。Python は公式の対応範囲に合わせて 3.12。

## 理由

- `mf` を使う以上 dbt-core は必ず入るので、v2 を併用しても得るものが少ない
- 環境が1つなら、CI もローカルの AI も `uv run dbt` / `uv run mf` だけで済む

## 影響

- 2026-11-18 に確認: dbt-core 1.12.7 + dbt-duckdb 1.11.1 + dbt-metricflow（mf 0.16.0）で、`dbt build`（PASS=42）と `mf validate-configs`（エラー0）が通った。`mf query` の結果（2024-09 の Philadelphia: revenue 16130.21 / order_count 1497 / gross_profit 12072.25）は、DuckDB に直接書いた SQL の結果と一致した
- semantic layer は新形式の YAML（`models:` の中に `semantic_model:` / `metrics:`）で書く。dbt-core 1.12 の推奨の形式で、旧形式（トップレベルの `semantic_models:`）は非推奨
- **partial parse を無効にした**（`dbt_project.yml` の `flags.partial_parse: false`）。新形式の YAML を変更したあと、dbt-core 1.12.7 の partial parse が「metric `gross_profit` が重複している」という誤ったエラーを出した。`--no-partial-parse` では通った。小さいプロジェクトなので速度の影響は小さい
- DuckDB では `decimal / 100` が double になり、集計で誤差が出た（売上合計が 671425.3699998885）。割ったあとに decimal にキャストするマクロ `cents_to_dollars` を作った
- 注文単位の指標（`revenue` など）は、明細側の切り口（商品）では分けられない（MetricFlow が fan-out の join を許さない）。商品別の分析には明細単位の指標を使う。`fct_order_items` には `customer` と `store` のエンティティも持たせ、店舗別の分析で両方のファクトの指標を一緒に使えるようにした（持たせないと `store__store_name` と `order__store__store_name` で名前が分かれ、同じクエリに入れられなかった）
