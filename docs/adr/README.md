# 設計判断の記録（ADR）

このプロジェクトの設計判断を Architecture Decision Record（ADR）として残す。書き方のルールはリポジトリ直下の `CLAUDE.md` を、雛形は [template.md](template.md) を参照。

## 一覧

| No. | タイトル | 状態 | 日付 |
|---|---|---|---|
| [0001](0001-metricflow-as-single-source-for-pages-and-ai.md) | MetricFlow の定義を唯一の定義元にして、静的ダッシュボードとローカル AI の両方から使う | 採用 | 2026-11-18 |
| [0002](0002-dbt-core-single-environment.md) | dbt-core 1.12 + dbt-duckdb + dbt-metricflow の1環境にする | 採用 | 2026-11-18 |
| [0003](0003-ai-scope-metrics-plus-public-models.md) | AI は指標に加えて、公開モデルへの読み取り専用 SQL も使えるようにする | 採用 | 2026-11-18 |
