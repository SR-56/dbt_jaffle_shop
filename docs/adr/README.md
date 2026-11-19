# 設計判断の記録（ADR）

このプロジェクトの設計判断を Architecture Decision Record（ADR）として残す。書き方のルールはリポジトリ直下の `CLAUDE.md` を、雛形は [template.md](template.md) を参照。

## 一覧

| No. | タイトル | 状態 | 日付 |
|---|---|---|---|
| [0001](0001-metricflow-as-single-source-for-pages-and-ai.md) | MetricFlow の定義を唯一の定義元にして、静的ダッシュボードとローカル AI の両方から使う | 採用 | 2026-11-18 |
| [0002](0002-dbt-core-single-environment.md) | dbt-core 1.12 + dbt-duckdb + dbt-metricflow の1環境にする | 採用 | 2026-11-18 |
| [0003](0003-ai-scope-metrics-plus-public-models.md) | AI は指標に加えて、公開モデルへの読み取り専用 SQL も使えるようにする | 採用 | 2026-11-18 |
| [0004](0004-ai-scope-from-semantic-manifest.md) | AI に公開する範囲を semantic layer（semantic_manifest.json）で決める | 採用 | 2026-11-18 |
| [0005](0005-remote-mcp-server.md) | MCP サーバーを Cloud Run に置き、GitHub ログインで自分だけに公開する | 採用 | 2026-11-19 |

## 未決事項

まだ ADR になっていない、これから決めること。

- 社内に限定公開する構成を、このリポジトリでどこまで再現するか（ADR-0005）
- 分析専用の作業場所を分けるか（ADR-0003 の影響を参照。MCP サーバーにすれば不要になる可能性がある）
- AI 分析の評価方法（質問セットの規模、正解の作り方、指標）
