# ADR-0004: AI に公開する範囲を semantic layer（semantic_manifest.json）で決める

- 状態: 採用
- 日付: 2026-11-18
- 関連: ADR-0003（公開の範囲の決め方を置き換え）

## 背景

ADR-0003 では、AI の SQL の対象を「`access: public` のモデルの、YAML に書いた列」にしていた。しかし `access` は本来、別の dbt プロジェクトから参照できるかを決める設定で、それを流用していた。指標（mf）と SQL で公開の範囲を別々に管理することにもなる。

semantic layer に載せたものだけを公開すればよく、列も entity か dimension にしたものだけにすればよいと考え、そうすることにした。

## 検討した選択肢

| 選択肢 | 良い点 | 悪い点 |
|---|---|---|
| A. `access: public` + YAML に書いた列（ADR-0003） | semantic layer に載せずに公開もできる | `access` の意味の流用。mf と SQL で範囲を二重に管理する |
| B. `enabled: false` で非公開にする | 設定が1つ | モデルが build されなくなり、ダッシュボードの指標も消える。公開の制御には使えない |
| C. モデルは semantic_manifest.json、列は YAML に書いた列（manifest.json） | 金額などの列も公開できる | 読む場所が2つ。semantic layer にない列も公開されるので「semantic layer = 公開範囲」にならない |
| D. モデルも列も semantic_manifest.json（entity / dimension にした列だけ） | 公開範囲が semantic layer と完全に一致する。読むのは semantic_manifest.json だけ | 金額などの数値の列も、公開するなら dimension にする必要がある |
| E. `config.meta` の独自キー（例: `ai_public: true`） | 意味がぶつからない | semantic layer とは別に、もう1つ管理の仕組みが増える |

## 決定

D を採用する。

- モデル: semantic model になっているもの（`semantic_model` が有効なもの）
- 列: entity か dimension にした列。金額などの数値も、公開するなら `dimension: categorical` にする
- `access` は使わない（既定のまま）

## 理由

- 「semantic layer に載せたもの = AI のコンテキスト」になり、指標と公開範囲を同じ YAML の同じ仕組みで管理できる。構成図の「dbt プロジェクトが唯一の定義元」と一致する
- `mf` で見える範囲と SQL で見える範囲が一致する
- C は、semantic_manifest.json には entity と dimension の列しか入らないことを補うための案だったが、列を dimension にすれば D で足りる

## 影響

- 2026-11-18 に確認:
  - `semantic_model: {enabled: false}` にすると、そのモデルは semantic_manifest.json から消える。manifest.json には残り、build もされる。そのモデルの dimension は `mf query` で使えなくなる（`customer__customer_type` がエラーになった）
  - semantic_manifest.json の semantic model には、entity と dimension の列しか入らない（`fct_orders` の `order_total` などは、dimension にするまで入っていなかった）。列の description は entity / dimension の description に引き継がれる
  - 金額の列（`order_total` など）を dimension にしても、`mf validate-configs` はエラーなしで、saved query の結果も変わらなかった。指標と同じ名前の dimension（`tax_paid`、`supply_cost`）があっても問題なかった
  - 公開される列は ADR-0003 のときと同じ（`customer_name` だけ非公開）。staging、time spine、`customer_name`、seed の CSV、元の DB には SQL から届かなかった
- **時間の dimension は `dimension: {type: time}` と辞書の形で書く。** `dimension: time` と文字列で書くと、dbt-core 1.12.7 では列の `granularity` が semantic_manifest.json に入らない。`mf validate-configs` は FUTURE_ERRORS を出すだけで通るが、`mf query` が実行時に「`type_params` should not be `None` for a time dimension」で失敗した
- 数値の列が dimension になるので、`mf list dimensions` の候補が増える（例: `order__order_total`）。「注文金額ごとの注文数」のように、値そのものでの集計にも使える
- semantic layer に載せずに AI にだけ見せる、ということはできない。必要になったら、entity を付けて semantic model にする
- 「集計は使わせたいが、行レベルの SQL では見せない」という区別もできない。必要になったら見直す
