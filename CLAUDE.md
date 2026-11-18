# CLAUDE.md

## プロジェクト概要

dbt 公式 jaffle shop のデータを使い、MetricFlow で定義した指標を静的ダッシュボードとローカルの AI 分析の両方から使うプロジェクト。

- 構成図: `docs/images/architecture.webp`。指標は MetricFlow（`models/marts/_marts.yml`）を唯一の定義元にする
- 実行環境: dbt-core 1.12 + dbt-duckdb + dbt-metricflow（uv で管理、Python 3.12）+ DuckDB（`jaffle_shop.duckdb`）
- コマンドは `uv run dbt ...` / `uv run mf ...`。`DBT_PROFILES_DIR=.`（プロジェクト直下の `profiles.yml` を使う。`.claude/settings.json` で設定済み）
- 2つの出口:
  - ダッシュボード: GitHub Actions（`.github/workflows/pages.yml`）が saved query（`models/marts/_saved_queries.yml`）を `mf query` → `scripts/export_metrics.py` で JSON 化 → `site/` を GitHub Pages に公開
  - AI 分析: ローカルの Claude Code が、定義済みの指標は `mf query` で、指標を超えた分析は公開モデルへの SQL（`scripts/public_data.py`）で出す。手順は `.claude/skills/analyze-data/SKILL.md`
- データについて聞かれたら、`analyze-data` スキルに従う。staging・seed・DuckDB のファイルを直接読まない
- AI に公開する範囲は semantic layer で決まる: semantic model になっているモデルの、entity か dimension にした列だけ（`target/semantic_manifest.json` から読む）。列を entity / dimension にするときは、AI に公開してよいかを考える
- 時間の dimension は `dimension: {type: time}` と辞書の形で書く。`dimension: time` と文字列で書くと、dbt-core 1.12.7 では粒度が semantic_manifest.json に入らず、`mf query` が実行時に失敗する
- semantic layer は新形式の YAML（`models:` の中に `semantic_model:` / `metrics:`）で書く。変更したら `uv run dbt build` と `uv run mf validate-configs` を通す

## 設計判断の記録（ADR）— 自律的に行うこと

設計判断は `docs/adr/` に ADR として記録する。なぜ今の構成になっているのかを、後から追えるようにすることが目的。

### 記録するタイミング

ユーザーに頼まれなくても、次のどれかに当てはまったら記録する。

- 複数の選択肢を比べて1つを選んだ（ツール、モデルの粒度、層の分け方、命名、マテリアライズ、テスト方針など）
- ユーザーが方針を決めた、または Claude の提案を受け入れた・却下した
- 既存の判断を変えた → 古い ADR の状態を「置換」にし、新しい ADR からリンクする
- 調べた結果、技術的な制約が分かった（例: MetricFlow で使えない YAML の書き方）

記録しないもの: 誤字の修正、自明な実装、一般的なベストプラクティスにそのまま従っただけのこと。

### 記録の手順

1. `docs/adr/template.md` をコピーして `docs/adr/NNNN-kebab-case-title.md` を作る（NNNN は連番）
2. `docs/adr/README.md` の一覧に1行追加し、未決事項が解決したらそこから消す
3. 状態は次の4つのどれか
   - **提案**: Claude が提案したが、ユーザーがまだ決めていない
   - **採用**: ユーザーが決めた、または了承した
   - **却下**
   - **置換**: 後の ADR で置き換えられた
4. ADR を作ったり更新したりしたら、応答の最後に「ADR-NNNN を記録しました」と一言添える

### 書き方

- 日本語で、簡潔に書く
- 「検討した選択肢」と「却下した理由」を必ず書く。判断を見直すときに一番必要になるのはここ
- 推測ではなく、実際に確認したこと（コマンドの結果など）を根拠に書く
