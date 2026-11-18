# ADR-0001: MetricFlow の定義を唯一の定義元にして、静的ダッシュボードとローカル AI の両方から使う

- 状態: 採用
- 日付: 2026-11-18
- 関連: ADR-0002, ADR-0003

## 背景

当初は「フラットな marts → ダッシュボード」と「スタースキーマ → semantic layer → Text-to-SQL」の2系統を目指していた（CLAUDE.md）。ユーザーが構成を見直し、指標の定義を MetricFlow に1本化することにした。構成図は README の mermaid 図。

## 検討した選択肢

| 選択肢 | 良い点 | 悪い点 |
|---|---|---|
| A. 2系統（ダッシュボードはフラットな marts、AI は semantic layer） | ダッシュボードに MetricFlow が不要 | 同じ KPI を2か所で定義することになり、数字がずれる恐れがある |
| B. MetricFlow を唯一の定義元にし、ダッシュボードは GitHub Actions で `mf query` した結果を静的 HTML（GitHub Pages）で見せる。AI はローカルの Claude Code が `mf` CLI を呼ぶ | 指標の定義が1か所。サーバー不要・費用ゼロで公開できる。AI は SQL を自由に書かず、定義済みの指標だけを使う | ダッシュボードは事前に集計した結果しか見せられない（対話的な絞り込みは JSON に含めた範囲だけ） |
| C. BI ツール（Evidence / Streamlit / Metabase など）をホスティング | 対話的に操作できる | ホスティングと運用（費用・停止時の対応）が必要になる |
| D. LLM に生の SQL を書かせる Text-to-SQL | 何でも聞ける | 指標の定義が LLM 任せになり、数字の正しさを保証できない |

## 決定

B を採用する。

## 理由

- 「ダッシュボードの数字」と「AI が答える数字」が同じ定義から出ることを、構成として保証できる
- GitHub Pages + Actions なら無料で公開でき、閲覧者はリンクを開くだけで見られる
- AI の入口を Claude Code にすれば、自前の LLM 呼び出しコードや MCP サーバーがいらない

## 影響

- ダッシュボード用のフラットな marts は作らない
- `mf query` には JSON 出力がない（`--csv` のみ、mf 0.16.0 の `--help` で確認）。`scripts/export_metrics.py` で CSV → JSON に変換する
- ダッシュボードに載せるデータセットは saved query（`models/marts/_saved_queries.yml`）として dbt 側に定義する。スクリプトは manifest にある saved query をすべて書き出すだけで、どの指標を出すかを持たない。指標のラベル・説明も manifest から JSON に入れ、ダッシュボードは表示するだけにした
- 比率の指標（平均注文単価）は月次の値を足し合わせられないので、全期間の値も saved query（`kpi_total`）で MetricFlow に計算させる
- ダッシュボードは外部ライブラリを使わない HTML + SVG にした（依存とビルド手順を増やさないため）
- AI が `mf query` 以外に何を参照できるかは ADR-0003 で決めた（当初は `mf query` だけにしていた）
- seed は固定データなので、定期実行しても結果は変わらない。トリガーは main への push + 手動実行を基本にする
