-- MetricFlow が日付で集計・穴埋めするための日付テーブル
select cast(range as date) as date_day
from range(date '2016-01-01', date '2030-01-01', interval 1 day)
