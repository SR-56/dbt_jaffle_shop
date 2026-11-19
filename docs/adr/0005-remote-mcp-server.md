# ADR-0005: MCP サーバーを Cloud Run に置き、GitHub ログインで自分だけに公開する

- 状態: 採用
- 日付: 2026-11-19（提案 2026-11-18）
- 関連: ADR-0001, ADR-0003, ADR-0004

## 背景

今の AI 分析は、リポジトリを clone して `uv sync` し、`dbt build` した手元の環境で Claude Code を動かすことが前提になっている。分析のルールも、リポジトリの中のスキル（`.claude/skills/analyze-data/SKILL.md`）にある。私は、リポジトリが手元になくても、MCP かサーバーを経由して分析できる状態にしたい。

## 検討した選択肢

| 選択肢 | 良い点 | 悪い点 |
|---|---|---|
| A. 自前の MCP サーバーを使う人の PC で動かす（`uvx --from git+...`） | サーバー代も認証も不要。今のコードをほぼ流用できる | 使う人の PC に uv と 400MB 前後の容量が要る（手元の環境は 359MB）。初回は build が走る（DB なしから 8 秒）。claude.ai のブラウザ版からは使えない |
| B. 自前の MCP サーバーをクラウドで動かす（Streamable HTTP） | URL だけで使える。claude.ai からも使える。ダッシュボードと同じ build からイメージを作れる | ホスティング・認証・悪用への対策が必要。0台まで縮める構成では起動待ちが出る |
| C. dbt 公式の MCP サーバー（dbt-mcp） | 自作しなくてよい | semantic layer の機能は dbt platform が前提とみられる（未確認）。dbt のコマンドをそのまま出す作りなら、semantic layer の範囲に絞れない |
| D. dbt platform ＋ DWH に移行する | 公式の構成になる | DuckDB は dbt platform の Semantic Layer に対応していない。DWH の移行、アカウント、費用が必要 |
| E. データだけクラウドへ（MotherDuck など） | データが手元から離れる | SQL を直接打つ経路になり、MetricFlow を唯一の定義元にした意味がなくなる |

## 決定

B を採用する（2026-11-19 に決定）。

- 使うのは自分だけ。claude.ai の Web 版・スマホ・Claude Code から使う
- 認証は GitHub ログインの OAuth（FastMCP 3.2.0 以上の `GitHubProvider`）。GitHub の login が SR-56 以外なら拒否する
- ホスティングは Cloud Run（最大1台、使わないときは0台）
- インフラは Terraform で管理し、同じリポジトリの `infra/` に置く
- ログイン情報の保存先は、まずメモリ（a）。再起動のあと、スマホからログインし直さずに使えなければ、外部の Redis（c）に切り替える
- 進め方: まず手元で stdio のまま MCP サーバーを作ってツールを固め、そのあと HTTP に切り替えてクラウドに置く

まだ決めていないこと:

- 社内に限定公開する構成（会社のログイン、利用者ごとの権限、監査ログ）を、このリポジトリでどこまで再現するか

### B の最小構成（検討の記録）

私の条件: 使うのは自分だけ、スマホからも分析したい。

- 構成: MCP サーバー（ツールは `get_context` / `query_metrics` / `run_sql` の3つ）、Dockerfile（イメージを作るときに `dbt build`）、Cloud Run（最大1台、使わないときは0台）、手でのデプロイ。`mf` は毎回別プロセスで起動する
- 公開するなら最小でも外せないもの: 認証、台数とリクエスト時間の上限、`run_sql` のメモリ・スレッド・実行時間・行数の上限、`query_metrics` の引数を semantic_manifest.json にある名前だけに絞ること
- 認証の候補:
  - 固定のトークン（claude.ai の「Request headers」）。ただしベータで、一部の組織にしか開放されていない。2026-11-18 に私の claude.ai（プラグイン → 追加 → カスタムコネクタを追加）を確認したところ、最初のダイアログには「名前」と「MCP サーバー URL」しかなく、ヘッダー・詳細設定・OAuth の client ID の欄はなかった（「続ける」の先は未確認）。使えない可能性が高い
  - 使えなければ、GitHub でログインする OAuth（FastMCP の `GitHubProvider`）。SR-56 以外を拒否する処理は自分で書く。FastMCP の OAuth Proxy には 2026-03 公表の脆弱性（GHSA-rww4-4w9c-7733）があるので、修正済みの版を使う
    - 必要なもの: GitHub OAuth App（コールバック URL は `https://<Cloud Run の URL>/auth/callback`）、`fastmcp>=3.2.0`、Secret Manager に `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` / `JWT_SIGNING_KEY` / `STORAGE_ENCRYPTION_KEY`
    - GitHub の OAuth App は誰でもログインできるので、トークンの `login` が `ALLOWED_GITHUB_LOGIN` と一致しなければ拒否する処理が必須
    - ログイン情報の保存先が未決: メモリ（再起動でログインし直しになるかは未確認）/ 最小台数 1 / 外部の Redis（Upstash など）。まずメモリで試し、再起動のあとに使えるかで決める
    - Cloud Run の URL が決まらないと OAuth App を登録できないので、最初のデプロイは2回に分ける
  - 認証なしは「自分だけ」を満たせないので外す。トークンを URL に入れる方式は、公式に避けるよう書かれているので外す

### インフラの管理（検討の記録）

採用した前提: インフラは Terraform で管理し、同じリポジトリの `infra/` に置く。ログイン情報の保存先は、まずメモリ（a）で試し、だめなら外部の Redis（c）に切り替える。

| 選択肢 | 良い点 | 悪い点 |
|---|---|---|
| 手で `gcloud run deploy` | 最初の作業が少ない | 構成が記録に残らず、作り直せない |
| Terraform（同じリポジトリ） | 構成を作り直せる。アプリと設定の変更を1つのコミットで直せる | 最初の作業が増える。状態ファイルの置き場所が要る |
| Terraform（別のリポジトリ） | 権限と担当を分けられる | 1人・1サービスでは、変更が2か所に分かれるだけになる |

- 担当の分け方: 最初の1回は手作業（プロジェクト、課金、状態ファイル用のバケット、OAuth App、Secret の値、コネクタの登録）。構成は Terraform。イメージの更新は GitHub Actions（OIDC 連携）
- Terraform で秘密の値を扱わない（状態ファイルに平文で残る）。作るのは Secret の入れ物と、読む権限だけにする
- Terraform 側で Cloud Run のイメージの変更を無視する（`ignore_changes`）。CI のデプロイと取り合わないため
- 方式 a では、Cloud Run を2台以上にしない（台数ごとにメモリが別になる）。再起動のあと、スマホからログインし直さずに使えなければ c に切り替える
- OAuth App は Terraform で管理できない見込み（未確認）。手で登録する

2026-11-18 に公式ドキュメントで確認した制約:

- スマホ（iOS / Android）のアプリから、リモートの MCP サーバーを使える。ただし、使えるのは Web 版か Desktop 版ですでに登録したものだけ
- カスタムコネクタは Anthropic のクラウドからサーバーへ接続する。サーバーはインターネットから届く場所に置く必要がある
- claude.ai が対応している認証は、認証なし・OAuth（自動登録、自分の client ID と secret など）・固定のヘッダー（ベータ）

## 理由

- 使う人の環境に何も要求しないのは B だけ
- C・D・E は、DuckDB と自前の MetricFlow という今の構成、または「semantic layer の範囲だけを公開する」方針（ADR-0004）と両立しない
- サーバーの中身は A と B で共通にできるので、手元で試してから公開しても作業が無駄にならない
- A を選ぶ場合も、サーバー本体はそのまま使える

## 影響

- 分析のルールは、スキルから MCP のサーバーの説明（instructions）とツールの説明に移す。リモートのクライアントにはスキルが届かないため
- `mf query` は 1回あたり 3.7 秒かかった（2026-11-18 に計測、`dbt debug` 相当の読み込みが毎回走るため）。サーバーでは MetricFlow の Python API で一度だけ読み込んで使い回す方法を、まず試す
  - 2026-11-19: 第1段階では、確実に動く「毎回 `mf` を別プロセスで起動する」方式にした。MCP の stdio 経由で `query_metrics` は 2.9 秒、`run_sql` は 0.1 秒だった
- 第1段階（手元の stdio）の実装で分かったこと（2026-11-19）:
  - `uv add 'fastmcp>=3.2.0'` で入ったのは 4.2.1。dbt-core・MetricFlow と衝突しなかった。4.2.1 にも `GitHubProvider`（`jwt_signing_key`、`client_storage` 付き）と `get_access_token()` がある
  - **`mf` の `--where` に利用者の文字列をそのまま渡してはいけない。** `mf` は sandbox の外で DuckDB 全体につないで動くので、where に SQL を書けると staging や seed の CSV に届いてしまう。絞り込みは「ディメンション・演算子・値」の組で受け取り、値は文字列リテラルとして quote し、`{` `}`（Jinja）と `\`・制御文字を拒否する。名前は英小文字・数字・`_` だけ、指標と saved query は manifest にあるものだけを受け付ける。`'` を含む値が、生成された SQL の中で文字列のまま扱われることを `--explain` で確認した
  - 結果が0行のとき、`mf query --csv` は正常終了するが CSV を作らない。0行として扱う
  - テスト（`tests/test_mcp_server.py`、21件）で、既知の値との一致と、範囲外（非公開の列、staging、time spine、seed の CSV、ATTACH、設定の変更、COPY）と不正な入力が拒否されることを確かめている
  - 2026-11-19 に、スキルを外した Claude Code（claude-sonnet-4-5）から MCP 経由で試した。4つの質問（指標と切り口の一覧、四半期ごとの平均注文単価、Brooklyn の商品種別ごとの粗利、併売トップ5）はどれも正しいツールを選び、数字は DuckDB に直接書いた SQL と一致した。顧客名は「見られない」と答えた
  - 一方で、答え方に癖が見つかった（指標の言い換え、行の自前の足し算、確かめない推測、期間の端の見落とし、併売を回数だけで判断）。サーバーの説明（instructions）に対策を足した。ツールの作りではなく説明で守らせているので、モデルが変わると効き方が変わりうる
- B の場合、インターネットに公開する `run_sql` には、sandbox に加えて、実行時間・メモリ・スレッド・返す行数の上限が必要
